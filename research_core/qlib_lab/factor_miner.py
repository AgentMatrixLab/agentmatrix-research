from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from common.paths import runtime_path
from contracts.factor import FactorDefinition, FactorEvaluation, FactorMetric
from registry.factor_registry import get_factor_definition, save_factor_definition
from research_core.qlib_lab.runtime import QlibWorkspaceConfig, init_qlib_workspace


def _now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _factor_id(expression: str, name: str = "") -> str:
    seed = f"{name}:{expression}".strip(":")
    return hashlib.md5(seed.encode("utf-8")).hexdigest()[:16]


def _ensure_multiindex(frame: pd.DataFrame) -> pd.DataFrame:
    if isinstance(frame.index, pd.MultiIndex):
        return frame
    if {"datetime", "instrument"}.issubset(frame.columns):
        return frame.set_index(["datetime", "instrument"]).sort_index()
    raise ValueError("Expected qlib data with a MultiIndex of (datetime, instrument)")


def _ic_per_date(frame: pd.DataFrame, rank: bool = False) -> list[float]:
    values: list[float] = []
    for _, daily in frame.groupby(level=0):
        valid = daily[["factor", "future_return"]].dropna()
        if len(valid) < 5:
            continue
        series_a = valid["factor"].rank() if rank else valid["factor"]
        series_b = valid["future_return"].rank() if rank else valid["future_return"]
        corr = series_a.corr(series_b)
        if pd.notna(corr):
            values.append(float(corr))
    return values


def _top_bottom_spread(frame: pd.DataFrame, quantile: float = 0.2) -> float:
    spreads: list[float] = []
    for _, daily in frame.groupby(level=0):
        valid = daily[["factor", "future_return"]].dropna()
        if len(valid) < 10:
            continue
        top_threshold = valid["factor"].quantile(1 - quantile)
        bottom_threshold = valid["factor"].quantile(quantile)
        long_leg = valid.loc[valid["factor"] >= top_threshold, "future_return"]
        short_leg = valid.loc[valid["factor"] <= bottom_threshold, "future_return"]
        if len(long_leg) == 0 or len(short_leg) == 0:
            continue
        spreads.append(float(long_leg.mean() - short_leg.mean()))
    return float(sum(spreads) / len(spreads)) if spreads else 0.0


