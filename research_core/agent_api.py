#!/usr/bin/env python3
"""
Agent API — Unified entry point for AI agents.

This module wraps all framework capabilities behind a single, self-documenting
Python API. AI agents only need to know two things:

1. ``discover()`` — see what the framework can do
2. ``explore_factors()`` / ``build_strategy()`` / ... — call specific capabilities

Every function returns structured, JSON-serializable results with actionable
``next_actions`` when applicable. Errors are caught and returned as structured
dicts with ``error`` + ``suggested_fix`` fields, never raw tracebacks.

Quick start::

    from research_core.agent_api import discover, explore_factors

    # Step 1: Discover capabilities
    print(discover())

    # Step 2: Explore factors
    result = explore_factors(goal="momentum factors", universe="csi300")
    print(result["gate_verdict"], result["summary"])
"""

from __future__ import annotations

import json
import traceback
from typing import Any, Optional

from research_core.agent_manifest import get_manifest


# ── Helper: safe wrapper ────────────────────────────────────────────────────

def _safe_call(func, *args, **kwargs) -> dict[str, Any]:
    """Call func and catch all exceptions, returning structured error dicts."""
    try:
        result = func(*args, **kwargs)
        # Convert dataclass to dict if needed
        if hasattr(result, "__dict__") and not isinstance(result, dict):
            if hasattr(result, "to_dict"):
                return result.to_dict()
            return _dataclass_to_dict(result)
        return result if isinstance(result, dict) else {"result": result}
    except ImportError as e:
        return {
            "error": f"Missing dependency: {e}",
            "suggested_fix": f"Install required packages: pip install -r scripts/requirements.txt -r requirements-factor-lab.txt",
            "missing_module": str(e).replace("No module named ", "").strip("'\""),
        }
    except FileNotFoundError as e:
        return {
            "error": f"File not found: {e}",
            "suggested_fix": "Check that the file path is correct and the file exists. Use overview() to see workspace paths.",
            "file": str(e),
        }
    except SystemExit as e:
        return {
            "error": "CLI exited unexpectedly (SystemExit).",
            "error_type": "SystemExit",
            "exit_code": e.code,
            "suggested_fix": "Check that all required arguments are provided. Use --help on the CLI subcommand for usage.",
        }
    except Exception as e:
        return {
            "error": str(e),
            "error_type": type(e).__name__,
            "suggested_fix": "Check the error message above. Call discover() to see available capabilities and their parameters.",
            "traceback": traceback.format_exc().split("\n")[-5:],
        }


