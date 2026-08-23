"""Summarize Alpha158 daily Rank IC metrics for all computed factors."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from research_core.alpha158_lab.factors.specs import ALPHA158_BATCHES
from research_core.factor_library.validation import summarize_ic

ROOT = Path(__file__).resolve().parents[1] / "runtime" / "alpha158_lab"


def main() -> None:
    ic = pd.read_csv(ROOT / "effectiveness" / "ic_series.csv", parse_dates=["date"])
    summary = summarize_ic(ic)
    summary = summary.rename(
        columns={
            "mean_ic": "ic_mean",
            "ic_ir": "ic_ir",
            "win_rate": "ic_win_rate",
            "n_periods": "n_periods",
        }
    )

    factor_batch: dict[str, str] = {}
    for batch_id, meta in sorted(ALPHA158_BATCHES.items()):
        for factor in meta["factors"]:  # type: ignore[union-attr]
            factor_batch[factor] = batch_id
    summary["batch"] = summary["factor"].map(factor_batch)
    summary["ic_win_rate_pct"] = (summary["ic_win_rate"] * 100).round(1)

    out = ROOT / "effectiveness" / "ic_summary_all.csv"
    summary.to_csv(out, index=False, encoding="utf-8-sig")

    print("=== Alpha158 IC Summary (daily Rank IC, forward_return_1d) ===")
    print(f"factors: {len(summary)}  periods_per_factor: {int(summary['n_periods'].iloc[0])}")
    print()
    print("--- Overall ---")
    print(
        f"IC mean: median={summary['ic_mean'].median():.4f} "
        f"avg={summary['ic_mean'].mean():.4f} "
        f"min={summary['ic_mean'].min():.4f} max={summary['ic_mean'].max():.4f}"
    )
    print(
        f"IC_IR:   median={summary['ic_ir'].median():.3f} avg={summary['ic_ir'].mean():.3f}"
    )
    print(
        f"IC win%: median={summary['ic_win_rate_pct'].median():.1f} "
        f"avg={summary['ic_win_rate_pct'].mean():.1f}"
    )
    print()
    print("--- Top 10 by IC_IR ---")
    cols = ["factor", "batch", "ic_mean", "ic_ir", "ic_win_rate_pct"]
    print(summary.nlargest(10, "ic_ir")[cols].to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    print()
    print("--- Bottom 10 by IC_IR ---")
    print(summary.nsmallest(10, "ic_ir")[cols].to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    print()
    print("--- By batch (mean) ---")
    batch = (
        summary.groupby("batch", sort=False)
        .agg(
            n_factors=("factor", "count"),
            ic_mean=("ic_mean", "mean"),
            ic_ir=("ic_ir", "mean"),
            ic_win_rate_pct=("ic_win_rate_pct", "mean"),
        )
        .round(4)
    )
    print(batch.to_string())
    print()
    print(f"saved: {out.resolve()}")


if __name__ == "__main__":
    main()