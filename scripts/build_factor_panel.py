"""Build the Factor Console dataset from real repository artifacts.

Every number this script emits is derived from a file that exists in the repo.
Nothing is simulated, sampled or invented. Where the pipeline has not run, the
output says so explicitly rather than showing a plausible-looking placeholder —
the console is a delivery-status instrument, so a fabricated bar would be worse
than an empty one.

Reads (all optional except the catalog):
    pages/factor-db-dashboard/data/factors.json     factor catalog (1058)
    pages/lifecycle-dashboard/data/overview.json    lifecycle state machine
    pages/lifecycle-dashboard/data/factors.json     per-factor lifecycle states
    pages/lifecycle-dashboard/data/evidence.json    lifecycle event log
    pages/lifecycle-dashboard/data/monitor.json     SLA / certificate policy
    pages/strategy-dashboard/data/strategies.json   strategy registry
    pages/strategy-dashboard/data/backtest_results.json
    configs/validation_gates.yaml                   frozen gates, split, costs
    data/factor_lab/validation_runs/**              real runs, when they exist

Writes:
    pages/factor-panel/data/panel.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research_core.factor_lab.catalog_readiness import (  # noqa: E402
    classify_expression,
    readiness_summary,
)

CN_TZ = timezone(timedelta(hours=8))
DEADLINE = datetime(2026, 10, 7, 23, 59, 59, tzinfo=CN_TZ)
TARGET_FACTORS = 300


# ── helpers ─────────────────────────────────────────────────────────────

def read_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:  # noqa: BLE001 - provenance is best-effort
        return "unknown"


def source_of(factor_id: str) -> str:
    return factor_id.split(":", 1)[0]


# ── collectors ──────────────────────────────────────────────────────────

def collect_catalog() -> tuple[list[dict], dict]:
    payload = read_json(ROOT / "pages/factor-db-dashboard/data/factors.json")
    if not payload:
        raise SystemExit(
            "catalog not found: pages/factor-db-dashboard/data/factors.json"
        )
    return payload["factors"], payload


def collect_gates() -> dict:
    """Frozen validation gates, parsed without requiring PyYAML at import time."""
    path = ROOT / "configs/validation_gates.yaml"
    try:
        import yaml  # type: ignore

        config = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"available": False, "path": str(path.relative_to(ROOT))}

    gates = config.get("gates", {})
    order = gates.get("order", [])
    rows = []
    for name in order:
        spec = gates.get(name, {})
        rows.append(
            {
                "gate": name,
                "thresholds": spec if isinstance(spec, dict) else {},
            }
        )
    return {
        "available": True,
        "path": str(path.relative_to(ROOT)),
        "order": order,
        "rows": rows,
        "split": config.get("split", {}),
        "cost": config.get("portfolio", {}).get("cost", {}),
        "forward_horizons": config.get("forward_returns", {}).get("horizons", []),
        "primary_horizon": config.get("forward_returns", {}).get("primary_horizon"),
        "styles": config.get("styles", {}).get("fields", []),
        "release": config.get("release", {}),
    }


def collect_lifecycle() -> dict:
    overview = read_json(ROOT / "pages/lifecycle-dashboard/data/overview.json") or {}
    factors = read_json(ROOT / "pages/lifecycle-dashboard/data/factors.json") or {}
    evidence = read_json(ROOT / "pages/lifecycle-dashboard/data/evidence.json") or {}
    monitor = read_json(ROOT / "pages/lifecycle-dashboard/data/monitor.json") or {}
    return {
        "states": overview.get("state_view", {}),
        "transitions": overview.get("transitions", []),
        "gate_funnel_design": overview.get("gate_funnel", []),
        "state_counts": overview.get("state_counts", {}),
        "observed_factors": {
            row["factor_id"]: row for row in factors.get("factors", [])
        },
        "observed_count": factors.get("count", 0),
        "events": evidence.get("events", []),
        "monitor": monitor,
    }


def collect_strategies() -> dict:
    strategies = read_json(ROOT / "pages/strategy-dashboard/data/strategies.json") or {}
    backtests = read_json(ROOT / "pages/strategy-dashboard/data/backtest_results.json") or {}
    return {
        "data_status": strategies.get("data_status", "unknown"),
        "generated_at": strategies.get("generated_at"),
        "rows": strategies.get("strategies", []),
        "backtest_meta": {
            k: backtests.get(k)
            for k in (
                "method",
                "backtest_window",
                "cost_model",
                "universe_rule",
                "top_n",
                "benchmark",
            )
        },
        "backtest_count": len(backtests.get("results", {}) or {}),
    }


def collect_real_runs() -> list[dict]:
    """Real validation runs, if the pipeline has produced any yet."""
    root = ROOT / "data/factor_lab/validation_runs"
    if not root.exists():
        return []
    runs = []
    for factor_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        result = factor_dir / "validation_result.json"
        manifest = factor_dir / "run_manifest.json"
        needs_human = factor_dir / "needs_human.json"
        entry = {"factor_id": factor_dir.name, "has_result": result.exists()}
        if result.exists():
            try:
                payload = json.loads(result.read_text(encoding="utf-8"))
                entry["passed"] = payload.get("passed")
                entry["result_hash"] = payload.get("result_hash")
            except Exception:  # noqa: BLE001
                entry["passed"] = None
        entry["has_manifest"] = manifest.exists()
        entry["needs_human"] = needs_human.exists()
        runs.append(entry)
    return runs


# ── assembly ────────────────────────────────────────────────────────────

def readiness_verdicts(factors: list[dict]) -> dict[str, object]:
    verdicts = []
    per_factor: dict[str, dict] = {}
    for factor in factors:
        v = classify_expression(factor.get("formula_expr", ""))
        verdicts.append(v)
        per_factor[factor["factor_id"]] = v
    return {"summary": readiness_summary(verdicts), "per_factor": per_factor}


def build_factors(
    catalog: list[dict],
    readiness: dict,
    lifecycle: dict,
) -> tuple[list[dict], dict]:
    observed = lifecycle["observed_factors"]
    rows = []
    state_counts: dict[str, int] = {}

    for factor in catalog:
        fid = factor["factor_id"]
        src = source_of(fid)
        v = readiness["per_factor"][fid]

        monitored = observed.get(fid)
        if monitored:
            state = monitored["state"]
            state_label = monitored.get("state_label")
            gate_detail = {
                "passed_all": monitored.get("passed_all"),
                "first_failure": monitored.get("first_failure"),
                "n_gates_run": monitored.get("n_gates_run"),
                "n_gates_passed": monitored.get("n_gates_passed"),
            }
        else:
            # Catalogued but never entered the monitored cohort.
            state = "0_conceived"
            state_label = lifecycle["states"].get("0_conceived", {}).get("label", "设想")
            gate_detail = None

        state_counts[state] = state_counts.get(state, 0) + 1

        rows.append(
            {
                "factor_id": fid,
                "name_cn": factor.get("name_cn"),
                "name_en": factor.get("name_en"),
                "source": src,
                "category": factor.get("category"),
                "subcategory": factor.get("subcategory"),
                "tier": factor.get("trust_tier"),
                "frequency": factor.get("frequency"),
                "history_start": factor.get("history_start"),
                "formula_expr": factor.get("formula_expr"),
                "definition": factor.get("definition"),
                "state": state,
                "state_label": state_label,
                "monitored": bool(monitored),
                "gates": gate_detail,
                "readiness": v.verdict,
                "blocking_operators": list(v.unresolved_operators),
                "aliased_operators": list(v.aliased_operators),
                "missing_fields": list(v.missing_fields),
                "parse_error": v.parse_error,
            }
        )

    return rows, state_counts


def build_funnel(
    catalog_count: int,
    readiness_summary_data: dict,
    real_runs: list[dict],
    lifecycle: dict,
    strategies: dict,
) -> list[dict]:
    runnable = readiness_summary_data["runnable"]
    blocked = catalog_count - runnable
    validated = sum(1 for r in real_runs if r.get("passed"))
    sent = len(real_runs)
    live_ready = lifecycle["state_counts"].get("4_live_ready", 0)
    published = lifecycle["state_counts"].get("6_published", 0)
    in_strategy = lifecycle["state_counts"].get("3_strategy_candidate", 0)

    def stage(key, label, count, evidence, status, detail=""):
        return {
            "key": key,
            "label": label,
            "count": count,
            "evidence": evidence,
            "status": status,
            "detail": detail,
        }

    return [
        stage(
            "catalog",
            "因子目录",
            catalog_count,
            "pages/factor-db-dashboard/data/factors.json",
            "real",
            "九源合一：Alpha101/158/360、GTJA191、TDXGS、JQ110、QAPI33、BARRA、JQGM",
        ),
        stage(
            "engine_ready",
            "引擎可算",
            runnable,
            "research_core/factor_lab/catalog_readiness.py",
            "computed",
            f"另有 {blocked} 个受算子/字段缺口阻塞，需补实现",
        ),
        stage(
            "submitted",
            "已送验",
            sent,
            "data/factor_lab/validation_runs/",
            "real" if sent else "not_run",
            "等待 115 服务器产出面板与因子值" if not sent else "",
        ),
        stage(
            "validated",
            "过闸",
            validated,
            "data/factor_lab/validation_runs/*/validation_result.json",
            "real" if sent else "not_run",
            "八道门槛全过" if sent else "门槛口径待与客户确认（基准/行业中性）",
        ),
        stage(
            "scored",
            "已评分",
            validated,
            "research_core/factor_lab/scoring.py",
            "not_implemented" if not validated else "real",
            "打分器已实现；权重与 A 层分数线仍待客户评审定稿"
            if not validated
            else "综合分与 S/A/B/C 分层",
        ),
        stage(
            "strategy",
            "进策略",
            in_strategy + len(strategies["rows"]),
            "pages/strategy-dashboard/data/strategies.json",
            "placeholder",
            f"策略台账 data_status={strategies['data_status']}；"
            "signal_pipeline.py 已能产出文件单/条件单/Supabase 信号",
        ),
        stage(
            "live",
            "实盘在线",
            live_ready + published,
            "pages/lifecycle-dashboard/data/overview.json",
            "not_run",
            "信号文件 / Supabase / QMT·掘金 对账尚未接通",
        ),
    ]


def build_payload() -> dict:
    now = datetime.now(CN_TZ)
    catalog, catalog_raw = collect_catalog()
    lifecycle = collect_lifecycle()
    strategies = collect_strategies()
    gates = collect_gates()
    real_runs = collect_real_runs()

    readiness = readiness_verdicts(catalog)
    factors, state_counts = build_factors(catalog, readiness, lifecycle)

    validated = sum(1 for r in real_runs if r.get("passed"))

    return {
        "schema_version": 1,
        "generated_at": now.isoformat(timespec="seconds"),
        "generator": "scripts/build_factor_panel.py",
        "code_commit": git_commit(),
        "honesty": {
            "simulated_data": False,
            "validation_runs_found": len(real_runs),
            "statement": (
                "本页所有计数均来自仓库内真实文件。未运行的生产环节明确标注为"
                "「未运行」，不使用演示或正态代理样本填充。"
            ),
            "catalog_note": catalog_raw.get("note"),
            "catalog_mode": catalog_raw.get("mode"),
        },
        "delivery": {
            "target_factors": TARGET_FACTORS,
            "deadline": DEADLINE.date().isoformat(),
            "days_remaining": round(
                (DEADLINE - now).total_seconds() / 86400.0, 2
            ),
            "validated_factors": validated,
            "gap_to_target": max(TARGET_FACTORS - validated, 0),
        },
        "funnel": build_funnel(
            len(catalog), readiness["summary"], real_runs, lifecycle, strategies
        ),
        "catalog": {
            "total": len(catalog),
            "by_source": catalog_raw["stats"].get("by_source", {}),
            "by_category": catalog_raw["stats"].get("by_category", {}),
            "tiers": catalog_raw.get("trust", {}).get("tier_counts", {}),
            "tier_definitions": catalog_raw.get("trust", {}).get(
                "tier_definitions", {}
            ),
            "readiness": readiness["summary"],
        },
        "lifecycle": {
            "states": lifecycle["states"],
            "transitions": lifecycle["transitions"],
            "design_gate_funnel": lifecycle["gate_funnel_design"],
            "observed_count": lifecycle["observed_count"],
            "state_counts": state_counts,
            "events": lifecycle["events"],
            "sla_policy": lifecycle["monitor"].get("sla_policy"),
            "certificates": lifecycle["monitor"].get("certificates"),
            "auto_transitions": lifecycle["monitor"].get("auto_transitions"),
        },
        "gates": gates,
        "strategies": strategies,
        "real_runs": real_runs,
        "factors": factors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default="pages/factor-panel/data/panel.json",
        help="output path, relative to the repository root",
    )
    args = parser.parse_args()

    payload = build_payload()
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    summary = payload["catalog"]["readiness"]
    counts = summary["counts"]
    print(f"wrote {out.relative_to(ROOT)}  ({out.stat().st_size / 1024:.0f} KiB)")
    print(f"  catalog            : {payload['catalog']['total']}")
    print(f"  runnable now       : {counts['runnable_now']}")
    print(f"  alias-only         : {counts['alias_only']}")
    print(f"  needs new numerics : {counts['needs_numerics']}")
    print(f"  unparsable         : {counts['unparsable']}")
    print(f"  runnable total     : {summary['runnable']} ({summary['runnable_ratio']:.1%})")
    print(f"  validation runs    : {payload['honesty']['validation_runs_found']}")
    print(f"  days to deadline   : {payload['delivery']['days_remaining']}")
    top = list(summary["operator_blockers"].items())[:8]
    if top:
        print("  top operator gaps  : " + ", ".join(f"{k} x{v}" for k, v in top))
    topf = list(summary["unknown_fields"].items())[:8]
    if topf:
        print("  top field gaps     : " + ", ".join(f"{k} x{v}" for k, v in topf))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
