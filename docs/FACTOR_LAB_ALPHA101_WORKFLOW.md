# Factor Lab Alpha101 Workflow

This document defines the back-end workflow for interns, external researchers, and agents who need to reproduce and validate Alpha101 factors inside `agentmatrix-research`.

## Goal

The current milestone is:

- keep `qlib_lab` as the existing production research line
- grow a unified `factor_lab` without breaking current prototypes
- use `Alpha101` as the first standard template
- preserve a path to `Alpha191`, `Alpha158`, `Barra`, and future paper-derived factor families

## Current Coverage

Implemented in the current back-end upgrade:

- unified `FactorResearchSpec`
- registry export for `Alpha101`
- proof package template and first validation bundle
- deterministic demo dataset for repeatable smoke runs
- `alpha1` to `alpha101` implemented in panel form, aligned against `docs/alphas 101.pdf`
- evaluation report export for coverage, IC, and long-short spread
- external truth comparison adapter via CSV-aligned reference panel
- formal proof report export with per-factor pass/partial/failed status
- truth CSV template export and schema manifest for batch proof preparation
- Flask API endpoints for front-end and agent consumption
- workspace skill template for AI-assisted reproduction workflow

Not yet fully closed:

- real market data adapters for `factor_lab`
- external truth source collection and 101/101 zero-error proof closure
- migration of `Alpha191`, `Alpha158`, and `Barra` into the same runtime

## Deterministic Research Run

Install the minimal back-end dependencies:

```bash
pip install -r requirements-factor-lab.txt
```

Initialize runtime folders and export the catalog:

```bash
python -m research_core.factor_lab.cli init-workspace
python -m research_core.factor_lab.cli export-alpha101 --proof-factor alpha101
```

Run the deterministic Alpha101 research demo:

```bash
python -m research_core.factor_lab.cli run-alpha101-demo --n-dates 420 --n-codes 8 --seed 29
```

If you need a schema-ready truth CSV template first:

```bash
python -m research_core.factor_lab.cli export-alpha101-truth-template --n-dates 420 --n-codes 8 --seed 29
```

If you already have an aligned truth panel, add it to the same run:

```bash
python -m research_core.factor_lab.cli run-alpha101-demo --n-dates 420 --n-codes 8 --seed 29 --truth-csv data/factor_lab/alpha101_truth_template_101f_420d_8c_s29.csv --truth-tolerance 1e-12
```

Validate the truth CSV before running the batch proof:

```bash
python -m research_core.factor_lab.cli validate-alpha101-truth --truth-csv data/factor_lab/alpha101_truth_template_101f_420d_8c_s29.csv
```

If you want a batch proof summary for all requested factors:

```bash
python -m research_core.factor_lab.cli run-alpha101-proof-batch --truth-csv data/factor_lab/alpha101_truth_template_101f_420d_8c_s29.csv --n-dates 420 --n-codes 8 --seed 29
```

This generates:

- factor frame CSV
- evaluation JSON report
- evaluation Markdown report
- per-factor proof JSON
- per-factor sample reconciliation JSON
- per-factor truth comparison JSON when `--truth-csv` is provided
- consolidated research proof report in JSON and Markdown
- job manifest JSON
- batch proof summary with `overall_status`, blocker factor lists, and readiness flag when `run-alpha101-proof-batch` is used

## Truth CSV Schema

The truth CSV is a wide panel with:

- required key columns: `date`, `code`
- required factor columns: one column per requested factor such as `alpha1`, `alpha2`, ..., `alpha101`
- row granularity: one row per `date` x `code`
- date format: `YYYY-MM-DD`
- code format: security identifier string aligned with the computed factor frame

Minimal example:

```csv
date,code,alpha1,alpha2
2020-01-02,000001.SZ,0.125,-0.4821
2020-01-02,000002.SZ,-0.375,0.1934
```

Recommended workflow:

1. export the template CSV and manifest
2. replace template factor values with your external truth values
3. keep column names unchanged
4. run `validate-alpha101-truth`
5. run `run-alpha101-proof-batch` with `--truth-csv`
6. inspect `runtime/factor_lab/truth/*.json`, `runtime/factor_lab/proofs/*.json`, and the proof report summary

Validation checks currently include:

- required columns and requested factor names
- `date` parsing
- duplicate `date` x `code` keys
- per-factor non-null coverage
- empty factor columns that would block downstream proof

## API Endpoints

Run the API:

```bash
python backend/factor_lab_api.py
```

Available endpoints:

- `GET /api/agents/factor-lab/overview`
- `GET /api/agents/factor-lab/alpha101/factors`
- `GET /api/agents/factor-lab/alpha101/factors/<factor_name>`
- `GET /api/agents/factor-lab/jobs`
- `POST /api/agents/factor-lab/jobs`
- `GET /api/agents/factor-lab/jobs/<job_id>`
- `GET /api/agents/factor-lab/artifacts/<job_id>/<artifact_kind>`

Recommended POST body for a deterministic job:

```json
{
  "factor_names": ["alpha1", "alpha2", "alpha3"],
  "n_dates": 160,
  "n_codes": 8,
  "seed": 7,
  "data_source": "demo",
  "truth_csv_path": "",
  "truth_tolerance": 1e-12
}
```

## AI Workflow

The intended AI-assisted workflow is:

1. read factor source and normalize the formula into a `FactorResearchSpec`
2. register the factor family into `factor_lab`
3. implement the factor in panel form with reusable operators
4. compute factor frame on deterministic or real aligned data
5. export evaluation artifacts and proof package
6. compare against external truth source when available
7. export the formal proof report with explicit pass/partial/failed status
8. hand the artifact bundle to reviewers or front-end workbench

## Push Criteria

This back-end slice is suitable to push when:

- all changed files have clean diagnostics
- `test_factors.py`, `test_registry.py`, and `test_service.py` pass
- `run-alpha101-demo` exports artifacts successfully
- exported catalog marks `alpha1` to `alpha101` as `implemented/code`
- proof files exist for the requested factors
- if a truth panel is supplied, truth comparison files and proof report are exported successfully

## Next Upgrade Path

- add official/public Alpha101 truth-source collectors so truth CSV no longer needs manual preparation
- replace deterministic demo data with aligned market data ingestion
- extend proof checks from CSV truth compare to richer source-lineage and audit signatures
- migrate Alpha191 runtime and validation into `factor_lab`
- bridge `qlib_lab` Alpha158 outputs into unified factor specs and proof artifacts
