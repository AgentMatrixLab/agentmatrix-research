from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research_core.factor_engine.base import FactorBase, FactorResult
from research_core.factor_engine.evaluator import FactorEvaluator, ICMetrics
from common.paths import data_path


class BatchFactorEvaluator:
    def __init__(
        self,
        close_matrix: pd.DataFrame,
        n_layers: int = 5,
        ic_method: str = "spearman",
        forward_periods: list[int] | None = None,
        output_dir: str | Path | None = None,
    ):
        self.close_matrix = close_matrix
        self.forward_periods = forward_periods or [1, 5, 10, 20]
        self.evaluator = FactorEvaluator(n_layers=n_layers, ic_method=ic_method)
        self.output_dir = Path(output_dir) if output_dir else data_path("factor_eval_results")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._forward_rets = self.evaluator.compute_forward_returns(
            close_matrix, self.forward_periods
        )

    def evaluate_factor(
        self,
        factor: FactorBase,
        panel_data: pd.DataFrame,
        verbose: bool = True,
    ) -> dict[str, Any]:
        if verbose:
            print(f"[BatchEval] Computing factor: {factor.metadata.factor_id} ({factor.metadata.name})")

        t0 = time.time()
        try:
            result = factor.compute(panel_data)
        except Exception as e:
            if verbose:
                print(f"[BatchEval] Error computing {factor.metadata.factor_id}: {e}")
            return {
                "factor_id": factor.metadata.factor_id,
                "name": factor.metadata.name,
                "category": factor.metadata.category,
                "status": "error",
                "error": str(e),
            }

        factor_matrix = self._result_to_matrix(result, panel_data)
        if factor_matrix.empty:
            return {
                "factor_id": factor.metadata.factor_id,
                "name": factor.metadata.name,
                "category": factor.metadata.category,
                "status": "no_data",
            }

        eval_result = self._evaluate_matrix(factor_matrix, factor.metadata.factor_id)
        eval_result["name"] = factor.metadata.name
        eval_result["category"] = factor.metadata.category
        eval_result["description"] = factor.metadata.description
        eval_result["formula"] = factor.metadata.formula
        eval_result["compute_time_ms"] = round((time.time() - t0) * 1000, 1)
        eval_result["status"] = "ok"

        if verbose:
            ic_1d = eval_result.get("ic_analysis", {}).get("1d", {})
            print(f"  IC(1d)={ic_1d.get('ic_mean', 'N/A'):.4f}, "
                  f"IR={ic_1d.get('ir', 'N/A'):.4f}, "
                  f"IC>0 ratio={ic_1d.get('ic_positive_ratio', 'N/A'):.2%}")

        return eval_result

    def evaluate_batch(
        self,
        factors: list[FactorBase],
        panel_data: pd.DataFrame,
        verbose: bool = True,
    ) -> pd.DataFrame:
        results = []
        for i, factor in enumerate(factors):
            if verbose:
                print(f"\n[{i+1}/{len(factors)}] Evaluating {factor.metadata.factor_id}")
            result = self.evaluate_factor(factor, panel_data, verbose=verbose)
            results.append(result)

        df = pd.DataFrame(results)
        if not df.empty and "ic_analysis" in df.columns:
            df["ic_1d_mean"] = df["ic_analysis"].apply(
                lambda x: x.get("1d", {}).get("ic_mean", np.nan) if isinstance(x, dict) else np.nan
            )
            df["ir_1d"] = df["ic_analysis"].apply(
                lambda x: x.get("1d", {}).get("ir", np.nan) if isinstance(x, dict) else np.nan
            )
            df = df.sort_values("ic_1d_mean", ascending=False, key=abs, na_position="last")

        return df

    def _result_to_matrix(
        self,
        result: FactorResult,
        panel_data: pd.DataFrame,
    ) -> pd.DataFrame:
        if "date" in panel_data.columns and "symbol" in panel_data.columns:
            pivot = panel_data.pivot_table(index="date", columns="symbol", values="close")
            dates = pivot.index
            symbols = pivot.columns
            matrix = pd.DataFrame(np.nan, index=dates, columns=symbols)
            for symbol, val in result.values.items():
                if symbol in matrix.columns:
                    matrix.iloc[-1][symbol] = val
            return matrix
        return pd.DataFrame()

    def _evaluate_matrix(
        self,
        factor_matrix: pd.DataFrame,
        factor_id: str,
    ) -> dict[str, Any]:
        ic_results = {}
        layer_results = {}
        for p in self.forward_periods:
            period_label = f"{p}d"
            fr = self._forward_rets.get(p)
            if fr is None:
                continue
            ic = self.evaluator.compute_ic_metrics(factor_matrix, fr, factor_id, period_label)
            ic_results[period_label] = ic.to_dict()

            if p == self.forward_periods[0]:
                layer = self.evaluator.layer_backtest(factor_matrix, fr, factor_id)
                layer_results = layer.to_dict()

        turnover = self.evaluator.compute_turnover(factor_matrix, factor_id)

        return {
            "factor_id": factor_id,
            "ic_analysis": ic_results,
            "layer_backtest": layer_results,
            "turnover": turnover.to_dict(),
        }

    def save_results(self, results_df: pd.DataFrame, filename: str = "batch_eval_results") -> Path:
        output_path = self.output_dir / f"{filename}.json"
        records = results_df.to_dict(orient="records")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2, default=str)
        return output_path

    def generate_summary(self, results_df: pd.DataFrame) -> dict[str, Any]:
        ok_df = results_df[results_df["status"] == "ok"]
        if ok_df.empty:
            return {"total": len(results_df), "valid": 0}

        total = len(ok_df)
        ic_means = ok_df["ic_1d_mean"].dropna()
        ir_values = ok_df["ir_1d"].dropna()

        significant = ok_df[ok_df["ic_1d_mean"].abs() > 0.03]
        strong = ok_df[ok_df["ic_1d_mean"].abs() > 0.05]

        return {
            "total_evaluated": len(results_df),
            "valid_factors": total,
            "significant_ic_count": len(significant),
            "strong_ic_count": len(strong),
            "avg_ic_1d": float(ic_means.mean()) if len(ic_means) > 0 else 0.0,
            "avg_ir_1d": float(ir_values.mean()) if len(ir_values) > 0 else 0.0,
            "best_factor": ok_df.iloc[0]["factor_id"] if not ok_df.empty else None,
            "best_ic": float(ic_means.max()) if len(ic_means) > 0 else 0.0,
            "by_category": ok_df.groupby("category")["ic_1d_mean"].agg(["mean", "count"]).to_dict()
            if "category" in ok_df.columns else {},
        }
