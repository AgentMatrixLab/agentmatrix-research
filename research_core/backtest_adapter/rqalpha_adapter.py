from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from contracts.attribution import AttributionReport, AttributionSummary
from contracts.backtest import BacktestRequest, BacktestResult, PerformanceMetrics
from research_core.backtest_adapter.base import BacktestAdapter
from research_core.backtest_adapter.rqalpha_pickle_parser import RQAlphaPickleParser


class RQAlphaBacktestAdapter(BacktestAdapter):
    engine_name = "rqalpha"

    def read_source(self, module_path: str) -> str:
        target = Path(module_path)
        if not target.exists():
            raise FileNotFoundError(f"Strategy module not found: {module_path}")
        return target.read_text(encoding="utf-8-sig")

    def parse_tree(self, module_path: str) -> ast.Module:
        return ast.parse(self.read_source(module_path))

    def detect_hooks(self, module_path: str) -> list[str]:
        tree = self.parse_tree(module_path)
        hooks: list[str] = []
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                if node.name in {"init", "before_trading", "handle_bar", "handle_tick", "after_trading"}:
                    hooks.append(node.name)
        return hooks

    def extract_user_config(self, module_path: str) -> dict[str, Any]:
        tree = self.parse_tree(module_path)
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {"__config__", "config"}:
                    try:
                        parsed = ast.literal_eval(node.value)
                    except Exception:
                        return {}
                    return parsed if isinstance(parsed, dict) else {}
        return {}

    def build_output_paths(self, request: BacktestRequest) -> dict[str, str]:
        explicit_pickle = request.strategy_params.get("result_pickle")
        explicit_report = request.strategy_params.get("report_save_path")
        module_dir = Path(request.module_path).resolve().parent
        artifact_dir = module_dir / "artifacts" / "rqalpha" / request.run_id
        result_pickle = Path(explicit_pickle) if explicit_pickle else artifact_dir / "result.pkl"
        report_dir = Path(explicit_report) if explicit_report else artifact_dir / "report"
        return {
            "artifact_dir": str(artifact_dir),
            "result_pickle": str(result_pickle),
            "report_save_path": str(report_dir),
        }

    def build_rqalpha_config(self, request: BacktestRequest, user_config: dict[str, Any]) -> dict[str, Any]:
        paths = self.build_output_paths(request)
        base = dict(user_config.get("base", {}))
        base.update(
            {
                "strategy_file": request.module_path,
                "start_date": request.start_time,
                "end_date": request.end_time,
                "benchmark": request.benchmark,
                "accounts": {"stock": request.initial_cash},
            }
        )

        if "frequency" not in base:
            base["frequency"] = request.strategy_params.get("frequency", "1d")

        mod = dict(user_config.get("mod", {}))
        sys_analyser = dict(mod.get("sys_analyser", {}))
        sys_analyser.update(
            {
                "enabled": True,
                "record": True,
                "output_file": paths["result_pickle"],
                "report_save_path": paths["report_save_path"],
                "plot": False,
            }
        )
        mod["sys_analyser"] = sys_analyser

        extra = dict(user_config.get("extra", {}))
        if request.strategy_params:
            extra.setdefault("context_vars", {}).update(request.strategy_params)

        return {
            "base": base,
            "extra": extra,
            "mod": mod,
        }

    def build_execution_plan(self, request: BacktestRequest) -> dict[str, Any]:
        self.validate(request)
        hooks = self.detect_hooks(request.module_path)
        user_config = self.extract_user_config(request.module_path)
        rqalpha_config = self.build_rqalpha_config(request, user_config)
        paths = self.build_output_paths(request)
        return {
            "engine": self.engine_name,
            "module_path": request.module_path,
            "hooks": hooks,
            "user_config": user_config,
            "rqalpha_config": rqalpha_config,
            "artifact_paths": paths,
        }

    def run(self, request: BacktestRequest) -> BacktestResult:
        plan = self.build_execution_plan(request)
        result_pickle = Path(plan["artifact_paths"]["result_pickle"])
        if result_pickle.exists():
            parser = RQAlphaPickleParser(result_pickle)
            parsed = parser.parse(
                run_id=request.run_id,
                strategy_id=request.strategy_id,
                strategy_version=request.strategy_version,
                benchmark=request.benchmark,
            )
            parsed.diagnostics["execution_plan"] = plan
            return parsed

        metrics = PerformanceMetrics(
            total_return=0.0,
            annualized_return=0.0,
            benchmark_return=0.0,
            excess_return=0.0,
            max_drawdown=0.0,
            sharpe=0.0,
            volatility=0.0,
        )
        attribution = AttributionReport(
            summary=AttributionSummary(total_return=0.0),
            notes=["RQAlpha adapter scaffold created. Add runtime invocation after environment and data bundle are wired."],
        )
        return BacktestResult(
            run_id=request.run_id,
            status="planned",
            engine=self.engine_name,
            strategy_id=request.strategy_id,
            strategy_version=request.strategy_version,
            benchmark=request.benchmark,
            metrics=metrics,
            attribution=attribution,
            diagnostics={"execution_plan": plan},
            artifacts=plan["artifact_paths"],
        )
