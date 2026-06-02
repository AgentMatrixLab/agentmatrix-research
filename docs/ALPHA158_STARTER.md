# Alpha158 Starter

This guide is for interns who want a reproducible starter workflow on top of qlib's built-in `Alpha158` dataset preset.

## What It Does

- creates a standard Alpha158 task configuration
- trains a baseline `LightGBM` forecasting model
- runs signal analysis and portfolio analysis with qlib workflow records
- stores the generated workflow template inside the current repository

## Install

```bash
pip install -r scripts/requirements.txt
```

## Prepare Data

```bash
set QLIB_PROVIDER_URI=D:\aiagent\agentmatrix-research\data\qlib\cn_data
python -m research_core.qlib_lab.cli init-data
```

If data is missing, download qlib market data first.

## Export the Starter Template

```bash
python -m research_core.qlib_lab.cli alpha158-template
```

This writes a template file such as:

- `runtime/qlib/alpha158_template.json`

## Run the Starter Workflow

```bash
python -m research_core.qlib_lab.cli alpha158-starter ^
  --market csi300 ^
  --benchmark SH000300 ^
  --train-start 2008-01-01 ^
  --train-end 2014-12-31 ^
  --valid-start 2015-01-01 ^
  --valid-end 2016-12-31 ^
  --test-start 2017-01-01 ^
  --test-end 2020-08-01 ^
  --topk 50 ^
  --n-drop 5 ^
  --experiment-name alpha158_starter
```

## Output

The workflow stores local artifacts under:

- `runtime/qlib/workflow_runs/<experiment_name>/alpha158_workflow.json`
- qlib recorder artifacts under the local qlib experiment directory

## Suggested Intern Tasks

1. run the baseline starter workflow
2. duplicate the template and change train/valid/test windows
3. change market from `csi300` to another supported universe
4. compare factor mining results from `mine-factor` with model-based workflow results
5. submit a PR with the modified workflow config and experiment summary

## Notes

- The starter is meant for research onboarding, not production deployment.
- It follows the standard qlib workflow pattern: dataset -> model -> signal analysis -> portfolio analysis.
- If `lightgbm` is missing, install it before running `alpha158-starter`.