def _dataclass_to_dict(obj) -> dict[str, Any]:
    """Recursively convert a dataclass to a dict."""
    import dataclasses
    if dataclasses.is_dataclass(obj):
        return {k: _dataclass_to_dict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [_dataclass_to_dict(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _dataclass_to_dict(v) for k, v in obj.items()}
    return obj


def _parse_cli_json(stdout: str) -> dict[str, Any] | None:
    """Parse a JSON object from CLI stdout.

    Handles three layouts:
    1. Pure JSON — the entire stdout is a single JSON object.
    2. Log + single-line JSON — log lines followed by a one-line JSON object.
    3. Log + multi-line JSON — log lines followed by a pretty-printed JSON
       object spanning multiple lines.

    Returns the parsed dict, or ``None`` when no valid JSON object is found.
    """
    text = (stdout or "").strip()
    if not text:
        return None

    # Try 1: entire output is pure JSON
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Try 2: scan backward for the last line that starts with '{' and attempt
    # to parse from that line to the end of the output. This covers both
    # single-line and pretty-printed (multi-line) JSON blocks.
    lines = text.split("\n")
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].lstrip().startswith("{"):
            candidate = "\n".join(lines[i:]).strip()
            try:
                result = json.loads(candidate)
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                continue

    # Try 3: brace-matching fallback — find the last '}' and scan backward for
    # the matching '{', then parse the substring. This catches edge cases where
    # the JSON does not start at the beginning of a line.
    last_close = text.rfind("}")
    if last_close != -1:
        depth = 0
        for j in range(last_close, -1, -1):
            ch = text[j]
            if ch == "}":
                depth += 1
            elif ch == "{":
                depth -= 1
                if depth == 0:
                    candidate = text[j:last_close + 1]
                    try:
                        result = json.loads(candidate)
                        if isinstance(result, dict):
                            return result
                    except json.JSONDecodeError:
                        pass
                    break

    return None


# ── Meta capabilities ──────────────────────────────────────────────────────

def discover() -> dict[str, Any]:
    """
    List all framework capabilities with parameters and examples.

    **Always call this first** to understand what the framework can do.

    Returns:
        Dict with 'framework', 'version', 'capabilities' list.
    """
    return get_manifest()


def overview() -> dict[str, Any]:
    """
    Get framework overview: workspace paths, available factor families,
    installed libraries, and runtime status.

    Returns:
        Dict with workspace, factor_families, backtest_engines,
        external_sim_engines, data_sources, next_actions.
    """
    return _safe_call(_overview_impl)


def _overview_impl() -> dict[str, Any]:
    from research_core.factor_lab.runtime import FactorLabWorkspaceConfig
    from research_core.factor_lab.libraries.alpha101 import IMPLEMENTED_ALPHA101_FACTORS
    from research_core.factor_lab.libraries.gtja191 import IMPLEMENTED_GTJA191_FACTORS

    config = FactorLabWorkspaceConfig()

    factor_families = {
        "alpha101": {"implemented": len(IMPLEMENTED_ALPHA101_FACTORS), "total": 101},
        "wq101": {"implemented": 10, "total": 101},
        "gtja191": {"implemented": len(IMPLEMENTED_GTJA191_FACTORS), "total": 191},
        "alpha158": {"implemented": 158, "total": 158},
        "barra": {"implemented": 10, "total": 10},
    }

    return {
        "framework": "AgentMatrix Research",
        "workspace": {
            "data_root": str(config.data_root),
            "runtime_root": str(config.runtime_root),
            "example_specs_path": str(config.specs_path("alpha101")),
            "example_job_path": str(config.job_path("demo_job")),
        },
        "factor_families": factor_families,
        "backtest_engines": ["gm", "rqalpha", "qlib"],
        "external_sim_engines": ["gm", "ptrade", "qmt"],
        "data_sources": ["demo", "amazingdata", "akshare"],
        "next_actions": [
            "Call explore_factors() to run factor exploration",
            "Call list_factors('alpha101') to see available factors",
            "Call check_data_source() to verify data connectivity",
        ],
    }


def check_data_source(env_file: str = "") -> dict[str, Any]:
    """
    Check connectivity and status of the amazingdata ClickHouse data source.

    Args:
        env_file: Optional path to ClickHouse env file.

    Returns:
        Dict with connected, tables, error.
    """
    return _safe_call(_check_data_source_impl, env_file)


def _check_data_source_impl(env_file: str) -> dict[str, Any]:
    from research_core.factor_lab.service import check_amazingdata

    payload = {"env_file": env_file} if env_file else None
    result = check_amazingdata(payload)

    return {
        "connected": result.get("ok", False),
        "details": result,
        "next_actions": (
            ["Data source is ready. Call explore_factors() to begin factor research."]
            if result.get("ok")
            else ["Data source not available. Use demo data for testing: explore_factors()"]
        ),
    }


# ── Factor research capabilities ───────────────────────────────────────────

def explore_factors(
    goal: str = "",
    universe: str = "csi300",
    factor_set: str = "alpha101",
    factors: Optional[list[str]] = None,
    start: str = "2023-01-01",
    end: str = "2025-12-31",
    horizon: int = 5,
    top_n: int = 10,
    auto: bool = True,
    cache_dir: str = "",
    output_dir: str = "",
) -> dict[str, Any]:
    """
    One-click factor exploration: auto-fetch market data, compute factors,
    evaluate IC/IR/OOS, run validation gates, return a structured verdict.

    This is the **main entry point** for factor research.

    Args:
        goal: Human-readable research goal (e.g. "low volatility quality factors").
        universe: Stock universe — "csi300", "csi500", "csi800", "all".
        factor_set: Factor family — "alpha101", "wq101", "gtja191", "alpha158", "barra".
        factors: Specific factor names, or None for auto top-N.
        start: Start date (YYYY-MM-DD).
        end: End date (YYYY-MM-DD).
        horizon: Forward return horizon in days.
        top_n: Number of top factors to report.
        auto: If True, auto-select factors when ``factors`` is None.
            If False, ``factors`` must be provided explicitly.
        cache_dir: Cache directory for market data.
        output_dir: Where to write the factor_lab job JSON + factor frame.
            Defaults to the factor_lab runtime root (``runtime/factor_lab``).
            The returned ``artifacts.job_path`` is the path to pass to
            ``build_strategy(validated_run_path=...)``.

    Returns:
        Dict with gate_verdict (🟢/🟡/🔴), factors_tested, factors_passed,
        top_factors, summary, report_path, artifacts (with job_path),
        next_actions.
    """
    return _safe_call(
        _explore_factors_impl,
        goal=goal, universe=universe, factor_set=factor_set,
        factors=factors, start=start, end=end, horizon=horizon,
        top_n=top_n, auto=auto, cache_dir=cache_dir, output_dir=output_dir,
    )


def _explore_factors_impl(**kwargs) -> dict[str, Any]:
    from research_core.factor_lab.agent_pipeline import explore, explore_to_markdown

    result = explore(**kwargs)
    job_path = result.artifacts.get("job_path", "")
    next_actions = list(result.next_actions)
    # Always steer the agent toward the documented explore → build_strategy flow.
    if job_path and not any("build_strategy" in a for a in next_actions):
        next_actions.insert(
            0,
            f"Call build_strategy(validated_run_path='{job_path}') to build target weights.",
        )
    return {
        "goal": result.goal,
        "universe": result.universe,
        "n_stocks": result.n_stocks,
        "date_range": result.date_range,
        "elapsed_seconds": result.elapsed_seconds,
        "factors_tested": result.factors_tested,
        "factors_passed": result.factors_passed,
        "top_factors": result.top_factors,
        "gate_verdict": result.gate_verdict,
        "gate_details": {
            "passed": result.gate_details.get("passed", 0),
            "total": result.gate_details.get("total", 0),
        },
        "summary": result.summary,
        "report_path": result.report_path,
        "artifacts": result.artifacts,
        "next_actions": next_actions,
        "markdown_report": explore_to_markdown(result),
    }


def validate_factor(
    factor_name: str,
    ic_mean: float,
    ic_ir: float,
    oos_retention: float = 0.0,
    decay_pct: float = 0.0,
    ic_std: float = 0.0,
    cost_resilience: Optional[bool] = None,
    sector_neutrality: Optional[float] = None,
    segment_consistency: Optional[int] = None,
    validated_run_path: str = "",
) -> dict[str, Any]:
    """
    Run the 7-gate validation system on a single factor's metrics.

    Gates: OOS retention, IC significance, IC IR, time decay, cost resilience,
    sector neutrality, segment consistency.

    Args:
        factor_name: Factor identifier.
        ic_mean: Mean Information Coefficient.
        ic_ir: IC Information Ratio (mean / std).
        oos_retention: Out-of-sample IC retention ratio (0-1).
        decay_pct: IC time decay percentage.
        ic_std: IC standard deviation.
        cost_resilience: Whether factor survives 50bp cost (optional).
        sector_neutrality: IC retention after sector neutralization (optional).
        segment_consistency: Number of profitable regimes out of 3 (optional).
        validated_run_path: Optional path to the factor_lab job JSON this factor came from.
            If provided, it is passed through to the result for linking to build_strategy().

    Returns:
        Dict with 'passed' (bool), 'gates' dict, 'fail_reasons', 'pass_reasons',
        and 'validated_run_path' (if provided).
    """
    return _safe_call(
        _validate_factor_impl,
        factor_name=factor_name, ic_mean=ic_mean, ic_ir=ic_ir,
        oos_retention=oos_retention, decay_pct=decay_pct, ic_std=ic_std,
        cost_resilience=cost_resilience, sector_neutrality=sector_neutrality,
        segment_consistency=segment_consistency,
        validated_run_path=validated_run_path,
    )


def _validate_factor_impl(**kwargs) -> dict[str, Any]:
    from research_core.factor_lab.validation_gate import ValidationGate

    validated_run_path = kwargs.pop("validated_run_path", "")
    gate = ValidationGate()
    verdict = gate.evaluate(**kwargs)
    result = verdict.to_dict()
    if validated_run_path:
        result["validated_run_path"] = validated_run_path
        # The verdict — not the presence of a run path — decides the guidance.
        # A failed factor must never be told to proceed to build_strategy().
        if verdict.passed:
            result["next_actions"] = [
                f"Factor '{verdict.factor_name}' passed with validated_run_path. "
                f"Call build_strategy(validated_run_path='{validated_run_path}') to create target weights.",
            ]
        else:
            result["next_actions"] = [
                f"Factor '{verdict.factor_name}' FAILED gates: "
                f"{', '.join(verdict.fail_reasons) or 'insufficient evidence'}.",
                "Do not call build_strategy() until the factor passes validation. "
                "Adjust the factor parameters or try a different factor family.",
            ]
    else:
        if verdict.passed:
            result["next_actions"] = [
                f"Factor '{verdict.factor_name}' passed validation.",
                "To build a strategy, you need a factor_lab job JSON path.",
                "Call explore_factors() to run a full exploration — its return includes "
                "artifacts.job_path which you can pass to build_strategy(validated_run_path=...).",
                "Or, if you already have a job path, re-call validate_factor() with validated_run_path=<path>.",
            ]
        else:
            result["next_actions"] = [
                f"Factor '{verdict.factor_name}' failed gates: {', '.join(verdict.fail_reasons)}",
                "Try different factor parameters or a different factor family.",
            ]
    return result


def evaluate_factor_csv(
    factor_csv: str,
    factor_name: str = "factor",
    sector_col: str = "sector",
    ic_threshold: float = 0.02,
    turnover_warn: float = 0.7,
) -> dict[str, Any]:
    """
    Full IC evaluation from a CSV file.

    The CSV must contain columns: date, code, factor_value, next_return.
    Optional: sector.

    Args:
        factor_csv: Path to CSV file.
        factor_name: Display name for the factor.
        sector_col: Column name for sector (if available).
        ic_threshold: Minimum |IC| to pass.
        turnover_warn: Turnover rate warning threshold.

    Returns:
        Dict with factor_name, status, mean_rank_ic, rank_icir,
        ic_positive_ratio, mean_turnover, warnings.
    """
    return _safe_call(
        _evaluate_factor_csv_impl,
        factor_csv=factor_csv, factor_name=factor_name,
        sector_col=sector_col, ic_threshold=ic_threshold,
        turnover_warn=turnover_warn,
    )


def _evaluate_factor_csv_impl(**kwargs) -> dict[str, Any]:
    import pandas as pd
    from research_core.factor_lab.evaluation import evaluate_factor, evaluation_summary

    factor_csv = kwargs.pop("factor_csv")
    factor_name = kwargs.pop("factor_name")
    sector_col = kwargs.pop("sector_col")

    df = pd.read_csv(factor_csv)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])

    report = evaluate_factor(
        df, factor_name,
        factor_col="factor_value", return_col="next_return",
        sector_col=sector_col if sector_col in df.columns else "sector",
        **kwargs,
    )

    return {
        "factor_name": report.factor_name,
        "status": report.status,
        "mean_rank_ic": report.ic_eval.mean_rank_ic if report.ic_eval else None,
        "rank_icir": report.ic_eval.rank_icir if report.ic_eval else None,
        "ic_positive_ratio": report.ic_eval.ic_positive_ratio if report.ic_eval else None,
        "mean_turnover": report.turnover.mean_turnover if report.turnover else None,
        "warnings": report.warnings,
        "next_actions": (
            [f"Factor '{factor_name}' looks good. Call validate_factor() for gate evaluation."]
            if report.status == "pass"
            else [f"Factor '{factor_name}' has issues. Check warnings."]
        ),
    }


