## Task: adhoc-20260421-generic-run-comparison
## Description: Generic eval run comparison — replace baseline-only compare with any-two-runs picker, case-level version matching (matched/drifted/unmatched buckets), scoped aggregates. Modify existing comparison page to support any run-to-run comparison.

## Phase: fixing-review
## Status: in-progress
## Current Group: D
## Base Branch: dev
## Task Branch: sam/adhoc/20260421-generic-run-comparison
## Plugins: frontend-mobile-development, backend-development
## Graphiti Group ID: llm-pipeline
## Excluded Phases: none
## Steps to Fix: [1,3,5,6,7]
## Work Mode: standard
## PRD Target Tasks: 0
## Last Updated: 2026-04-22 10:58

## Agents
| Name | Agent | Phase | Step | Skills | Group | Status | Revisions | Agent ID | Commits | Context7 Docs |
|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|
| Frontend comparison UI research | frontend-mobile-development:frontend-developer | research | 1 | - | A | complete | 0 | a8ba5c2d48353bdbc | 2c9b329b | - |
| Backend comparison logic research | backend-development:backend-architect | research | 2 | - | A | complete | 0 | a36edd5e701e73d61 | 2c9b329b | - |
| Assumption Check | code-documentation:code-reviewer | validate | 1 | - | A | complete | 1 | a20d56ad5a3832e24 | a4bde376 | - |
| Plan | planning | planning | 1 | - | A | complete | 0 | a60feb2cf2494a2ea | c2e269ac | - |
| Add case_id to CaseResultItem | backend-development:backend-architect | implementation | 1 | - | A | complete | 1 | afaca1f080245dc19 | b8c76a6a,de2bff9d,0ceffc3d | - |
| Sync frontend TS types | frontend-mobile-development:frontend-developer | implementation | 2 | - | A | complete | 0 | a721761759d582a9b | 6249de3d,de2bff9d | - |
| Zod schema compareRunId + alias | frontend-mobile-development:frontend-developer | implementation | 3 | - | B | complete | 1 | a26d93ef239524bff | 8b48ccac,5b037a42 | /colinhacks/zod |
| Rename labels Base/Compare | frontend-mobile-development:frontend-developer | implementation | 4 | - | B | complete | 0 | a60cf7843d0fd984e | aac9ca0a,5b037a42 | - |
| Universal compare button + picker | frontend-mobile-development:frontend-developer | implementation | 5 | - | C | complete | 1 | a7a8d177dea94dab1 | e0509022,e16d48a2 | - |
| Case version matching logic | frontend-mobile-development:frontend-developer | implementation | 6 | - | D | in-progress | 0 | ad6bce4c62a996dc6 | 0da4c5a0,febfdd6a | - |
| Delta summary snapshot diff | frontend-mobile-development:frontend-developer | implementation | 7 | - | D | in-progress | 0 | ae04cab6675148f8a | febfdd6a | - |
| Export neutral meta-prompt | frontend-mobile-development:frontend-developer | implementation | 8 | - | E | complete | 0 | accaa787bd57e47f7 | e22de50e | - |
| Verify build | full-stack-orchestration:test-automator | testing | 1 | - | A | complete | 0 | a8a93c72276b486b7 | fae357b1 | - |
| Architecture review | comprehensive-review:architect-review | review | 1 | - | A | pending | 0 | a9cdd929eb7782c79 | 3bbee64d | - |
