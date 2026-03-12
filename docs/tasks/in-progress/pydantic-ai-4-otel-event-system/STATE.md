## Task: pydantic-ai-4-otel-event-system
## Description: Enable pydantic.ai OTel instrumentation for pipeline agents, create pipeline event system (StepPrepared/StepStarting/StepCompleted), log token usage per step for cost tracking

## Phase: implementation
## Status: in-progress
## Current Group: A
## Base Branch: dev
## Task Branch: sam/pydantic-ai/4-otel-event-system
## Plugins: backend-development, observability-monitoring, python-development
## Graphiti Group ID: llm-pipeline
## Excluded Phases: none
## Steps to Fix: none
## Work Mode: standard
## Last Updated: 2026-03-12 17:13

## Agents
| Name | Agent | Phase | Step | Skills | Group | Status | Revisions | Agent ID | Commits | Context7 Docs |
|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|
| OTel & pydantic-ai instrumentation | observability-monitoring:observability-engineer | research | 1 | observability-monitoring:distributed-tracing | A | complete | 0 | a5651cbd7002978e8 | 02fdc53a | - |
| Pipeline event system patterns | backend-development:backend-architect | research | 2 | backend-development:architecture-patterns | A | complete | 0 | aa87bdc306123785f | 02fdc53a | - |
| Current codebase analysis | python-development:python-pro | research | 3 | python-development:async-python-patterns | A | complete | 0 | adbb7d2e49cdc3bec | 02fdc53a | - |
| Assumption Check | code-documentation:code-reviewer | validate | 1 | - | A | complete | 1 | a960cdaac04338850 | b16dd7c1 | - |
| Plan | planning | planning | 1 | - | A | complete | 0 | a7ddf70998337c775 | ef432117 | - |
| Token fields on PipelineStepState | backend-development:backend-architect | implementation | 1 | - | A | in-progress | 0 | pending | pending | /pydantic/pydantic-ai/v1_0_5 |
| Token fields on events | backend-development:backend-architect | implementation | 2 | - | A | complete | 0 | a1246e0ff41c38f10 | 188cc5a6 | - |
| instrument= in build_step_agent | backend-development:backend-architect | implementation | 3 | - | B | pending | 0 | pending | pending | /pydantic/pydantic-ai/v1_0_5 |
| instrumentation_settings on PipelineConfig | backend-development:backend-architect | implementation | 4 | - | B | pending | 0 | pending | pending | /pydantic/pydantic-ai/v1_0_5 |
| Token capture normal path | backend-development:backend-architect | implementation | 5 | - | C | pending | 0 | pending | pending | /pydantic/pydantic-ai/v1_0_5 |
| Token capture consensus path | backend-development:backend-architect | implementation | 6 | - | C | pending | 0 | pending | pending | - |
| Persist tokens in _save_step_state | backend-development:backend-architect | implementation | 7 | - | D | pending | 0 | pending | pending | - |
| OTel optional deps | backend-development:backend-architect | implementation | 8 | - | E | pending | 0 | pending | pending | - |
| docs/observability.md | backend-development:backend-architect | implementation | 9 | - | E | pending | 0 | pending | pending | /pydantic/pydantic-ai/v1_0_5 |
| Unit tests token capture | backend-development:backend-architect | implementation | 10 | - | F | pending | 0 | pending | pending | - |