def list_factors(factor_set: str = "alpha101") -> dict[str, Any]:
    """
    List all available factors in a given factor family.

    Args:
        factor_set: "alpha101", "wq101", "gtja191", "alpha158", "barra".

    Returns:
        Dict with 'items' list (each has factor_name, implemented, proof_status).
    """
    return _safe_call(_list_factors_impl, factor_set)


def _list_factors_impl(factor_set: str) -> dict[str, Any]:
    from research_core.factor_lab.runtime import FactorLabWorkspaceConfig
    from research_core.factor_lab.service import (
        list_alpha101_factors,
        list_factor_set_factors,
    )

    config = FactorLabWorkspaceConfig()

    if factor_set == "alpha101":
        items = list_alpha101_factors(config)
    else:
        items = list_factor_set_factors(factor_set, config)

    return {
        "factor_set": factor_set,
        "count": len(items),
        "items": items,
        "next_actions": [
            f"Call explore_factors(factor_set='{factor_set}') to evaluate these factors.",
            f"Call explore_factors(factors=['{items[0]['factor_name' if 'factor_name' in items[0] else 'name']}']) to test a specific factor.",
        ] if items else ["No factors found. Try a different factor_set."],
    }


# ── Strategy building capabilities ─────────────────────────────────────────

def build_strategy(
    validated_run_path: str,
    factor_names: Optional[list[str]] = None,
    rebalance_frequency: str = "daily",
    top_n: int = 50,
    long_short: bool = False,
    as_of: str = "",
    start: str = "",
    end: str = "",
    output_dir: str = "",
) -> dict[str, Any]:
    """
    Build target weight signals from a validated factor research run.

    Args:
        validated_run_path: Path to factor_lab job JSON.
        factor_names: Specific factors to use (default: job's requested_factors).
        rebalance_frequency: "single", "daily", "weekly", "monthly".
        top_n: Number of names to hold per side.
        long_short: Build long-short weights instead of long-only.
        as_of: Single snapshot date (forces "single" frequency).
        start: First signal date for multi-date exports.
        end: Last signal date for multi-date exports.
        output_dir: Optional output directory.

    Returns:
        Dict with strategy_id, signal_path, artifacts (with signals/config).
    """
    return _safe_call(
        _build_strategy_impl,
        validated_run_path=validated_run_path,
        factor_names=factor_names,
        rebalance_frequency=rebalance_frequency,
        top_n=top_n, long_short=long_short,
        as_of=as_of, start=start, end=end,
        output_dir=output_dir or None,
    )


