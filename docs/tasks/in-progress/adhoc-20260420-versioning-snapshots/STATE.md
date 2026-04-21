## Task: adhoc-20260420-versioning-snapshots
## Description: Dataset and prompt versioning with run-time snapshots (case_versions, prompt_versions, model_snapshot, instructions_schema_snapshot on EvaluationRun), soft delete (deleted_at), bidirectional YAML sync for datasets matching prompts pattern, and compare-view version-mismatch badge.

## Phase: testing
## Status: in-progress
## Current Group: A
## Base Branch: dev
## Task Branch: sam/adhoc/20260420-versioning-snapshots
## Plugins: database-design, backend-development, python-development
## Graphiti Group ID: llm-pipeline
## Excluded Phases: none
## Steps to Fix: none
## Work Mode: standard
## PRD Target Tasks: 0
## Last Updated: 2026-04-21 11:22

## Agents
| Name | Agent | Phase | Step | Skills | Group | Status | Revisions | Agent ID | Commits | Context7 Docs |
|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|
| Schema architecture research | database-design:database-architect | research | 1 | - | A | complete | 1 | a9329691024f44b8c | ccf8aaa4 | - |
| Runtime paths & YAML sync research | backend-development:backend-architect | research | 2 | - | A | complete | 0 | ad5da342bce5bf932 | ccf8aaa4 | - |
| Python/SQLModel versioning research | python-development:python-pro | research | 3 | - | A | complete | 1 | aaf0cd23978d077bf | ccf8aaa4 | - |
| Assumption Check | code-documentation:code-reviewer | validate | 1 | - | A | complete | 2 | aa930d7945b045fa9 | 5bf52473 | - |
| Plan | planning | planning | 1 | - | A | complete | 0 | ada764be7e14da977 | 3d1fc724 | - |
| Move compare_versions to utils | python-development:python-pro | implementation | 1 | - | A | complete | 0 | ad5e5876729095fb4 | 0434a5a3 | /pydantic/pydantic |
| Prompt schema updates | database-design:database-architect | implementation | 3 | database-design:postgresql | A | complete | 0 | a8bbbad352da681c4 | 44a7b796,0434a5a3 | /websites/sqlmodel_tiangolo,/websites/sqlalchemy_en_20_core |
| EvaluationCase + EvaluationRun schema | database-design:database-architect | implementation | 4 | database-design:postgresql | A | complete | 0 | aed406fd9d4bdb977 | 0434a5a3 | /websites/sqlmodel_tiangolo,/websites/sqlalchemy_en_20_orm |
| Versioning helper module | python-development:python-pro | implementation | 2 | python-development:python-testing-patterns | B | complete | 0 | a757db5087b0ed70d | 78cbae7b | /websites/sqlmodel_tiangolo,/websites/sqlalchemy_en_20_orm |
| Migration + partial unique indexes | database-design:database-architect | implementation | 5 | database-design:postgresql | B | complete | 0 | aabd1595fb76071bc | 78cbae7b | /websites/sqlalchemy_en_20_core |
| Prompt read-site updates | backend-development:backend-architect | implementation | 6 | - | C | complete | 0 | ac9a82e84080566e1 | cbea8c12,b8e0b72b | /websites/sqlmodel_tiangolo |
| Prompt write-site + YAML sync | backend-development:backend-architect | implementation | 7 | backend-development:api-design-principles | C | complete | 0 | a5ee03bc57fd13815 | ac1e6160,b8e0b72b | /websites/sqlmodel_tiangolo,/pydantic/pydantic |
| EvaluationCase read/write sites | backend-development:backend-architect | implementation | 8 | - | C | complete | 0 | aac386015be965cea | b8e0b72b | /websites/sqlmodel_tiangolo |
| Runner snapshot population | backend-development:backend-architect | implementation | 9 | backend-development:workflow-orchestration-patterns | C | complete | 0 | ae94878986ab150d4 | 340fca29,b8e0b72b | /websites/pydantic_dev_validation |
| Dataset YAML bidirectional sync | backend-development:backend-architect | implementation | 10 | - | D | complete | 0 | a185d4e99100f39a0 | a2e7bb49 | /websites/sqlmodel_tiangolo |
| Sandbox seed filter | python-development:python-pro | implementation | 11 | - | D | complete | 0 | aa743938edd9ee142 | a2e7bb49 | - |
| API response shape for snapshots | backend-development:backend-architect | implementation | 12 | backend-development:api-design-principles | D | complete | 0 | abd0b630535fa2119 | fce91026,a2e7bb49 | /pydantic/pydantic |
| Verify build | full-stack-orchestration:test-automator | testing | 1 | - | A | in-progress | 0 | pending | pending | - |
