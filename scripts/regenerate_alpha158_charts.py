"""Regenerate Alpha158 effectiveness diagnostics and charts from cached parquet."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from research_core.alpha158_lab.config import Alpha158ResearchConfig
from research_core.alpha158_lab.factors.specs import ALPHA158_FIRST_10
from research_core.alpha158_lab.research.effectiveness import forward_daily_return_frame, run_effectiveness_suite
from research_core.alpha158_lab.research.visualize import (
    plot_long_short_nav,
    plot_quantile_layer_returns,
)
from research_core.factor_library.validation import compute_ic_series


def main() -> None:
    cfg = Alpha158ResearchConfig()
    root = cfg.output_dir
    panel = pd.read_parquet(root / "market_panel.parquet")
    factor_frame = pd.read_parquet(root / "alpha158_factors_smartdata.parquet")

    effectiveness = run_effectiveness_suite(
        market_panel=panel,
        factor_frame=factor_frame,
        factor_names=list(ALPHA158_FIRST_10),
        output_dir=root / "effectiveness",
    )

    return_df = forward_daily_return_frame(panel)
    ic_df = compute_ic_series(
        factor_frame,
        return_df,
        list(ALPHA158_FIRST_10),
        return_col="forward_return_1d",
    )
    ic_df.to_csv(root / "effectiveness" / "ic_series.csv", index=False)

    chart_dir = root / "charts"
    old_glob = list(chart_dir.glob("*_quantile_spread.png"))
    for path in old_glob:
        path.unlink(missing_ok=True)

    for factor in ALPHA158_FIRST_10:
        from research_core.alpha158_lab.research.visualize import plot_ic_series

        plot_ic_series(ic_df, factor, chart_dir)
        spread_path = root / "effectiveness" / f"{factor}_long_short_spread.csv"
        bucket_path = root / "effectiveness" / f"{factor}_quantile_returns.csv"
        plot_long_short_nav(pd.read_csv(spread_path), factor, chart_dir)
        plot_quantile_layer_returns(pd.read_csv(bucket_path), factor, chart_dir)

    from research_core.alpha158_lab.research.batch_report import (
        BatchReportConfig,
        ensure_report_template,
        generate_batch_report,
    )

    reports_root = root / "reports"
    ensure_report_template(reports_root)
    batch_payload = generate_batch_report(
        BatchReportConfig(
            batch_id="batch_01",
            batch_title="Alpha158 批次01：KBar + OPEN0（因子 #1-#10）",
            factor_names=list(ALPHA158_FIRST_10),
            factor_index_start=1,
            factor_index_end=10,
            charts_dir=chart_dir,
            reports_root=reports_root,
            compute_range=cfg.compute_range_label,
            validation_range=cfg.validation_range_label,
        ),
        workspace=cfg,
    )

    print(f"Regenerated charts under: {chart_dir.resolve()}")
    print(f"Effectiveness report: {effectiveness['path']}")
    print(f"Batch report: {batch_payload['report_markdown']}")


if __name__ == "__main__":
    main()