def _build_strategy_impl(**kwargs) -> dict[str, Any]:
    from research_core.strategy_engine.alpha_strategy import build_alpha_strategy_package

    payload = build_alpha_strategy_package(**kwargs)
    result = _dataclass_to_dict(payload) if hasattr(payload, "__dict__") else payload
    # Ensure top-level signal_path for backward compat
    if "signal_path" not in result and "artifacts" in result:
        result["signal_path"] = result["artifacts"].get("signals", "")
    result["next_actions"] = [
        f"Strategy signals built at {result.get('signal_path', 'output')}.",
        "Call package_backtest() to package for external simulation.",
    ]
    return result


# ── Backtest capabilities ──────────────────────────────────────────────────

def package_backtest(
    engine: str,
    signal_path: str,
    strategy_id: str = "alpha_strategy",
    start: str = "",
    end: str = "",
    benchmark: str = "",
    initial_cash: float = 1_000_000.0,
    slippage_bps: float = 0.0,
    commission_bps: float = 0.0,
    run_id: str = "",
    output_dir: str = "",
) -> dict[str, Any]:
    """
    Package target weight signals for external backtest engines.

    Args:
        engine: "gm" (掘金), "ptrade", or "qmt".
        signal_path: Path to target weights CSV.
        strategy_id: Strategy identifier.
        start: Simulation start time.
        end: Simulation end time.
        benchmark: Benchmark symbol.
        initial_cash: Initial capital.
        slippage_bps: Slippage in basis points.
        commission_bps: Commission in basis points.
        run_id: Simulation run ID (auto-generated if empty).
        output_dir: Optional output directory.

    Returns:
        Dict with run_id, engine, package_dir, package_path, artifacts.
    """
    return _safe_call(
        _package_backtest_impl,
        engine=engine, signal_path=signal_path,
        strategy_id=strategy_id, start=start, end=end,
        benchmark=benchmark, initial_cash=initial_cash,
        slippage_bps=slippage_bps, commission_bps=commission_bps,
        run_id=run_id, output_dir=output_dir or None,
    )


