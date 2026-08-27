from __future__ import annotations

import gc
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from research_core.alpha158_lab.config import Alpha158ResearchConfig
from research_core.alpha158_lab.data.smartdata import (
    fetch_trade_date_bounds,
    load_market_panel,
    save_panel,
)
from research_core.alpha158_lab.factors.compute import compute_alpha158_factors
from research_core.alpha158_lab.factors.specs import ALPHA158_BATCHES, ALPHA158_FIRST_10
from research_core.alpha158_lab.research.effectiveness import forward_daily_return_frame, run_effectiveness_suite
from research_core.alpha158_lab.research.batch_report import (
    BatchReportConfig,
    ensure_report_template,
    generate_batch_report,
)
from research_core.alpha158_lab.research.report import build_master_report
from research_core.alpha158_lab.research.visualize import (
    plot_ic_series,
    plot_long_short_nav,
    plot_quantile_layer_returns,
)
from research_core.alpha158_lab.validation.accuracy import build_accuracy_report
from research_core.alpha158_lab.validation.qlib_truth import export_qlib_alpha158_truth
from research_core.factor_library.validation import compute_ic_series


def _resolve_compute_dates(cfg: Alpha158ResearchConfig) -> Alpha158ResearchConfig:
    """Resolve compute window from SmartData DB, or from cached panel when DB is unavailable."""
    panel_path = cfg.output_dir / "market_panel.parquet"
    if panel_path.exists():
        panel_dates = pd.read_parquet(panel_path, columns=["date"])["date"]
        panel_dates = pd.to_datetime(panel_dates)
        cfg.start_date = str(panel_dates.min().date())
        cfg.end_date = str(panel_dates.max().date())
        return cfg

    db_start, db_end = fetch_trade_date_bounds(
        start_date=cfg.request_start,
        end_date=cfg.request_end,
    )
    cfg.start_date = db_start
    cfg.end_date = db_end
    return cfg


def _load_or_fetch_panel(cfg: Alpha158ResearchConfig, *, reload_panel: bool) -> pd.DataFrame:
    panel_path = cfg.output_dir / "market_panel.parquet"
    if panel_path.exists() and not reload_panel:
        return pd.read_parquet(panel_path)

    panel = load_market_panel(
        start_date=cfg.start_date,
        end_date=cfg.end_date,
    )
    save_panel(panel, str(panel_path))
    return panel


def _downcast_factor_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    factor_cols = [col for col in out.columns if col not in {"date", "code"}]
    if factor_cols:
        out[factor_cols] = out[factor_cols].astype("float32")
    return out


def _merge_factors_parquet(factor_path: Path, batch_factors: pd.DataFrame) -> None:
    """Append/replace batch factor columns on disk without a full pandas sort copy."""
    batch_factors = _downcast_factor_frame(batch_factors)
    new_table = pa.Table.from_pandas(batch_factors, preserve_index=False)
    new_factor_cols = [name for name in new_table.column_names if name not in {"date", "code"}]

    if not factor_path.exists():
        pq.write_table(new_table, factor_path)
        return

    existing = pq.read_table(factor_path)
    drop_names = {
        candidate
        for col in new_factor_cols
        for candidate in (col, f"{col}_x", f"{col}_y")
        if candidate in existing.column_names
    }
    keep_names = [name for name in existing.column_names if name not in drop_names]
    existing = existing.select(keep_names)
    merged = existing.join(new_table, keys=["date", "code"], join_type="full outer")
    pq.write_table(merged, factor_path)
    del existing, new_table, merged
    gc.collect()


def _load_factor_slice(factor_path: Path, factor_names: list[str]) -> pd.DataFrame:
    columns = ["date", "code", *factor_names]
    return pd.read_parquet(factor_path, columns=columns)


