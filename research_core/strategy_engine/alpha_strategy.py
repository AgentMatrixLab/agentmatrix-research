from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from common.paths import runtime_path
from contracts.strategy import StrategyContext, StrategyDecision, StrategyMetadata, TargetPosition
from research_core.strategy_engine.base import BaseStrategyKernel


def _winsorize_by_date(frame: pd.DataFrame, columns: list[str], lower: float = 0.01, upper: float = 0.99) -> pd.DataFrame:
    result = frame.copy()
    for column in columns:
        result[column] = result.groupby("date")[column].transform(
            lambda values: values.clip(values.quantile(lower), values.quantile(upper))
        )
    return result


def build_alpha_scores(
    factor_frame: pd.DataFrame,
    *,
    factor_names: list[str],
    winsorize: bool = True,
    industry_col: str = "",
) -> pd.DataFrame:
    frame = factor_frame.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    if winsorize:
        frame = _winsorize_by_date(frame, factor_names)
    score_columns: list[str] = []
    for factor_name in factor_names:
        score_col = f"{factor_name}_rank_score"
        frame[score_col] = frame.groupby("date")[factor_name].rank(pct=True)
        if industry_col and industry_col in frame.columns:
            frame[score_col] = frame[score_col] - frame.groupby(["date", industry_col])[score_col].transform("mean")
        score_columns.append(score_col)
    frame["alpha_score"] = frame[score_columns].mean(axis=1, skipna=True)
    return frame[["date", "code", "alpha_score", *factor_names]].dropna(subset=["alpha_score"])


def build_target_weights(
    scores: pd.DataFrame,
    *,
    as_of: str | None = None,
    start: str | None = None,
    end: str | None = None,
    rebalance_frequency: str = "single",
    top_n: int = 50,
    long_short: bool = False,
    max_abs_weight: float = 0.10,
) -> pd.DataFrame:
    frame = scores.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    selected_dates = _select_rebalance_dates(frame, as_of=as_of, start=start, end=end, frequency=rebalance_frequency)
    targets = [
        _build_target_weights_for_date(
            frame,
            selected_date=date_value,
            top_n=top_n,
            long_short=long_short,
            max_abs_weight=max_abs_weight,
        )
        for date_value in selected_dates
    ]
    return pd.concat(targets, ignore_index=True) if targets else pd.DataFrame(
        columns=["date", "code", "alpha_score", "target_weight", "side"]
    )


def _select_rebalance_dates(
    scores: pd.DataFrame,
    *,
    as_of: str | None = None,
    start: str | None = None,
    end: str | None = None,
    frequency: str = "single",
) -> list[pd.Timestamp]:
    frame = scores.copy()
    available = frame[["date"]].dropna().copy()
    if start:
        available = available.loc[available["date"] >= pd.Timestamp(start)]
    if end:
        available = available.loc[available["date"] <= pd.Timestamp(end)]
    unique_dates = pd.Series(sorted(pd.Timestamp(value) for value in available["date"].unique()))
    if unique_dates.empty:
        window = f"[{start or '-inf'}, {end or '+inf'}]"
        raise ValueError(f"No alpha scores available in requested rebalance window {window}")

    if as_of:
        target_date = pd.Timestamp(as_of)
        prior_dates = unique_dates.loc[unique_dates <= target_date]
        if prior_dates.empty:
            raise ValueError(f"No alpha scores available on or before {target_date.date()}")
        return [pd.Timestamp(prior_dates.iloc[-1])]

    normalized = frequency.lower().replace("-", "_")
    if normalized in {"single", "snapshot"}:
        return [pd.Timestamp(unique_dates.iloc[-1])]
    if normalized in {"daily", "trade_date", "each_date"}:
        return [pd.Timestamp(value) for value in unique_dates]
    if normalized in {"weekly", "week"}:
        return [pd.Timestamp(value) for value in unique_dates.groupby(unique_dates.dt.to_period("W")).max()]
    if normalized in {"monthly", "month"}:
        return [pd.Timestamp(value) for value in unique_dates.groupby(unique_dates.dt.to_period("M")).max()]
    raise ValueError("rebalance_frequency must be one of: single, daily, weekly, monthly")


