from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def plot_ic_series(ic_df: pd.DataFrame, factor_name: str, output_dir: Path) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    if ic_df.empty or "factor" not in ic_df.columns:
        return ""
    data = ic_df[ic_df["factor"] == factor_name].copy()
    if data.empty:
        return ""
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(pd.to_datetime(data["date"]), data["ic"], label=factor_name, linewidth=1.2)
    ax.axhline(0.0, color="gray", linestyle="--", linewidth=1)
    ax.set_title(f"{factor_name} Rank IC Time Series")
    ax.set_xlabel("Date")
    ax.set_ylabel("IC")
    ax.legend()
    path = output_dir / f"{factor_name}_ic_series.png"
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return str(path.resolve())


def plot_long_short_nav(spread_df: pd.DataFrame, factor_name: str, output_dir: Path) -> str:
    """Plot cumulative long-short NAV from monthly top-minus-bottom spreads."""
    output_dir.mkdir(parents=True, exist_ok=True)
    if spread_df.empty:
        return ""

    data = spread_df.copy()
    data["date"] = pd.to_datetime(data["date"])
    if "nav" not in data.columns:
        data["nav"] = (1.0 + data["spread"]).cumprod()

    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw={"height_ratios": [2, 1]})

    axes[0].plot(data["date"], data["nav"], color="#4C78A8", linewidth=1.5)
    axes[0].axhline(1.0, color="gray", linestyle="--", linewidth=1)
    axes[0].set_title(f"{factor_name} Long-Short NAV")
    axes[0].set_ylabel("Cumulative NAV")

    colors = ["#E45756" if value < 0 else "#54A24B" for value in data["spread"]]
    bar_width = max(8, min(18, 360 / max(len(data), 1)))
    axes[1].bar(data["date"], data["spread"], color=colors, width=bar_width, align="center")
    axes[1].axhline(0.0, color="gray", linestyle="--", linewidth=1)
    axes[1].set_title(f"{factor_name} Monthly Long-Short Spread")
    axes[1].set_xlabel("Date")
    axes[1].set_ylabel("Spread")

    path = output_dir / f"{factor_name}_long_short_nav.png"
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return str(path.resolve())


def plot_quantile_layer_returns(bucket_df: pd.DataFrame, factor_name: str, output_dir: Path) -> str:
    """Plot decile average forward returns for monotonicity inspection."""
    output_dir.mkdir(parents=True, exist_ok=True)
    if bucket_df.empty:
        return ""

    data = bucket_df.sort_values("quantile").copy()
    colors = ["#E45756" if value < 0 else "#4C78A8" for value in data["mean_return"]]

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(data["quantile"].astype(str), data["mean_return"], color=colors, width=0.7)
    ax.axhline(0.0, color="gray", linestyle="--", linewidth=1)
    ax.set_title(f"{factor_name} Decile Mean Forward Return")
    ax.set_xlabel("Quantile (1=low factor, 10=high factor)")
    ax.set_ylabel("Mean Monthly Forward Return")
    ax.set_xticks(data["quantile"].astype(str))

    path = output_dir / f"{factor_name}_quantile_returns.png"
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return str(path.resolve())


def plot_quantile_bar(quantile_df: pd.DataFrame, factor_name: str, output_dir: Path) -> str:
    """Backward-compatible alias: render decile chart when CSV exists, else skip."""
    bucket_path = output_dir.parent / "effectiveness" / f"{factor_name}_quantile_returns.csv"
    if bucket_path.exists():
        return plot_quantile_layer_returns(pd.read_csv(bucket_path), factor_name, output_dir)
    return ""