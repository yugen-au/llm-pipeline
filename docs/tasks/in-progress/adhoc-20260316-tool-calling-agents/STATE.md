## Task: adhoc-20260316-tool-calling-agents
## Description: Add tool-calling agent support to build_step_agent() - add tools param and extend StepDeps with extra dict for domain-specific deps

## Phase: review
## Status: in-progress
## Current Group: A
## Base Branch: dev
## Task Branch: sam/adhoc/20260316-tool-calling-agents
## Plugins: python-development, backend-development, llm-application-dev, frontend-mobile-development
## Graphiti Group ID: llm-pipeline
## Excluded Phases: none
## Steps to Fix: [3,5,6]
## Work Mode: standard
## Last Updated: 2026-03-16 16:13

## Agents
| Name | Agent | Phase | Step | Skills | Group | Status | Revisions | Agent ID | Commits | Context7 Docs |
|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|
| pydantic-ai Agent Patterns | llm-application-dev:ai-engineer | research | 1 | - | A | complete | 0 | a141be18bfd8aa8fb | 197b9739 | - |
| StepDeps and Builder Architecture | python-development:python-pro | research | 2 | - | A | complete | 0 | a7b22640266b64171 | 197b9739 | - |
| Tool Registration Patterns | backend-development:backend-architect | research | 3 | - | A | complete | 0 | a64e34d133e8102c6 | 197b9739 | - |
| Assumption Check | code-documentation:code-reviewer | validate | 1 | - | A | complete | 1 | a039fbacda721881a | 19366631 | - |
| Plan | planning | planning | 1 | - | A | complete | 0 | a044d2048f8cc83f9 | c4cc41ee | - |
| AgentSpec + Registry | python-development:python-pro | implementation | 1 | - | A | complete | 0 | afab2d489be2e56a0 | e0c933c3 | /pydantic/pydantic-ai |
| step.py get_agent tuple | python-development:python-pro | implementation | 2 | - | A | complete | 0 | a09c425826571b8a2 | de0390a2,e0c933c3 | - |
| Tool Call Event Types | python-development:python-pro | implementation | 5 | - | A | complete | 1 | a7e33819cc697e76a | f304b1c4,e0c933c3,36df7d45 | - |
| build_step_agent tools | python-development:python-pro | implementation | 3 | - | B | complete | 1 | af873fb05d84b475c | 14247ed4,ea241a76 | /pydantic/pydantic-ai |
| pipeline.py wiring | python-development:python-pro | implementation | 4 | - | B | complete | 0 | aa46d0b317774f351 | eacb3e5f,14247ed4 | - |
| EventEmittingToolset | llm-application-dev:ai-engineer | implementation | 6 | - | C | complete | 1 | a31e6bb7fe3d0823c | 97cdf208,e2deca6e | /pydantic/pydantic-ai |
| Introspection tools metadata | python-development:python-pro | implementation | 7 | - | C | complete | 0 | a6c2c3a88c44fcc95 | 7af07319,97cdf208 | - |
| Frontend TS types | frontend-mobile-development:frontend-developer | implementation | 8 | - | C | complete | 0 | a7cc922276b879df5 | e9058b51,97cdf208 | - |
| Frontend UI display | frontend-mobile-development:frontend-developer | implementation | 9 | - | D | complete | 0 | ab483a410599572e7 | a17e88b6 | - |
| Verify build | full-stack-orchestration:test-automator | testing | 1 | - | A | complete | 1 | a1f487950615b73ac | fdfe75b6,84ce0230 | - |
| Architecture review | comprehensive-review:architect-review | review | 1 | - | A | complete | 1 | a87f1495f24a3f11a | 5897f3df | - |
