from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path

from common.paths import data_path
from research_core.qlib_lab.auto_factor_miner import AIFactorMiner
from research_core.qlib_lab.backtest import run_factor_backtest
from research_core.qlib_lab.factor_miner import QlibFactorLab
from research_core.qlib_lab.intern_starter import generate_starter_pack
from research_core.qlib_lab.runtime import QlibWorkspaceConfig, init_qlib_workspace, qlib_data_download_hint
from research_core.qlib_lab.workflow import Alpha158WorkflowConfig, export_alpha158_template, run_alpha158_workflow


def _json_default(value):
    if is_dataclass(value):
        return asdict(value)
    return str(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentMatrix Qlib research CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-data", help="Initialize qlib workspace and print data download hint")
    init_parser.add_argument("--provider-uri", default=str(data_path("qlib", "cn_data")))
    init_parser.add_argument("--region", default="cn")

    mine_parser = subparsers.add_parser("mine-factor", help="Register and evaluate one qlib factor expression")
    mine_parser.add_argument("--name", required=True)
    mine_parser.add_argument("--expression", required=True)
    mine_parser.add_argument("--description", required=True)
    mine_parser.add_argument("--start", required=True)
    mine_parser.add_argument("--end", required=True)
    mine_parser.add_argument("--horizon", type=int, default=5)
    mine_parser.add_argument("--author", default="intern")
    mine_parser.add_argument("--tags", nargs="*", default=[])

    reproduce_parser = subparsers.add_parser("reproduce-factor", help="Re-run a registered factor")
    reproduce_parser.add_argument("--factor-id", required=True)
    reproduce_parser.add_argument("--start", required=True)
    reproduce_parser.add_argument("--end", required=True)
    reproduce_parser.add_argument("--horizon", type=int, default=5)

    auto_parser = subparsers.add_parser("auto-mine", help="Generate factor candidates with AI and batch evaluate them")
    auto_parser.add_argument("--theme", required=True)
    auto_parser.add_argument("--start", required=True)
    auto_parser.add_argument("--end", required=True)
    auto_parser.add_argument("--horizon", type=int, default=5)
    auto_parser.add_argument("--count", type=int, default=5)
    auto_parser.add_argument("--author", default="ai")
    auto_parser.add_argument("--feedback", default="", help="Structured feedback from previous iteration (JSON file path or inline text)")
    auto_parser.add_argument("--provider", default="openai", help="LLM provider: openai, deepseek, qwen, zhipu, moonshot, custom, or a base URL")

    backtest_parser = subparsers.add_parser("backtest", help="Run factor backtest via qlib data engine")
    backtest_parser.add_argument("--start", required=True)
    backtest_parser.add_argument("--end", required=True)
    backtest_parser.add_argument("--factor-id")
    backtest_parser.add_argument("--factor-expression")
    backtest_parser.add_argument("--top-k", type=int, default=30)
    backtest_parser.add_argument("--horizon", type=int, default=5)
    backtest_parser.add_argument("--long-short", action="store_true")

    compare_parser = subparsers.add_parser("compare-factors", help="Compare multiple factors: correlation matrix + IC decay")
    compare_parser.add_argument("--factor-ids", nargs="+", required=True, help="Factor IDs to compare")
    compare_parser.add_argument("--start", default="2010-01-01")
    compare_parser.add_argument("--end", default="2019-12-31")
    compare_parser.add_argument("--mode", default="correlation", choices=["correlation", "ic_decay", "full"],
                                help="Comparison mode")

    redundancy_parser = subparsers.add_parser("check-redundancy", help="Check if a factor is redundant with existing ones")
    redundancy_parser.add_argument("--factor-id", required=True, help="New factor ID to check")
    redundancy_parser.add_argument("--existing-ids", nargs="+", required=True, help="Existing factor IDs")
    redundancy_parser.add_argument("--threshold", type=float, default=0.7, help="Correlation threshold")
    redundancy_parser.add_argument("--start", default="2010-01-01")
    redundancy_parser.add_argument("--end", default="2019-12-31")

    cluster_parser = subparsers.add_parser("cluster-factors", help="Cluster factors by value correlation")
    cluster_parser.add_argument("--factor-ids", nargs="+", required=True, help="Factor IDs to cluster")
    cluster_parser.add_argument("--n-clusters", type=int, default=5)
    cluster_parser.add_argument("--start", default="2010-01-01")
    cluster_parser.add_argument("--end", default="2019-12-31")

    alpha158_template_parser = subparsers.add_parser("alpha158-template", help="Export an Alpha158 starter workflow template")
    alpha158_template_parser.add_argument("--output")

    alpha158_starter_parser = subparsers.add_parser("alpha158-starter", help="Run the preset Alpha158 starter workflow")
    alpha158_starter_parser.add_argument("--market", default="csi300")
    alpha158_starter_parser.add_argument("--benchmark", default="SH000300")
    alpha158_starter_parser.add_argument("--train-start", default="2008-01-01")
    alpha158_starter_parser.add_argument("--train-end", default="2014-12-31")
    alpha158_starter_parser.add_argument("--valid-start", default="2015-01-01")
    alpha158_starter_parser.add_argument("--valid-end", default="2016-12-31")
    alpha158_starter_parser.add_argument("--test-start", default="2017-01-01")
    alpha158_starter_parser.add_argument("--test-end", default="2020-08-01")
    alpha158_starter_parser.add_argument("--topk", type=int, default=50)
    alpha158_starter_parser.add_argument("--n-drop", type=int, default=5)
    alpha158_starter_parser.add_argument("--experiment-name", default="alpha158_starter")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    config = QlibWorkspaceConfig.from_env()
    if getattr(args, "provider_uri", None):
        config.provider_uri = args.provider_uri
    if getattr(args, "region", None):
        config.region = args.region

    lab = QlibFactorLab(config=config)

    if args.command == "init-data":
        payload = init_qlib_workspace(config)
        payload["download_hint"] = qlib_data_download_hint(config)
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default))
        return

    if args.command == "mine-factor":
        payload = lab.mine_expression(
            name=args.name,
            expression=args.expression,
            description=args.description,
            start_time=args.start,
            end_time=args.end,
            horizon=args.horizon,
            author=args.author,
            tags=args.tags,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default))
        return

    if args.command == "reproduce-factor":
        payload = lab.reproduce_factor(
            factor_id=args.factor_id,
            start_time=args.start,
            end_time=args.end,
            horizon=args.horizon,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default))
        return

    if args.command == "auto-mine":
        miner = AIFactorMiner(lab)
        feedback_text = args.feedback
        if feedback_text and Path(feedback_text).is_file():
            feedback_text = Path(feedback_text).read_text(encoding="utf-8")
        payload = miner.auto_mine(
            theme=args.theme,
            start_time=args.start,
            end_time=args.end,
            horizon=args.horizon,
            count=args.count,
            author=args.author,
            feedback=feedback_text,
            provider=args.provider,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default))
        return

    if args.command == "backtest":
        if not args.factor_id and not args.factor_expression:
            raise ValueError("backtest requires --factor-id or --factor-expression")
        result = run_factor_backtest(
            lab, run_id=uuid.uuid4().hex[:12],
            strategy_id=args.factor_id or "adhoc_factor_strategy", strategy_version="v1",
            benchmark=config.benchmark, start_time=args.start, end_time=args.end,
            factor_id=args.factor_id, factor_expression=args.factor_expression,
            top_k=args.top_k, horizon=args.horizon, long_short=args.long_short,
        )
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2, default=_json_default))
        return

    if args.command == "compare-factors":
        from research_core.qlib_lab.factor_compare import pairwise_correlation, ic_decay_curve
        payload = {}
        if args.mode in ("correlation", "full"):
            corr = pairwise_correlation(args.factor_ids, args.start, args.end)
            payload["correlation_matrix"] = corr.to_dict()
        if args.mode in ("ic_decay", "full"):
            decay = ic_decay_curve(args.factor_ids, start=args.start, end=args.end)
            payload["ic_decay"] = decay.to_dict()
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default))
        return

    if args.command == "check-redundancy":
        from research_core.qlib_lab.factor_compare import find_redundant
        result = find_redundant(args.factor_id, args.existing_ids, args.threshold, args.start, args.end)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "cluster-factors":
        from research_core.qlib_lab.factor_compare import factor_cluster
        result = factor_cluster(args.factor_ids, args.n_clusters, args.start, args.end)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "alpha158-template":
        payload = {
            "template_path": export_alpha158_template(output_path=args.output),
            "starter_pack": generate_starter_pack(output_path=args.output),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default))
        return

    if args.command == "alpha158-starter":
        workflow_config = Alpha158WorkflowConfig(
            market=args.market,
            benchmark=args.benchmark,
            train_start=args.train_start,
            train_end=args.train_end,
            valid_start=args.valid_start,
            valid_end=args.valid_end,
            test_start=args.test_start,
            test_end=args.test_end,
            topk=args.topk,
            n_drop=args.n_drop,
            experiment_name=args.experiment_name,
        )
        payload = run_alpha158_workflow(workflow_config, workspace=config)
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default))
        return


if __name__ == "__main__":
    main()
