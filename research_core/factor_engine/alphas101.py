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
        df["d1"] = df["open"] - df["delay_high"]
        df["d2"] = df["open"] - df["delay_close"]
        df["d3"] = df["open"] - df["delay_low"]
        df["r1"] = df.groupby("date")["d1"].transform(lambda x: x.rank(pct=True))
        df["r2"] = df.groupby("date")["d2"].transform(lambda x: x.rank(pct=True))
        df["r3"] = df.groupby("date")["d3"].transform(lambda x: x.rank(pct=True))
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


class Alpha3(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_003",
            name="Alpha#3",
            category="alpha101",
            description="(-1 * correlation(rank(open), rank(volume), 10))",
            lookback_days=10,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["open", "volume", "symbol"])
        df = data.copy()
        df["rank_open"] = df.groupby("date")["open"].transform(lambda x: x.rank(pct=True))
        df["rank_vol"] = df.groupby("date")["volume"].transform(lambda x: x.rank(pct=True))
        df["corr"] = df.groupby("symbol").apply(
            lambda g: g["rank_open"].rolling(10, min_periods=5).corr(g["rank_vol"])
        ).reset_index(level=0, drop=True)
        df["factor"] = -1 * df["corr"]

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha4(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_004",
            name="Alpha#4",
            category="alpha101",
            description="(-1 * ts_rank(rank(low), 9))",
            lookback_days=9,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["low", "symbol"])
        df = data.copy()
        df["rank_low"] = df.groupby("date")["low"].transform(lambda x: x.rank(pct=True))
        df["ts_rank"] = df.groupby("symbol")["rank_low"].transform(
            lambda x: x.rolling(9, min_periods=5).apply(lambda w: pd.Series(w).rank(pct=True).iloc[-1], raw=True)
        )
        df["factor"] = -1 * df["ts_rank"]

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha5(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_005",
            name="Alpha#5",
            category="alpha101",
            description="(-1 * ts_max(rank(correlation(ts_rank(volume, 5), ts_rank(high, 5), 5)), 3))",
            lookback_days=5,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["high", "volume", "symbol"])
        df = data.copy()
        df["ts_rank_vol"] = df.groupby("symbol")["volume"].transform(
            lambda x: x.rolling(5, min_periods=3).apply(lambda w: pd.Series(w).rank(pct=True).iloc[-1], raw=True)
        )
        df["ts_rank_high"] = df.groupby("symbol")["high"].transform(
            lambda x: x.rolling(5, min_periods=3).apply(lambda w: pd.Series(w).rank(pct=True).iloc[-1], raw=True)
        )
        df["corr"] = df.groupby("symbol").apply(
            lambda g: g["ts_rank_vol"].rolling(5, min_periods=3).corr(g["ts_rank_high"])
        ).reset_index(level=0, drop=True)
        df["rank_corr"] = df.groupby("date")["corr"].transform(lambda x: x.rank(pct=True))
        df["ts_max_rank"] = df.groupby("symbol")["rank_corr"].transform(
            lambda x: x.rolling(3, min_periods=1).max()
        )
        df["factor"] = -1 * df["ts_max_rank"]

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha7(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_007",
            name="Alpha#7",
            category="alpha101",
            description="((adv20 < volume) ? (-1 * ts_rank(abs(delta(close, 7)), 60) * sign(delta(close, 7))) : -1)",
            lookback_days=60,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["close", "volume", "symbol"])
        df = data.copy()
        df["adv20"] = df.groupby("symbol")["volume"].transform(
            lambda x: x.rolling(20, min_periods=10).mean()
        )
        df["delta_close_7"] = df.groupby("symbol")["close"].diff(7)
        df["abs_delta"] = df["delta_close_7"].abs()
        df["ts_rank_abs"] = df.groupby("symbol")["abs_delta"].transform(
            lambda x: x.rolling(60, min_periods=30).apply(lambda w: pd.Series(w).rank(pct=True).iloc[-1], raw=True)
        )
        df["sign_delta"] = np.sign(df["delta_close_7"])
        df["factor"] = np.where(
            df["adv20"] < df["volume"],
            -1 * df["ts_rank_abs"] * df["sign_delta"],
            -1.0,
        )

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha8(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_008",
            name="Alpha#8",
            category="alpha101",
            description="(-1 * correlation(open, volume, 10).rolling(5, 1).sum())",
            lookback_days=10,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["open", "volume", "symbol"])
        df = data.copy()
        df["corr"] = df.groupby("symbol").apply(
            lambda g: g["open"].rolling(10, min_periods=5).corr(g["volume"])
        ).reset_index(level=0, drop=True)
        df["sum_corr"] = df.groupby("symbol")["corr"].transform(
            lambda x: x.rolling(5, min_periods=1).sum()
        )
        df["factor"] = -1 * df["sum_corr"]

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha10(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_010",
            name="Alpha#10",
            category="alpha101",
            description="rank(((close - open) / ((high - low) + 0.001)))",
            lookback_days=0,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["close", "open", "high", "low", "symbol"])
        df = data.copy()
        hl_range = df["high"] - df["low"] + 0.001
        df["inner"] = (df["close"] - df["open"]) / hl_range
        df["factor"] = df.groupby("date")["inner"].transform(lambda x: x.rank(pct=True))

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha13(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_013",
            name="Alpha#13",
            category="alpha101",
            description="(-1 * rank(covariance(rank(close), rank(volume), 5)))",
            lookback_days=5,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["close", "volume", "symbol"])
        df = data.copy()
        df["rank_close"] = df.groupby("date")["close"].transform(lambda x: x.rank(pct=True))
        df["rank_vol"] = df.groupby("date")["volume"].transform(lambda x: x.rank(pct=True))
        df["cov"] = df.groupby("symbol").apply(
            lambda g: g["rank_close"].rolling(5, min_periods=3).cov(g["rank_vol"])
        ).reset_index(level=0, drop=True)
        df["factor"] = -1 * df.groupby("date")["cov"].transform(lambda x: x.rank(pct=True))

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha16(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_016",
            name="Alpha#16",
            category="alpha101",
            description="(-1 * rank(covariance(rank(high), rank(volume), 5)))",
            lookback_days=5,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["high", "volume", "symbol"])
        df = data.copy()
        df["rank_high"] = df.groupby("date")["high"].transform(lambda x: x.rank(pct=True))
        df["rank_vol"] = df.groupby("date")["volume"].transform(lambda x: x.rank(pct=True))
        df["cov"] = df.groupby("symbol").apply(
            lambda g: g["rank_high"].rolling(5, min_periods=3).cov(g["rank_vol"])
        ).reset_index(level=0, drop=True)
        df["factor"] = -1 * df.groupby("date")["cov"].transform(lambda x: x.rank(pct=True))

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha17(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_017",
            name="Alpha#17",
            category="alpha101",
            description="(((-1 * rank(ts_rank(close, 10))) * rank(delta(delta(close, 1), 1)) * rank(ts_rank(volume / adv20, 5))) + 1)",
            lookback_days=10,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["close", "volume", "symbol"])
        df = data.copy()
        df["adv20"] = df.groupby("symbol")["volume"].transform(
            lambda x: x.rolling(20, min_periods=10).mean()
        )
        df["ts_rank_close"] = df.groupby("symbol")["close"].transform(
            lambda x: x.rolling(10, min_periods=5).apply(lambda w: pd.Series(w).rank(pct=True).iloc[-1], raw=True)
        )
        df["delta_close"] = df.groupby("symbol")["close"].diff(1)
        df["delta_delta"] = df.groupby("symbol")["delta_close"].diff(1)
        df["vol_adv"] = df["volume"] / df["adv20"].replace(0, np.nan)
        df["ts_rank_vol"] = df.groupby("symbol")["vol_adv"].transform(
            lambda x: x.rolling(5, min_periods=3).apply(lambda w: pd.Series(w).rank(pct=True).iloc[-1], raw=True)
        )
        r1 = df.groupby("date")["ts_rank_close"].transform(lambda x: x.rank(pct=True))
        r2 = df.groupby("date")["delta_delta"].transform(lambda x: x.rank(pct=True))
        r3 = df.groupby("date")["ts_rank_vol"].transform(lambda x: x.rank(pct=True))
        df["factor"] = (-1 * r1 * r2 * r3) + 1

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha18(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_018",
            name="Alpha#18",
            category="alpha101",
            description="(-1 * rank(((stddev(abs(close - open)) + (close - open)) + ts_corr(close, open, 10))))",
            lookback_days=10,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["close", "open", "symbol"])
        df = data.copy()
        df["co_diff"] = df["close"] - df["open"]
        df["std_abs"] = df.groupby("symbol")["co_diff"].transform(
            lambda x: x.abs().rolling(10, min_periods=5).std()
        )
        df["corr_co"] = df.groupby("symbol").apply(
            lambda g: g["close"].rolling(10, min_periods=5).corr(g["open"])
        ).reset_index(level=0, drop=True)
        df["inner"] = df["std_abs"] + df["co_diff"] + df["corr_co"]
        df["factor"] = -1 * df.groupby("date")["inner"].transform(lambda x: x.rank(pct=True))

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha19(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_019",
            name="Alpha#19",
            category="alpha101",
            description="((-1 * sign(delta(close, 7))) * (1 + rank(decay_linear(close / delay(close, 1) - 1, 5))))",
            lookback_days=7,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["close", "symbol"])
        df = data.copy()
        df["delay_close"] = df.groupby("symbol")["close"].shift(1)
        df["ret_1d"] = df["close"] / df["delay_close"] - 1
        df["decay_ret"] = df.groupby("symbol")["ret_1d"].transform(
            lambda x: x.rolling(5, min_periods=1).apply(
                lambda w: (w * np.arange(1, len(w) + 1)).sum() / np.arange(1, len(w) + 1).sum(), raw=True
            )
        )
        df["delta_close_7"] = df.groupby("symbol")["close"].diff(7)
        df["factor"] = -1 * np.sign(df["delta_close_7"]) * (1 + df.groupby("date")["decay_ret"].transform(lambda x: x.rank(pct=True)))

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha21(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_021",
            name="Alpha#21",
            category="alpha101",
            description="(-1 * (rank(ts_corr(close, volume, 5)) * rank(ts_corr(close, volume, 20))))",
            lookback_days=20,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["close", "volume", "symbol"])
        df = data.copy()
        df["corr_5"] = df.groupby("symbol").apply(
            lambda g: g["close"].rolling(5, min_periods=3).corr(g["volume"])
        ).reset_index(level=0, drop=True)
        df["corr_20"] = df.groupby("symbol").apply(
            lambda g: g["close"].rolling(20, min_periods=10).corr(g["volume"])
        ).reset_index(level=0, drop=True)
        df["factor"] = -1 * (
            df.groupby("date")["corr_5"].transform(lambda x: x.rank(pct=True))
            * df.groupby("date")["corr_20"].transform(lambda x: x.rank(pct=True))
        )

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha26(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_026",
            name="Alpha#26",
            category="alpha101",
            description="(-1 * ts_max(ts_corr(ts_rank(volume, 5), ts_rank(high, 5), 5), 3))",
            lookback_days=5,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["high", "volume", "symbol"])
        df = data.copy()
        df["ts_rank_vol"] = df.groupby("symbol")["volume"].transform(
            lambda x: x.rolling(5, min_periods=3).apply(lambda w: pd.Series(w).rank(pct=True).iloc[-1], raw=True)
        )
        df["ts_rank_high"] = df.groupby("symbol")["high"].transform(
            lambda x: x.rolling(5, min_periods=3).apply(lambda w: pd.Series(w).rank(pct=True).iloc[-1], raw=True)
        )
        df["corr"] = df.groupby("symbol").apply(
            lambda g: g["ts_rank_vol"].rolling(5, min_periods=3).corr(g["ts_rank_high"])
        ).reset_index(level=0, drop=True)
        df["ts_max_corr"] = df.groupby("symbol")["corr"].transform(
            lambda x: x.rolling(3, min_periods=1).max()
        )
        df["factor"] = -1 * df["ts_max_corr"]

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha28(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_028",
            name="Alpha#28",
            category="alpha101",
            description="scale(((correlation(adv20, low) * -1) + rank(covariance(rank(close), rank(volume), 5))))",
            lookback_days=20,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["close", "low", "volume", "symbol"])
        df = data.copy()
        df["adv20"] = df.groupby("symbol")["volume"].transform(
            lambda x: x.rolling(20, min_periods=10).mean()
        )
        df["corr_adv_low"] = df.groupby("symbol").apply(
            lambda g: g["adv20"].rolling(20, min_periods=10).corr(g["low"])
        ).reset_index(level=0, drop=True)
        df["rank_close"] = df.groupby("date")["close"].transform(lambda x: x.rank(pct=True))
        df["rank_vol"] = df.groupby("date")["volume"].transform(lambda x: x.rank(pct=True))
        df["cov_rv"] = df.groupby("symbol").apply(
            lambda g: g["rank_close"].rolling(5, min_periods=3).cov(g["rank_vol"])
        ).reset_index(level=0, drop=True)
        df["inner"] = -1 * df["corr_adv_low"] + df.groupby("date")["cov_rv"].transform(lambda x: x.rank(pct=True))
        mean_abs = df["inner"].abs().mean()
        df["factor"] = df["inner"] / mean_abs if mean_abs > 0 else df["inner"]

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha33(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_033",
            name="Alpha#33",
            category="alpha101",
            description="rank(-1 + (close / delay(close, 1)))",
            lookback_days=1,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["close", "symbol"])
        df = data.copy()
        df["delay_close"] = df.groupby("symbol")["close"].shift(1)
        df["ret"] = df["close"] / df["delay_close"] - 1
        df["factor"] = df.groupby("date")["ret"].transform(lambda x: x.rank(pct=True))

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha34(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_034",
            name="Alpha#34",
            category="alpha101",
            description="mean(close - delay(close, 1) < 0 ? std(close - delay(close, 1), 20) : close / delay(close, 1), 20)",
            lookback_days=20,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["close", "symbol"])
        df = data.copy()
        df["delay_close"] = df.groupby("symbol")["close"].shift(1)
        df["ret"] = df["close"] - df["delay_close"]
        df["std_ret_20"] = df.groupby("symbol")["ret"].transform(
            lambda x: x.rolling(20, min_periods=10).std()
        )
        df["close_ratio"] = df["close"] / df["delay_close"].replace(0, np.nan)
        df["cond_val"] = np.where(df["ret"] < 0, df["std_ret_20"], df["close_ratio"])
        df["factor"] = df.groupby("symbol")["cond_val"].transform(
            lambda x: x.rolling(20, min_periods=10).mean()
        )

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha37(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_037",
            name="Alpha#37",
            category="alpha101",
            description="(-1 * rank(correlation(delay(open, 1), delay(volume, 1), 3)))",
            lookback_days=3,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["open", "volume", "symbol"])
        df = data.copy()
        df["delay_open"] = df.groupby("symbol")["open"].shift(1)
        df["delay_vol"] = df.groupby("symbol")["volume"].shift(1)
        df["corr"] = df.groupby("symbol").apply(
            lambda g: g["delay_open"].rolling(3, min_periods=2).corr(g["delay_vol"])
        ).reset_index(level=0, drop=True)
        df["factor"] = -1 * df.groupby("date")["corr"].transform(lambda x: x.rank(pct=True))

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha42(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_042",
            name="Alpha#42",
            category="alpha101",
            description="(-1 * rank(std(high, 10)) * correlation(high, volume, 10))",
            lookback_days=10,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["high", "volume", "symbol"])
        df = data.copy()
        df["std_high"] = df.groupby("symbol")["high"].transform(
            lambda x: x.rolling(10, min_periods=5).std()
        )
        df["corr_hv"] = df.groupby("symbol").apply(
            lambda g: g["high"].rolling(10, min_periods=5).corr(g["volume"])
        ).reset_index(level=0, drop=True)
        df["factor"] = -1 * (
            df.groupby("date")["std_high"].transform(lambda x: x.rank(pct=True))
            * df["corr_hv"]
        )

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha44(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_044",
            name="Alpha#44",
            category="alpha101",
            description="(-1 * correlation(high, rank(volume), 5))",
            lookback_days=5,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["high", "volume", "symbol"])
        df = data.copy()
        df["rank_vol"] = df.groupby("date")["volume"].transform(lambda x: x.rank(pct=True))
        df["corr"] = df.groupby("symbol").apply(
            lambda g: g["high"].rolling(5, min_periods=3).corr(g["rank_vol"])
        ).reset_index(level=0, drop=True)
        df["factor"] = -1 * df["corr"]

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha49(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_049",
            name="Alpha#49",
            category="alpha101",
            description="sum(((high + low) >= (delay(high, 1) + delay(low, 1)) ? 0 : max(abs(high - delay(high, 1)), abs(low - delay(low, 1)))), 12) / (sum(((high + low) >= (delay(high, 1) + delay(low, 1)) ? 0 : max(abs(high - delay(high, 1)), abs(low - delay(low, 1)))), 12) + sum(((high + low) <= (delay(high, 1) + delay(low, 1)) ? 0 : max(abs(high - delay(high, 1)), abs(low - delay(low, 1)))), 12))",
            lookback_days=12,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["high", "low", "symbol"])
        df = data.copy()
        df["delay_high"] = df.groupby("symbol")["high"].shift(1)
        df["delay_low"] = df.groupby("symbol")["low"].shift(1)
        hl_sum = df["high"] + df["low"]
        delay_hl_sum = df["delay_high"] + df["delay_low"]
        abs_dh = (df["high"] - df["delay_high"]).abs()
        abs_dl = (df["low"] - df["delay_low"]).abs()
        max_diff = np.maximum(abs_dh, abs_dl)
        up_move = np.where(hl_sum >= delay_hl_sum, 0, max_diff)
        down_move = np.where(hl_sum <= delay_hl_sum, 0, max_diff)
        df["up_move"] = up_move
        df["down_move"] = down_move
        df["sum_up"] = df.groupby("symbol")["up_move"].transform(
            lambda x: x.rolling(12, min_periods=6).sum()
        )
        df["sum_down"] = df.groupby("symbol")["down_move"].transform(
            lambda x: x.rolling(12, min_periods=6).sum()
        )
        df["factor"] = df["sum_up"] / (df["sum_up"] + df["sum_down"]).replace(0, np.nan)

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha50(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_050",
            name="Alpha#50",
            category="alpha101",
            description="(-1 * ts_max(rank(correlation(rank(volume), rank(vwap), 5)), 3))",
            lookback_days=5,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["close", "high", "low", "volume", "amount", "symbol"])
        df = data.copy()
        df["vwap"] = df["amount"] / df["volume"].replace(0, np.nan)
        df["rank_vol"] = df.groupby("date")["volume"].transform(lambda x: x.rank(pct=True))
        df["rank_vwap"] = df.groupby("date")["vwap"].transform(lambda x: x.rank(pct=True))
        df["corr"] = df.groupby("symbol").apply(
            lambda g: g["rank_vol"].rolling(5, min_periods=3).corr(g["rank_vwap"])
        ).reset_index(level=0, drop=True)
        df["rank_corr"] = df.groupby("date")["corr"].transform(lambda x: x.rank(pct=True))
        df["ts_max_rank"] = df.groupby("symbol")["rank_corr"].transform(
            lambda x: x.rolling(3, min_periods=1).max()
        )
        df["factor"] = -1 * df["ts_max_rank"]

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class Alpha55(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="alpha101_055",
            name="Alpha#55",
            category="alpha101",
            description="(-1 * correlation(rank(close - min(low, 5)), rank(volume), 5))",
            lookback_days=5,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["close", "low", "volume", "symbol"])
        df = data.copy()
        df["min_low_5"] = df.groupby("symbol")["low"].transform(
            lambda x: x.rolling(5, min_periods=3).min()
        )
        df["close_min_low"] = df["close"] - df["min_low_5"]
        df["rank_cml"] = df.groupby("date")["close_min_low"].transform(lambda x: x.rank(pct=True))
        df["rank_vol"] = df.groupby("date")["volume"].transform(lambda x: x.rank(pct=True))
        df["corr"] = df.groupby("symbol").apply(
            lambda g: g["rank_cml"].rolling(5, min_periods=3).corr(g["rank_vol"])
        ).reset_index(level=0, drop=True)
        df["factor"] = -1 * df["corr"]

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
        "alpha101_003": Alpha3,
        "alpha101_004": Alpha4,
        "alpha101_005": Alpha5,
        "alpha101_006": Alpha6,
        "alpha101_007": Alpha7,
        "alpha101_008": Alpha8,
        "alpha101_010": Alpha10,
        "alpha101_012": Alpha12,
        "alpha101_013": Alpha13,
        "alpha101_015": Alpha15,
        "alpha101_016": Alpha16,
        "alpha101_017": Alpha17,
        "alpha101_018": Alpha18,
        "alpha101_019": Alpha19,
        "alpha101_020": Alpha20,
        "alpha101_021": Alpha21,
        "alpha101_026": Alpha26,
        "alpha101_028": Alpha28,
        "alpha101_033": Alpha33,
        "alpha101_034": Alpha34,
        "alpha101_037": Alpha37,
        "alpha101_041": Alpha41,
        "alpha101_042": Alpha42,
        "alpha101_044": Alpha44,
        "alpha101_049": Alpha49,
        "alpha101_050": Alpha50,
        "alpha101_053": Alpha53,
        "alpha101_055": Alpha55,
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