def _package_backtest_impl(**kwargs) -> dict[str, Any]:
    from dataclasses import asdict
    from contracts.backtest import ExternalSimulationRequest
    from research_core.backtest_adapter.external_simulation import package_external_simulation

    engine = kwargs.pop("engine")
    signal_path = kwargs.pop("signal_path")
    strategy_id = kwargs.pop("strategy_id")
    run_id = kwargs.pop("run_id") or f"{strategy_id}_{engine}"

    request = ExternalSimulationRequest(
        run_id=run_id,
        engine=engine,
        strategy_id=strategy_id,
        strategy_version="v1",
        signal_path=signal_path,
        start_time=kwargs.get("start", ""),
        end_time=kwargs.get("end", ""),
        benchmark=kwargs.get("benchmark", ""),
        initial_cash=kwargs.get("initial_cash", 1_000_000.0),
        slippage_bps=kwargs.get("slippage_bps", 0.0),
        commission_bps=kwargs.get("commission_bps", 0.0),
    )
    output_dir = kwargs.get("output_dir")
    package = package_external_simulation(request, output_dir=output_dir)
    result = _dataclass_to_dict(package)
    # Ensure top-level package_path for backward compat
    if "package_path" not in result:
        result["package_path"] = result.get("package_dir", "")
    result["next_actions"] = [
        f"Package ready for {engine}. Run the simulation in the engine terminal.",
        "After simulation, call parse_backtest_result() to parse the result.",
    ]
    return result


def parse_backtest_result(
    engine: str,
    run_id: str,
    result_path: str,
) -> dict[str, Any]:
    """
    Parse an external backtest engine's result file into a standardized result.

    Args:
        engine: "gm", "ptrade", or "qmt".
        run_id: Simulation run ID.
        result_path: Path to the engine's result file.

    Returns:
        Dict with run_id, engine, metrics, equity_curve, trades.
    """
    return _safe_call(
        _parse_backtest_result_impl,
        engine=engine, run_id=run_id, result_path=result_path,
    )


def _parse_backtest_result_impl(**kwargs) -> dict[str, Any]:
    from research_core.backtest_adapter.external_simulation import parse_external_simulation_result

    result = parse_external_simulation_result(**kwargs)
    data = _dataclass_to_dict(result)
    data["next_actions"] = [
        "Review performance metrics. If satisfactory, consider live deployment.",
        "If metrics are poor, go back to explore_factors() with different parameters.",
    ]
    return data


# ── Qlib Lab capabilities ──────────────────────────────────────────────────

def mine_factor(
    name: str,
    expression: str,
    description: str = "",
    start: str = "2021-01-01",
    end: str = "2024-12-31",
) -> dict[str, Any]:
    """
    Mine a single factor using Qlib expression syntax.

    Args:
        name: Factor name.
        expression: Qlib expression (e.g. "Ref($close, 5) / $close - 1").
        description: Human-readable description.
        start: Start date.
        end: End date.

    Returns:
        Dict with factor_name, expression, ic_mean, ic_ir, rank_ic_mean,
        long_short_spread, status, definition, evaluation, top_metrics.
    """
    return _safe_call(
        _mine_factor_impl,
        name=name, expression=expression,
        description=description, start=start, end=end,
    )


def _mine_factor_impl(**kwargs) -> dict[str, Any]:
    import subprocess as _sp
    import sys as _sys

    name = kwargs["name"]
    expression = kwargs["expression"]
    description = kwargs.get("description", "")
    start = kwargs.get("start", "2021-01-01")
    end = kwargs.get("end", "2024-12-31")

    cmd = [
        _sys.executable, "-m", "research_core.qlib_lab.cli",
        "mine-factor",
        "--name", name,
        "--expression", expression,
        "--description", description or f"Factor: {name}",
        "--start", start,
        "--end", end,
    ]
    proc = _sp.run(cmd, capture_output=True, text=True, timeout=600)
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    if proc.returncode != 0:
        return {
            "factor_name": name,
            "expression": expression,
            "status": "error",
            "returncode": proc.returncode,
            "output": (stdout + "\n" + stderr).strip()[-2000:],
            "error": f"Qlib CLI exited with code {proc.returncode}",
            "suggested_fix": "Ensure Qlib is installed and market data is available. Try: pip install pyqlib",
            "next_actions": ["Check error output above.", "Verify Qlib data is initialized."],
        }

    # Parse CLI JSON output (handles pure JSON, log+single-line, log+multi-line)
    cli_result = _parse_cli_json(stdout)

    if cli_result is None:
        return {
            "factor_name": name,
            "expression": expression,
            "status": "error",
            "returncode": proc.returncode,
            "output_summary": stdout.strip()[-1000:],
            "error": "Failed to parse CLI JSON output",
            "next_actions": ["Check raw output for metrics.", "Call validate_factor() manually."],
        }

    # Extract structured metrics from CLI JSON
    top_metrics = cli_result.get("top_metrics", {})
    evaluation = cli_result.get("evaluation", {})
    definition = cli_result.get("definition", {})

    # Build metrics dict from evaluation.metrics list (more complete)
    metrics_dict = {}
    for m in evaluation.get("metrics", []):
        metrics_dict[m["name"]] = m["value"]

    ic_mean = top_metrics.get("ic_mean", metrics_dict.get("ic_mean"))
    ic_ir = top_metrics.get("icir", metrics_dict.get("icir"))
    rank_ic_mean = top_metrics.get("rank_ic_mean", metrics_dict.get("rank_ic_mean"))
    long_short_spread = top_metrics.get("long_short_spread", metrics_dict.get("long_short_spread"))

    result = {
        "factor_name": definition.get("name", name),
        "expression": definition.get("expression", expression),
        "ic_mean": ic_mean,
        "ic_ir": ic_ir,
        "rank_ic_mean": rank_ic_mean,
        "long_short_spread": long_short_spread,
        "status": "completed",
        "returncode": proc.returncode,
        "definition": definition,
        "evaluation": evaluation,
        "top_metrics": top_metrics,
        "next_actions": [
            f"Factor '{name}' IC={ic_mean}, IR={ic_ir}." if ic_mean is not None else "Check output for IC metrics.",
            "Call validate_factor() to run validation gates.",
            "Call qlib_backtest() with this expression for a full backtest.",
        ],
    }

    # Include artifact paths if available
    artifacts = evaluation.get("artifacts", {})
    if artifacts:
        result["artifacts"] = artifacts

    return result


