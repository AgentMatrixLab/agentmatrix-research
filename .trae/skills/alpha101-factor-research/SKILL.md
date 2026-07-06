---
name: "alpha101-factor-research"
description: "Builds and validates Alpha101 factors in factor_lab. Invoke when reproducing Alpha101, exporting proof artifacts, or preparing intern/agent research runs."
---
## Environment Prerequisites

Before running any command in this skill, confirm the execution environment:

- **Shell**: All commands in this skill are written as **single lines** and run as-is in PowerShell, Git Bash, macOS, or Linux. **Do not split a command across multiple lines using backslash (`\`) continuation** — `\` works in Bash but fails in Windows PowerShell with `ParserError`. Always emit each command on one line.
- **Python env**: Requires Python 3.10+ with dependencies installed (`pip install -r scripts/requirements.txt` and `pip install -r requirements-factor-lab.txt`). Use whatever Python already works on this machine — no special environment setup is needed.
- **Working directory**: Run all commands from the project root (the folder containing `research_core/`, `contracts/`, `backend/`).

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

Critical — pass panel parameters explicitly when generating and consuming demo truth.
export-alpha101-truth-template and run-alpha101-proof-batch must use identical --n-dates, --n-codes, and --seed values. Their built-in defaults differ (160/seed 7 vs 420/seed 29), so relying on defaults produces mismatched data and fails.
validate-alpha101-truth does not accept panel-shape arguments; it only validates the generated truth CSV before batch proof.

1. Read the current `factor_lab` contracts, runtime layout, specs, and existing Alpha101 implementation.
2. Preserve existing working paths such as `qlib_lab` and `gtja191_lab`; make additive changes.
3. Export or refresh the Alpha101 spec and catalog:

   ```bash
   python -m research_core.factor_lab.cli export-alpha101 --proof-factor alpha1
   ```

4. Export a truth CSV template when preparing a truth-aligned proof run:

   ```bash
   python -m research_core.factor_lab.cli export-alpha101-truth-template --n-dates 420 --n-codes 8 --seed 29
   ```

5. Validate the generated truth CSV before batch proof:

   ```bash
   python -m research_core.factor_lab.cli validate-alpha101-truth --truth-csv data/factor_lab/alpha101_truth_template_101f_420d_8c_s29.csv
   ```

6. Run deterministic research or batch proof:

   Deterministic run:

   ```bash
   python -m research_core.factor_lab.cli run-alpha101-demo --n-dates 420 --n-codes 8 --seed 29
   ```

  Batch proof against **project-generated demo truth** (internal consistency only — hard-codes `data_source="demo"`, no external reference):

   ```bash
   python -m research_core.factor_lab.cli run-alpha101-proof-batch --truth-csv data/factor_lab/alpha101_truth_template_101f_420d_8c_s29.csv --n-dates 420 --n-codes 8 --seed 29
   ```
   
   > **Note:** Proves self-consistency, not correctness against an authority. A real external-truth comparison (JoinQuant/RiceQuant/public impl on the **same real data**) is a separate, not-yet-automated step. Until then, proof status is at most `partial`.

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