def _merge_ic_series(existing_path: Path, new_df: pd.DataFrame) -> pd.DataFrame:
    """Merge long-format IC rows keyed by (date, factor)."""
    new_df = new_df.copy()
    new_df["date"] = pd.to_datetime(new_df["date"])
    if not existing_path.exists():
        return new_df.sort_values(["date", "factor"]).reset_index(drop=True)

    existing = pd.read_csv(existing_path)
    if existing.empty:
        return new_df.sort_values(["date", "factor"]).reset_index(drop=True)

    if "factor" in existing.columns:
        existing["date"] = pd.to_datetime(existing["date"])
        merged = pd.concat([existing, new_df], ignore_index=True)
        merged = merged.drop_duplicates(subset=["date", "factor"], keep="last")
        return merged.sort_values(["date", "factor"]).reset_index(drop=True)

    # Legacy wide-format fallback: one column per factor.
    existing["date"] = pd.to_datetime(existing["date"])
    drop_cols = [col for col in new_df.columns if col != "date" and col in existing.columns]
    existing = existing.drop(columns=drop_cols, errors="ignore")
    merged = existing.merge(new_df, on="date", how="outer")
    return merged.sort_values("date").reset_index(drop=True)


def run_alpha158_batch(
    batch_id: str,
    config: Alpha158ResearchConfig | None = None,
    *,
    reload_panel: bool = False,
) -> dict[str, Any]:
    if batch_id not in ALPHA158_BATCHES:
        raise KeyError(f"Unknown batch_id: {batch_id}. Available: {sorted(ALPHA158_BATCHES)}")

    batch_meta = ALPHA158_BATCHES[batch_id]
    factor_names = list(batch_meta["factors"])
    cfg = config or Alpha158ResearchConfig()
    cfg = _resolve_compute_dates(cfg)
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, str] = {}

    panel = _load_or_fetch_panel(cfg, reload_panel=reload_panel)
    artifacts["market_panel"] = str((cfg.output_dir / "market_panel.parquet").resolve())

    batch_factors = compute_alpha158_factors(panel, factor_names=factor_names)
    factor_path = cfg.output_dir / "alpha158_factors_smartdata.parquet"
    batch_factor_path = cfg.output_dir / "factors" / f"{batch_id}.parquet"
    batch_factor_path.parent.mkdir(parents=True, exist_ok=True)
    _downcast_factor_frame(batch_factors).to_parquet(batch_factor_path, index=False)
    artifacts["batch_factor_frame"] = str(batch_factor_path.resolve())
    _merge_factors_parquet(factor_path, batch_factors)
    del batch_factors
    gc.collect()
    factor_frame = _load_factor_slice(factor_path, factor_names)
    artifacts["factor_frame"] = str(factor_path.resolve())

    truth_summary = export_qlib_alpha158_truth(
        start_date=cfg.overlap_start,
        end_date=cfg.overlap_end,
        instruments="all",
        output_dir=cfg.output_dir / "truth" / batch_id,
        factor_names=factor_names,
    )
    artifacts["qlib_truth"] = truth_summary["path"]
    truth = pd.read_parquet(truth_summary["path"])

    validation_dir = cfg.output_dir / "validation" / batch_id
    accuracy = build_accuracy_report(
        computed=factor_frame,
        truth=truth,
        factor_names=factor_names,
        overlap_start=cfg.overlap_start,
        overlap_end=cfg.overlap_end,
        output_dir=validation_dir,
    )
    artifacts["accuracy_report"] = accuracy["markdown_path"]

    effectiveness_dir = cfg.output_dir / "effectiveness" / batch_id
    effectiveness = run_effectiveness_suite(
        market_panel=panel,
        factor_frame=factor_frame,
        factor_names=factor_names,
        output_dir=effectiveness_dir,
    )
    artifacts["effectiveness_report"] = effectiveness["path"]

    return_df = forward_daily_return_frame(panel)
    ic_df = compute_ic_series(
        factor_frame,
        return_df,
        factor_names,
        return_col="forward_return_1d",
    )
    ic_path = cfg.output_dir / "effectiveness" / "ic_series.csv"
    ic_df = _merge_ic_series(ic_path, ic_df)
    ic_df.to_csv(ic_path, index=False)
    artifacts["ic_series"] = str(ic_path.resolve())

    chart_dir = cfg.output_dir / "charts"
    for factor in factor_names:
        plot_ic_series(ic_df, factor, chart_dir)
        spread_path = effectiveness_dir / f"{factor}_long_short_spread.csv"
        bucket_path = effectiveness_dir / f"{factor}_quantile_returns.csv"
        if spread_path.exists():
            plot_long_short_nav(pd.read_csv(spread_path), factor, chart_dir)
        if bucket_path.exists():
            plot_quantile_layer_returns(pd.read_csv(bucket_path), factor, chart_dir)

    if batch_id == "batch_01":
        master = build_master_report(
            accuracy_report=accuracy,
            effectiveness_report=effectiveness,
            artifacts=artifacts,
            output_dir=cfg.output_dir / "reports",
        )
        artifacts["master_report"] = master["markdown_path"]

    reports_root = cfg.output_dir / "reports"
    ensure_report_template(reports_root)
    batch_payload = generate_batch_report(
        BatchReportConfig(
            batch_id=batch_id,
            batch_title=str(batch_meta["batch_title"]),
            factor_names=factor_names,
            factor_index_start=int(batch_meta["factor_index_start"]),
            factor_index_end=int(batch_meta["factor_index_end"]),
            charts_dir=chart_dir,
            reports_root=reports_root,
            compute_range=cfg.compute_range_label,
            validation_range=cfg.validation_range_label,
        ),
        workspace=cfg,
    )
    artifacts["batch_report"] = batch_payload["report_markdown"]
    artifacts["batch_mosaics"] = json.dumps([m["path"] for m in batch_payload.get("mosaics", [])])

    manifest = {
        "batch_id": batch_id,
        "config": {
            "compute_range": cfg.compute_range_label,
            "validation_range": cfg.validation_range_label,
            "start_date": cfg.start_date,
            "end_date": cfg.end_date,
            "request_start": cfg.request_start,
            "request_end": cfg.request_end,
            "overlap_start": cfg.overlap_start,
            "overlap_end": cfg.overlap_end,
            "compute_codes": int(panel["code"].nunique()),
            "post_validation_note": (
                f"{cfg.overlap_end} 之后仅完成 SmartData 因子计算，"
                "待外部 truth 补齐后再做截面偏差校验。"
            ),
        },
        "artifacts": artifacts,
        "accuracy_status": accuracy["overall_status"],
        "factor_names": factor_names,
    }
    manifest_path = cfg.output_dir / f"pipeline_manifest_{batch_id}.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path.resolve())
    return manifest


