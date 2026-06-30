# Amazingdata Alpha Pipeline

This document defines the AgentMatrix alpha research path from source discovery to internal validation, external terminal simulation, and live-readiness gates.

## Workflow

1. `feeder` prepares `alpha_resource.md` from a paper, report, or local source.
2. `factor_lab` converts the idea into `FactorResearchSpec`, computes the factor, and validates it on deterministic demo data or amazingdata.
3. Internal validation writes data-quality, panel snapshot, evaluation, proof, and red-flag artifacts under `runtime/factor_lab/`.
4. Validated factor frames are converted into target weights by `research_core.strategy_engine.alpha_strategy`.
5. External simulation packages are generated for `gm`, `ptrade`, or `qmt` under `runtime/external_sim/`.
6. Terminal simulation results are parsed back into AgentMatrix before any live-readiness promotion.

## Commands

Check amazingdata:

```bash
python -m research_core.factor_lab.cli check-amazingdata
```

Run internal validation on amazingdata:

```bash
python -m research_core.factor_lab.cli run-factor-research --factor-set wq101 --data-source amazingdata --start 2023-01-01 --end 2025-12-31 --universe csi800 --max-symbols 300
```

Run a deterministic smoke test:

```bash
python -m research_core.factor_lab.cli run-factor-research --factor-set wq101 --data-source demo --n-dates 160 --n-codes 8 --seed 7
```

Build strategy signals from a validated job:

```bash
python -m research_core.strategy_engine.cli build-alpha-strategy --validated-run runtime/factor_lab/jobs/<job_id>.json --top-n 50
```

Package external simulation:

```bash
python -m research_core.backtest_adapter.cli package-external-sim --engine gm --strategy <strategy_id> --signal-path runtime/strategy_engine/<strategy_id>/target_weights.csv --start 2023-01-01 --end 2025-12-31
```

## Lifecycle Gates

Valid states are:

```text
candidate -> implemented -> internal_validated -> strategy_candidate -> external_sim_ready -> external_sim_passed -> live_ready -> live_approved
```

`live_ready` and `live_approved` require explicit approvals. Internal validation alone is not live approval.

## Data Rules

- amazingdata uses read-only ClickHouse config, normally `~/.config/db4quant/smartdata_ro.env`.
- Do not commit credentials or paste secrets into chat.
- Stop on empty panels, failed schema checks, duplicate date-code rows, bad date parsing, or required field coverage below threshold.
- Preserve raw factor direction. Do not auto-flip signs to improve metrics.
- Treat demo runs as smoke tests, not market evidence.
