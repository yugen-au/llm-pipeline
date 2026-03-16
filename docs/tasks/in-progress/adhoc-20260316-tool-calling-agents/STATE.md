## Task: adhoc-20260316-tool-calling-agents
## Description: Add tool-calling agent support to build_step_agent() - add tools param and extend StepDeps with extra dict for domain-specific deps

## Phase: implementation
## Status: in-progress
## Current Group: B
## Base Branch: dev
## Task Branch: sam/adhoc/20260316-tool-calling-agents
## Plugins: python-development, backend-development, llm-application-dev, frontend-mobile-development
## Graphiti Group ID: llm-pipeline
## Excluded Phases: none
## Steps to Fix: none
## Work Mode: standard
## Last Updated: 2026-03-16 15:04

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
| Tool Call Event Types | python-development:python-pro | implementation | 5 | - | A | complete | 0 | a7e33819cc697e76a | f304b1c4,e0c933c3 | - |
| build_step_agent tools | python-development:python-pro | implementation | 3 | - | B | complete | 0 | af873fb05d84b475c | 14247ed4 | /pydantic/pydantic-ai |
| pipeline.py wiring | python-development:python-pro | implementation | 4 | - | B | complete | 0 | aa46d0b317774f351 | eacb3e5f | - |
| EventEmittingToolset | llm-application-dev:ai-engineer | implementation | 6 | - | C | pending | 0 | pending | pending | /pydantic/pydantic-ai |
| Introspection tools metadata | python-development:python-pro | implementation | 7 | - | C | pending | 0 | pending | pending | - |
| Frontend TS types | frontend-mobile-development:frontend-developer | implementation | 8 | - | C | pending | 0 | pending | pending | - |
| Frontend UI display | frontend-mobile-development:frontend-developer | implementation | 9 | - | D | pending | 0 | pending | pending | - |
