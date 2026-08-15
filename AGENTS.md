# AGENTS.md — AI Agent Entry Guide

> **Read this first.** This file is the universal front door for any AI agent
> (Claude, GPT, Trae, Cursor, WorkBuddy, ...) working with this codebase.

## TL;DR — Start Here

```python
from research_core.agent_api import discover, explore_factors

# Step 1: See what the framework can do
caps = discover()
for c in caps["capabilities"]:
    print(c["name"], "→", c["description"][:60])

# Step 2: Explore factors (the main workflow)
result = explore_factors(goal="momentum factors", universe="csi300")
print(result["gate_verdict"], result["summary"])
```

Or via CLI:

```bash
python -m research_core.agent_api discover
python -m research_core.agent_api explore --goal "momentum factors" --universe csi300
```

---

## What Is This Framework?

AgentMatrix Research is a **quantitative research framework** for systematic
alpha discovery in the A-share market. It provides:

- **Factor exploration** — Auto-fetch data, compute factors, evaluate IC/IR/OOS
- **Validation gates** — 7-gate quality control system (red/yellow/green verdicts)
- **Strategy building** — Turn validated factors into target weight signals
- **Backtest packaging** — Package signals for GM/PTrade/QMT external simulation
- **Qlib factor mining** — Expression-based factor mining and backtesting

---

## Capability Map — "I want to..."

| You want to... | Call this | CLI |
|---|---|---|
| See all capabilities | `discover()` | `discover` |
| Get framework overview | `overview()` | `overview` |
| Check data connectivity | `check_data_source()` | `check-data` |
| **Explore factors** (main entry) | `explore_factors()` | `explore` |
| Validate a factor's metrics | `validate_factor()` | `validate` |
| Evaluate factor from CSV | `evaluate_factor_csv()` | `evaluate-csv` |
| List available factors | `list_factors()` | `list-factors` |
| Build strategy signals | `build_strategy()` | `build` |
| Package for backtest | `package_backtest()` | `package` |
| Parse backtest result | `parse_backtest_result()` | `parse-result` |
| Mine a factor (Qlib) | `mine_factor()` | `mine` |
| Auto-mine factors (AI) | `auto_mine()` | `auto-mine` |
| Qlib expression backtest | `qlib_backtest()` | `qlib-backtest` |

---

## Decision Tree — Which Function Do I Call?

```
What are you trying to do?
│
├── "I just arrived, what can this framework do?"
│     └── discover()  →  read the capabilities list
│
├── "I want to find good factors"
│     └── explore_factors(goal="...", universe="csi300", factor_set="alpha101")
│           → returns gate_verdict (🟢/🟡/🔴), top_factors, summary,
│             report_path, artifacts (with job_path), next_actions
│
├── "I have factor metrics, are they good enough?"
│     └── validate_factor(factor_name="...", ic_mean=0.035, ic_ir=0.45, oos_retention=0.75)
│           → returns passed (bool), gates, fail_reasons, pass_reasons
│
├── "I have a CSV with factor values, evaluate it"
│     └── evaluate_factor_csv(factor_csv="data.csv", factor_name="momentum_20d")
│           → returns status, mean_rank_ic, rank_icir, turnover, warnings
│
├── "What factors are available?"
│     └── list_factors(factor_set="alpha101")
│           → returns list of factors with implementation/proof status
│
├── "Factors passed validation, build a strategy"
│     └── build_strategy(validated_run_path="runtime/factor_lab/jobs/xxx.json")
│           → returns strategy_id, artifacts (with signals/config)
│
├── "Strategy is ready, package for backtest"
│     └── package_backtest(engine="gm", signal_path="target_weights.csv", start=..., end=...)
│           → returns package_dir, artifacts
│
├── "Backtest finished, parse the result"
│     └── parse_backtest_result(engine="gm", run_id="...", result_path="result.pkl")
│           → returns run_id, engine, status, metrics, source_path, artifacts, diagnostics
│
├── "I want to mine new factors with Qlib"
│     ├── mine_factor(name="reversal", expression="Ref($close, 5) / $close - 1")
│     │     → returns factor_name, ic_mean, ic_ir, rank_ic_mean, long_short_spread,
│     │       definition, evaluation, top_metrics, status
│     ├── auto_mine(theme="mid-cap momentum with turnover confirmation")
│     │     → returns theme, generated_count, results, candidates, best_factor, best_ic
│     └── qlib_backtest(factor_expression="($close / Ref($close, 20) - 1)")
│           → returns expression, annualized_return, sharpe_ratio, max_drawdown,
│             total_return, volatility, win_rate, metrics, equity_curve
│
└── "I need to check if the data source is available"
      └── check_data_source()
            → returns connected (bool), details, next_actions
```

