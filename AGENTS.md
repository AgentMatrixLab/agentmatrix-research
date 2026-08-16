# AGENTS.md — AI Agent Repository Entry

> Read this file first if you are an AI agent working inside this repository.
> This document is a **navigation guide only**: it lists modules that already
> exist, CLIs that already work, and docs that already describe them. It
>makes no claim about unified APIs, manifests, or pre-plugged pipeline abstractions.

## What this repository is

AgentMatrix Research is a modular quantitative research project for A-share
alpha discovery. Code is split by role: pure data contracts in `contracts/`,
executable research code in `research_core/`, a legacy transition layer in
`backend/` + `scripts/`, and supporting docs in `docs/`. Everything must be
run from the repository root (the directory containing `research_core/`).

## Core directory map

| Path | Role |
|---|---|
| `research_core/factor_lab/` | Factor discovery, validation and truth-proof runs (Alpha101, GTJA191, Alpha158, Barra, WQ101) |
| `research_core/strategy_engine/` | Build target-weight / alpha-strategy packages from validated factor runs |
| `research_core/backtest_adapter/` | Package signals for external simulation engines (掘金 / PTrade / QMT) and parse their results |
| `research_core/qlib_lab/` | Qlib-based factor mining, Alpha158 workflow, backtesting and intern starter packs |
| `contracts/` | Typed dataclass contracts shared across modules: `factor.py`, `strategy.py`, `backtest.py`, `attribution.py`, `factor_research.py` |
| `docs/` | Detailed workflow and architecture docs (see "Further reading" below) |
| `backend/`, `scripts/` | Legacy transition layers. New work should target `research_core/` and `contracts/` only. |

## Existing CLI entry points

Every module below already has a working `__main__`. Read each file or run
with `--help` for the actual parameters and subcommands. This guide does not
replicate the full CLI surface.

```bash
# Factor Lab — list factor sets, run research jobs, validate truth proof CSVs
python -m research_core.factor_lab.cli --help

# Strategy Engine — build target weights from a validated factor run
python -m research_core.strategy_engine.cli --help

# Backtest Adapter — package signals for GM / PTrade / QMT, then parse results
python -m research_core.backtest_adapter.cli --help

# Qlib Lab — Qlib factor mining, Alpha158 workflow, backtesting
python -m research_core.qlib_lab.cli --help
```

## Prerequisites and environment

- Python 3.10+ (64-bit recommended; 32-bit Windows cannot load some
  optional numerical dependencies such as `scipy`).
- Install project dependencies with `pip install -r scripts/requirements.txt`
  and `pip install -r requirements-factor-lab.txt`.
- `research_core/` and `contracts/` assume the working directory is the
  repository root. Do not `cd` into a subdirectory and run a CLI from there.
- Research runs write outputs under `runtime/`; never commit that directory.
- Qlib needs its own data directory; follow `docs/ALPHA158_STARTER.md` if you
  need it. The project does not ship market data.

## Skills packaged with this repository

For longer-running, opinionated research flows, prefer the bundled Skill
definitions. Each one documents its own commands, inputs and outputs:

- `.trae/skills/agentmatrix-alpha-pipeline/SKILL.md`
- `.trae/skills/alpha101-factor-research/SKILL.md`
- `.trae/skills/factor-research-proof-pipeline/SKILL.md`
- `.trae/skills/feeder/SKILL.md`
- `.trae/skills/quant-api-v2/SKILL.md`

## Safety and hygiene

- **Do not commit secrets, API tokens, private cookies or credentials** of
  any kind. If you set them via shell variables, do not echo them into logs.
- **Do not commit the contents of `runtime/`, `.pytest_cache/`, `__pycache__/`
  or generated parquet/CSV outputs.** These directories are intentionally
  local.
- **Do not hardcode local absolute paths** (Windows drive letters, user
  directories) into code or output metadata. Use project-relative paths and
  the existing `common.paths` helpers.
- When an AI assistant needs to add new capability, prefer extending an
  existing module over introducing another "unified" wrapper layer.

## Further reading

Pick the closest match from `docs/` instead of guessing workflows:

- `docs/FACTOR_LAB_ALPHA101_WORKFLOW.md` — Alpha101 research and truth-proof flow
- `docs/FACTOR_LAB_TRUTH_COMPARE.md` — Truth compare contract and tooling
- `docs/ALPHA158_STARTER.md` — Qlib / Alpha158 setup and starter pack
- `docs/FACTOR_LAB_CONTRIBUTOR_GUIDE.md` — Factor Lab contribution rules
- `CONTRIBUTING.md` — General pull-request and review guidance
- `README.md` — Repository overview and architecture principles
