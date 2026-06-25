# Factor Lab Contributor Guide

> How to add a new factor library: from idea to merged PR in 5 steps.

## Overview

The AgentMatrix Research `factor_lab` is the central registry for quantitative
factors.  Each factor library—whether formula-based like `alpha101` or external
data-driven like `jq_gm`—lives under `research_core/factor_lab/libraries/`.

This guide covers the end-to-end workflow using `jq_gm` (the first non-formula
library, driven by GM SDK financial data) as the reference implementation.

## 1. Understand the Framework

Before writing code, read these files in order:

| File | What You Learn |
|------|---------------|
| `factor_lab/cli.py` | How CLI subcommands are registered (look for `factor_lab` parser) |
| `factor_lab/service.py` | Research job lifecycle: compute → evaluate → proof-template → proof-batch |
| `factor_lab/validation.py` | How `FactorResearchSpec` is validated and proof templates exported |
| `factor_lab/truth.py` | How truth CSV is loaded and compared against computed values |
| `libraries/alpha101/specs.py` | The canonical Spec format — study this before writing your own |

Then run the alpha101 demo to see the pipeline:

```bash
python -m research_core.factor_lab.cli run-alpha101-demo
```

## 2. Define Your Factor Specs

Each factor is a `FactorResearchSpec` dataclass.  Required fields:

| Field | Purpose | Example |
|-------|---------|---------|
| `factor_name` | Unique identifier, lowercase | `"pe_ttm"` |
| `display_name` | Human-readable name | `"PE (TTM)"` |
| `description` | What it measures; ≤60 chars | `"Price-to-earnings ratio trailing 4 quarters."` |
| `formula` | How it's calculated | `"tot_mv / net_profit_ttm"` |
| `frequency` | Always `"day"` for daily factors | `"day"` |
| `tags` | Category + sub-tags | `["valuation", "fundamental"]` |
| `source_document` | Provenance; what source defines this factor | `"JoinQuant Factor Board Taxonomy — GM SDK Implementation"` |
| `required_fields` | Raw data columns needed | `["tot_mv", "close"]` |
| `preprocessing` | Steps applied before computation | `["adjust_prices", "align_trading_calendar"]` |
| `validation_targets` | Acceptance thresholds | `[{"statistic": "coverage", "threshold": 0.8}]` |
| `metadata` | Library-specific fields; key for `jq_gm` | `{"gm_field": "stk_get_daily_mktvalue_pt", "gm_fields": "tot_mv"}` |

For non-formula libraries (like `jq_gm`), the `metadata` dict holds the
data-source routing information.  Every spec MUST have `gm_field` (the GM API
endpoint) or the compute engine won't know how to fetch data.

Specs go in `libraries/<your_lib>/specs.py`.

## 3. Implement the Compute Engine

Create `libraries/<your_lib>/factors.py` with a standardized function:

```python
def compute_<your_lib>_factors(
    panel: pd.DataFrame,
    factor_names: list[str],
    *,
    securities: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    **kwargs,
) -> pd.DataFrame:
    """Compute factor values.  Returns wide format: date, code, *factor_names."""
```

Key contract:
- **Input**: OHLCV panel DataFrame (date, code, OHLCV columns)
- **Output**: DataFrame with columns `[date, code, *factor_names]`
- **Stub mode**: When your data source is unavailable (CI, local dev), return a
  NaN-filled frame with correct columns — the pipeline must NOT crash.

The `jq_gm` library wraps GM (掘金) SDK via `gm_factor_lib.calc_factors()`.
In CI mode, it falls back to NaN stubs so unit tests and format validation
still run.

## 4. Write Tests

Minimum test coverage:

```python
# tests/libraries/<your_lib>/test_factors.py

class TestSpecFormat:
    """Every spec has required fields, unique names, consistent metadata."""
    def test_all_specs_have_required_fields(self): ...
    def test_all_specs_have_gm_metadata(self): ...
    def test_factor_names_are_unique(self): ...
    def test_spec_count_is_N(self): ...

class TestComputeStub:
    """Stub mode returns correct columns, handles empty factor list."""
    def test_stub_returns_correct_columns(self): ...
    def test_stub_handles_empty_factor_list(self): ...
```

Tests run in CI without any data-source credentials — stub mode ensures this.

## 5. Register CLI Commands and Submit PR

In `factor_lab/cli.py`, register your library's subcommands under the
`factor_lab` parser.  In `factor_lab/service.py`, add the research job
implementation that orchestrates demo → proof → evaluation.

CI gates that must pass:
1. **Unit tests** — `pytest research_core/factor_lab/`
2. **Coverage check** — every spec has `gm_field` + tests exist
3. **Regression check** — factor outputs stable between builds
4. **Proof-batch** — runs with truth CSV and generates validation report

## Reference: jq_gm File Layout

```
libraries/jq_gm/
├── __init__.py          # Module entry
├── specs.py             # 215 FactorResearchSpec across 10 categories
├── factors.py           # compute_jq_gm_factors() with stub fallback
└── test_factors.py      # 18 tests covering spec format + compute routing
```

Related files (at `factor_lab/` level):
```
factor_lab/
├── diagnostics.py       # 12 root-cause MISMATCH detectors (from CrossvalidationTYD)
├── nc_classifier.py     # 3-layer NC classifier with 127+ known patterns
├── service.py           # Research job orchestration
├── cli.py               # CLI registration
├── truth.py             # Truth CSV loading + comparison
└── validation.py        # Proof template generation
```

## When the Data Source Differs

If you're integrating a different data source (Wind, Tushare, Bloomberg):

1. Follow the same Spec format — `metadata` holds source-specific routing
2. Implement stub mode so CI never requires credentials
3. Document field mappings and unit scaling rules in `docs/<source>_mapping.md`
4. Register NC (not comparable) factors with detailed reasons

See `docs/gm_field_mapping.md` and `docs/unit_scale_rules.md` for examples.
