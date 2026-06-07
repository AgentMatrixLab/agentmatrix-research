# Contributing

Thanks for contributing to `agentmatrix-research`.

This repository is a public research workspace for:

- factor mining
- factor reproduction
- unified factor specifications and proof packages
- qlib-based workflow experiments
- backtest adapters
- strategy and dataset research

## Principles

- Keep research reproducible
- Keep secrets and private data out of Git
- Keep runtime artifacts local unless they are intentionally curated examples
- Prefer small, reviewable PRs over large mixed changes

## Branch Naming

Use short, descriptive branch names:

```text
feat/alpha158-rolling-window
feat/factor-momentum-liquidity
fix/qlib-cli-backtest
docs/intern-onboarding
```

## Pull Request Scope

One PR should focus on one of these:

- one factor idea
- one workflow improvement
- one adapter improvement
- one documentation update

Avoid mixing:

- feature work
- dependency upgrades
- large refactors
- unrelated docs cleanup

## Front-end Boundary

Keep user-facing pages, interaction flows, and workbench UI in the dedicated front-end repository.

Use `agentmatrix-research` for:

- factor definitions and implementations
- reproducibility and truth-aligned validation
- catalog exports and runtime artifacts
- APIs and agent skills that power the front-end

## Required For Research PRs

If your PR changes factor logic, strategy logic, or qlib workflow behavior, include:

- hypothesis or rationale
- exact commands you ran
- evaluation output summary
- backtest summary if applicable
- key artifact paths or attached screenshots

If your PR starts a new factor family such as Alpha101, Alpha191, Alpha158, Barra, or paper-derived factors, also include:

- the `FactorResearchSpec` or spec export path
- the validation proof template or proof artifact path
- a statement describing whether the UI work lives in the front-end repository

Use the templates under `docs/templates/`.

## Factor Research Workflow

Recommended path for interns:

1. Create or choose one hypothesis
2. Run `mine-factor` or `auto-mine`
3. Re-run with `reproduce-factor`
4. Run `backtest`
5. Summarize metrics and open a PR

Recommended path for model workflow:

1. Export the Alpha158 template
2. Run `alpha158-starter`
3. Modify one variable at a time
4. Compare with baseline
5. Open a PR with experiment notes

## What To Commit

Safe to commit:

- source code under `research_core/`, `contracts/`, `registry/`, `docs/`
- reviewed config templates
- curated lightweight JSON templates
- sanitized example outputs if intentionally added

Do not commit:

- downloaded qlib market data
- `mlruns` experiment directories
- backtest dumps under ignored runtime directories
- private account exports
- local notebooks with secrets or absolute paths

## Pre-PR Checklist

Before opening a PR:

```bash
git diff --check
python -m py_compile research_core/your_module.py
```

Also:

- search for `C:\Users\`, `Desktop`, `token`, `secret`, and `key`
- confirm no `.env` or provider credentials are included
- confirm paths in docs are generic or argument-based

## Review Expectations

Reviewers will focus on:

- correctness
- reproducibility
- privacy and open-source hygiene
- whether the result is useful for future research

PRs without enough context may be asked to add:

- factor proposal
- experiment report
- clearer commands
- better artifact descriptions

## Public Repo Hygiene

Read:

- `OPEN_SOURCE_SANITIZATION_CHECKLIST.md`
- `docs/QLIB_FACTOR_WORKFLOW.md`
- `docs/ALPHA158_STARTER.md`

If you are unsure whether a file should be public, do not include it in the PR.
