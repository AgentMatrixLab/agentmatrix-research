"""Generate a standardized Alpha158 batch report with chart mosaics."""

from __future__ import annotations

import argparse
import json

from research_core.alpha158_lab.config import Alpha158ResearchConfig
from research_core.alpha158_lab.factors.specs import ALPHA158_FIRST_10
from research_core.alpha158_lab.research.batch_report import (
    BatchReportConfig,
    ensure_report_template,
    generate_batch_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Alpha158 batch report")
    parser.add_argument("--batch-id", default="batch_01")
    parser.add_argument("--batch-title", default="Alpha158 批次01：KBar + OPEN0（因子 #1-#10）")
    parser.add_argument("--factor-index-start", type=int, default=1)
    parser.add_argument("--factor-index-end", type=int, default=10)
    parser.add_argument(
        "--factors",
        default=",".join(ALPHA158_FIRST_10),
        help="Comma-separated factor names",
    )
    args = parser.parse_args()

    cfg = Alpha158ResearchConfig()
    reports_root = cfg.output_dir / "reports"
    ensure_report_template(reports_root)

    factor_names = [name.strip() for name in args.factors.split(",") if name.strip()]
    payload = generate_batch_report(
        BatchReportConfig(
            batch_id=args.batch_id,
            batch_title=args.batch_title,
            factor_names=factor_names,
            factor_index_start=args.factor_index_start,
            factor_index_end=args.factor_index_end,
            charts_dir=cfg.output_dir / "charts",
            reports_root=reports_root,
            compute_range=cfg.compute_range_label,
            validation_range=cfg.validation_range_label,
        ),
        workspace=cfg,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()