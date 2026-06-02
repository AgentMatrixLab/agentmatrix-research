from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


FACTOR_CATEGORIES = [
    "value", "momentum", "volatility", "liquidity", "size",
    "quality", "growth", "sentiment", "technical", "composite",
    "alpha101", "barra",
]


@dataclass(slots=True)
class FactorMetadata:
    factor_id: str
    name: str
    category: str = "custom"
    description: str = ""
    formula: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    lookback_days: int = 0
    universe: str = "all_a"
    frequency: str = "daily"
    source: str = "manual"
    version: str = "v1"


@dataclass(slots=True)
class FactorResult:
    factor_id: str
    date: str
    values: pd.Series
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def coverage(self) -> int:
        return self.values.notna().sum()

    @property
    def coverage_ratio(self) -> float:
        total = len(self.values)
        return self.coverage / total if total > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "factor_id": self.factor_id,
            "date": self.date,
            "values": self.values.to_dict(),
            "coverage": self.coverage,
            "coverage_ratio": round(self.coverage_ratio, 4),
            "metadata": self.metadata,
        }


class FactorBase(ABC):
    def __init__(self, metadata: FactorMetadata):
        self._metadata = metadata

    @property
    def metadata(self) -> FactorMetadata:
        return self._metadata

    @abstractmethod
    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        raise NotImplementedError

    def validate_input(self, data: pd.DataFrame, required_columns: list[str] | None = None) -> None:
        if data.empty:
            raise ValueError(f"[{self._metadata.factor_id}] Input DataFrame is empty")
        if required_columns:
            missing = set(required_columns) - set(data.columns)
            if missing:
                raise ValueError(
                    f"[{self._metadata.factor_id}] Missing required columns: {missing}"
                )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self._metadata.factor_id} name={self._metadata.name}>"


def ts_sum(df: pd.Series, window: int) -> pd.Series:
    return df.rolling(window=window, min_periods=1).sum()


def ts_mean(df: pd.Series, window: int) -> pd.Series:
    return df.rolling(window=window, min_periods=1).mean()


def ts_std(df: pd.Series, window: int) -> pd.Series:
    return df.rolling(window=window, min_periods=1).std()


def ts_max(df: pd.Series, window: int) -> pd.Series:
    return df.rolling(window=window, min_periods=1).max()


def ts_min(df: pd.Series, window: int) -> pd.Series:
    return df.rolling(window=window, min_periods=1).min()


def ts_rank(df: pd.Series, window: int = 20) -> pd.Series:
    return df.rolling(window=window, min_periods=1).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False
    )


def ts_delta(df: pd.Series, period: int) -> pd.Series:
    return df.diff(period)


def ts_delay(df: pd.Series, period: int) -> pd.Series:
    return df.shift(period)


def ts_return(df: pd.Series, period: int) -> pd.Series:
    return df.pct_change(period)


def ts_corr(x: pd.Series, y: pd.Series, window: int) -> pd.Series:
    return x.rolling(window=window, min_periods=2).corr(y)


def ts_cov(x: pd.Series, y: pd.Series, window: int) -> pd.Series:
    return x.rolling(window=window, min_periods=2).cov(y)


def rank(df: pd.Series) -> pd.Series:
    return df.rank(pct=True)


def scale(df: pd.Series, a: float = 1.0) -> pd.Series:
    s = df.abs().sum()
    if s == 0:
        return df * 0
    return df / s * a


def sign(df: pd.Series) -> pd.Series:
    return df.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))


def decay_linear(df: pd.Series, window: int) -> pd.Series:
    weights = pd.Series(range(1, window + 1), dtype=float)
    return df.rolling(window=window, min_periods=1).apply(
        lambda x: (x * weights[:len(x)].values).sum() / weights[:len(x)].values.sum(),
        raw=True,
    )


def product(df: pd.Series, window: int) -> pd.Series:
    return df.rolling(window=window, min_periods=1).apply(lambda x: x.prod(), raw=True)
