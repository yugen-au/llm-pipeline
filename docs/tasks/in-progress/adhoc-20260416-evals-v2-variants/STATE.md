## Task: adhoc-20260416-evals-v2-variants
## Description: Evals v2 variant comparison — delta-based step definition overrides, EvaluationVariant table, runner integration, variant CRUD routes, frontend variant editor + comparison view

## Phase: fixing-review
## Status: in-progress
## Current Group: A
## Base Branch: dev
## Task Branch: sam/adhoc/20260416-evals-v2-variants
## Plugins: backend-development, frontend-mobile-development, python-development
## Graphiti Group ID: llm-pipeline
## Excluded Phases: none
## Steps to Fix: [2,3,4,5,6]
## Work Mode: standard
## PRD Target Tasks: 0
## Last Updated: 2026-04-20 09:36

## Agents
| Name | Agent | Phase | Step | Skills | Group | Status | Revisions | Agent ID | Commits | Context7 Docs |
|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|
| Existing evals + sandbox arch | backend-development:backend-architect | research | 1 | - | A | complete | 0 | af832eb75a95bf8cf | 56bd7e5e | - |
| Frontend evals patterns | frontend-mobile-development:frontend-developer | research | 2 | - | A | complete | 0 | a2059e21e65a9fc3b | 56bd7e5e | - |
| Pydantic create_model + delta | python-development:python-pro | research | 3 | - | A | complete | 0 | ad5d2087663677746 | 56bd7e5e | - |
| Assumption Check | code-documentation:code-reviewer | validate | 1 | - | A | complete | 1 | a593c36154cf4363e | da26c741 | - |
| Plan | planning | planning | 1 | - | A | complete | 0 | a0bf164b49e299fcd | 299354b2 | - |
| EvaluationVariant model + migration | python-development:python-pro | implementation | 1 | python-development:python-testing-patterns | A | complete | 0 | a43ec22fa5b73262f | f00e56a3,8bb85a25 | /fastapi/sqlmodel |
| apply_instruction_delta() utility | python-development:python-pro | implementation | 2 | python-development:python-testing-patterns | A | in-progress | 1 | a868d19f2c82b884f | 8bb85a25 | /websites/pydantic_dev_validation |
| Runner integration - delta + prompt override | python-development:python-pro | implementation | 3 | python-development:python-testing-patterns | B | pending | 0 | a1b5b78eda4b80e3e | 519a92d2 | /fastapi/sqlmodel |
| Variant CRUD API routes | backend-development:backend-architect | implementation | 4 | backend-development:api-design-principles | B | pending | 0 | a51ff3ae2ab07a9b7 | 3435d20d,519a92d2 | /fastapi/sqlmodel |
| Frontend API layer - variants + run types | frontend-mobile-development:frontend-developer | implementation | 5 | frontend-mobile-development:react-state-management | C | pending | 0 | ad2accfc6e4f449ea | 42bd31f2 | /tanstack/router |
| Variants tab + variant editor route | frontend-mobile-development:frontend-developer | implementation | 6 | frontend-mobile-development:react-state-management | D | pending | 0 | adb1e6314d1da7afc | bf925d58 | /tanstack/router |
| Run comparison view | frontend-mobile-development:frontend-developer | implementation | 7 | frontend-mobile-development:react-state-management | D | complete | 0 | a0683257e071b7cd8 | 8e14f525,bf925d58 | /tanstack/router |
| Verify build | full-stack-orchestration:test-automator | testing | 1 | - | A | complete | 0 | ab44bc3cae5435f6f | 58064b81,d90740d5 | - |
| Architecture review | comprehensive-review:architect-review | review | 1 | - | A | pending | 0 | a1697ff3934d57d1b | 8adbc25c,f66ed069 | - |
