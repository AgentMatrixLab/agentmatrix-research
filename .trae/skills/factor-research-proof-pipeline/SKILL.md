---
name: "factor-research-proof-pipeline"
description: "Standardizes factor reproduction, truth validation, and proof export in factor_lab. Invoke when building or reviewing Alpha101, Alpha191, Alpha158, Barra, or paper-derived factor workflows."
---

# Factor Research Proof Pipeline

Use this skill when the task is to reproduce a factor family end to end inside `agentmatrix-research`, and the output must include code, validation evidence, and reusable artifacts for interns or agents.

## Primary Goal

Turn a factor idea or factor family into a repeatable back-end research bundle with:

- normalized `FactorResearchSpec`
- reusable panel implementation
- evaluation metrics
- truth-source comparison when available
- proof package and formal report
- API or CLI handoff for front-end or agent orchestration

## Invocation Conditions

Invoke this skill when:

- a user asks to reproduce `Alpha101`, `Alpha191`, `Alpha158`, `Barra`, or paper factors
- a user asks for “proof”, “无偏差校验”, “真值对照”, or “formal report”
- an intern workflow needs to be standardized
- an agent workflow must be made repeatable across factor families

Do not use this skill for front-end page building. Keep UI work in the dedicated front-end repository.

## Required Process

1. Read the current contracts, existing family specs, runtime layout, and validation rules in `research_core/factor_lab/`.
2. Preserve existing working paths such as `qlib_lab` and `gtja191_lab`; only add incremental capabilities.
3. Normalize the target factor or factor family into `FactorResearchSpec` entries.
4. Implement factor logic with reusable operators instead of ad hoc scripts.
5. Run aligned factor computation on deterministic or real data.
6. Export:
   - catalog and specs
   - factor frame
   - evaluation report
   - proof JSON
   - sample reconciliation
   - truth comparison artifact when available
   - formal research report
   - batch proof summary with overall status and blocker factor lists when the family supports grouped proof
7. Run targeted tests and diagnostics for changed files.
8. State clearly whether the result is:
   - `planned`
   - `implemented`
   - `partial proof`
   - `passed proof`

## Proof Rule

Never claim “fully reproduced”, “zero bias”, or “100% no-error proof” unless all of the following exist:

- formula and field mapping checks pass
- sample point reconciliation exists
- multi-period evaluation artifact exists
- external truth comparison artifact exists
- proof status is `passed`

If the external truth source is not available, the correct wording is `partial proof`, not final proof.

## Output Checklist

Before handoff, ensure the workspace contains:

- updated code in `research_core/factor_lab/`
- updated docs under `docs/`
- one or more `SKILL.md` files when the workflow is meant to be reusable by agents
- passing tests for the edited scope
- exported runtime artifacts under `runtime/factor_lab/`
- truth CSV validation output when external truth is part of the workflow
