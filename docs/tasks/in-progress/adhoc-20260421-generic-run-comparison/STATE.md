## Task: adhoc-20260421-generic-run-comparison
## Description: Generic eval run comparison — replace baseline-only compare with any-two-runs picker, case-level version matching (matched/drifted/unmatched buckets), scoped aggregates. Modify existing comparison page to support any run-to-run comparison.

## Phase: implementation
## Status: in-progress
## Current Group: C
## Base Branch: dev
## Task Branch: sam/adhoc/20260421-generic-run-comparison
## Plugins: frontend-mobile-development, backend-development
## Graphiti Group ID: llm-pipeline
## Excluded Phases: none
## Steps to Fix: none
## Work Mode: standard
## PRD Target Tasks: 0
## Last Updated: 2026-04-21 18:10

## Agents
| Name | Agent | Phase | Step | Skills | Group | Status | Revisions | Agent ID | Commits | Context7 Docs |
|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|
| Frontend comparison UI research | frontend-mobile-development:frontend-developer | research | 1 | - | A | complete | 0 | a8ba5c2d48353bdbc | 2c9b329b | - |
| Backend comparison logic research | backend-development:backend-architect | research | 2 | - | A | complete | 0 | a36edd5e701e73d61 | 2c9b329b | - |
| Assumption Check | code-documentation:code-reviewer | validate | 1 | - | A | complete | 1 | a20d56ad5a3832e24 | a4bde376 | - |
| Plan | planning | planning | 1 | - | A | complete | 0 | a60feb2cf2494a2ea | c2e269ac | - |
| Add case_id to CaseResultItem | backend-development:backend-architect | implementation | 1 | - | A | complete | 0 | abaa93095c8b1019a | b8c76a6a,de2bff9d | - |
| Sync frontend TS types | frontend-mobile-development:frontend-developer | implementation | 2 | - | A | complete | 0 | a721761759d582a9b | 6249de3d,de2bff9d | - |
| Zod schema compareRunId + alias | frontend-mobile-development:frontend-developer | implementation | 3 | - | B | complete | 0 | a2bc6b43303ea9b16 | 8b48ccac,5b037a42 | /colinhacks/zod |
| Rename labels Base/Compare | frontend-mobile-development:frontend-developer | implementation | 4 | - | B | complete | 0 | a60cf7843d0fd984e | aac9ca0a,5b037a42 | - |
| Universal compare button + picker | frontend-mobile-development:frontend-developer | implementation | 5 | - | C | complete | 0 | ac0ed5da409f87dfd | e0509022 | - |
| Case version matching logic | frontend-mobile-development:frontend-developer | implementation | 6 | - | D | pending | 0 | - | pending | - |
| Delta summary snapshot diff | frontend-mobile-development:frontend-developer | implementation | 7 | - | D | pending | 0 | - | pending | - |
| Export neutral meta-prompt | frontend-mobile-development:frontend-developer | implementation | 8 | - | E | pending | 0 | - | pending | - |
