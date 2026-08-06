#!/usr/bin/env python3
"""
Agent Manifest — Self-describing capability registry.

AI agents call ``get_manifest()`` to discover everything this framework can do,
without reading source code or docs. Each capability includes a name, description,
parameter schema, and a copy-paste-ready example.

Usage::

    from research_core.agent_manifest import get_manifest
    manifest = get_manifest()
    for cap in manifest["capabilities"]:
        print(cap["name"], "-", cap["description"])
"""

from __future__ import annotations

import copy
import json
from typing import Any


# ── Capability definitions ─────────────────────────────────────────────────

_CAPABILITIES: list[dict[str, Any]] = [
    # ── Discovery ──────────────────────────────────────────────
    {
        "name": "discover",
        "category": "meta",
        "description": "List all framework capabilities with parameters and examples. "
                       "Always call this first to understand what the framework can do.",
        "function": "research_core.agent_api.discover",
        "cli": "python -m research_core.agent_api discover",
        "parameters": {},
        "returns": "Dict with 'framework', 'version', 'capabilities' list",
        "example": "from research_core.agent_api import discover\nresult = discover()",
    },

    # ── Factor Exploration ─────────────────────────────────────
    {
        "name": "explore_factors",
        "category": "factor_research",
        "description": "One-click factor exploration: auto-fetch market data, compute "
                       "factors, evaluate IC/IR/OOS, run validation gates, return a "
                       "structured verdict (red/yellow/green). This is the main entry "
                       "point for factor research.",
        "function": "research_core.agent_api.explore_factors",
        "cli": "python -m research_core.agent_api explore --goal 'low volatility quality' --universe csi300 --factor-set alpha101",
        "parameters": {
            "goal": {"type": "str", "default": "", "description": "Human-readable research goal"},
            "universe": {"type": "str", "default": "csi300", "options": ["csi300", "csi500", "csi800", "all"]},
            "factor_set": {"type": "str", "default": "alpha101", "options": ["alpha101", "wq101", "gtja191", "alpha158", "barra"]},
            "factors": {"type": "list[str] or None", "default": "None (auto top-10)"},
            "start": {"type": "str", "default": "2023-01-01"},
            "end": {"type": "str", "default": "2025-12-31"},
            "horizon": {"type": "int", "default": 5, "description": "Forward return horizon in days"},
            "top_n": {"type": "int", "default": 10},
            "auto": {"type": "bool", "default": True, "description": "If True, auto-fetch data and auto-select factors"},
            "cache_dir": {"type": "str", "default": "", "description": "Cache directory for market data"},
        },
        "returns": "ExploreResult with gate_verdict, top_factors, summary, report_path, artifacts, next_actions",
        "example": (
            "from research_core.agent_api import explore_factors\n"
            "result = explore_factors(goal='momentum factors', universe='csi500')\n"
            "print(result['gate_verdict'], result['summary'])"
        ),
    },

    # ── Factor Validation ──────────────────────────────────────
    {
        "name": "validate_factor",
        "category": "factor_research",
        "description": "Run the 7-gate validation system on a single factor's metrics. "
                       "Returns pass/fail with human-readable reasons and actionable next steps.",
        "function": "research_core.agent_api.validate_factor",
        "cli": "python -m research_core.agent_api validate --factor-name alpha1 --ic-mean 0.035 --ic-ir 0.45 --oos-retention 0.75",
        "parameters": {
            "factor_name": {"type": "str", "required": True},
            "ic_mean": {"type": "float", "required": True, "description": "Mean Information Coefficient"},
            "ic_ir": {"type": "float", "required": True, "description": "IC Information Ratio (mean/std)"},
            "oos_retention": {"type": "float", "default": 0.0, "description": "Out-of-sample IC retention ratio"},
            "decay_pct": {"type": "float", "default": 0.0, "description": "IC time decay percentage"},
            "ic_std": {"type": "float", "default": 0.0},
            "cost_resilience": {"type": "bool or None", "default": "None", "description": "Whether factor survives 50bp cost"},
            "sector_neutrality": {"type": "float or None", "default": "None"},
            "segment_consistency": {"type": "int or None", "default": "None"},
            "validated_run_path": {"type": "str", "default": "", "description": "Optional path to the source job JSON; passed through for linking to build_strategy()"},
        },
        "returns": "Dict with 'passed', 'gates', 'fail_reasons', 'pass_reasons', 'validated_run_path'",
        "example": (
            "from research_core.agent_api import validate_factor\n"
            "v = validate_factor('alpha1', ic_mean=0.035, ic_ir=0.45, oos_retention=0.75)\n"
            "print('PASS' if v['passed'] else 'FAIL', v['fail_reasons'])"
        ),
    },

    # ── Factor Evaluation (from CSV) ───────────────────────────
    {
        "name": "evaluate_factor_csv",
        "category": "factor_research",
        "description": "Full IC evaluation from a CSV file containing date, code, "
                       "factor_value, next_return columns. Computes rank IC, IC decay, "
                       "turnover, and sector neutrality.",
        "function": "research_core.agent_api.evaluate_factor_csv",
        "cli": "python -m research_core.agent_api evaluate-csv --factor-csv data.csv --factor-name momentum_20d",
        "parameters": {
            "factor_csv": {"type": "str", "required": True, "description": "Path to CSV file"},
            "factor_name": {"type": "str", "default": "factor"},
            "sector_col": {"type": "str", "default": "sector"},
            "ic_threshold": {"type": "float", "default": 0.02},
            "turnover_warn": {"type": "float", "default": 0.7},
        },
        "returns": "Dict with factor_name, status, mean_rank_ic, rank_icir, ic_positive_ratio, mean_turnover, warnings",
        "example": (
            "from research_core.agent_api import evaluate_factor_csv\n"
            "report = evaluate_factor_csv('my_factor.csv', factor_name='momentum_20d')\n"
            "print(report['status'], report['mean_rank_ic'])"
        ),
    },

    # ── List Available Factors ─────────────────────────────────
    {
        "name": "list_factors",
        "category": "factor_research",
        "description": "List all available factors in a given factor family with their "
                       "implementation status and proof status.",
        "function": "research_core.agent_api.list_factors",
        "cli": "python -m research_core.agent_api list-factors --factor-set alpha101",
        "parameters": {
            "factor_set": {"type": "str", "default": "alpha101", "options": ["alpha101", "wq101", "gtja191", "alpha158", "barra"]},
        },
        "returns": "Dict with factor_set, count, items (list of factor dicts)",
        "example": (
            "from research_core.agent_api import list_factors\n"
            "result = list_factors('alpha101')\n"
            "for f in result['items']: print(f['factor_name'], f['proof_status'])"
        ),
    },

    # ── Build Strategy ─────────────────────────────────────────
    {
        "name": "build_strategy",
        "category": "strategy",
        "description": "Build target weight signals from a validated factor research run. "
                       "Takes a factor_lab job JSON and produces target weights for "
                       "long-only or long-short strategies.",
        "function": "research_core.agent_api.build_strategy",
        "cli": "python -m research_core.agent_api build --validated-run runtime/factor_lab/jobs/<job_id>.json --rebalance-frequency daily --top-n 50",
        "parameters": {
            "validated_run_path": {"type": "str", "required": True, "description": "Path to factor_lab job JSON"},
            "factor_names": {"type": "list[str] or None", "default": "None (use job defaults)"},
            "rebalance_frequency": {"type": "str", "default": "daily", "options": ["single", "daily", "weekly", "monthly"]},
            "top_n": {"type": "int", "default": 50, "description": "Number of names per side"},
            "long_short": {"type": "bool", "default": False},
            "as_of": {"type": "str", "default": "", "description": "Single snapshot date (forces 'single' frequency)"},
            "start": {"type": "str", "default": ""},
            "end": {"type": "str", "default": ""},
        },
        "returns": "Dict with strategy_id, signal_path, artifacts (with signals/config)",
        "example": (
            "from research_core.agent_api import build_strategy\n"
            "result = build_strategy('runtime/factor_lab/jobs/abc123.json', top_n=50)\n"
            "print(result['strategy_id'], result['artifacts']['signals'])"
        ),
    },

    # ── Package External Simulation ────────────────────────────
    {
        "name": "package_backtest",
        "category": "backtest",
        "description": "Package target weight signals for external backtest engines "
                       "(GM/掘金, PTrade, QMT). Produces engine-specific simulation files.",
        "function": "research_core.agent_api.package_backtest",
        "cli": "python -m research_core.agent_api package --engine gm --signal-path target_weights.csv --start 2023-01-01 --end 2025-12-31",
        "parameters": {
            "engine": {"type": "str", "required": True, "options": ["gm", "ptrade", "qmt"]},
            "signal_path": {"type": "str", "required": True, "description": "Path to target weights CSV"},
            "strategy_id": {"type": "str", "default": "alpha_strategy"},
            "start": {"type": "str", "required": True},
            "end": {"type": "str", "required": True},
            "benchmark": {"type": "str", "default": ""},
            "initial_cash": {"type": "float", "default": 1000000.0},
            "slippage_bps": {"type": "float", "default": 0.0},
            "commission_bps": {"type": "float", "default": 0.0},
        },
        "returns": "Dict with run_id, engine, package_dir, package_path, artifacts (signals, config, etc.)",
        "example": (
            "from research_core.agent_api import package_backtest\n"
            "pkg = package_backtest(engine='gm', signal_path='target_weights.csv',\n"
            "                       start='2023-01-01', end='2025-12-31')\n"
            "print(pkg['package_dir'])"
        ),
    },

    # ── Parse External Result ──────────────────────────────────
    {
        "name": "parse_backtest_result",
        "category": "backtest",
        "description": "Parse an external backtest engine's result file into a "
                       "standardized BacktestResult contract with metrics, equity curve, "
                       "and trades.",
        "function": "research_core.agent_api.parse_backtest_result",
        "cli": "python -m research_core.agent_api parse-result --engine gm --run-id abc123 --result-path result.pkl",
        "parameters": {
            "engine": {"type": "str", "required": True, "options": ["gm", "ptrade", "qmt"]},
            "run_id": {"type": "str", "required": True},
            "result_path": {"type": "str", "required": True, "description": "Path to engine result file"},
        },
        "returns": "Dict with run_id, engine, metrics, equity_curve, trades",
        "example": (
            "from research_core.agent_api import parse_backtest_result\n"
            "result = parse_backtest_result(engine='gm', run_id='abc', result_path='result.pkl')\n"
            "print(result['metrics'])"
        ),
    },

    # ── Qlib Factor Mining ─────────────────────────────────────
    {
        "name": "mine_factor",
        "category": "qlib_lab",
        "description": "Mine a single factor using Qlib expression syntax. Computes the "
                       "factor, evaluates IC, and optionally runs a backtest.",
        "function": "research_core.agent_api.mine_factor",
        "cli": "python -m research_core.agent_api mine --name short_term_reversal --expression 'Ref($close, 5) / $close - 1' --start 2021-01-01 --end 2024-12-31",
        "parameters": {
            "name": {"type": "str", "required": True, "description": "Factor name"},
            "expression": {"type": "str", "required": True, "description": "Qlib expression, e.g. 'Ref($close, 5) / $close - 1'"},
            "description": {"type": "str", "default": ""},
            "start": {"type": "str", "default": "2021-01-01"},
            "end": {"type": "str", "default": "2024-12-31"},
        },
        "returns": "Dict with factor_name, expression, ic_mean, ic_ir, rank_ic_mean, long_short_spread, status, definition, evaluation, top_metrics",
        "example": (
            "from research_core.agent_api import mine_factor\n"
            "result = mine_factor('reversal_5d', 'Ref($close, 5) / $close - 1')\n"
            "print(result['ic_mean'], result['status'])"
        ),
    },

    # ── Qlib Auto Mining ───────────────────────────────────────
    {
        "name": "auto_mine",
        "category": "qlib_lab",
        "description": "AI-assisted automatic factor mining. Provide a theme description "
                       "and Qlib generates and evaluates candidate factor expressions.",
        "function": "research_core.agent_api.auto_mine",
        "cli": "python -m research_core.agent_api auto-mine --theme 'mid-cap momentum with turnover confirmation' --start 2021-01-01 --end 2024-12-31",
        "parameters": {
            "theme": {"type": "str", "required": True, "description": "Natural language factor theme"},
            "start": {"type": "str", "default": "2021-01-01"},
            "end": {"type": "str", "default": "2024-12-31"},
        },
        "returns": "Dict with theme, generated_count, results (list of candidate dicts with definition/evaluation/top_metrics), candidates (summary list), best_factor, best_ic",
        "example": (
            "from research_core.agent_api import auto_mine\n"
            "result = auto_mine('low volatility quality factors')\n"
            "print(result['best_factor'], result['best_ic'])"
        ),
    },

    # ── Qlib Backtest ──────────────────────────────────────────
    {
        "name": "qlib_backtest",
        "category": "qlib_lab",
        "description": "Run a Qlib factor-expression backtest with full performance metrics.",
        "function": "research_core.agent_api.qlib_backtest",
        "cli": "python -m research_core.agent_api qlib-backtest --factor-expression '($close / Ref($close, 20) - 1) * Log($volume / Ref($volume, 20))' --start 2021-01-01 --end 2024-12-31",
        "parameters": {
            "factor_expression": {"type": "str", "required": True},
            "start": {"type": "str", "default": "2021-01-01"},
            "end": {"type": "str", "default": "2024-12-31"},
        },
        "returns": "Dict with expression, annualized_return, sharpe_ratio, max_drawdown, total_return, volatility, win_rate, metrics, equity_curve",
        "example": (
            "from research_core.agent_api import qlib_backtest\n"
            "result = qlib_backtest('($close / Ref($close, 20) - 1)')\n"
            "print(result['sharpe_ratio'])"
        ),
    },

    # ── Framework Overview ─────────────────────────────────────
    {
        "name": "overview",
        "category": "meta",
        "description": "Get framework overview: workspace paths, available factor families, "
                       "installed libraries, and runtime status.",
        "function": "research_core.agent_api.overview",
        "cli": "python -m research_core.agent_api overview",
        "parameters": {},
        "returns": "Dict with workspace, factor_families, backtest_engines, external_sim_engines, data_sources, next_actions",
        "example": "from research_core.agent_api import overview\nprint(overview())",
    },

    # ── Check Data Source ──────────────────────────────────────
    {
        "name": "check_data_source",
        "category": "data",
        "description": "Check connectivity and status of the amazingdata ClickHouse data source. "
                       "Returns connection status, available tables, and row counts.",
        "function": "research_core.agent_api.check_data_source",
        "cli": "python -m research_core.agent_api check-data",
        "parameters": {
            "env_file": {"type": "str", "default": "", "description": "Optional ClickHouse env file path"},
        },
        "returns": "Dict with connected, tables, error",
        "example": "from research_core.agent_api import check_data_source\nprint(check_data_source())",
    },
]