def auto_mine(
    theme: str,
    start: str = "2021-01-01",
    end: str = "2024-12-31",
) -> dict[str, Any]:
    """
    AI-assisted automatic factor mining.

    Args:
        theme: Natural language factor theme (e.g. "mid-cap momentum with turnover confirmation").
        start: Start date.
        end: End date.

    Returns:
        Dict with theme, generated_count, results, candidates, best_factor, best_ic.
    """
    return _safe_call(
        _auto_mine_impl,
        theme=theme, start=start, end=end,
    )


def _auto_mine_impl(**kwargs) -> dict[str, Any]:
    import subprocess as _sp
    import sys as _sys

    theme = kwargs["theme"]
    start = kwargs.get("start", "2021-01-01")
    end = kwargs.get("end", "2024-12-31")

    cmd = [
        _sys.executable, "-m", "research_core.qlib_lab.cli",
        "auto-mine",
        "--theme", theme,
        "--start", start,
        "--end", end,
    ]
    proc = _sp.run(cmd, capture_output=True, text=True, timeout=600)
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    if proc.returncode != 0:
        return {
            "theme": theme,
            "status": "error",
            "returncode": proc.returncode,
            "output": (stdout + "\n" + stderr).strip()[-2000:],
            "error": f"Qlib CLI exited with code {proc.returncode}",
            "suggested_fix": "Ensure Qlib is installed and market data is available.",
            "next_actions": ["Check error output above."],
        }

    # Parse CLI JSON output (handles pure JSON, log+single-line, log+multi-line)
    cli_result = _parse_cli_json(stdout)

    if cli_result is None:
        return {
            "theme": theme,
            "status": "error",
            "returncode": proc.returncode,
            "output_summary": stdout.strip()[-1000:],
            "error": "Failed to parse CLI JSON output",
            "next_actions": ["Check raw output for candidate factors."],
        }

    # Extract structured data from CLI JSON
    generated_count = cli_result.get("generated_count", 0)
    results = cli_result.get("results", [])

    # Build a summary of best candidates
    candidates_summary = []
    for r in results:
        top_metrics = r.get("top_metrics", {})
        definition = r.get("definition", {})
        candidate = r.get("candidate", {})
        candidates_summary.append({
            "name": definition.get("name", candidate.get("name", "")),
            "expression": definition.get("expression", candidate.get("expression", "")),
            "ic_mean": top_metrics.get("ic_mean"),
            "icir": top_metrics.get("icir"),
            "rank_ic_mean": top_metrics.get("rank_ic_mean"),
            "long_short_spread": top_metrics.get("long_short_spread"),
        })

    # Best factor = first in results (already sorted by IC)
    best = candidates_summary[0] if candidates_summary else None

    result = {
        "theme": theme,
        "generated_count": generated_count,
        "results": results,
        "candidates": candidates_summary,
        "best_factor": best["name"] if best else None,
        "best_ic": best["ic_mean"] if best else None,
        "status": "completed",
        "returncode": proc.returncode,
        "next_actions": [
            f"Generated {generated_count} candidate factors." if generated_count else "No candidates generated.",
            "Call mine_factor() to test a specific expression.",
            "Call qlib_backtest() for a full backtest on the best candidate.",
        ],
    }

    return result


def qlib_backtest(
    factor_expression: str,
    start: str = "2021-01-01",
    end: str = "2024-12-31",
) -> dict[str, Any]:
    """
    Run a Qlib factor-expression backtest.

    Args:
        factor_expression: Qlib expression (e.g. "($close / Ref($close, 20) - 1)").
        start: Start date.
        end: End date.

    Returns:
        Dict with expression, annualized_return, sharpe_ratio, max_drawdown,
        total_return, volatility, win_rate, metrics, equity_curve.
    """
    return _safe_call(
        _qlib_backtest_impl,
        factor_expression=factor_expression,
        start=start, end=end,
    )


