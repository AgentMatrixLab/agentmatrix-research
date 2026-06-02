# Qlib Factor Workflow

This document describes the recommended workflow for interns and researchers to use `agentmatrix-research` as a unified factor R&D workspace.

## Goals

- Mine new factors with native qlib expressions
- Reproduce prior factors from the registry
- Let AI propose candidate factors and batch-evaluate them
- Run quick factor backtests with consistent artifacts
- Keep all outputs inside the current repository

## Install

```bash
pip install -r scripts/requirements.txt
```

## Prepare Qlib Data

Set the provider path if you do not want to use the default repository-local location:

```bash
set QLIB_PROVIDER_URI=D:\aiagent\agentmatrix-research\data\qlib\cn_data
```

Initialize the local workspace:

```bash
python -m research_core.qlib_lab.cli init-data
```

If qlib data is not downloaded yet, use the official helper from the qlib repository:

```bash
python scripts/get_data.py qlib_data --target_dir D:\aiagent\agentmatrix-research\data\qlib\cn_data --region cn
```

## 1. Mine a Factor

```bash
python -m research_core.qlib_lab.cli mine-factor ^
  --name short_term_reversal ^
  --expression "Ref($close, 5) / $close - 1" ^
  --description "5-day reversal factor" ^
  --start 2021-01-01 ^
  --end 2024-12-31 ^
  --horizon 5 ^
  --author intern_a
```

Outputs:

- `runtime/qlib/factor_registry.json`
- `runtime/qlib/factors/*.csv`
- `runtime/qlib/evaluations/*.json`

## 2. Reproduce a Factor

Use the registry factor id from the previous output:

```bash
python -m research_core.qlib_lab.cli reproduce-factor ^
  --factor-id 1234567890abcdef ^
  --start 2022-01-01 ^
  --end 2024-12-31 ^
  --horizon 5
```

## 3. AI Auto-Mine Factors

Set an LLM key if you want live proposal generation:

```bash
set OPENAI_API_KEY=your_key_here
set QFACTOR_OPENAI_MODEL=gpt-4.1-mini
```

Run auto-mining:

```bash
python -m research_core.qlib_lab.cli auto-mine ^
  --theme "mid-cap momentum with turnover confirmation" ^
  --start 2021-01-01 ^
  --end 2024-12-31 ^
  --count 5 ^
  --horizon 5
```

If no LLM key is configured, the system falls back to a built-in candidate set.

## 4. Quick Factor Backtest

Backtest a registered factor:

```bash
python -m research_core.qlib_lab.cli backtest ^
  --factor-id 1234567890abcdef ^
  --start 2021-01-01 ^
  --end 2024-12-31 ^
  --top-k 30 ^
  --horizon 5 ^
  --long-short
```

Or backtest an ad-hoc expression:

```bash
python -m research_core.qlib_lab.cli backtest ^
  --factor-expression "($close / Ref($close, 20) - 1) * Log($volume / Ref($volume, 20))" ^
  --start 2021-01-01 ^
  --end 2024-12-31
```

Artifacts are stored in:

- `runtime/qlib/backtests/*.json`

## 5. Alpha158 Starter Workflow

Export the preset template:

```bash
python -m research_core.qlib_lab.cli alpha158-template
```

Run the baseline Alpha158 workflow:

```bash
python -m research_core.qlib_lab.cli alpha158-starter ^
  --market csi300 ^
  --benchmark SH000300 ^
  --experiment-name alpha158_starter
```

See `docs/ALPHA158_STARTER.md` for the step-by-step intern onboarding workflow.

## Evaluation Metrics

Current default metrics include:

- `ic_mean`
- `rank_ic_mean`
- `icir`
- `positive_ic_ratio`
- `long_short_spread`

Backtest outputs include:

- total return
- annualized return
- volatility
- sharpe
- max drawdown
- win rate

## Suggested Intern Workflow

1. Start from one hypothesis and one qlib expression
2. Run `mine-factor`
3. Keep factors with stable positive `ic_mean` and reasonable `icir`
4. Run `backtest`
5. Submit a PR with:
   - factor expression
   - rationale
   - evaluation json
   - backtest json

## Notes

- This workflow is designed for factor research and screening, not production trading execution.
- Use qlib-native data for reproducibility before porting factors into GM or RQAlpha execution flows.
- New factor definitions are stored in a repository-local registry so interns can collaborate via Git.
