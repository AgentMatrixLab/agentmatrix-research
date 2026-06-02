from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from common.paths import runtime_path
from research_core.qlib_lab.runtime import QlibWorkspaceConfig, init_qlib_workspace


@dataclass(slots=True)
class Alpha158WorkflowConfig:
    market: str = "csi300"
    benchmark: str = "SH000300"
    train_start: str = "2008-01-01"
    train_end: str = "2014-12-31"
    valid_start: str = "2015-01-01"
    valid_end: str = "2016-12-31"
    test_start: str = "2017-01-01"
    test_end: str = "2020-08-01"
    account: float = 100000000.0
    topk: int = 50
    n_drop: int = 5
    experiment_name: str = "alpha158_starter"

    @property
    def data_handler_config(self) -> dict[str, Any]:
        return {
            "start_time": self.train_start,
            "end_time": self.test_end,
            "fit_start_time": self.train_start,
            "fit_end_time": self.train_end,
            "instruments": self.market,
        }

    @property
    def segments(self) -> dict[str, tuple[str, str]]:
        return {
            "train": (self.train_start, self.train_end),
            "valid": (self.valid_start, self.valid_end),
            "test": (self.test_start, self.test_end),
        }


def build_alpha158_task(config: Alpha158WorkflowConfig) -> dict[str, Any]:
    return {
        "model": {
            "class": "LGBModel",
            "module_path": "qlib.contrib.model.gbdt",
            "kwargs": {
                "loss": "mse",
                "colsample_bytree": 0.8879,
                "learning_rate": 0.0421,
                "subsample": 0.8789,
                "lambda_l1": 205.6999,
                "lambda_l2": 580.9768,
                "max_depth": 8,
                "num_leaves": 210,
                "num_threads": 20,
            },
        },
        "dataset": {
            "class": "DatasetH",
            "module_path": "qlib.data.dataset",
            "kwargs": {
                "handler": {
                    "class": "Alpha158",
                    "module_path": "qlib.contrib.data.handler",
                    "kwargs": config.data_handler_config,
                },
                "segments": config.segments,
            },
        },
    }


def build_port_analysis_config(config: Alpha158WorkflowConfig) -> dict[str, Any]:
    return {
        "executor": {
            "class": "SimulatorExecutor",
            "module_path": "qlib.backtest.executor",
            "kwargs": {
                "time_per_step": "day",
                "generate_portfolio_metrics": True,
            },
        },
        "strategy": {
            "class": "TopkDropoutStrategy",
            "module_path": "qlib.contrib.strategy.signal_strategy",
            "kwargs": {
                "signal": "<PRED>",
                "topk": config.topk,
                "n_drop": config.n_drop,
            },
        },
        "backtest": {
            "start_time": config.test_start,
            "end_time": config.test_end,
            "account": config.account,
            "benchmark": config.benchmark,
            "exchange_kwargs": {
                "freq": "day",
                "limit_threshold": 0.095,
                "deal_price": "close",
                "open_cost": 0.0005,
                "close_cost": 0.0015,
                "min_cost": 5,
            },
        },
    }


def export_alpha158_template(
    config: Alpha158WorkflowConfig | None = None,
    *,
    output_path: str | None = None,
) -> str:
    config = config or Alpha158WorkflowConfig()
    payload = {
        "workflow": asdict(config),
        "task": build_alpha158_task(config),
        "port_analysis_config": build_port_analysis_config(config),
    }
    target = Path(output_path) if output_path else runtime_path("qlib", "alpha158_template.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(target)


def run_alpha158_workflow(
    config: Alpha158WorkflowConfig | None = None,
    *,
    workspace: QlibWorkspaceConfig | None = None,
) -> dict[str, Any]:
    config = config or Alpha158WorkflowConfig()
    workspace = workspace or QlibWorkspaceConfig.from_env()
    init_qlib_workspace(workspace, require_package=True, require_data=True)

    try:
        import lightgbm  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "lightgbm is required for the Alpha158 starter workflow. Install it with `pip install lightgbm`."
        ) from exc

    from qlib.utils import flatten_dict, init_instance_by_config
    from qlib.workflow import R
    from qlib.workflow.record_temp import PortAnaRecord, SigAnaRecord, SignalRecord

    task = build_alpha158_task(config)
    port_analysis_config = build_port_analysis_config(config)
    model = init_instance_by_config(task["model"])
    dataset = init_instance_by_config(task["dataset"])
    example_df = dataset.prepare("train")

    artifact_dir = runtime_path("qlib", "workflow_runs", config.experiment_name)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    config_path = artifact_dir / "alpha158_workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "workflow": asdict(config),
                "task": task,
                "port_analysis_config": port_analysis_config,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    with R.start(experiment_name=config.experiment_name):
        R.log_params(**flatten_dict(task))
        model.fit(dataset)
        R.save_objects(**{"params.pkl": model})
        recorder = R.get_recorder()
        SignalRecord(model, dataset, recorder).generate()
        SigAnaRecord(recorder).generate()
        PortAnaRecord(recorder, port_analysis_config, "day").generate()

        return {
            "experiment_name": config.experiment_name,
            "workflow_config": asdict(config),
            "provider_uri": workspace.resolved_provider_uri(),
            "example_rows": int(len(example_df)),
            "artifact_config": str(config_path),
            "recorder_id": getattr(recorder, "id", ""),
        }
