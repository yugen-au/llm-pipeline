## Task: pydantic-ai-4-otel-event-system
## Description: Enable pydantic.ai OTel instrumentation for pipeline agents, create pipeline event system (StepPrepared/StepStarting/StepCompleted), log token usage per step for cost tracking

## Phase: testing
## Status: in-progress
## Current Group: A
## Base Branch: dev
## Task Branch: sam/pydantic-ai/4-otel-event-system
## Plugins: backend-development, observability-monitoring, python-development
## Graphiti Group ID: llm-pipeline
## Excluded Phases: none
## Steps to Fix: [1,5,7,9,10]
## Work Mode: standard
## Last Updated: 2026-03-12 19:52

## Agents
| Name | Agent | Phase | Step | Skills | Group | Status | Revisions | Agent ID | Commits | Context7 Docs |
|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|
| OTel & pydantic-ai instrumentation | observability-monitoring:observability-engineer | research | 1 | observability-monitoring:distributed-tracing | A | complete | 0 | a5651cbd7002978e8 | 02fdc53a | - |
| Pipeline event system patterns | backend-development:backend-architect | research | 2 | backend-development:architecture-patterns | A | complete | 0 | aa87bdc306123785f | 02fdc53a | - |
| Current codebase analysis | python-development:python-pro | research | 3 | python-development:async-python-patterns | A | complete | 0 | adbb7d2e49cdc3bec | 02fdc53a | - |
| Assumption Check | code-documentation:code-reviewer | validate | 1 | - | A | complete | 1 | a960cdaac04338850 | b16dd7c1 | - |
| Plan | planning | planning | 1 | - | A | complete | 0 | a7ddf70998337c775 | ef432117 | - |
| Token fields on PipelineStepState | backend-development:backend-architect | implementation | 1 | - | A | complete | 1 | a4f150e3d1f795a1b | 080e13d1,21df2c8c | /pydantic/pydantic-ai/v1_0_5 |
| Token fields on events | backend-development:backend-architect | implementation | 2 | - | A | complete | 0 | a1246e0ff41c38f10 | 188cc5a6,080e13d1 | - |
| instrument= in build_step_agent | backend-development:backend-architect | implementation | 3 | - | B | complete | 0 | a4b8f05ba7e3f72e9 | 6d830755 | /pydantic/pydantic-ai/v1_0_5 |
| instrumentation_settings on PipelineConfig | backend-development:backend-architect | implementation | 4 | - | B | complete | 0 | af51af70cd4e64799 | 6d830755 | /pydantic/pydantic-ai/v1_0_5 |
| Token capture normal path | backend-development:backend-architect | implementation | 5 | - | C | complete | 1 | a25382aa438259569 | 1358a620,f1744ea0 | /pydantic/pydantic-ai/v1_0_5 |
| Token capture consensus path | backend-development:backend-architect | implementation | 6 | - | C | complete | 0 | a37d02e632da83375 | 1358a620 | - |
| Persist tokens in _save_step_state | backend-development:backend-architect | implementation | 7 | - | D | complete | 1 | a9a18f5b853e3dea7 | f7345a30,5d0001a9 | - |
| OTel optional deps | backend-development:backend-architect | implementation | 8 | - | E | complete | 0 | a83eee2b0b4f40da7 | 5e5ce8d1,5d7197e5 | - |
| docs/observability.md | backend-development:backend-architect | implementation | 9 | - | E | complete | 1 | add36b13e23e02bba | 5d7197e5,a79e956d | /pydantic/pydantic-ai/v1_0_5 |
| Unit tests token capture | backend-development:backend-architect | implementation | 10 | - | F | complete | 1 | afb329ff0b69571d9 | 300ab1e7,c566e975 | - |
| Verify build | full-stack-orchestration:test-automator | testing | 1 | - | A | in-progress | 1 | a8178e374c6d82449 | 330f46d6 | - |
| Architecture review | comprehensive-review:architect-review | review | 1 | - | A | pending | 0 | ae3d687e7b61fec62 | 5b8e8da3 | - |
