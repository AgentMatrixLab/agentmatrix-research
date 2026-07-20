---
name: "feeder"
description: "Find, deduplicate, review, and normalize factor research sources into alpha_resource.md for AgentMatrix factor_lab."
---

# AgentMatrix Feeder Skill

Use this skill when an agent needs to turn a paper, broker report, local PDF, web page, or structured note into a testable `alpha_resource.md`.

## Rules

- Do not claim alpha validity. This skill only prepares a source for factor research.
- Reject vague strategy commentary, performance-only summaries, and black-box descriptions that cannot become a factor formula or data source.
- Preserve source provenance, formula assumptions, required fields, frequency, universe, rebalance rule, horizon, and expected direction.
- Do not bypass paywalls, CAPTCHA, login restrictions, or vendor terms.
- Do not ask users to paste credentials, cookies, tokens, private keys, or passwords into chat.

## Required Output

Write one `alpha_resource.md` containing:

- source title, author/institution, date, URL or local path
- novelty and duplicate notes
- factor family and formula
- required fields and field definitions
- frequency, universe, horizon, rebalance rule, and neutralization assumptions
- implementation uncertainties and stop conditions
- recommended `factor_lab` command for the next stage

## Handoff

Pass `alpha_resource.md` to the factor research skill. If the source is not implementable, stop with a short handoff explaining the missing formula, data fields, or point-in-time assumptions.
