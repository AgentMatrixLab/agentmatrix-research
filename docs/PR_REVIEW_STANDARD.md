# PR Review Standard

This document defines the pull request review standard for `agentmatrix-research`.

It is designed for maintainers, researchers, interns, and AI agents such as Hermes.

The goal is not only to decide whether code "runs", but to decide whether a PR should enter the mainline of the unified factor research back-end.

## Review North Star

Every PR should be reviewed against the repository's main goal:

- build a unified factor research back-end
- support reproducible factor implementation
- support truth-aligned validation and proof artifacts
- support future factor families such as Alpha101, Alpha191, Alpha158, Barra, and paper-derived factors
- support agent-executable workflows instead of one-off manual scripts

A PR should move the repository closer to this target.

If a PR only adds code that runs locally but does not fit the unified back-end direction, it should not be merged.

## Core Review Questions

Reviewers should answer the following questions in order:

1. Does this PR fit the repository mission?
2. Does it improve the unified mainline instead of creating a parallel path?
3. Does it preserve existing working behavior?
4. Is the implementation technically correct?
5. Is the validation and evidence sufficient?
6. Is the PR scoped clearly enough to review and maintain?

If the answer to any of the first four questions is "no", the PR should not be merged.

## Mainline Rule

The repository mainline is the unified research back-end, not a collection of isolated prototypes.

Reviewers should prefer PRs that strengthen:

- `research_core/factor_lab/`
- shared operators and contracts
- proof, truth, validation, and reporting paths
- API, service, CLI, and runtime layers used by the mainline

Reviewers should reject or defer PRs that:

- create a parallel framework when the same work belongs in `factor_lab`
- duplicate logic that already exists in the mainline
- bypass truth, validation, or proof conventions
- add local-only or demo-only logic without integration into the standard workflow

## Merge Decision Levels

Use the following decision levels.

### Merge

Use `Approve` or merge directly when all of the following are true:

- no known blocker or regression
- behavior aligns with the repository mission
- implementation is technically sound
- review scope is clear
- evidence or tests are sufficient for the change type

### Comment But Do Not Merge

Use when:

- the PR direction is valuable
- the implementation is incomplete
- there is no need for a formal rejection because the PR is self-authored or exploratory

This is common for self-opened PRs submitted through the maintainer account or AI agents using the maintainer account.

### Request Changes

Use when there is a concrete blocker such as:

- runtime error
- import error
- syntax error
- broken API compatibility
- incorrect factor logic
- misleading or false validation result
- hidden security or data hygiene issue
- workflow that can report false success

### Close As Superseded

Use when:

- the PR direction is already covered by a later and more complete PR
- the PR is part of a stacked sequence and should not be merged independently
- the PR no longer has standalone merge value

In this case, close with a comment explaining which newer PR supersedes it.

## Hard Blockers

Any of the following should block merge immediately:

- `SyntaxError`, `ImportError`, or import-time crash
- incompatible function signature changes that break existing callers
- changes that silently alter factor semantics without clear justification
- CI or validation logic that can show green while actually failing
- missing referenced symbols, files, or contracts
- direct leakage of tokens, secrets, account paths, or private artifacts
- writing provider-specific credentials into repo files
- changes that damage reproducibility or proof traceability

## Factor-Specific Review Rules

If a PR changes factor logic, operator semantics, or truth comparison behavior, reviewers should check:

- formula intent and source alignment
- operator semantics
- data field assumptions
- window handling
- missing value handling
- ranking and neutralization semantics
- impact on existing factor outputs

For factor-family work, reviewers should prefer:

- shared operators when the logic is truly reusable
- local helper logic when generalization is not yet stable

Do not force premature abstraction if it creates regression risk.

## Validation Expectations

Validation depth should match PR type.

### Operator or factor logic changes

Expected evidence:

- targeted tests or reproducible commands
- sample output or validation notes
- no obvious regression in existing callers

### Truth, proof, reporting, or runtime changes

Expected evidence:

- proof or truth artifact path
- command used to generate the artifact
- summary of what was validated
- explanation of any known gaps

### CI or workflow changes

Expected evidence:

- full workflow path is reviewed
- failure behavior is explicit
- no `continue-on-error` on critical steps without a final failure gate
- PR-range detection is correct for multi-commit PRs

## Review Questions For PR Authors

If context is missing, ask the author to provide:

- what problem the PR is solving
- why this belongs in the mainline
- what commands were run
- what tests or proofs were produced
- what existing behavior could be affected

If the author cannot answer these clearly, the PR is usually not ready.

## Rules For Stacked PRs

If several PRs are stacked on top of each other:

- identify the newest complete version
- avoid merging earlier partial versions first unless they have clear standalone value
- close older superseded PRs after the newer one is merged
- preserve author credit where possible by merging the original PR branch instead of rewriting from scratch

When reviewing stacked PRs, do not judge each one in isolation from the stack history.

## Rules For Self-Authored PRs

If a PR was opened using the maintainer's own account, GitHub may not allow formal `Request changes`.

In this case:

- leave a clear `Comment`
- state whether the PR should not be merged
- keep the PR open for fixes or close it if it is superseded

Lack of a formal `Request changes` button does not make the PR mergeable.

## Preferred Review Order

When many PRs are open at once, reviewers should process them in this order:

1. mergeable and mainline-aligned PRs
2. superseded PRs that should be closed
3. PRs with clear blockers and required changes
4. exploratory or parallel-path PRs that need strategic redirection

This keeps the mainline moving without merging unstable or redundant work.

## Standard Reviewer Output

A good review comment should include:

- the merge decision
- the main reason
- the concrete blocker, if any
- the expected next action

Examples:

- "Can merge. This PR strengthens the unified factor_lab mainline and no new blocker was found."
- "Do not merge yet. This introduces a runtime compatibility regression because existing callers still pass `top_k`."
- "Close as superseded. The same direction is covered by the newer and more complete PR #N."

## Review Summary Template

Use the following template when needed:

```text
Decision:
- Merge / Comment only / Request changes / Close as superseded

Why:
- mainline alignment
- correctness
- regression risk
- validation sufficiency

Next action:
- merge now
- fix blocker and resubmit
- close this PR and keep the newer PR
```

## Final Principle

The repository should not merge code simply because it is interesting, large, or functional in isolation.

It should merge code that is:

- correct
- reproducible
- auditable
- aligned with the unified back-end mainline
- useful for future factor research and agent execution
