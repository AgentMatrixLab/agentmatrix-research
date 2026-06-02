from __future__ import annotations

import numpy as np
import pandas as pd

from research_core.factor_engine.base import FactorBase, FactorMetadata, FactorResult


class SizeFactor(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="barra_size",
            name="Barra Size",
            category="barra",
            description="Log of total market capitalization. Captures the size effect (small-cap premium).",
            formula="log(total_mv)",
            lookback_days=0,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["symbol"])
        mv_col = kwargs.get("market_cap_col", "total_mv")
        if mv_col not in data.columns:
            raise ValueError(f"Column '{mv_col}' not found. Provide market cap data or specify market_cap_col.")
        df = data.copy()
        df["factor"] = np.log(df[mv_col].replace(0, np.nan))

        latest_date = df["date"].max() if "date" in df.columns else "N/A"
        values = df.set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date),
            values=values,
        )


class MomentumFactor(FactorBase):
    def __init__(self, lookback: int = 252, skip_days: int = 21):
        meta = FactorMetadata(
            factor_id="barra_momentum",
            name="Barra Momentum",
            category="barra",
            description=f"Cumulative return over past {lookback} trading days, skipping the most recent {skip_days} days.",
            formula=f"close/delay(close,{skip_days}) - 1 over past {lookback} days",
            lookback_days=lookback,
            parameters={"lookback": lookback, "skip_days": skip_days},
        )
        self.lookback = lookback
        self.skip_days = skip_days
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["close", "symbol"])
        df = data.copy()
        max_days = df.groupby("symbol")["close"].transform("count").max()
        effective_lookback = min(self.lookback, max(max_days - self.skip_days - 1, 10))
        skip = min(self.skip_days, effective_lookback // 4)
        if effective_lookback + skip >= max_days:
            effective_lookback = max(max_days - skip - 1, 10)
        df["mom"] = df.groupby("symbol")["close"].transform(
            lambda x: x.shift(skip) / x.shift(effective_lookback + skip) - 1
        )
        df["factor"] = df["mom"]

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class VolatilityFactor(FactorBase):
    def __init__(self, lookback: int = 20):
        meta = FactorMetadata(
            factor_id="barra_volatility",
            name="Barra Volatility",
            category="barra",
            description=f"Standard deviation of daily returns over {lookback} trading days.",
            formula=f"std(daily_return, {lookback})",
            lookback_days=lookback,
            parameters={"lookback": lookback},
        )
        self.lookback = lookback
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["close", "symbol"])
        df = data.copy()
        df["daily_ret"] = df.groupby("symbol")["close"].pct_change()
        df["factor"] = df.groupby("symbol")["daily_ret"].transform(
            lambda x: x.rolling(self.lookback, min_periods=self.lookback // 2).std()
        )

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class LiquidityFactor(FactorBase):
    def __init__(self, lookback: int = 20):
        meta = FactorMetadata(
            factor_id="barra_liquidity",
            name="Barra Liquidity",
            category="barra",
            description=f"Average daily turnover rate over {lookback} trading days.",
            formula=f"mean(turnover, {lookback})",
            lookback_days=lookback,
            parameters={"lookback": lookback},
        )
        self.lookback = lookback
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["turnover", "symbol"])
        df = data.copy()
        df["factor"] = df.groupby("symbol")["turnover"].transform(
            lambda x: x.rolling(self.lookback, min_periods=self.lookback // 2).mean()
        )

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class ValueFactor(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="barra_value",
            name="Barra Value (BP)",
            category="barra",
            description="Book-to-Price ratio. Captures the value premium. Uses PB if available, otherwise (total_assets - total_liab) / total_mv.",
            formula="1/PB or (total_assets - total_liab) / total_mv",
            lookback_days=0,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["symbol"])
        df = data.copy()
        pb_col = kwargs.get("pb_col", "pb")
        if pb_col in df.columns:
            df["factor"] = 1.0 / df[pb_col].replace({0: np.nan})
        elif "total_assets" in df.columns and "total_liab" in df.columns and "total_mv" in df.columns:
            book_value = df["total_assets"] - df["total_liab"]
            df["factor"] = book_value / df["total_mv"].replace(0, np.nan)
        else:
            raise ValueError(
                f"Column '{pb_col}' not found. Provide PB data, or (total_assets, total_liab, total_mv) columns."
            )

        latest_date = df["date"].max() if "date" in df.columns else "N/A"
        values = df.set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date),
            values=values,
        )


class EarningsYieldFactor(FactorBase):
    def __init__(self):
        meta = FactorMetadata(
            factor_id="barra_earnings_yield",
            name="Barra Earnings Yield (EP)",
            category="barra",
            description="Earnings-to-Price ratio. Uses PE_TTM if available, otherwise net_profit / total_mv.",
            formula="1/PE_TTM or net_profit / total_mv",
            lookback_days=0,
        )
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["symbol"])
        df = data.copy()
        pe_col = kwargs.get("pe_col", "pe_ttm")
        if pe_col in df.columns:
            df["factor"] = 1.0 / df[pe_col].replace({0: np.nan})
        elif "net_profit" in df.columns and "total_mv" in df.columns:
            df["factor"] = df["net_profit"] / df["total_mv"].replace(0, np.nan)
        else:
            raise ValueError(
                f"Column '{pe_col}' not found. Provide PE data, or (net_profit, total_mv) columns."
            )

        latest_date = df["date"].max() if "date" in df.columns else "N/A"
        values = df.set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date),
            values=values,
        )


class BetaFactor(FactorBase):
    def __init__(self, lookback: int = 252):
        meta = FactorMetadata(
            factor_id="barra_beta",
            name="Barra Beta",
            category="barra",
            description=f"Market beta estimated from {lookback}-day regression of stock returns on market returns.",
            formula=f"beta(stock_ret, market_ret, {lookback})",
            lookback_days=lookback,
            parameters={"lookback": lookback},
        )
        self.lookback = lookback
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["close", "symbol"])
        df = data.copy()
        df["stock_ret"] = df.groupby("symbol")["close"].pct_change()

        market_ret = kwargs.get("market_returns")
        if market_ret is None:
            market_close = df.groupby("date")["close"].mean()
            market_ret = market_close.pct_change()
            market_ret.name = "market_ret"

        df = df.merge(market_ret.reset_index().rename(columns={"close": "market_ret"}),
                      on="date", how="left", suffixes=("", "_mkt"))
        if "market_ret" not in df.columns:
            if "market_ret_mkt" in df.columns:
                df["market_ret"] = df["market_ret_mkt"]

        def rolling_beta(g):
            cov = g["stock_ret"].rolling(self.lookback, min_periods=60).cov(g["market_ret"])
            var = g["market_ret"].rolling(self.lookback, min_periods=60).var()
            return cov / var.replace(0, np.nan)

        df["factor"] = df.groupby("symbol").apply(rolling_beta).reset_index(level=0, drop=True)

        latest_date = df["date"].max()
        values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date.date()),
            values=values,
        )


class BarraFactorRegistry:
    _factors: dict[str, type[FactorBase]] = {
        "barra_size": SizeFactor,
        "barra_momentum": MomentumFactor,
        "barra_volatility": VolatilityFactor,
        "barra_liquidity": LiquidityFactor,
        "barra_value": ValueFactor,
        "barra_earnings_yield": EarningsYieldFactor,
        "barra_beta": BetaFactor,
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
