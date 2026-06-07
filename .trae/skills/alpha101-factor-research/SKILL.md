---
name: "alpha101-factor-research"
description: "Builds and validates Alpha101 factors in factor_lab. Invoke when reproducing Alpha101, exporting proof artifacts, or preparing intern/agent research runs."
---

# Alpha101 Factor Research

Use this skill when the user wants to reproduce, validate, review, or export Alpha101 factors inside `agentmatrix-research`.

## Scope

This skill is for the back-end research flow only:

- factor specification
- panel implementation
- deterministic or aligned data runs
- evaluation artifact export
- proof package generation
- API and CLI handoff for front-end or agent consumption

Do not use this skill to build UI pages. Front-end interaction belongs in the dedicated front-end repository.

## Workflow

1. Read the current `factor_lab` contracts, runtime layout, specs, and existing Alpha101 implementation.
2. Preserve existing working paths such as `qlib_lab` and `gtja191_lab`; make additive changes.
3. Export or refresh the Alpha101 spec and catalog:

   ```bash
   python -m research_core.factor_lab.cli export-alpha101 --proof-factor alpha101
   ```

4. Export a truth CSV template when an external truth process is needed:

   ```bash
   python -m research_core.factor_lab.cli export-alpha101-truth-template --n-dates 420 --n-codes 8 --seed 29
   ```

5. Validate the truth CSV before batch proof:

   ```bash
   python -m research_core.factor_lab.cli validate-alpha101-truth --truth-csv data/factor_lab/alpha101_truth_template_101f_420d_8c_s29.csv
   ```

6. Run deterministic research or batch proof:

   Deterministic run:

   ```bash
   python -m research_core.factor_lab.cli run-alpha101-demo --n-dates 420 --n-codes 8 --seed 29
   ```

   Batch proof with aligned external truth:

   ```bash
   python -m research_core.factor_lab.cli run-alpha101-proof-batch --truth-csv data/factor_lab/alpha101_truth_template_101f_420d_8c_s29.csv --n-dates 420 --n-codes 8 --seed 29
   ```

7. Verify the generated artifacts:

   - `runtime/factor_lab/specs/alpha101_specs.json`
   - `runtime/factor_lab/catalogs/alpha101_catalog.json`
   - `runtime/factor_lab/frames/`
   - `runtime/factor_lab/reports/`
   - `runtime/factor_lab/proofs/`
   - `runtime/factor_lab/samples/`
   - `runtime/factor_lab/truth/`
   - `runtime/factor_lab/jobs/`

8. Run regression checks:

   ```bash
   python -m unittest research_core.factor_lab.libraries.alpha101.test_factors
   python -m unittest research_core.factor_lab.test_registry
   python -m unittest research_core.factor_lab.test_service
   ```

9. If the user needs front-end or agent integration, expose the Flask API:

   ```bash
   python backend/factor_lab_api.py
   ```

## Output Standard

Always aim to leave behind:

- updated code
- passing tests
- exported runtime artifacts
- explicit proof status for each factor
- truth comparison artifacts when an external reference is provided
- batch proof summary with overall readiness and blocker factors
- a clear statement of what is fully proven and what still requires external truth comparison

## Review Rule

Never claim “zero bias” or “fully reproduced” unless there is an external truth-source comparison artifact. Internal consistency, sample checks, and evaluation reports are necessary but not sufficient for the final proof standard.