def _qlib_backtest_impl(**kwargs) -> dict[str, Any]:
    import subprocess as _sp
    import sys as _sys

    expression = kwargs["factor_expression"]
    start = kwargs.get("start", "2021-01-01")
    end = kwargs.get("end", "2024-12-31")

    cmd = [
        _sys.executable, "-m", "research_core.qlib_lab.cli",
        "backtest",
        "--factor-expression", expression,
        "--start", start,
        "--end", end,
    ]
    proc = _sp.run(cmd, capture_output=True, text=True, timeout=600)
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    if proc.returncode != 0:
        return {
            "expression": expression,
            "status": "error",
            "returncode": proc.returncode,
            "output": (stdout + "\n" + stderr).strip()[-2000:],
            "error": f"Qlib CLI exited with code {proc.returncode}",
            "suggested_fix": "Ensure Qlib is installed and market data is available.",
            "next_actions": ["Check error output above."],
        }

    # Parse CLI JSON output (handles pure JSON, log+single-line, log+multi-line)
    cli_result = _parse_cli_json(stdout)

    if cli_result is None:
        return {
            "expression": expression,
            "status": "error",
            "returncode": proc.returncode,
            "output_summary": stdout.strip()[-1000:],
            "error": "Failed to parse CLI JSON output",
            "next_actions": ["Check raw output for performance metrics."],
        }

    # Extract metrics from CLI JSON
    metrics = cli_result.get("metrics", {})
    annualized_return = metrics.get("annualized_return")
    sharpe_ratio = metrics.get("sharpe")
    max_drawdown = metrics.get("max_drawdown")
    total_return = metrics.get("total_return")
    volatility = metrics.get("volatility")
    win_rate = metrics.get("win_rate")

    result = {
        "expression": expression,
        "annualized_return": annualized_return,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown": max_drawdown,
        "total_return": total_return,
        "volatility": volatility,
        "win_rate": win_rate,
        "status": cli_result.get("status", "completed"),
        "returncode": proc.returncode,
        "run_id": cli_result.get("run_id"),
        "engine": cli_result.get("engine"),
        "metrics": metrics,
        "equity_curve": cli_result.get("equity_curve"),
        "next_actions": [
            f"Sharpe={sharpe_ratio}, Return={annualized_return}, MDD={max_drawdown}."
            if sharpe_ratio is not None
            else "Check output for performance metrics.",
            "If Sharpe > 1, call build_strategy() to create tradeable signals.",
        ],
    }

    # Include artifacts if available
    artifacts = cli_result.get("artifacts")
    if artifacts:
        result["artifacts"] = artifacts

    # Include diagnostics if available
    diagnostics = cli_result.get("diagnostics")
    if diagnostics:
        result["diagnostics"] = diagnostics

    return result


# ── CLI entry point ────────────────────────────────────────────────────────

