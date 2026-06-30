from __future__ import annotations

import json
from dataclasses import asdict
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
    top_n: int = 50,
    long_short: bool = False,
    max_abs_weight: float = 0.10,
) -> pd.DataFrame:
    frame = scores.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    target_date = pd.Timestamp(as_of) if as_of else frame["date"].max()
    available_dates = sorted(frame.loc[frame["date"] <= target_date, "date"].unique())
    if not available_dates:
        raise ValueError(f"No alpha scores available on or before {target_date.date()}")
    selected_date = pd.Timestamp(available_dates[-1])
    cross_section = frame.loc[frame["date"] == selected_date].sort_values("alpha_score", ascending=False)
    if cross_section.empty:
        raise ValueError(f"No alpha scores for selected date {selected_date.date()}")

    top = cross_section.head(top_n).copy()
    top["target_weight"] = min(1.0 / max(1, len(top)), max_abs_weight)
    top["side"] = "long"
    if long_short:
        bottom = cross_section.tail(top_n).copy()
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
    weights = build_target_weights(scores, as_of=as_of or None, top_n=top_n, long_short=long_short)

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
        "as_of": str(weights["date"].iloc[0]) if not weights.empty else as_of,
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
