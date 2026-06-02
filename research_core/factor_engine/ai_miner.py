from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research_core.factor_engine.base import FactorBase, FactorMetadata, FactorResult
from research_core.factor_engine.evaluator import FactorEvaluator
from common.paths import data_path


@dataclass(slots=True)
class MinedFactor:
    factor_id: str
    expression: str
    category: str
    ic_1d: float
    ir_1d: float
    ic_positive_ratio: float
    layer_long_short: float
    source: str
    generation: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "factor_id": self.factor_id,
            "expression": self.expression,
            "category": self.category,
            "ic_1d": round(self.ic_1d, 4),
            "ir_1d": round(self.ir_1d, 4),
            "ic_positive_ratio": round(self.ic_positive_ratio, 4),
            "layer_long_short": round(self.layer_long_short, 4),
            "source": self.source,
            "generation": self.generation,
        }


class ExpressionFactor(FactorBase):
    def __init__(
        self,
        factor_id: str,
        name: str,
        expression: str,
        category: str = "ai_mined",
    ):
        meta = FactorMetadata(
            factor_id=factor_id,
            name=name,
            category=category,
            description=f"AI-mined factor: {expression}",
            formula=expression,
        )
        self.expression = expression
        super().__init__(meta)

    def compute(self, data: pd.DataFrame, **kwargs) -> FactorResult:
        self.validate_input(data, ["close", "symbol"])
        df = data.copy()

        try:
            values = self._safe_eval(df)
        except Exception as e:
            latest_date = df["date"].max() if "date" in df.columns else "N/A"
            return FactorResult(
                factor_id=self.metadata.factor_id,
                date=str(latest_date),
                values=pd.Series(dtype=float, name="factor"),
                metadata={"error": str(e)},
            )

        latest_date = df["date"].max() if "date" in df.columns else "N/A"
        if "symbol" in df.columns:
            result_values = df[df["date"] == latest_date].set_index("symbol")["factor"]
        else:
            result_values = values

        return FactorResult(
            factor_id=self.metadata.factor_id,
            date=str(latest_date),
            values=result_values,
        )

    def _safe_eval(self, df: pd.DataFrame) -> pd.Series:
        namespace = {
            "np": np,
            "pd": pd,
            "abs": np.abs,
            "log": np.log,
            "sign": np.sign,
            "sqrt": np.sqrt,
            "rank": lambda x: x.rank(pct=True) if isinstance(x, pd.Series) else x,
            "ts_mean": lambda x, w: x.rolling(w, min_periods=1).mean(),
            "ts_std": lambda x, w: x.rolling(w, min_periods=1).std(),
            "ts_sum": lambda x, w: x.rolling(w, min_periods=1).sum(),
            "ts_max": lambda x, w: x.rolling(w, min_periods=1).max(),
            "ts_min": lambda x, w: x.rolling(w, min_periods=1).min(),
            "ts_delta": lambda x, d: x.diff(d),
            "ts_delay": lambda x, d: x.shift(d),
            "ts_rank": lambda x, w: x.rolling(w, min_periods=1).apply(
                lambda v: pd.Series(v).rank(pct=True).iloc[-1], raw=False
            ),
            "ts_corr": lambda x, y, w: x.rolling(w, min_periods=2).corr(y),
            "decay_linear": lambda x, w: x.rolling(w, min_periods=1).apply(
                lambda v: (v * np.arange(1, len(v) + 1)).sum() / np.arange(1, len(v) + 1).sum(),
                raw=True,
            ),
            "close": df["close"],
            "open": df.get("open", df["close"]),
            "high": df.get("high", df["close"]),
            "low": df.get("low", df["close"]),
            "volume": df.get("volume", pd.Series(1.0, index=df.index)),
            "amount": df.get("amount", pd.Series(1.0, index=df.index)),
            "returns": df["close"].pct_change(),
        }

        for col in df.columns:
            if col not in namespace and col not in ("date", "symbol"):
                namespace[col] = df[col]

        result = eval(self.expression, {"__builtins__": {}}, namespace)
        df["factor"] = result
        return result