def run_alpha158_pipeline(
    config: Alpha158ResearchConfig | None = None,
    *,
    reload_panel: bool = False,
) -> dict[str, Any]:
    return run_alpha158_batch("batch_01", config=config, reload_panel=reload_panel)


def run_alpha158_all(
    config: Alpha158ResearchConfig | None = None,
    *,
    reload_panel: bool = True,
    start_batch: str = "batch_01",
) -> dict[str, Any]:
    """Run all 16 Alpha158 batches sequentially, then return a consolidated summary."""
    batch_ids = sorted(ALPHA158_BATCHES)
    if start_batch not in batch_ids:
        raise KeyError(f"Unknown start_batch: {start_batch}")

    cfg = config or Alpha158ResearchConfig()
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    start_idx = batch_ids.index(start_batch)
    manifests: list[dict[str, Any]] = []

    for idx, batch_id in enumerate(batch_ids[start_idx:], start=start_idx):
        manifest = run_alpha158_batch(
            batch_id,
            cfg,
            reload_panel=reload_panel and idx == start_idx,
        )
        manifests.append(manifest)

    pass_count = sum(1 for m in manifests if m.get("accuracy_status") == "PASS")
    fail_batches = [m["batch_id"] for m in manifests if m.get("accuracy_status") not in {"PASS", None}]
    return {
        "batches_run": len(manifests),
        "batch_ids": [m["batch_id"] for m in manifests],
        "pass_batches": pass_count,
        "fail_batches": fail_batches,
        "accuracy_status": "PASS" if not fail_batches else "PARTIAL",
        "factor_count": sum(len(m.get("factor_names", [])) for m in manifests),
        "manifests": [m.get("manifest_path") for m in manifests],
        "output_dir": str(cfg.output_dir.resolve()),
    }