# AgentMatrix Research

> Quantitative research framework: unified contracts, backtest adapters, strategy engine, and factor library for systematic alpha discovery.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)



## For AI Agents

**If you are an AI agent (Claude, GPT, Trae, Cursor, WorkBuddy, …), read [`AGENTS.md`](AGENTS.md) first.**

`AGENTS.md` is a lightweight navigation entry that points to existing modules,
CLI entry points, bundled Skills and relevant docs.


- GitHub Pages portal: [agentmatrixlab.github.io/agentmatrix-research](https://agentmatrixlab.github.io/agentmatrix-research/)
- Use the portal for repo navigation, docs entry, workflow links, and common test commands.

## What Is This?

`agentmatrix-research` is the research backbone of [AgentMatrixLab](https://agentmatrixlab.com). It provides:

- **Unified Contracts** — Standardized data structures for strategies, backtests, and attribution
- **Backtest Adapters** — Pluggable adapters for backtest engines (GM/掘金, RQAlpha, with more to come)
- **Strategy Engine** — Base classes and agent-style strategy implementations
- **Factor Library** — Factor definition, signal tracking, IC evaluation, and pseudo-backtest
- **Factor Lab** — Unified factor specification, catalog export, proof package, and multi-library roadmap
- **Qlib Lab** — Factor mining, factor reproduction, AI-assisted factor generation, and qlib-based validity backtests
- **Data Loaders** — AkShare-based A-share market data fetching utilities
- **Document Normalizer** — Research document processing via MinerU (DeerFlow copilot)

## Project Structure

```
agentmatrix-research/
├── common/                  # Shared utilities (paths, configs)
├── contracts/               # Data contracts & interfaces
│   ├── strategy.py          #   StrategyMetadata, StrategyDecision, TargetPosition
│   ├── backtest.py          #   BacktestRequest, BacktestResult, PerformanceMetrics
│   └── attribution.py       #   AttributionReport, AttributionSummary
├── research_core/           # Core research modules
│   ├── backtest_adapter/    #   GM adapter, RQAlpha adapter, result parsers
│   ├── factor_lab/          #   Unified factor specs, registry, and validation proof templates
│   ├── qlib_lab/            #   Qlib-based factor mining and backtest workflow
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

### Prerequisites

- Python 3.10+
- [AkShare](https://github.com/akfamily/akshare) for market data
- [Qlib](https://github.com/microsoft/qlib) for factor research workflow
- [掘金量化](https://www.myquant.cn/) (optional, for GM backtest adapter)

### Install

```bash
git clone https://github.com/AgentMatrixLab/agentmatrix-research.git
cd agentmatrix-research
pip install -r scripts/requirements.txt
pip install -r requirements-factor-lab.txt
```

### Qlib Factor Workflow

```bash
python -m research_core.qlib_lab.cli init-data
python -m research_core.qlib_lab.cli mine-factor --name short_term_reversal --expression "Ref($close, 5) / $close - 1" --description "5-day reversal factor" --start 2021-01-01 --end 2024-12-31
python -m research_core.qlib_lab.cli auto-mine --theme "mid-cap momentum with turnover confirmation" --start 2021-01-01 --end 2024-12-31
python -m research_core.qlib_lab.cli backtest --factor-expression "($close / Ref($close, 20) - 1) * Log($volume / Ref($volume, 20))" --start 2021-01-01 --end 2024-12-31
python -m research_core.qlib_lab.cli alpha158-template
python -m research_core.qlib_lab.cli alpha158-starter --market csi300 --benchmark SH000300
```

See [QLIB_FACTOR_WORKFLOW.md](docs/QLIB_FACTOR_WORKFLOW.md) for the full intern workflow.
See [ALPHA158_STARTER.md](docs/ALPHA158_STARTER.md) for the baseline model workflow.
See [FACTOR_LAB_BACKEND_BOUNDARY.md](docs/FACTOR_LAB_BACKEND_BOUNDARY.md) for the back-end vs front-end ownership split.
See [FACTOR_LAB_ALPHA101_WORKFLOW.md](docs/FACTOR_LAB_ALPHA101_WORKFLOW.md) for the unified Alpha101 back-end research workflow.
See [AMAZINGDATA_ALPHA_PIPELINE.md](docs/AMAZINGDATA_ALPHA_PIPELINE.md) for the amazingdata internal-validation to external-simulation workflow.
See [CONTRIBUTING.md](CONTRIBUTING.md) for PR, factor proposal, and experiment report conventions.

### Factor Lab Bootstrap

```bash
python -m research_core.factor_lab.cli init-workspace
python -m research_core.factor_lab.cli overview
python -m research_core.factor_lab.cli list-alpha101
python -m research_core.factor_lab.cli export-alpha101 --proof-factor alpha101
python -m research_core.factor_lab.cli export-alpha101-truth-template --n-dates 420 --n-codes 8 --seed 29
python -m research_core.factor_lab.cli validate-alpha101-truth --truth-csv data/factor_lab/alpha101_truth_template_101f_420d_8c_s29.csv
python -m research_core.factor_lab.cli run-alpha101-proof-batch --truth-csv data/factor_lab/alpha101_truth_template_101f_420d_8c_s29.csv --n-dates 420 --n-codes 8 --seed 29
python -m research_core.factor_lab.cli check-amazingdata
python -m research_core.factor_lab.cli run-factor-research --factor-set wq101 --data-source demo --n-dates 160 --n-codes 8 --seed 7
python -m research_core.strategy_engine.cli build-alpha-strategy --validated-run runtime/factor_lab/jobs/<job_id>.json --rebalance-frequency daily --top-n 50
```

### Factor Lab Truth Compare (factor values validation)

Upload-style factor values are compared point-by-point against the library truth
(local CSV or Supabase `factor_truth_values`). Fully testable offline:

```bash
python -m research_core.factor_lab.cli export-alpha101-truth-template --n-dates 60 --n-codes 5 --seed 29
python scripts/dev/make_truth_compare_samples.py
python scripts/run_truth_compare.py --factor-family alpha101 --factor-name alpha1 \
  --values-csv data/factor_lab/samples/factor_values_alpha1_pass.csv \
  --truth-csv data/factor_lab/alpha101_truth_template_101f_60d_5c_s29.csv
