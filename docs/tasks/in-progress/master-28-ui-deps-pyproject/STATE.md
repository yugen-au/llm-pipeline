## Task: master-28-ui-deps-pyproject
## Description: Update pyproject.toml with [ui] optional dependencies (FastAPI, uvicorn, websockets, python-multipart) and CLI entry point for llm-pipeline

## Phase: testing
## Status: in-progress
## Current Group: A
## Base Branch: dev
## Task Branch: sam/master/28-ui-deps-pyproject
## Plugins: python-development, dependency-management
## Graphiti Group ID: llm-pipeline
## Excluded Phases: none
## Steps to Fix: [1,2]
## Work Mode: standard
## Last Updated: 2026-02-21 12:46

## Agents
| Name | Agent | Phase | Step | Skills | Group | Status | Revisions | Agent ID | Commits | Context7 Docs |
|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|
| Packaging & Deps Research | python-development:python-pro | research | 1 | - | A | complete | 0 | a162818a6dcb12710 | 65b69fa | - |
| Assumption Check | code-documentation:code-reviewer | validate | 1 | - | A | complete | 1 | a4d623cb240c07e19 | 524d753 | - |
| Plan | planning | planning | 1 | - | A | complete | 0 | aefa8314f1588a241 | 06f12a9 | - |
| Update pyproject.toml | python-development:python-pro | implementation | 1 | - | A | complete | 1 | a605001cdbf740c8d | b8fdcfc,ae1c2e5,7681b30 | - |
| Add import guard | python-development:python-pro | implementation | 2 | - | A | complete | 1 | a5ca5d47d647edcaf | ae1c2e5,f481e3b | - |
| Verify build | full-stack-orchestration:test-automator | testing | 1 | - | A | in-progress | 1 | ad942695aad1c0bc3 | 9780702 | - |
| Architecture review | code-review-ai:architect-review | review | 1 | - | A | pending | 0 | a2cb214ca7413d0d2 | a65b541 | - |