def _build_cli():
    """Build the unified agent CLI parser."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="research_core.agent_api",
        description="AgentMatrix Research — Unified Agent API CLI",
        epilog="Call 'discover' first to see all available capabilities.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # discover
    sub.add_parser("discover", help="List all capabilities")

    # overview
    sub.add_parser("overview", help="Framework overview")

    # check-data
    cd = sub.add_parser("check-data", help="Check data source connectivity")
    cd.add_argument("--env-file", default="")

    # explore
    ex = sub.add_parser("explore", help="One-click factor exploration")
    ex.add_argument("--goal", default="")
    ex.add_argument("--universe", default="csi300", choices=["csi300", "csi500", "csi800", "all"])
    ex.add_argument("--factor-set", default="alpha101", choices=["alpha101", "wq101", "gtja191", "alpha158", "barra"])
    ex.add_argument("--factors", default="")
    ex.add_argument("--start", default="2023-01-01")
    ex.add_argument("--end", default="2025-12-31")
    ex.add_argument("--horizon", type=int, default=5)
    ex.add_argument("--top-n", type=int, default=10)
    ex.add_argument("--auto", dest="auto", action="store_true", default=True,
                    help="Auto-select factors when --factors is empty (default)")
    ex.add_argument("--no-auto", dest="auto", action="store_false",
                    help="Require explicit --factors; disable auto-selection")
    ex.add_argument("--cache-dir", default="")
    ex.add_argument("--output-dir", default="")
    ex.add_argument("--format", default="json", choices=["json", "markdown"])

    # validate
    va = sub.add_parser("validate", help="Run validation gates on factor metrics")
    va.add_argument("--factor-name", required=True)
    va.add_argument("--ic-mean", type=float, required=True)
    va.add_argument("--ic-ir", type=float, required=True)
    va.add_argument("--oos-retention", type=float, default=0.0)
    va.add_argument("--decay-pct", type=float, default=0.0)
    va.add_argument("--ic-std", type=float, default=0.0)
    va.add_argument("--cost-resilience", action="store_true", default=None)
    va.add_argument("--sector-neutrality", type=float, default=None)
    va.add_argument("--segment-consistency", type=int, default=None)
    va.add_argument("--validated-run-path", default="")

    # evaluate-csv
    ev = sub.add_parser("evaluate-csv", help="Evaluate factor from CSV file")
    ev.add_argument("--factor-csv", required=True)
    ev.add_argument("--factor-name", default="factor")
    ev.add_argument("--sector-col", default="sector")
    ev.add_argument("--ic-threshold", type=float, default=0.02)
    ev.add_argument("--turnover-warn", type=float, default=0.7)

    # list-factors
    lf = sub.add_parser("list-factors", help="List available factors")
    lf.add_argument("--factor-set", default="alpha101", choices=["alpha101", "wq101", "gtja191", "alpha158", "barra"])

    # build
    bd = sub.add_parser("build", help="Build strategy from validated factor run")
    bd.add_argument("--validated-run", required=True)
    bd.add_argument("--factors", default="")
    bd.add_argument("--rebalance-frequency", default="daily", choices=["single", "daily", "weekly", "monthly"])
    bd.add_argument("--top-n", type=int, default=50)
    bd.add_argument("--long-short", action="store_true")
    bd.add_argument("--as-of", default="")
    bd.add_argument("--start", default="")
    bd.add_argument("--end", default="")
    bd.add_argument("--output-dir", default="")

    # package
    pk = sub.add_parser("package", help="Package signals for external simulation")
    pk.add_argument("--engine", required=True, choices=["gm", "ptrade", "qmt"])
    pk.add_argument("--signal-path", required=True)
    pk.add_argument("--strategy", default="alpha_strategy")
    pk.add_argument("--start", required=True)
    pk.add_argument("--end", required=True)
    pk.add_argument("--benchmark", default="")
    pk.add_argument("--initial-cash", type=float, default=1_000_000.0)
    pk.add_argument("--slippage-bps", type=float, default=0.0)
    pk.add_argument("--commission-bps", type=float, default=0.0)
    pk.add_argument("--run-id", default="")
    pk.add_argument("--output-dir", default="")

    # parse-result
    pr = sub.add_parser("parse-result", help="Parse external simulation result")
    pr.add_argument("--engine", required=True, choices=["gm", "ptrade", "qmt"])
    pr.add_argument("--run-id", required=True)
    pr.add_argument("--result-path", required=True)

    # mine
    mn = sub.add_parser("mine", help="Mine a single factor via Qlib")
    mn.add_argument("--name", required=True)
    mn.add_argument("--expression", required=True)
    mn.add_argument("--description", default="")
    mn.add_argument("--start", default="2021-01-01")
    mn.add_argument("--end", default="2024-12-31")

    # auto-mine
    am = sub.add_parser("auto-mine", help="AI-assisted factor mining")
    am.add_argument("--theme", required=True)
    am.add_argument("--start", default="2021-01-01")
    am.add_argument("--end", default="2024-12-31")

    # qlib-backtest
    qb = sub.add_parser("qlib-backtest", help="Qlib expression backtest")
    qb.add_argument("--factor-expression", required=True)
    qb.add_argument("--start", default="2021-01-01")
    qb.add_argument("--end", default="2024-12-31")

    return parser


def main():
    """CLI entry point for python -m research_core.agent_api."""
    import sys as _sys
    parser = _build_cli()
    args = parser.parse_args()

    result: dict[str, Any] = {}
    try:
        if args.command == "discover":
            result = discover()
            print(json.dumps(result, ensure_ascii=False, indent=2))

        elif args.command == "overview":
            result = overview()
            print(json.dumps(result, ensure_ascii=False, indent=2))

        elif args.command == "check-data":
            result = check_data_source(args.env_file)
            print(json.dumps(result, ensure_ascii=False, indent=2))

        elif args.command == "explore":
            factor_list = None
            if args.factors:
                factor_list = [f.strip() for f in args.factors.split(",") if f.strip()]
            result = explore_factors(
                goal=args.goal, universe=args.universe, factor_set=args.factor_set,
                factors=factor_list, start=args.start, end=args.end,
                horizon=args.horizon, top_n=args.top_n, auto=args.auto,
                cache_dir=args.cache_dir, output_dir=args.output_dir,
            )
            if args.format == "markdown" and "markdown_report" in result:
                print(result["markdown_report"])
            else:
                print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

        elif args.command == "validate":
            result = validate_factor(
                factor_name=args.factor_name, ic_mean=args.ic_mean,
                ic_ir=args.ic_ir, oos_retention=args.oos_retention,
                decay_pct=args.decay_pct, ic_std=args.ic_std,
                cost_resilience=args.cost_resilience,
                sector_neutrality=args.sector_neutrality,
                segment_consistency=args.segment_consistency,
                validated_run_path=args.validated_run_path,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

        elif args.command == "evaluate-csv":
            result = evaluate_factor_csv(
                factor_csv=args.factor_csv, factor_name=args.factor_name,
                sector_col=args.sector_col, ic_threshold=args.ic_threshold,
                turnover_warn=args.turnover_warn,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

        elif args.command == "list-factors":
            result = list_factors(args.factor_set)
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

        elif args.command == "build":
            factor_names = None
            if args.factors:
                factor_names = [f.strip() for f in args.factors.split(",") if f.strip()]
            result = build_strategy(
                validated_run_path=args.validated_run,
                factor_names=factor_names,
                rebalance_frequency=args.rebalance_frequency,
                top_n=args.top_n, long_short=args.long_short,
                as_of=args.as_of, start=args.start, end=args.end,
                output_dir=args.output_dir,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

        elif args.command == "package":
            result = package_backtest(
                engine=args.engine, signal_path=args.signal_path,
                strategy_id=args.strategy, start=args.start, end=args.end,
                benchmark=args.benchmark, initial_cash=args.initial_cash,
                slippage_bps=args.slippage_bps, commission_bps=args.commission_bps,
                run_id=args.run_id, output_dir=args.output_dir,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

        elif args.command == "parse-result":
            result = parse_backtest_result(
                engine=args.engine, run_id=args.run_id, result_path=args.result_path,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

        elif args.command == "mine":
            result = mine_factor(
                name=args.name, expression=args.expression,
                description=args.description, start=args.start, end=args.end,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

        elif args.command == "auto-mine":
            result = auto_mine(theme=args.theme, start=args.start, end=args.end)
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

        elif args.command == "qlib-backtest":
            result = qlib_backtest(
                factor_expression=args.factor_expression,
                start=args.start, end=args.end,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    except Exception as exc:
        print(json.dumps({"error": str(exc), "error_type": type(exc).__name__}, ensure_ascii=False))
        _sys.exit(1)

    # Non-zero exit on structured errors so CI and agents can detect failures
    if isinstance(result, dict) and result.get("error") or result.get("status") == "error":
        _sys.exit(1)


if __name__ == "__main__":
    main()