# ── Category metadata ───────────────────────────────────────────────────────

_CATEGORIES = {
    "meta": {
        "label": "Framework Discovery",
        "description": "Discover capabilities, get overview, check data sources",
    },
    "factor_research": {
        "label": "Factor Research",
        "description": "Explore, validate, and evaluate alpha factors",
    },
    "strategy": {
        "label": "Strategy Building",
        "description": "Build target weight signals from validated factors",
    },
    "backtest": {
        "label": "Backtest & Simulation",
        "description": "Package and parse external backtest engine results",
    },
    "qlib_lab": {
        "label": "Qlib Factor Lab",
        "description": "Factor mining and expression-based backtesting via Qlib",
    },
    "data": {
        "label": "Data Sources",
        "description": "Check and manage market data sources",
    },
}


def get_manifest() -> dict[str, Any]:
    """
    Return the full capability manifest.

    AI agents should call this first to discover everything the framework can do.
    """
    return {
        "framework": "AgentMatrix Research",
        "version": "1.0.0",
        "description": (
            "Quantitative research framework for systematic alpha discovery: "
            "factor exploration, validation gates, strategy building, and backtest packaging."
        ),
        "language": "Python 3.10+",
        "categories": copy.deepcopy(_CATEGORIES),
        "capabilities": copy.deepcopy(_CAPABILITIES),
        "entry_points": {
            "python_api": "from research_core.agent_api import discover, explore_factors, ...",
            "cli": "python -m research_core.agent_api <command>",
            "agent_guide": "See AGENTS.md at repository root",
        },
        "quick_start": {
            "discover": "from research_core.agent_api import discover; print(discover())",
            "explore": (
                "from research_core.agent_api import explore_factors\n"
                "result = explore_factors(goal='momentum factors', universe='csi300')\n"
                "print(result['gate_verdict'], result['summary'])"
            ),
        },
        "design_principles": [
            "Every function returns structured, JSON-serializable results",
            "Every result includes actionable 'next_actions' when applicable",
            "Errors include suggested fixes, not just tracebacks",
            "The manifest is the single source of truth for capabilities",
            "CLI and Python API are always in sync",
        ],
    }