---

## The Full Research Pipeline

This is the end-to-end workflow an AI agent should follow:

```
1. discover()           → Understand capabilities
2. check_data_source()  → Verify data is available
3. explore_factors()    → Find good factors (🟢/🟡/🔴 verdict)
4. validate_factor()    → Confirm specific factors pass gates
5. build_strategy()     → Turn factors into target weights
6. package_backtest()   → Package for GM/PTrade/QMT simulation
7. parse_backtest_result() → Parse simulation results
```

Each step's output includes `next_actions` telling you what to do next.

---

## Design Principles (Why AI Agents Like This API)

1. **Self-describing** — Call `discover()` to see everything. No need to read
   source code or docs.

2. **Structured returns** — Every function returns JSON-serializable dicts.
   No raw objects, no print statements to parse.

3. **Actionable errors** — Errors come with `suggested_fix` fields, not just
   tracebacks. Missing dependency? It tells you what to install.

4. **Next actions** — Results include `next_actions` lists, so the agent
   always knows what to do next without guessing.

5. **Dual interface** — Every function has both a Python API and a CLI
   command. Use whichever is more convenient.

6. **No hidden state** — Functions are stateless. Call them in any order,
   repeat calls, parallelize — no surprises.

---

## Environment Setup

### Prerequisites

- Python 3.10+
- Dependencies: `pip install -r scripts/requirements.txt -r requirements-factor-lab.txt`

### Quick Verify

```bash
# Verify the agent API is importable
python -c "from research_core.agent_api import discover; print(discover()['framework'])"

# See all capabilities
python -m research_core.agent_api discover
```

### Working Directory

All commands should be run from the **project root** (the directory containing
`research_core/`, `contracts/`, `backend/`).

---

## Factor Families

| Family | Code | Factors | Description |
|---|---|---|---|
| Alpha101 | `alpha101` | 101 | WorldQuant 101 Alphas |
| WQ101 | `wq101` | 10 (of 101) | WorldQuant Alpha 1-10 |
| GTJA191 | `gtja191` | 191 | 国泰君安 191 Alphas |
| Alpha158 | `alpha158` | 158 | Qlib Alpha158 standard set |
| Barra | `barra` | 10 | Barra style factors |

---

## Universes

| Code | Description |
|---|---|
| `csi300` | 沪深300 (default) |
| `csi500` | 中证500 |
| `csi800` | 沪深800 |
| `all` | All A-share |

---

## Backtest Engines

| Engine | Code | Type |
|---|---|---|
| 掘金量化 | `gm` | External simulation |
| PTrade | `ptrade` | External simulation |
| QMT | `qmt` | External simulation |
| RQAlpha | `rqalpha` | Internal (pickle parse) |
| Qlib | `qlib` | Internal (expression) |

---

## Common Patterns

### Pattern 1: Quick Factor Screen

