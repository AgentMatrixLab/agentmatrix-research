from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass(slots=True)
class ICMetrics:
    factor_id: str
    period: str
    ic_mean: float
    ic_std: float
    ir: float
    ic_positive_ratio: float
    ic_t_stat: float
    ic_series: pd.Series = field(default_factory=pd.Series, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "factor_id": self.factor_id,
            "period": self.period,
            "ic_mean": round(self.ic_mean, 4),
            "ic_std": round(self.ic_std, 4),
            "ir": round(self.ir, 4),
            "ic_positive_ratio": round(self.ic_positive_ratio, 4),
            "ic_t_stat": round(self.ic_t_stat, 4),
        }


@dataclass(slots=True)
class LayerTestResult:
    factor_id: str
    n_layers: int
    layer_returns: dict[str, float]
    long_short_return: float
    monotonicity_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "factor_id": self.factor_id,
            "n_layers": self.n_layers,
            "layer_returns": {k: round(v, 4) for k, v in self.layer_returns.items()},
            "long_short_return": round(self.long_short_return, 4),
            "monotonicity_score": round(self.monotonicity_score, 4),
        }


@dataclass(slots=True)
class TurnoverMetrics:
    factor_id: str
    avg_turnover: float
    autocorrelation: float
    half_life: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "factor_id": self.factor_id,
            "avg_turnover": round(self.avg_turnover, 4),
            "autocorrelation": round(self.autocorrelation, 4),
            "half_life": round(self.half_life, 2),
        }


