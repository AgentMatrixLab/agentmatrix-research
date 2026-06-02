# AgentMatrix Research Core

> Quantitative research framework: unified contracts, backtest adapters, strategy engine, and factor library for systematic alpha discovery.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

## What Is This?

`agentmatrix-research-core` is the research backbone of [AgentMatrixLab](https://agentmatrixlab.com). It provides:

- **Unified Contracts** — Standardized data structures for strategies, backtests, and attribution
- **Backtest Adapters** — Pluggable adapters for backtest engines (GM/掘金, RQAlpha, with more to come)
- **Strategy Engine** — Base classes and agent-style strategy implementations
- **Factor Library** — Factor definition, signal tracking, IC evaluation, and pseudo-backtest
- **Data Loaders** — AkShare-based A-share market data fetching utilities
- **Document Normalizer** — Research document processing via MinerU (DeerFlow copilot)

## Project Structure

```
agentmatrix-research-core/
├── common/                  # Shared utilities (paths, configs)
├── contracts/               # Data contracts & interfaces
│   ├── strategy.py          #   StrategyMetadata, StrategyDecision, TargetPosition
│   ├── backtest.py          #   BacktestRequest, BacktestResult, PerformanceMetrics
│   └── attribution.py       #   AttributionReport, AttributionSummary
├── research_core/           # Core research modules
│   ├── backtest_adapter/    #   GM adapter, RQAlpha adapter, result parsers
│   ├── strategy_engine/     #   Strategy base classes & agent engines
│   │   └── samples/         #     Runnable sample strategies
│   ├── attribution_engine/  #   Return attribution framework
│   ├── data_loader/         #   Market data fetching (AkShare)
│   ├── dataset_builder/     #   Dataset construction (scaffold)
│   └── risk_rule_engine/    #   Risk rule framework (scaffold)
├── registry/                #   Factor / Strategy / Run registries (scaffold)
├── data_layer/              #   Serving repositories (scaffold)
├── deerflow/                #   DeerFlow research copilot
│   └── research_copilot/
│       └── document_normalizer/
├── runtime/                 #   Runtime artifacts
└── scripts/                 #   Migration-era scripts (deprecated, use research_core/ instead)
```

## Quick Start

### Workflow Summary

1. **Fork** the repository to your GitHub account
2. **Clone** your fork locally
3. **Create a feature branch**: `git checkout -b feature/your-feature-name`
4. **Make changes** and test locally
5. **Commit** and **push** to your fork
6. **Create a Pull Request** to the original repository

### Prerequisites

- Python 3.10+
- [AkShare](https://github.com/akfamily/akshare) for market data
- [掘金量化](https://www.myquant.cn/) (optional, for GM backtest adapter)

### Install

```bash
git clone https://github.com/AgentMatrixLab/agentmatrix-research-core.git
cd agentmatrix-research-core
pip install -r scripts/requirements.txt
```

### Run a Sample Strategy

```python
from research_core.strategy_engine.samples.gm_small_cap_monthly import init, algo

# Or use the backtest adapter to generate an execution plan:
from research_core.backtest_adapter.example_gm_plan import main
main("gm_small_cap_monthly")
```

### Define a Custom Strategy

```python
from contracts.strategy import StrategyKernel, StrategyMetadata, StrategyDecision, StrategyContext

class MyStrategy(StrategyKernel):
    def metadata(self) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id="my-strategy-v1",
            name="My Custom Strategy",
            source_engine="custom",
        )

    def generate_decision(self, context: StrategyContext, market_data) -> StrategyDecision:
        # Your logic here
        ...
```

## Contracts

The `contracts/` module defines the canonical data structures used across all components:

| Contract | Purpose |
|----------|---------|
| `StrategyMetadata` | Strategy identity, version, tags |
| `StrategyDecision` | Target positions + diagnostics from a strategy run |
| `BacktestRequest` | Input specification for a backtest run |
| `BacktestResult` | Output: metrics, equity curve, trades, holdings |
| `AttributionReport` | Return decomposition by dimension |

These contracts enable **engine-agnostic** strategy development: write once, backtest on GM or RQAlpha without changing strategy code.

## Backtest Adapters

| Adapter | Status | Engine |
|---------|--------|--------|
| `GMBacktestAdapter` | ✅ Scaffold (execution plan generation) | [掘金量化](https://www.myquant.cn/) |
| `RQAlphaAdapter` | ✅ Scaffold (pickle result parsing) | [RQAlpha](https://github.com/ricequant/rqalpha) |
| `QlibAdapter` | 🔜 Planned | [Qlib](https://github.com/microsoft/qlib) |

## Contributing

We welcome contributions! Please follow these guidelines:

1. **New modules** → Place under `research_core/` (not `scripts/` or `backend/`)
2. **Contracts** → Extend `contracts/` for any new cross-component data structures
3. **Strategy samples** → Add to `research_core/strategy_engine/samples/`
4. **Code style** → Follow PEP 8, use type hints
5. **Sensitive data** → Never commit API keys, tokens, or real trading parameters. Use environment variables.

### Development Workflow

```bash
# Create a feature branch
git checkout -b feat/my-feature

# Make changes and test
python -m py_compile research_core/my_module.py

# Submit a PR to main
```

## Architecture Principles

1. **Contracts first** — Define the interface before the implementation
2. **Engine-agnostic** — Strategy code should not depend on a specific backtest engine
3. **Separation of concerns** — Strategy logic ≠ Data fetching ≠ Execution ≠ Attribution
4. **Reproducibility** — Every run produces a `BacktestResult` with full metadata

## Migration Notes

The `backend/` and `scripts/` directories are **legacy transition layers** from the original monorepo. New development should target `research_core/` and `contracts/` exclusively.

See [VERSION_UPDATE_2026-04-07.md](VERSION_UPDATE_2026-04-07.md) for the full migration history.

## License

This project is licensed under the [Apache License 2.0](LICENSE).

---

© 2025-2026 [AgentMatrixLab](https://agentmatrixlab.com)