```python
from research_core.agent_api import explore_factors

result = explore_factors(
    goal="low volatility quality factors",
    universe="csi300",
    factor_set="alpha101",
    start="2023-01-01",
    end="2025-12-31",
)

if result["gate_verdict"] == "🟢":
    print("Good factors found!")
    for f in result["top_factors"][:5]:
        print(f"  {f['name']}: IC={f['ic_mean']}, IR={f['ic_ir']}")
else:
    print("Need to try different factors or parameters")
    for action in result["next_actions"]:
        print(f"  → {action}")
```

### Pattern 2: Validate Then Build

```python
from research_core.agent_api import validate_factor, build_strategy

# Validate
v = validate_factor("alpha1", ic_mean=0.035, ic_ir=0.45, oos_retention=0.75)
if v["passed"]:
    # Build strategy from a validated run
    s = build_strategy(
        validated_run_path="runtime/factor_lab/jobs/abc123.json",
        top_n=50,
        rebalance_frequency="daily",
    )
    print(f"Strategy signals at: {s['artifacts']['signals']}")
```

### Pattern 3: Full Pipeline

```python
from research_core.agent_api import (
    discover, check_data_source, explore_factors,
    build_strategy, package_backtest,
)

# 1. Check environment
check_data_source()

# 2. Explore
result = explore_factors(goal="momentum", universe="csi300")

# 3. Build (if green)
if result["gate_verdict"] in ("🟢", "🟡"):
    job_path = result.get("artifacts", {}).get("job_path", "")
    if job_path:
        strategy = build_strategy(validated_run_path=job_path)

        # 4. Package
        pkg = package_backtest(
            engine="gm",
            signal_path=strategy["artifacts"]["signals"],
            start="2023-01-01",
            end="2025-12-31",
        )
        print(f"Ready for GM simulation: {pkg['package_dir']}")
```

---

## Error Handling

All functions catch exceptions and return structured error dicts:

```python
result = explore_factors(...)
if "error" in result:
    print(f"Error: {result['error']}")
    print(f"Fix:  {result['suggested_fix']}")
else:
    # Process successful result
    ...
```

Common error patterns:

| Error | Cause | Fix |
|---|---|---|
| `Missing dependency` | Package not installed | `pip install -r scripts/requirements.txt` |
| `File not found` | Wrong path | Use `overview()` to see workspace paths |
| `No gates applicable` | Insufficient metrics | Provide more metrics to `validate_factor()` |

---

## For Skill Authors

If you are creating a `.trae/skills/` or `.workbuddy/skills/` SKILL.md for this
framework, reference the agent API:

```markdown
## Commands

# Discover capabilities
python -m research_core.agent_api discover

# Explore factors
python -m research_core.agent_api explore --goal "momentum" --universe csi300

# Validate
python -m research_core.agent_api validate --factor-name alpha1 --ic-mean 0.035 --ic-ir 0.45 --oos-retention 0.75
```

The manifest at `research_core/agent_manifest.py` is the single source of truth
for capability definitions. Update it when adding new functions to `agent_api.py`.

---

## File Map

| File | Purpose |
|---|---|
| `AGENTS.md` (this file) | Universal AI agent entry guide |
| `research_core/agent_api.py` | Unified Python API + CLI |
| `research_core/agent_manifest.py` | Self-describing capability manifest |
| `research_core/factor_lab/agent_pipeline.py` | Factor exploration pipeline |
| `research_core/factor_lab/validation_gate.py` | 7-gate validation system |
| `research_core/factor_lab/cli.py` | Factor Lab CLI (legacy, still works) |
| `research_core/strategy_engine/cli.py` | Strategy engine CLI (legacy, still works) |
| `research_core/backtest_adapter/cli.py` | Backtest adapter CLI (legacy, still works) |
| `research_core/qlib_lab/cli.py` | Qlib Lab CLI (legacy, still works) |
| `contracts/` | Data contracts (StrategyMetadata, BacktestResult, etc.) |

---

## Version

Agent API v1.0.0 — see `research_core/agent_manifest.py` for the canonical version.
