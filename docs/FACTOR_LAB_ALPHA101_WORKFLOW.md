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
- `alpha1` to `alpha10` implemented in panel form
- evaluation report export for coverage, IC, and long-short spread
- Flask API endpoints for front-end and agent consumption
- workspace skill template for AI-assisted reproduction workflow

Not yet fully closed:

- external truth-source comparison for zero-bias proof
- real market data adapters for `factor_lab`
- full `Alpha101` 11-101 implementation
- migration of `Alpha191`, `Alpha158`, and `Barra` into the same runtime

## Deterministic Research Run

Install the minimal back-end dependencies:

```bash
pip install -r requirements-factor-lab.txt
```

Initialize runtime folders and export the catalog:

```bash
python -m research_core.factor_lab.cli init-workspace
python -m research_core.factor_lab.cli export-alpha101 --proof-factor alpha1
```

Run the deterministic Alpha101 research demo:

```bash
python -m research_core.factor_lab.cli run-alpha101-demo --factors alpha1,alpha2,alpha3,alpha4,alpha5,alpha6,alpha7,alpha8,alpha9,alpha10 --n-dates 160 --n-codes 8 --seed 7
```

This generates:

- factor frame CSV
- evaluation JSON report
- evaluation Markdown report
- per-factor proof JSON
- per-factor sample reconciliation JSON
- job manifest JSON

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
  "data_source": "demo"
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
7. hand the artifact bundle to reviewers or front-end workbench

## Push Criteria

This back-end slice is suitable to push when:

- all changed files have clean diagnostics
- `test_factors.py`, `test_registry.py`, and `test_service.py` pass
- `run-alpha101-demo` exports artifacts successfully
- exported catalog marks `alpha1` to `alpha10` as `implemented/code`
- proof files exist for the requested factors

## Next Upgrade Path

- add external truth adapters for Alpha101 official or public references
- replace deterministic demo data with aligned market data ingestion
- extend proof checks from `partial` to fully `passed`
- migrate Alpha191 runtime and validation into `factor_lab`
- bridge `qlib_lab` Alpha158 outputs into unified factor specs and proof artifacts
