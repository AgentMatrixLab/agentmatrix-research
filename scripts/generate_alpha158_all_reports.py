"""Regenerate all Alpha158 batch reports plus master summary and dashboard."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

from research_core.alpha158_lab.config import Alpha158ResearchConfig
from research_core.alpha158_lab.factors.specs import ALPHA158_BATCHES
from research_core.alpha158_lab.research.batch_report import (
    BatchReportConfig,
    ensure_report_template,
    generate_batch_report,
)

REPO = Path(__file__).resolve().parents[1]


def _sync_compute_dates(cfg: Alpha158ResearchConfig) -> Alpha158ResearchConfig:
    panel_path = cfg.output_dir / "market_panel.parquet"
    if panel_path.exists():
        panel = pd.read_parquet(panel_path, columns=["date"])
        panel["date"] = pd.to_datetime(panel["date"])
        cfg.start_date = str(panel["date"].min().date())
        cfg.end_date = str(panel["date"].max().date())
    return cfg


def regenerate_batch_reports(cfg: Alpha158ResearchConfig) -> list[dict]:
    reports_root = cfg.output_dir / "reports"
    ensure_report_template(reports_root)
    payloads: list[dict] = []
    for batch_id in sorted(ALPHA158_BATCHES):
        meta = ALPHA158_BATCHES[batch_id]
        payload = generate_batch_report(
            BatchReportConfig(
                batch_id=batch_id,
                batch_title=str(meta["batch_title"]),
                factor_names=list(meta["factors"]),  # type: ignore[arg-type]
                factor_index_start=int(meta["factor_index_start"]),
                factor_index_end=int(meta["factor_index_end"]),
                charts_dir=cfg.output_dir / "charts",
                reports_root=reports_root,
                compute_range=cfg.compute_range_label,
                validation_range=cfg.validation_range_label,
            ),
            workspace=cfg,
        )
        payloads.append(
            {
                "batch_id": batch_id,
                "report": payload.get("report_markdown"),
                "accuracy_status": payload.get("accuracy", {}).get("overall_status"),
            }
        )
    return payloads


def main() -> None:
    cfg = _sync_compute_dates(Alpha158ResearchConfig())
    batch_payloads = regenerate_batch_reports(cfg)

    scripts = [
        REPO / "scripts" / "generate_alpha158_master_summary.py",
        REPO / "scripts" / "generate_alpha158_dashboard.py",
    ]
    outputs: dict[str, object] = {"batches": batch_payloads}
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO)
    for script in scripts:
        print(f"\n=== RUN {script.name} ===", flush=True)
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(REPO),
            env=env,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if proc.stdout.strip():
            print(proc.stdout.strip())
        outputs[script.stem] = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""

    master_dir = cfg.output_dir / "reports" / "master"
    outputs["artifacts"] = {
        "dashboard_html": str((master_dir / "MASTER_DASHBOARD.html").resolve()),
        "master_summary_md": str((master_dir / "MASTER_SUMMARY.md").resolve()),
        "accuracy_csv": str((master_dir / "accuracy_all.csv").resolve()),
        "ic_summary_csv": str((master_dir / "ic_summary_all.csv").resolve()),
    }
    print(json.dumps(outputs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()