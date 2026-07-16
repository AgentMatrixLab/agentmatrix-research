"""Reset and rerun Alpha158 batches 01-15 with the updated universe/date logic."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pandas as pd

from research_core.alpha158_lab.factors.specs import ALPHA158_BATCHES
from research_core.alpha158_lab.pipeline import run_alpha158_batch

ROOT = Path(__file__).resolve().parents[1] / "runtime" / "alpha158_lab"
BATCH_IDS = [f"batch_{i:02d}" for i in range(1, 16)]
DEFAULT_START_FROM = "batch_01"


def _factors_for_batches(batch_ids: list[str]) -> list[str]:
    names: list[str] = []
    for batch_id in batch_ids:
        names.extend(ALPHA158_BATCHES[batch_id]["factors"])  # type: ignore[arg-type]
    return names


def _clean_batch_artifacts() -> None:
    for batch_id in BATCH_IDS:
        for sub in ("truth", "validation", "effectiveness"):
            path = ROOT / sub / batch_id
            if path.exists():
                shutil.rmtree(path)
        manifest = ROOT / f"pipeline_manifest_{batch_id}.json"
        if manifest.exists():
            manifest.unlink()
        report_dir = ROOT / "reports" / batch_id
        if report_dir.exists():
            shutil.rmtree(report_dir)

    panel = ROOT / "market_panel.parquet"
    if panel.exists():
        panel.unlink()

    factor_path = ROOT / "alpha158_factors_smartdata.parquet"
    if factor_path.exists():
        frame = pd.read_parquet(factor_path)
        redo_factors = set(_factors_for_batches(BATCH_IDS))
        drop_cols = [
            col
            for col in frame.columns
            if col in redo_factors or col.endswith("_x") or col.endswith("_y")
        ]
        kept = frame.drop(columns=drop_cols, errors="ignore")
        if kept.shape[1] <= 2:
            factor_path.unlink()
        else:
            kept.to_parquet(factor_path, index=False)

    ic_path = ROOT / "effectiveness" / "ic_series.csv"
    if ic_path.exists():
        ic = pd.read_csv(ic_path)
        if "factor" in ic.columns:
            redo_factors = set(_factors_for_batches(BATCH_IDS))
            ic = ic[~ic["factor"].isin(redo_factors)]
            if ic.empty:
                ic_path.unlink()
            else:
                ic.to_csv(ic_path, index=False)


def main() -> None:
    start_from = DEFAULT_START_FROM
    if len(sys.argv) > 1:
        start_from = sys.argv[1]
    if start_from not in BATCH_IDS:
        raise SystemExit(f"Unknown batch: {start_from}")

    if start_from == "batch_01":
        _clean_batch_artifacts()

    pending = BATCH_IDS[BATCH_IDS.index(start_from) :]
    results: dict[str, str] = {}
    for idx, batch_id in enumerate(pending):
        print(f"\n=== RUN {batch_id} ({idx + 1}/{len(pending)}) ===", flush=True)
        payload = run_alpha158_batch(
            batch_id,
            reload_panel=(start_from == "batch_01" and idx == 0),
        )
        results[batch_id] = payload.get("accuracy_status", "UNKNOWN")
        print(json.dumps(
            {
                "batch_id": batch_id,
                "accuracy_status": results[batch_id],
                "compute_range": payload.get("config", {}).get("compute_range"),
                "compute_codes": payload.get("config", {}).get("compute_codes"),
            },
            ensure_ascii=False,
        ), flush=True)

    print("\n=== SUMMARY ===", flush=True)
    print(json.dumps(results, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr, flush=True)
        raise