class FactorEvaluator:
    def __init__(self, n_layers: int = 5, ic_method: str = "spearman"):
        self.n_layers = n_layers
        self.ic_method = ic_method

    def compute_ic_series(
        self,
        factor_values: pd.DataFrame,
        forward_returns: pd.DataFrame,
    ) -> pd.Series:
        if factor_values.shape != forward_returns.shape:
            min_cols = factor_values.columns.intersection(forward_returns.columns)
            factor_values = factor_values[min_cols]
            forward_returns = forward_returns[min_cols]

        common_idx = factor_values.index.intersection(forward_returns.index)
        factor_values = factor_values.loc[common_idx]
        forward_returns = forward_returns.loc[common_idx]

        ic_list = []
        dates = []
        for date in common_idx:
            fv = factor_values.loc[date].dropna()
            fr = forward_returns.loc[date].dropna()
            common_stocks = fv.index.intersection(fr.index)
            if len(common_stocks) < 10:
                continue
            fv = fv[common_stocks]
            fr = fr[common_stocks]

            if self.ic_method == "spearman":
                ic = fv.corr(fr, method="spearman")
            elif self.ic_method == "pearson":
                ic = fv.corr(fr, method="pearson")
            else:
                ic = fv.corr(fr, method="spearman")

            if not np.isnan(ic):
                ic_list.append(ic)
                dates.append(date)

        return pd.Series(ic_list, index=dates, name="IC")

    def compute_ic_metrics(
        self,
        factor_values: pd.DataFrame,
        forward_returns: pd.DataFrame,
        factor_id: str = "",
        period: str = "1d",
    ) -> ICMetrics:
        ic_series = self.compute_ic_series(factor_values, forward_returns)
        if ic_series.empty:
            return ICMetrics(
                factor_id=factor_id, period=period,
                ic_mean=0.0, ic_std=0.0, ir=0.0,
                ic_positive_ratio=0.0, ic_t_stat=0.0,
                ic_series=ic_series,
            )

        ic_mean = ic_series.mean()
        ic_std = ic_series.std()
        ir = ic_mean / ic_std if ic_std > 0 else 0.0
        ic_pos = (ic_series > 0).sum() / len(ic_series)
        n = len(ic_series)
        ic_t = ic_mean / (ic_std / np.sqrt(n)) if ic_std > 0 and n > 0 else 0.0

        return ICMetrics(
            factor_id=factor_id,
            period=period,
            ic_mean=ic_mean,
            ic_std=ic_std,
            ir=ir,
            ic_positive_ratio=ic_pos,
            ic_t_stat=ic_t,
            ic_series=ic_series,
        )

    def compute_forward_returns(
        self,
        close_matrix: pd.DataFrame,
        periods: list[int] | None = None,
    ) -> dict[int, pd.DataFrame]:
        if periods is None:
            periods = [1, 5, 10, 20]
        result = {}
        for p in periods:
            result[p] = close_matrix.pct_change(p).shift(-p)
        return result

    def layer_backtest(
        self,
        factor_values: pd.DataFrame,
        forward_returns: pd.DataFrame,
        factor_id: str = "",
        n_layers: int | None = None,
    ) -> LayerTestResult:
        n = n_layers or self.n_layers
        layer_returns = {}
        common_idx = factor_values.index.intersection(forward_returns.index)

        all_layer_rets = {f"L{i+1}": [] for i in range(n)}

        for date in common_idx:
            fv = factor_values.loc[date].dropna()
            fr = forward_returns.loc[date].dropna()
            common = fv.index.intersection(fr.index)
            if len(common) < n * 2:
                continue
            fv = fv[common].sort_values()
            fr = fr[common]

            layer_size = len(fv) // n
            for i in range(n):
                start = i * layer_size
                end = start + layer_size if i < n - 1 else len(fv)
                layer_stocks = fv.index[start:end]
                avg_ret = fr[layer_stocks].mean()
                if not np.isnan(avg_ret):
                    all_layer_rets[f"L{i+1}"].append(avg_ret)

        for layer_name, rets in all_layer_rets.items():
            layer_returns[layer_name] = np.mean(rets) if rets else 0.0

        long_ret = layer_returns.get(f"L{n}", 0.0)
        short_ret = layer_returns.get("L1", 0.0)
        long_short = long_ret - short_ret

        rets_list = list(layer_returns.values())
        if len(rets_list) >= 2:
            rank_corr = pd.Series(rets_list).corr(
                pd.Series(range(1, len(rets_list) + 1)), method="spearman"
            )
            monotonicity = abs(rank_corr)
        else:
            monotonicity = 0.0

        return LayerTestResult(
            factor_id=factor_id,
            n_layers=n,
            layer_returns=layer_returns,
            long_short_return=long_short,
            monotonicity_score=monotonicity,
        )

    def compute_turnover(
        self,
        factor_values: pd.DataFrame,
        factor_id: str = "",
    ) -> TurnoverMetrics:
        ranked = factor_values.rank(axis=1, pct=True)
        turnover_series = []
        dates = ranked.index.tolist()

        for i in range(1, len(dates)):
            prev = ranked.loc[dates[i - 1]].dropna()
            curr = ranked.loc[dates[i]].dropna()
            common = prev.index.intersection(curr.index)
            if len(common) < 5:
                continue
            diff = (curr[common] - prev[common]).abs().sum() / len(common)
            turnover_series.append(diff)

        if not turnover_series:
            return TurnoverMetrics(factor_id=factor_id, avg_turnover=0.0, autocorrelation=0.0, half_life=0.0)

        avg_to = np.mean(turnover_series)

        ts = pd.Series(turnover_series)
        autocorr = ts.autocorr(lag=1) if len(ts) > 1 else 0.0

        factor_mean = factor_values.mean(axis=1).dropna()
        if len(factor_mean) > 1:
            ac = factor_mean.autocorr(lag=1)
            if ac is not None and 0 < ac < 1:
                half_life = -np.log(2) / np.log(ac)
            else:
                half_life = 0.0
        else:
            half_life = 0.0

        return TurnoverMetrics(
            factor_id=factor_id,
            avg_turnover=avg_to,
            autocorrelation=autocorr if not np.isnan(autocorr) else 0.0,
            half_life=half_life,
        )

    def full_evaluation(
        self,
        factor_values: pd.DataFrame,
        close_matrix: pd.DataFrame,
        factor_id: str = "",
        forward_periods: list[int] | None = None,
    ) -> dict[str, Any]:
        if forward_periods is None:
            forward_periods = [1, 5, 10, 20]

        forward_rets = self.compute_forward_returns(close_matrix, forward_periods)

        ic_results = {}
        layer_results = {}
        for p in forward_periods:
            period_label = f"{p}d"
            fr = forward_rets[p]
            ic = self.compute_ic_metrics(factor_values, fr, factor_id, period_label)
            ic_results[period_label] = ic.to_dict()

            if p == forward_periods[0]:
                layer = self.layer_backtest(factor_values, fr, factor_id)
                layer_results = layer.to_dict()

        turnover = self.compute_turnover(factor_values, factor_id)

        return {
            "factor_id": factor_id,
            "ic_analysis": ic_results,
            "layer_backtest": layer_results,
            "turnover": turnover.to_dict(),
        }
