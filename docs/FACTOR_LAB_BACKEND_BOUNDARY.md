# Factor Lab Backend Boundary

This document defines the repository boundary between `agentmatrix-research` and the separate AgentMatrix front-end workspace.

## Purpose

`agentmatrix-research` is the back-end research engine for:

- factor specifications
- factor reproduction pipelines
- truth-aligned validation
- IC / grouping / long-short evaluation
- runtime artifacts and proof packages
- agent-orchestrated research skills

It is not the source of truth for product UI.

## Repository Split

Back-end repository responsibilities:

- `research_core/factor_lab/` unified factor research framework
- `research_core/qlib_lab/` qlib-native research workflow
- `research_core/gtja191_lab/` current GTJA191 prototype
- validation reports, proof templates, and catalog exports
- HTTP or internal APIs consumed by front-end apps
- AI-agent execution skills and orchestration logic

Front-end repository responsibilities:

- all user-facing pages
- workbench layout
- charts, tables, filters, dialogs
- task interaction and reviewer workflows
- experiment submission and review UI

## Product Rule

If a feature is mainly about layout, interaction, page routing, or user-facing controls, implement it in the front-end repository.

If a feature is mainly about factor logic, data alignment, reproducibility, validation, or artifact generation, implement it in `agentmatrix-research`.

## Alpha101 Standard Path

The recommended first standard sample is:

1. Define `FactorResearchSpec`
2. Export Alpha101 catalog
3. Build validation proof package template
4. Implement factor computation under the unified framework
5. Expose API contracts to the front-end workbench

This keeps the research kernel stable while allowing the front-end to evolve independently.
