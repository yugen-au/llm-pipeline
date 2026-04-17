## Task: adhoc-20260416-evals-v2-variants
## Description: Evals v2 variant comparison — delta-based step definition overrides, EvaluationVariant table, runner integration, variant CRUD routes, frontend variant editor + comparison view

## Phase: implementation
## Status: in-progress
## Current Group: C
## Base Branch: dev
## Task Branch: sam/adhoc/20260416-evals-v2-variants
## Plugins: backend-development, frontend-mobile-development, python-development
## Graphiti Group ID: llm-pipeline
## Excluded Phases: none
## Steps to Fix: none
## Work Mode: standard
## PRD Target Tasks: 0
## Last Updated: 2026-04-17 16:12

## Agents
| Name | Agent | Phase | Step | Skills | Group | Status | Revisions | Agent ID | Commits | Context7 Docs |
|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|
| Existing evals + sandbox arch | backend-development:backend-architect | research | 1 | - | A | complete | 0 | af832eb75a95bf8cf | 56bd7e5e | - |
| Frontend evals patterns | frontend-mobile-development:frontend-developer | research | 2 | - | A | complete | 0 | a2059e21e65a9fc3b | 56bd7e5e | - |
| Pydantic create_model + delta | python-development:python-pro | research | 3 | - | A | complete | 0 | ad5d2087663677746 | 56bd7e5e | - |
| Assumption Check | code-documentation:code-reviewer | validate | 1 | - | A | complete | 1 | a593c36154cf4363e | da26c741 | - |
| Plan | planning | planning | 1 | - | A | complete | 0 | a0bf164b49e299fcd | 299354b2 | - |
| EvaluationVariant model + migration | python-development:python-pro | implementation | 1 | python-development:python-testing-patterns | A | complete | 0 | a43ec22fa5b73262f | f00e56a3,8bb85a25 | /fastapi/sqlmodel |
| apply_instruction_delta() utility | python-development:python-pro | implementation | 2 | python-development:python-testing-patterns | A | complete | 0 | a868d19f2c82b884f | 8bb85a25 | /websites/pydantic_dev_validation |
| Runner integration - delta + prompt override | python-development:python-pro | implementation | 3 | python-development:python-testing-patterns | B | complete | 0 | a1b5b78eda4b80e3e | 519a92d2 | /fastapi/sqlmodel |
| Variant CRUD API routes | backend-development:backend-architect | implementation | 4 | backend-development:api-design-principles | B | complete | 0 | a51ff3ae2ab07a9b7 | 3435d20d,519a92d2 | /fastapi/sqlmodel |
| Frontend API layer - variants + run types | frontend-mobile-development:frontend-developer | implementation | 5 | frontend-mobile-development:react-state-management | C | in-progress | 0 | pending | pending | /tanstack/router |
| Variants tab + variant editor route | frontend-mobile-development:frontend-developer | implementation | 6 | frontend-mobile-development:react-state-management | D | pending | 0 | pending | pending | /tanstack/router |
| Run comparison view | frontend-mobile-development:frontend-developer | implementation | 7 | frontend-mobile-development:react-state-management | D | pending | 0 | pending | pending | /tanstack/router |
