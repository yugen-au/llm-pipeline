## Task: adhoc-20260416-pydantic-evals-v1
## Description: Integrate pydantic-evals into llm-pipeline: YAML datasets (llm-pipeline-evals/) with bidirectional DB sync, step/pipeline-level evaluation, auto field-match evaluators from instructions schema, custom evaluators on step_definition, live eval runner, new DB tables (EvaluationDataset/Case/Run/CaseResult), backend routes, frontend Evals tab (dataset list, case editor, run history, run detail), CLI command, worked sentiment_analysis example.

## Phase: summary
## Status: in-progress
## Current Group: A
## Base Branch: dev
## Task Branch: sam/adhoc/20260416-pydantic-evals-v1
## Plugins: llm-application-dev, backend-development, frontend-mobile-development
## Graphiti Group ID: llm-pipeline
## Excluded Phases: none
## Steps to Fix: [4]
## Work Mode: standard
## PRD Target Tasks: 0
## Last Updated: 2026-04-16 14:47

## Agents
| Name | Agent | Phase | Step | Skills | Group | Status | Revisions | Agent ID | Commits | Context7 Docs |
|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|
| pydantic-evals API research | llm-application-dev:ai-engineer | research | 1 | - | A | complete | 0 | af401525e1c085f50 | 1a236556 | - |
| Backend architecture research | backend-development:backend-architect | research | 2 | - | A | complete | 0 | a1654374433803c14 | 1a236556 | - |
| Frontend patterns research | frontend-mobile-development:frontend-developer | research | 3 | - | A | complete | 0 | a9ae5be52dbebc037 | 1a236556 | - |
| Assumption Check | code-documentation:code-reviewer | validate | 1 | - | A | complete | 1 | a14671863eb362f54 | f7730fd7 | - |
| Plan | planning | planning | 1 | - | A | complete | 0 | ad6008c323d225293 | 6bdfc45e | - |
| Core dep + DB models + table reg | backend-development:backend-architect | implementation | 1 | - | A | complete | 0 | ab4c5ff2d477803c7 | ff862ebd,534770d4 | - |
| evaluators= param + auto FieldMatch | backend-development:backend-architect | implementation | 2 | - | A | complete | 0 | ad0a8c24e93aa8842 | 2644c8ad,534770d4 | - |
| YAML sync + eval runner + CLI | llm-application-dev:ai-engineer | implementation | 3 | - | A | complete | 0 | a4459d6dbc298e2b5 | 534770d4 | - |
| Backend routes datasets+cases | backend-development:backend-architect | implementation | 4 | - | B | complete | 2 | a892409485a506cf0 | 0bebd93e,06677777,c501e432,bd220aa7 | - |
| Backend routes runs+introspection | backend-development:backend-architect | implementation | 5 | - | B | complete | 1 | ae93a80df9e09653c | 06677777,3b86f82e | - |
| Wire evals router + startup sync | backend-development:backend-architect | implementation | 6 | - | B | complete | 0 | a8773e0286187058a | 9683d3cb,06677777 | - |
| Frontend API hooks + routes | frontend-mobile-development:frontend-developer | implementation | 7 | - | C | complete | 0 | a2d14f07542e90288 | 7f5f9583,bb4b604c | /tanstack/router |
| Frontend dataset list + detail | frontend-mobile-development:frontend-developer | implementation | 8 | - | C | complete | 0 | ac557c08e614fd3a4 | bb4b604c | /tanstack/router |
| Frontend run detail + sidebar | frontend-mobile-development:frontend-developer | implementation | 9 | - | C | complete | 0 | a67a6b99bff887b05 | 9c07d16e,bb4b604c | /tanstack/router |
| Worked example sentiment eval | llm-application-dev:ai-engineer | implementation | 10 | llm-application-dev:llm-evaluation | D | complete | 0 | a25b1d92630002ffb | 365732ca | - |
| Verify build | full-stack-orchestration:test-automator | testing | 1 | - | A | complete | 2 | aae3aad3d2d63372d | 2726fb2a,d7ea715d,04ed6123 | - |
| Architecture review | comprehensive-review:architect-review | review | 1 | - | A | complete | 2 | aeafe414fedb9c79f | 7426e072,dfe627bd,747d8c4f | - |
| Create summary | code-documentation:docs-architect | summary | 1 | - | A | in-progress | 0 | pending | pending | - |
