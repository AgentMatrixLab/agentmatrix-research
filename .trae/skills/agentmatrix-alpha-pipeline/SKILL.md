---
name: "agentmatrix-alpha-pipeline"
description: "Run the AgentMatrix alpha pipeline from alpha_resource.md through internal validation, strategy packaging, external simulation, and live-readiness gates."
---

# AgentMatrix Alpha Pipeline Skill

Use this skill when the task is to run or review the full alpha research pipeline in `agentmatrix-research`.

## Stages

1. Feeder produces `alpha_resource.md`.
2. Factor research normalizes `FactorResearchSpec`, implements the factor, and runs internal validation.
3. Validated factors are promoted to `strategy_candidate` only when data quality and red-flag checks are acceptable.
4. Strategy engine builds target weights with the same factor signal path used in research.
5. Backtest adapter packages GM, PTrade, or QMT external simulation files.
6. Returned terminal simulation evidence is parsed and attached before any `live_ready` promotion.

## Commands

Check amazingdata:

```bash
python -m research_core.factor_lab.cli check-amazingdata
```

Run internal validation:

```bash
python -m research_core.factor_lab.cli run-factor-research --factor-set wq101 --data-source amazingdata --start 2023-01-01 --end 2025-12-31 --universe csi800 --max-symbols 300
```

Build strategy signals:

```bash
python -m research_core.strategy_engine.cli build-alpha-strategy --validated-run runtime/factor_lab/jobs/<job_id>.json --top-n 50
```

Package external simulation:

```bash
python -m research_core.backtest_adapter.cli package-external-sim --engine gm --strategy <strategy_id> --signal-path runtime/strategy_engine/<strategy_id>/target_weights.csv --start 2023-01-01 --end 2025-12-31
```

## Proof Rules

- Internal validation is necessary but not sufficient for live trading.
- Never promote to `live_ready` without external simulation evidence and explicit human approval.
- Never auto-flip factor direction to improve metrics.
- Stop on failed data-quality status, missing required fields, empty factor coverage, or unresolved lookahead risk.