class QlibFactorLab:
    def __init__(self, config: QlibWorkspaceConfig | None = None):
        self.config = config or QlibWorkspaceConfig.from_env()

    def init_workspace(self) -> dict[str, Any]:
        return init_qlib_workspace(self.config, require_package=True, require_data=True)

    def register_factor(
        self,
        name: str,
        expression: str,
        description: str = "",
        *,
        source: str = "manual",
        author: str = "intern",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> FactorDefinition:
        definition = FactorDefinition(
            factor_id=_factor_id(expression, name),
            name=name,
            expression=expression,
            description=description,
            source=source,
            author=author,
            tags=tags or [],
            metadata={"registered_at": _now_iso(), **(metadata or {})},
        )
        save_factor_definition(definition)
        return definition

    def _resolve_instruments(self, instruments):
        """Resolve string market name to actual instrument list for client provider."""
        if instruments is None:
            instruments = self.config.universe
        if isinstance(instruments, str):
            inst_file = Path(self.config.resolved_provider_uri()) / "instruments" / f"{instruments}.txt"
            if inst_file.exists():
                return sorted({line.split('\t')[0] for line in inst_file.read_text().splitlines() if line.strip()})
            return instruments  # pass through, let qlib handle it
        return instruments

    def fetch_expression_frame(
        self,
        expression: str,
        start_time: str,
        end_time: str,
        *,
        instruments: str | list[str] | None = None,
    ) -> pd.DataFrame:
        self.init_workspace()

        from qlib.data import D

        instruments = self._resolve_instruments(instruments)
        frame = D.features(
            instruments=instruments,
            fields=[expression, "$close"],
            start_time=start_time,
            end_time=end_time,
            freq=self.config.freq,
        )
        frame.columns = ["factor", "close"]
        frame = _ensure_multiindex(frame).sort_index()
        frame["future_return"] = (
            frame.groupby(level=1)["close"].shift(-5) / frame["close"] - 1.0
        )
        return frame

    def evaluate_factor(
        self,
        definition: FactorDefinition,
        *,
        start_time: str,
        end_time: str,
        horizon: int = 5,
        instruments: str | list[str] | None = None,
    ) -> dict[str, Any]:
        self.init_workspace()

        from qlib.data import D

        instruments = self._resolve_instruments(instruments)
        frame = D.features(
            instruments=instruments,
            fields=[definition.expression, "$close"],
            start_time=start_time,
            end_time=end_time,
            freq=self.config.freq,
        )
        frame.columns = ["factor", "close"]
        frame = _ensure_multiindex(frame).sort_index()
        frame["future_return"] = (
            frame.groupby(level=1)["close"].shift(-horizon) / frame["close"] - 1.0
        )

        ic_values = _ic_per_date(frame, rank=False)
        rank_ic_values = _ic_per_date(frame, rank=True)
        coverage = int(frame["factor"].notna().sum())
        sample_days = int(frame.index.get_level_values(0).nunique())
        mean_ic = float(sum(ic_values) / len(ic_values)) if ic_values else 0.0
        mean_rank_ic = float(sum(rank_ic_values) / len(rank_ic_values)) if rank_ic_values else 0.0
        ic_std = float(pd.Series(ic_values).std(ddof=0)) if ic_values else 0.0
        icir = float(mean_ic / ic_std) if ic_std else 0.0
        long_short = _top_bottom_spread(frame)
        positive_rate = (
            float(sum(1 for value in ic_values if value > 0) / len(ic_values))
            if ic_values
            else 0.0
        )

        metrics = [
            FactorMetric(name="ic_mean", value=mean_ic),
            FactorMetric(name="rank_ic_mean", value=mean_rank_ic),
            FactorMetric(name="icir", value=icir),
            FactorMetric(name="positive_ic_ratio", value=positive_rate),
            FactorMetric(name="long_short_spread", value=long_short),
        ]
        evaluation = FactorEvaluation(
            factor_id=definition.factor_id,
            score_horizon=horizon,
            coverage=coverage,
            metrics=metrics,
            diagnostics={
                "sample_days": sample_days,
                "start_time": start_time,
                "end_time": end_time,
                "instruments": instruments or self.config.universe,
                "region": self.config.region,
                "provider_uri": self.config.resolved_provider_uri(),
            },
        )

        artifact_prefix = f"{definition.factor_id}_{start_time}_{end_time}".replace(":", "-")
        factors_dir = runtime_path("qlib", "factors")
        eval_dir = runtime_path("qlib", "evaluations")
        factors_dir.mkdir(parents=True, exist_ok=True)
        eval_dir.mkdir(parents=True, exist_ok=True)

        frame_path = factors_dir / f"{artifact_prefix}.csv"
        eval_path = eval_dir / f"{artifact_prefix}.json"
        frame.reset_index().to_csv(frame_path, index=False)
        eval_payload = asdict(evaluation)
        eval_payload["evaluated_at"] = _now_iso()
        eval_path.write_text(json.dumps(eval_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        evaluation.artifacts["factor_frame"] = str(frame_path)
        evaluation.artifacts["evaluation"] = str(eval_path)
        eval_payload["artifacts"] = evaluation.artifacts
        eval_path.write_text(json.dumps(eval_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        return {
            "definition": asdict(definition),
            "evaluation": asdict(evaluation),
            "top_metrics": {
                "ic_mean": mean_ic,
                "rank_ic_mean": mean_rank_ic,
                "icir": icir,
                "long_short_spread": long_short,
            },
        }

    def mine_expression(
        self,
        *,
        name: str,
        expression: str,
        description: str,
        start_time: str,
        end_time: str,
        horizon: int = 5,
        source: str = "manual",
        author: str = "intern",
        tags: list[str] | None = None,
        instruments: str | list[str] | None = None,
    ) -> dict[str, Any]:
        definition = self.register_factor(
            name=name,
            expression=expression,
            description=description,
            source=source,
            author=author,
            tags=tags,
        )
        return self.evaluate_factor(
            definition,
            start_time=start_time,
            end_time=end_time,
            horizon=horizon,
            instruments=instruments,
        )

    def reproduce_factor(
        self,
        factor_id: str,
        *,
        start_time: str,
        end_time: str,
        horizon: int = 5,
        instruments: str | list[str] | None = None,
    ) -> dict[str, Any]:
        payload = get_factor_definition(factor_id)
        if payload is None:
            raise KeyError(f"Factor not found in registry: {factor_id}")
        definition = FactorDefinition(**{key: value for key, value in payload.items() if key in FactorDefinition.__dataclass_fields__})
        return self.evaluate_factor(
            definition,
            start_time=start_time,
            end_time=end_time,
            horizon=horizon,
            instruments=instruments,
        )