def _build_target_weights_for_date(
    scores: pd.DataFrame,
    *,
    selected_date: pd.Timestamp,
    top_n: int,
    long_short: bool,
    max_abs_weight: float,
) -> pd.DataFrame:
    cross_section = scores.loc[scores["date"] == selected_date].sort_values("alpha_score", ascending=False)
    if cross_section.empty:
        raise ValueError(f"No alpha scores for selected date {selected_date.date()}")

    top = cross_section.head(top_n).copy()
    top["target_weight"] = min(1.0 / max(1, len(top)), max_abs_weight)
    top["side"] = "long"
    if long_short:
        leg_size = min(int(top_n), int(len(cross_section) // 2))
        if leg_size < 1:
            raise ValueError(
                f"At least two securities are required for long_short targets on {selected_date.date()}"
            )
        top = cross_section.head(leg_size).copy()
        long_codes = set(top["code"].astype(str))
        bottom = cross_section.loc[~cross_section["code"].astype(str).isin(long_codes)].tail(leg_size).copy()
        if bottom.empty:
            raise ValueError(f"No non-overlapping short leg available for {selected_date.date()}")
        top["side"] = "long"
        bottom["target_weight"] = -min(0.5 / max(1, len(bottom)), max_abs_weight)
        bottom["side"] = "short"
        top["target_weight"] = min(0.5 / max(1, len(top)), max_abs_weight)
        selected = pd.concat([top, bottom], ignore_index=True)
    else:
        selected = top
    selected["date"] = selected_date.strftime("%Y-%m-%d")
    return selected[["date", "code", "alpha_score", "target_weight", "side"]].reset_index(drop=True)


class AlphaSignalStrategyKernel(BaseStrategyKernel):
    def __init__(
        self,
        *,
        strategy_id: str,
        factor_names: list[str],
        top_n: int = 50,
        long_short: bool = False,
    ):
        super().__init__(
            StrategyMetadata(
                strategy_id=strategy_id,
                name=f"Alpha signal strategy: {strategy_id}",
                version="v1",
                source="factor_lab",
                source_engine="agentmatrix",
                execution_engine="external_sim",
                tags=["alpha", "factor_lab"],
            )
        )
        self.factor_names = factor_names
        self.top_n = top_n
        self.long_short = long_short

    def generate_decision(self, context: StrategyContext, market_data: Any) -> StrategyDecision:
        scores = build_alpha_scores(pd.DataFrame(market_data), factor_names=self.factor_names)
        weights = build_target_weights(scores, as_of=context.as_of, top_n=self.top_n, long_short=self.long_short)
        targets = [
            TargetPosition(
                symbol=row.code,
                target_weight=float(row.target_weight),
                side=str(row.side),
                reason="factor_lab_alpha_score",
                metadata={"alpha_score": float(row.alpha_score), "as_of": str(row.date)},
            )
            for row in weights.itertuples(index=False)
        ]
        return StrategyDecision(
            metadata=self.metadata(),
            context=context,
            targets=targets,
            parameters={"factor_names": self.factor_names, "top_n": self.top_n, "long_short": self.long_short},
            diagnostics={"target_count": len(targets)},
            raw_signals=weights.to_dict(orient="records"),
        )


def build_alpha_strategy_package(
    *,
    validated_run_path: str | Path,
    factor_names: list[str] | None = None,
    as_of: str = "",
    start: str = "",
    end: str = "",
    rebalance_frequency: str = "daily",
    top_n: int = 50,
    long_short: bool = False,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    run_path = Path(validated_run_path)
    payload = json.loads(run_path.read_text(encoding="utf-8"))
    frame_path = Path(payload["artifacts"]["factor_frame"])
    frame = pd.read_csv(frame_path)
    requested_factors = factor_names or list(payload.get("requested_factors", []))
    if not requested_factors:
        raise ValueError("No factor names supplied and validated run has no requested_factors.")
    scores = build_alpha_scores(frame, factor_names=requested_factors)
    weights = build_target_weights(
        scores,
        as_of=as_of or None,
        start=start or None,
        end=end or None,
        rebalance_frequency="single" if as_of else rebalance_frequency,
        top_n=top_n,
        long_short=long_short,
    )

    strategy_id = f"{payload['job_id']}_alpha_strategy"
    target_dir = Path(output_dir) if output_dir else runtime_path("strategy_engine", strategy_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    signal_path = target_dir / "target_weights.csv"
    config_path = target_dir / "strategy_config.json"
    weights.to_csv(signal_path, index=False, encoding="utf-8")
    config = {
        "strategy_id": strategy_id,
        "source_job_id": payload["job_id"],
        "source_run": str(run_path),
        "factor_names": requested_factors,
        "as_of": str(weights["date"].iloc[0]) if as_of and not weights.empty else as_of,
        "signal_start": str(weights["date"].min()) if not weights.empty else start,
        "signal_end": str(weights["date"].max()) if not weights.empty else end,
        "rebalance_frequency": "single" if as_of else rebalance_frequency,
        "top_n": top_n,
        "long_short": long_short,
        "signal_path": str(signal_path),
        "lifecycle_state": "strategy_candidate",
    }
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "strategy_id": strategy_id,
        "status": "created",
        "artifacts": {
            "signals": str(signal_path),
            "config": str(config_path),
        },
        "config": config,
        "sample_targets": weights.head(10).to_dict(orient="records"),
    }