def get_capabilities_by_category(category: str) -> list[dict[str, Any]]:
    """Filter capabilities by category."""
    return [c for c in _CAPABILITIES if c["category"] == category]


def get_capability(name: str) -> dict[str, Any] | None:
    """Look up a single capability by name."""
    for c in _CAPABILITIES:
        if c["name"] == name:
            return c
    return None


def manifest_to_markdown() -> str:
    """Render the manifest as agent-readable markdown."""
    m = get_manifest()
    lines = [
        f"# {m['framework']} — Capability Manifest",
        "",
        m["description"],
        "",
        f"**Version**: {m['version']} | **Language**: {m['language']}",
        "",
        "## Design Principles",
        "",
    ]
    for p in m["design_principles"]:
        lines.append(f"- {p}")

    lines.append("")
    lines.append("## Capabilities by Category")
    lines.append("")

    for cat_key, cat_info in m["categories"].items():
        lines.append(f"### {cat_info['label']} (`{cat_key}`)")
        lines.append(f"_{cat_info['description']}_")
        lines.append("")
        caps = get_capabilities_by_category(cat_key)
        for cap in caps:
            lines.append(f"#### `{cap['name']}`")
            lines.append(f"{cap['description']}")
            lines.append(f"")
            lines.append(f"**Python**: `{cap['function']}`")
            lines.append(f"**CLI**: `{cap['cli']}`")
            lines.append(f"**Returns**: {cap['returns']}")
            if cap["parameters"]:
                lines.append(f"")
                lines.append(f"| Parameter | Type | Required | Default | Description |")
                lines.append(f"|-----------|------|----------|---------|-------------|")
                for pname, pinfo in cap["parameters"].items():
                    req = "Yes" if pinfo.get("required") else "No"
                    default = pinfo.get("default", "")
                    desc = pinfo.get("description", "")
                    lines.append(f"| `{pname}` | {pinfo['type']} | {req} | {default} | {desc} |")
            lines.append(f"")
            lines.append(f"**Example**:")
            lines.append(f"```python")
            lines.append(cap["example"])
            lines.append(f"```")
            lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    print(json.dumps(get_manifest(), ensure_ascii=False, indent=2))
