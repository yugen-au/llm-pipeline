## Task: pydantic-ai-1-agent-registry-core
## Description: Implement AgentRegistry, StepDeps, agent builder utilities, update StepDefinition/LLMStep with pydantic-ai Agent integration, deprecate create_llm_call()

## Phase: fixing-review
## Status: in-progress
## Current Group: B
## Base Branch: dev
## Task Branch: sam/pydantic-ai/1-agent-registry-core
## Plugins: backend-development, python-development, llm-application-dev
## Graphiti Group ID: llm-pipeline
## Excluded Phases: none
## Steps to Fix: [4,6,7,8]
## Work Mode: standard
## Last Updated: 2026-03-12 10:50

## Agents
| Name | Agent | Phase | Step | Skills | Group | Status | Revisions | Agent ID | Commits | Context7 Docs |
|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|
| Codebase Architecture Research | backend-development:backend-architect | research | 1 | - | A | complete | 0 | a1b7d946093de3471 | 9edcf9b | - |
| Pydantic AI Agent Patterns | llm-application-dev:ai-engineer | research | 2 | - | A | complete | 0 | a2aa9cf3b169ff540 | 9edcf9b | - |
| Python Registry & Deprecation Patterns | python-development:python-pro | research | 3 | - | A | complete | 0 | a63312bb750eafd8a | 9edcf9b | - |
| Assumption Check | code-documentation:code-reviewer | validate | 1 | - | A | complete | 1 | a1480359d8940a630 | 7468bd4 | - |
| Plan | planning | planning | 1 | - | A | complete | 0 | a9cc8439dc516d921 | f019c3c | - |
| Create naming.py Utility | python-development:python-pro | implementation | 1 | - | A | complete | 0 | abc4a97d1d7f0fbc9 | e38efca | - |
| Fix LLMStep.step_name | python-development:python-pro | implementation | 2 | - | B | complete | 0 | a195df8082f9bf58d | f41180b | - |
| Fix StepDefinition snake_case | python-development:python-pro | implementation | 3 | - | B | complete | 0 | a58de518b2be4c2b6 | 1e4c51d,f41180b | - |
| Fix StepKeyDict._normalize_key | python-development:python-pro | implementation | 4 | - | B | complete | 1 | a8ea73b8a6d0b3627 | afa63ac,f41180b,52ff578 | - |
| Create agent_registry.py | backend-development:backend-architect | implementation | 5 | - | C | complete | 0 | a18b3cf39e822d6f0 | be173cf | /pydantic/pydantic-ai |
| Create agent_builders.py | llm-application-dev:ai-engineer | implementation | 6 | - | C | pending | 0 | a5eb624422d8bb682 | be173cf | /pydantic/pydantic-ai |
| Update StepDefinition | python-development:python-pro | implementation | 7 | - | D | pending | 0 | a67d3b92314ec35c7 | 8881f18 | - |
| Update LLMStep | python-development:python-pro | implementation | 8 | - | D | pending | 0 | aab48a789cf3e1579 | 8881f18 | /pydantic/pydantic-ai |
| Update PipelineConfig | backend-development:backend-architect | implementation | 9 | - | E | complete | 0 | ac0a8efa743ba332e | 5972079 | - |
| Add pydantic-ai dep | python-development:python-pro | implementation | 10 | - | E | complete | 0 | a342bc724feaf9abe | 200b56a,5972079 | - |
| Update __init__.py exports | python-development:python-pro | implementation | 11 | - | F | complete | 0 | a309527c755b4a8fe | 4ed29a8 | - |
| Verify build | full-stack-orchestration:test-automator | testing | 1 | - | A | complete | 0 | ad831e960debee7a6 | 344306d | - |
| Architecture review | comprehensive-review:architect-review | review | 1 | - | A | pending | 0 | a124071b0f3e82e53 | ae27d0f | - |