class AIFactorMiner:
    TEMPLATE_EXPRESSIONS = [
        "rank(ts_delta(close, {d1}))",
        "rank(ts_mean(returns, {d1}))",
        "-1 * rank(ts_std(returns, {d1}))",
        "rank(ts_corr(close, volume, {d1}))",
        "rank(decay_linear(returns, {d1}))",
        "rank(ts_delta(log(close), {d1}))",
        "-1 * rank(ts_std(close/ts_mean(close, {d1}) - 1, {d2}))",
        "rank(ts_mean(abs(returns), {d1}))",
        "rank(ts_corr(rank(close), rank(volume), {d1}))",
        "rank(ts_delta(ts_rank(close, {d1}), {d2}))",
        "rank((close - ts_min(low, {d1})) / (ts_max(high, {d1}) - ts_min(low, {d1})))",
        "-1 * rank(ts_corr(open, close, {d1}))",
        "rank(ts_sum(sign(returns) * volume, {d1}))",
        "rank(ts_mean(close, {d1}) / ts_mean(close, {d2}) - 1)",
        "rank(ts_corr(returns, ts_delay(returns, {d1}), {d2}))",
    ]

    def __init__(
        self,
        close_matrix: pd.DataFrame,
        panel_data: pd.DataFrame,
        output_dir: str | Path | None = None,
        ic_threshold: float = 0.03,
        ir_threshold: float = 0.3,
    ):
        self.close_matrix = close_matrix
        self.panel_data = panel_data
        self.output_dir = Path(output_dir) if output_dir else data_path("ai_mined_factors")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ic_threshold = ic_threshold
        self.ir_threshold = ir_threshold
        self.evaluator = FactorEvaluator()
        self._forward_rets = self.evaluator.compute_forward_returns(close_matrix, [1, 5])
        self._mined_factors: list[MinedFactor] = []
        self._generation = 0

    def generate_candidates(self, n_candidates: int = 50) -> list[str]:
        candidates = []
        param_ranges = {
            "d1": [3, 5, 10, 15, 20, 30, 60],
            "d2": [3, 5, 10, 20],
        }

        for template in self.TEMPLATE_EXPRESSIONS:
            params_needed = re.findall(r"\{(\w+)\}", template)
            if not params_needed:
                candidates.append(template)
                continue

            from itertools import product as iter_product
            param_combos = list(iter_product(
                *[param_ranges.get(p, [5]) for p in params_needed]
            ))

            for combo in param_combos[:5]:
                expr = template.format(**dict(zip(params_needed, combo)))
                candidates.append(expr)

        np.random.shuffle(candidates)
        return candidates[:n_candidates]

    def evaluate_expression(self, expression: str) -> MinedFactor | None:
        factor_id = f"ai_mined_{abs(hash(expression)) % 100000:05d}"
        try:
            factor = ExpressionFactor(
                factor_id=factor_id,
                name=f"AI-Mined-{factor_id}",
                expression=expression,
            )
            result = factor.compute(self.panel_data)
            if result.values.empty or result.coverage_ratio < 0.3:
                return None

            factor_matrix = self._result_to_matrix(result)
            if factor_matrix.empty:
                return None

            fr_1d = self._forward_rets.get(1)
            if fr_1d is None:
                return None

            ic_metrics = self.evaluator.compute_ic_metrics(
                factor_matrix, fr_1d, factor_id, "1d"
            )

            layer = self.evaluator.layer_backtest(factor_matrix, fr_1d, factor_id)

            return MinedFactor(
                factor_id=factor_id,
                expression=expression,
                category="ai_mined",
                ic_1d=ic_metrics.ic_mean,
                ir_1d=ic_metrics.ir,
                ic_positive_ratio=ic_metrics.ic_positive_ratio,
                layer_long_short=layer.long_short_return,
                source="template_search",
                generation=self._generation,
            )

        except Exception:
            return None

    def mine(
        self,
        n_candidates: int = 50,
        verbose: bool = True,
    ) -> list[MinedFactor]:
        self._generation += 1
        candidates = self.generate_candidates(n_candidates)

        if verbose:
            print(f"[AIMiner] Generation {self._generation}: Evaluating {len(candidates)} candidates...")

        valid_factors = []
        for i, expr in enumerate(candidates):
            mined = self.evaluate_expression(expr)
            if mined is None:
                continue

            if abs(mined.ic_1d) >= self.ic_threshold and abs(mined.ir_1d) >= self.ir_threshold:
                valid_factors.append(mined)
                if verbose:
                    print(f"  ✅ [{i+1}/{len(candidates)}] IC={mined.ic_1d:.4f} IR={mined.ir_1d:.4f} | {expr[:60]}")
            elif verbose and (i + 1) % 10 == 0:
                print(f"  [{i+1}/{len(candidates)}] Processed...")

        self._mined_factors.extend(valid_factors)

        if verbose:
            print(f"[AIMiner] Generation {self._generation} complete: "
                  f"{len(valid_factors)}/{len(candidates)} factors passed threshold")

        return valid_factors

    def get_top_factors(self, top_n: int = 10, metric: str = "ic_1d") -> list[MinedFactor]:
        sorted_factors = sorted(
            self._mined_factors,
            key=lambda f: abs(getattr(f, metric)),
            reverse=True,
        )
        return sorted_factors[:top_n]

    def save_results(self, filename: str | None = None) -> Path:
        if filename is None:
            filename = f"ai_mined_gen{self._generation}.json"
        output_path = self.output_dir / filename
        data = [f.to_dict() for f in self._mined_factors]
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return output_path

    def _result_to_matrix(self, result: FactorResult) -> pd.DataFrame:
        if "date" in self.panel_data.columns and "symbol" in self.panel_data.columns:
            pivot = self.panel_data.pivot_table(index="date", columns="symbol", values="close")
            dates = pivot.index
            symbols = pivot.columns
            matrix = pd.DataFrame(np.nan, index=dates, columns=symbols)
            for symbol, val in result.values.items():
                if symbol in matrix.columns:
                    matrix.iloc[-1][symbol] = val
            return matrix
        return pd.DataFrame()
