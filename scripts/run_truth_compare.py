"""任务一 · 真值对照执行器（本地版）"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_TOLERANCE = 1e-8
DEFAULT_MIN_OVERLAP = 0.9
DEFAULT_PASS_EXACT = 0.99
MAX_MISMATCH_SAMPLES = 12


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_keys(frame: pd.DataFrame) -> pd.DataFrame:
    frame["date"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")
    frame["symbol"] = frame["symbol"].astype(str).str.strip()
    return frame


def _pick(col_map: dict, *names: str) -> str | None:
    for name in names:
        if name in col_map:
            return col_map[name]
    return None


def load_uploaded_values(csv_path: Path, factor_name: str) -> pd.DataFrame:
    frame = pd.read_csv(csv_path)
    col_map = {str(c).strip().lower(): c for c in frame.columns}
    date_col = _pick(col_map, "date", "trade_date")
    code_col = _pick(col_map, "symbol", "code", "order_book_id")
    if not date_col or not code_col:
        raise ValueError(f"{csv_path} 缺少日期列(date/trade_date)或代码列(symbol/code)")

    if "factor_value" in col_map:
        value_col = col_map["factor_value"]
    elif factor_name.lower() in col_map:
        value_col = col_map[factor_name.lower()]
    else:
        raise ValueError(
            f"{csv_path} 里既没有 factor_value 列，也没有 {factor_name} 列，无法取值"
        )

    out = frame.rename(
        columns={date_col: "date", code_col: "symbol", value_col: "submitted_value"}
    )[["date", "symbol", "submitted_value"]].copy()
    out = _normalize_keys(out)
    out["submitted_value"] = pd.to_numeric(out["submitted_value"], errors="coerce")
    return out


def load_truth_from_csv(csv_path: Path, factor_name: str) -> pd.DataFrame | None:
    frame = pd.read_csv(csv_path)
    col_map = {str(c).strip().lower(): c for c in frame.columns}
    if factor_name.lower() not in col_map:
        return None
    date_col = _pick(col_map, "date", "trade_date")
    code_col = _pick(col_map, "code", "symbol", "order_book_id")
    out = frame.rename(
        columns={date_col: "date", code_col: "symbol", col_map[factor_name.lower()]: "truth_value"}
    )[["date", "symbol", "truth_value"]].copy()
    out = _normalize_keys(out)
    out["truth_value"] = pd.to_numeric(out["truth_value"], errors="coerce")
    return out.dropna(subset=["truth_value"])


def load_truth_from_supabase(factor_family: str, factor_name: str) -> pd.DataFrame | None:
    base_url = os.environ.get("FACTOR_LAB_SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("FACTOR_LAB_SUPABASE_WRITE_KEY", "")
    if not base_url or not key:
        return None
    rows: list[dict] = []
    page_size, offset = 1000, 0
    while True:
        url = (
            f"{base_url}/rest/v1/factor_truth_values"
            f"?select=symbol,trade_date,truth_value"
            f"&factor_family=eq.{factor_family}&factor_name=eq.{factor_name}"
            f"&order=trade_date.asc&limit={page_size}&offset={offset}"
        )
        req = urllib.request.Request(
            url, headers={"apikey": key, "Authorization": f"Bearer {key}"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            batch = json.loads(resp.read().decode("utf-8"))
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    if not rows:
        return None
    frame = pd.DataFrame(rows).rename(columns={"trade_date": "date"})
    frame = _normalize_keys(frame)
    frame["truth_value"] = pd.to_numeric(frame["truth_value"], errors="coerce")
    return frame[["date", "symbol", "truth_value"]].dropna(subset=["truth_value"])


def compare_values(submitted: pd.DataFrame, truth: pd.DataFrame, tolerance: float) -> dict:
    merged = submitted.merge(truth, on=["date", "symbol"], how="inner")
    compared = int(len(merged))
    if compared == 0:
        return {
            "compared_count": 0,
            "exact_match_count": 0,
            "exact_match_ratio": 0.0,
            "max_abs_error": None,
            "mean_abs_error": None,
            "cross_section_spearman_mean": None,
            "cross_section_pearson_mean": None,
            "mismatch_count": 0,
            "mismatch_samples": [],
        }

    merged["abs_error"] = (merged["submitted_value"] - merged["truth_value"]).abs()
    both_nan = merged["submitted_value"].isna() & merged["truth_value"].isna()
    exact_mask = both_nan | (merged["abs_error"] <= tolerance)
    abs_err = merged["abs_error"].dropna()

    spearman_vals, pearson_vals = [], []
    valid = merged.dropna(subset=["submitted_value", "truth_value"])
    for _, day in valid.groupby("date"):
        if len(day) < 3:
            continue
        spearman_vals.append(day["submitted_value"].corr(day["truth_value"], method="spearman"))
        pearson_vals.append(day["submitted_value"].corr(day["truth_value"], method="pearson"))

    mismatches = merged.loc[
        ~exact_mask, ["date", "symbol", "submitted_value", "truth_value", "abs_error"]
    ].head(MAX_MISMATCH_SAMPLES)

    return {
        "compared_count": compared,
        "exact_match_count": int(exact_mask.sum()),
        "exact_match_ratio": float(exact_mask.mean()),
        "max_abs_error": float(abs_err.max()) if len(abs_err) else None,
        "mean_abs_error": float(abs_err.mean()) if len(abs_err) else None,
        "cross_section_spearman_mean": float(np.nanmean(spearman_vals)) if spearman_vals else None,
        "cross_section_pearson_mean": float(np.nanmean(pearson_vals)) if pearson_vals else None,
        "mismatch_count": int((~exact_mask).sum()),
        "mismatch_samples": mismatches.to_dict(orient="records"),
    }


def decide_status(metrics: dict, uploaded_count: int, tolerance: float,
                  min_overlap: float, pass_exact: float) -> tuple[float, str, list[str]]:
    compared = metrics["compared_count"]
    overlap = compared / uploaded_count if uploaded_count else 0.0
    reasons: list[str] = []

    if overlap < min_overlap:
        reasons.append(f"overlap_ratio={overlap:.4f} < min_overlap_ratio={min_overlap}")
    if metrics["exact_match_ratio"] < pass_exact:
        reasons.append(
            f"exact_match_ratio={metrics['exact_match_ratio']:.4f} < pass_exact_match_ratio={pass_exact}"
        )
    max_err = metrics["max_abs_error"]
    if max_err is None or max_err > tolerance:
        reasons.append(f"max_abs_error={max_err} > tolerance={tolerance}")

    return overlap, ("passed" if not reasons else "failed"), reasons


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="任务一 · 真值对照执行器")
    parser.add_argument("--factor-family", required=True)
    parser.add_argument("--factor-name", required=True)
    parser.add_argument("--values-csv", required=True)
    parser.add_argument("--truth-csv", help="本地真值文件（宽表）；不传则尝试 Supabase")
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    parser.add_argument("--min-overlap", type=float, default=DEFAULT_MIN_OVERLAP)
    parser.add_argument("--pass-exact", type=float, default=DEFAULT_PASS_EXACT)
    parser.add_argument("--task-id", help="可选：关联的 agent task，结果同步进其 status.json")
    args = parser.parse_args()

    run_id = f"truthcmp-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    run_dir = ROOT / "runtime" / "factor_lab" / "truth_compare" / run_id

    submitted = load_uploaded_values(Path(args.values_csv), args.factor_name)
    uploaded_count = int(len(submitted))
    duplicate_keys = int(submitted.duplicated(subset=["date", "symbol"]).sum())
    null_values = int(submitted["submitted_value"].isna().sum())
    data_quality = {
        "uploaded_rows": uploaded_count,
        "duplicate_key_count": duplicate_keys,
        "null_value_count": null_values,
        "date_range": [
            str(submitted["date"].min()) if uploaded_count else None,
            str(submitted["date"].max()) if uploaded_count else None,
        ],
        "symbol_count": int(submitted["symbol"].nunique()) if uploaded_count else 0,
    }

    truth = None
    truth_source = None
    if args.truth_csv:
        truth = load_truth_from_csv(Path(args.truth_csv), args.factor_name)
        truth_source = f"local_csv:{args.truth_csv}"
    if truth is None:
        truth = load_truth_from_supabase(args.factor_family, args.factor_name)
        if truth is not None:
            truth_source = "supabase:factor_truth_values"

    if truth is None or len(truth) == 0:
        status, reasons, metrics, overlap = "not_comparable", ["no_library_truth"], None, 0.0
    else:
        metrics = compare_values(submitted, truth, args.tolerance)
        overlap, status, reasons = decide_status(
            metrics, uploaded_count, args.tolerance, args.min_overlap, args.pass_exact
        )

    decision = "accept" if status == "passed" else "reject"

    comparison_payload = {
        "schema_version": "truth_comparison_v1",
        "run_id": run_id,
        "generated_at": now_iso(),
        "factor_family": args.factor_family,
        "factor_name": args.factor_name,
        "truth_source": truth_source,
        "criteria": {
            "tolerance": args.tolerance,
            "min_overlap_ratio": args.min_overlap,
            "pass_exact_match_ratio": args.pass_exact,
        },
        "data_quality": data_quality,
        "truth_rows": int(len(truth)) if truth is not None else 0,
        "overlap_ratio": overlap,
        "status": status,
        "metrics": metrics,
    }
    final_decision = {
        "task_type": "truth_compare",
        "run_id": run_id,
        "decision": decision,
        "truth_status": status,
        "reasons": reasons,
        "decided_at": now_iso(),
    }

    write_json(run_dir / "truth_comparison.json", comparison_payload)
    write_json(run_dir / "final_decision.json", final_decision)

    factor_id = f"{args.factor_family}:{args.factor_name}"
    sync_payload = {
        "generated_at": now_iso(),
        "blocked_reason": "等待 FACTOR_LAB_SUPABASE_WRITE_KEY（service_role）",
        "tables": {
            "factor_truth_comparisons": {
                "run_id": run_id,
                "factor_family": args.factor_family,
                "factor_name": args.factor_name,
                "task_id": args.task_id,
                "truth_source": truth_source,
                "uploaded_rows": uploaded_count,
                "truth_rows": int(len(truth)) if truth is not None else 0,
                "overlap_ratio": overlap,
                "exact_match_ratio": metrics["exact_match_ratio"] if metrics else None,
                "max_abs_error": metrics["max_abs_error"] if metrics else None,
                "mean_abs_error": metrics["mean_abs_error"] if metrics else None,
                "status": status,
                "decision": decision,
                "payload": comparison_payload,
            },
            "public_dashboard_factors": {
                "factor_id": factor_id,
                "factor_name": args.factor_name,
                "factor_family": args.factor_family,
                "truth_status": status,
                "truth_exact_match_ratio": metrics["exact_match_ratio"] if metrics else None,
                "truth_max_abs_error": metrics["max_abs_error"] if metrics else None,
                "latest_task_id": args.task_id,
                "latest_checked_at": now_iso(),
            },
        },
    }
    write_json(run_dir / "supabase_sync_payload.json", sync_payload)

    if args.task_id:
        task_dir = ROOT / "runtime" / "factor_lab" / "agent_tasks" / args.task_id
        status_path = task_dir / "status.json"
        if status_path.exists():
            status_payload = json.loads(status_path.read_text(encoding="utf-8"))
            status_payload["status"] = "completed" if status == "passed" else "failed"
            status_payload["current_gate"] = "G5"
            status_payload["progress"] = 100
            status_payload["message"] = f"truth_compare {status}: {decision}"
            status_payload["truth_execution"] = {
                "run_id": run_id,
                "truth_status": status,
                "decision": decision,
                "overlap_ratio": overlap,
                "exact_match_ratio": metrics["exact_match_ratio"] if metrics else None,
                "max_abs_error": metrics["max_abs_error"] if metrics else None,
                "artifacts_dir": str(run_dir),
                "executed_at": now_iso(),
            }
            status_payload["updated_at"] = now_iso()
            write_json(status_path, status_payload)

    print(f"run_id        : {run_id}")
    print(f"factor        : {args.factor_family}/{args.factor_name}")
    print(f"truth_source  : {truth_source}")
    print(f"uploaded_rows : {uploaded_count}  truth_rows: {int(len(truth)) if truth is not None else 0}")
    print(f"overlap_ratio : {overlap:.4f}")
    if metrics:
        print(f"exact_match   : {metrics['exact_match_ratio']:.4f} ({metrics['exact_match_count']}/{metrics['compared_count']})")
        print(f"max_abs_error : {metrics['max_abs_error']}")
        print(f"mean_abs_error: {metrics['mean_abs_error']}")
    print(f"STATUS        : {status}  ->  decision: {decision}")
    if reasons:
        print(f"reasons       : {reasons}")
    print(f"artifacts     : {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())