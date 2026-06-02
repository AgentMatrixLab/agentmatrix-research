from __future__ import annotations

import numpy as np
import pandas as pd

from research_core.factor_engine.base import (
    FactorBase,
    FactorMetadata,
    FactorResult,
    rank,
    scale,
    sign,
    ts_corr,
    ts_delta,
    ts_delay,
    ts_max,
    ts_mean,
    ts_min,
    ts_rank,
    ts_std,
    ts_sum,
    decay_linear,
    product,
)


def _group_apply(df: pd.DataFrame, group_col: str, value_col: str, func) -> pd.Series:
    return df.groupby(group_col)[value_col].transform(func)


class Alpha1(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_001",
            name="Alpha#1",
            category="alpha101",
            description="(rank(Ts_ArgMax(SignedPower(((returns < 0) ? stddev(returns, 20) : close), 2.), 5)) - 0.5)",
            formula="rank(ts_argmax(signed_power(if(returns<0, std(returns,20), close), 2), 5)) - 0.5",
            lookback_days=20,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["close", "symbol"])
        df = data.copy()
        df["returns"] = df.groupby("symbol")["close"].pct_change()
        df["std_20"] = df.groupby("symbol")["returns"].transform(
            lambda x: x.rolling(20, min_periods=1).std()
        )
        df["cond"] = np.where(df["returns"] < 0, df["std_20"], df["close"])
        df["signed_power"] = np.sign(df["cond"]) * df["cond"] ** 2
        df["ts_argmax_5"] = df.groupby("symbol")["signed_power"].transform(
            lambda x: x.rolling(5, min_periods=1).apply(np.argmax, raw=True)
        )
        df["factor"] = df.groupby("date")["ts_argmax_5"].transform(
            lambda x: x.rank(pct=True)
        ) - 0.5

        result = df.set_index(["date", "symbol"])["factor"].unstack(level="symbol")
        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha2(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_002",
            name="Alpha#2",
            category="alpha101",
            description="(-1 * correlation(rank(delta(log(volume), 2)), rank(((close - open) / open)), 6))",
            lookback_days=6,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["close", "open", "volume", "symbol"])
        df = data.copy()
        df["log_vol"] = np.log(df["volume"].replace(0, np.nan))
        df["delta_log_vol"] = df.groupby("symbol")["log_vol"].transform(
            lambda x: x.diff(2)
        )
        df["rank_delta_log_vol"] = df.groupby("date")["delta_log_vol"].transform(
            lambda x: x.rank(pct=True)
        )
        df["intraday_ret"] = (df["close"] - df["open"]) / df["open"]
        df["rank_intraday"] = df.groupby("date")["intraday_ret"].transform(
            lambda x: x.rank(pct=True)
        )
        df["corr"] = df.groupby("symbol").apply(
            lambda g: g["rank_delta_log_vol"].rolling(6, min_periods=3).corr(
                g["rank_intraday"]
            )
        ).reset_index(level=0, drop=True)
        df["factor"] = -1 * df["corr"]

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha6(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_006",
            name="Alpha#6",
            category="alpha101",
            description="(-1 * ts_corr(open, volume, 10))",
            lookback_days=10,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["open", "volume", "symbol"])
        df = data.copy()
        df["corr"] = df.groupby("symbol").apply(
            lambda g: g["open"].rolling(10, min_periods=5).corr(g["volume"])
        ).reset_index(level=0, drop=True)
        df["factor"] = -1 * df["corr"]

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha12(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_012",
            name="Alpha#12",
            category="alpha101",
            description="sign(delta(volume, 1)) * (-1 * delta(close, 1))",
            lookback_days=1,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["close", "volume", "symbol"])
        df = data.copy()
        df["delta_vol"] = df.groupby("symbol")["volume"].diff(1)
        df["delta_close"] = df.groupby("symbol")["close"].diff(1)
        df["factor"] = np.sign(df["delta_vol"]) * (-1 * df["delta_close"])

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha15(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_015",
            name="Alpha#15",
            category="alpha101",
            description="(-1 * sum(rank(correlation(rank(high), rank(volume), 3)), 3))",
            lookback_days=3,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["high", "volume", "symbol"])
        df = data.copy()
        df["rank_high"] = df.groupby("date")["high"].transform(
            lambda x: x.rank(pct=True)
        )
        df["rank_vol"] = df.groupby("date")["volume"].transform(
            lambda x: x.rank(pct=True)
        )
        df["corr"] = df.groupby("symbol").apply(
            lambda g: g["rank_high"].rolling(3, min_periods=2).corr(g["rank_vol"])
        ).reset_index(level=0, drop=True)
        df["rank_corr"] = df.groupby("date")["corr"].transform(
            lambda x: x.rank(pct=True)
        )
        df["sum_rank_corr"] = df.groupby("symbol")["rank_corr"].transform(
            lambda x: x.rolling(3, min_periods=1).sum()
        )
        df["factor"] = -1 * df["sum_rank_corr"]

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha20(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_020",
            name="Alpha#20",
            category="alpha101",
            description="((-1 * rank(open - delay(high, 1))) * rank(open - delay(close, 1)) * rank(open - delay(low, 1)))",
            lookback_days=1,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["open", "high", "low", "close", "symbol"])
        df = data.copy()
        df["delay_high"] = df.groupby("symbol")["high"].shift(1)
        df["delay_close"] = df.groupby("symbol")["close"].shift(1)
        df["delay_low"] = df.groupby("symbol")["low"].shift(1)
        df["r1"] = df.groupby("date")["open"].sub(df["delay_high"]).groupby(df["date"]).transform(
            lambda x: x.rank(pct=True)
        )
        df["r2"] = df.groupby("date")["open"].sub(df["delay_close"]).groupby(df["date"]).transform(
            lambda x: x.rank(pct=True)
        )
        df["r3"] = df.groupby("date")["open"].sub(df["delay_low"]).groupby(df["date"]).transform(
            lambda x: x.rank(pct=True)
        )
        df["factor"] = -1 * df["r1"] * df["r2"] * df["r3"]

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha41(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_041",
            name="Alpha#41",
            category="alpha101",
            description="(((high * low)**0.5) - vwap)",
            lookback_days=0,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["high", "low", "close", "volume", "symbol"])
        df = data.copy()
        df["vwap"] = df["amount"] / df["volume"].replace(0, np.nan)
        df["hl_sqrt"] = np.sqrt(df["high"] * df["low"])
        df["factor"] = df["hl_sqrt"] - df["vwap"]

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha53(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_053",
            name="Alpha#53",
            category="alpha101",
            description="(-1 * delta((((close - low) - (high - close)) / (close - low)), 9))",
            lookback_days=9,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["close", "high", "low", "symbol"])
        df = data.copy()
        cl = df["close"] - df["low"]
        cl = cl.replace(0, np.nan)
        df["inner"] = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / cl
        df["delta_inner"] = df.groupby("symbol")["inner"].diff(9)
        df["factor"] = -1 * df["delta_inner"]

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha101Registry:
    _factors: dict[str, type[FactorBase]] = {
        "alpha101_001": Alpha1,
        "alpha101_002": Alpha2,
        "alpha101_006": Alpha6,
        "alpha101_012": Alpha12,
        "alpha101_015": Alpha15,
        "alpha101_020": Alpha20,
        "alpha101_041": Alpha41,
        "alpha101_053": Alpha53,
    }

    @classmethod
    def list_factors(cls) -> list[str]:
        return list(cls._factors.keys())

    @classmethod
    def get_factor(cls, factor_id: str) -> FactorBase | None:
        klass = cls._factors.get(factor_id)
        if klass is None:
            return None
        return klass()

    @classmethod
    def get_all_factors(cls) -> list[FactorBase]:
        return [cls.get_factor(fid) for fid in cls.list_factors()]
