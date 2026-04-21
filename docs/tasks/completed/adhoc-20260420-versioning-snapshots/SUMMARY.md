# Task Summary

## Work Completed

Implemented append-only versioning for Prompt and EvaluationCase models with run-time snapshot capture on EvaluationRun. Added partial unique indexes enforced at DB level, a generic db/versioning.py helper used across all write sites, bidirectional YAML sync for datasets mirroring the prompts pattern, soft-delete semantics (is_active=False, is_latest=True), and snapshot API response shapes. 12 implementation steps across 4 groups (A-D). 2 review fixes applied post-architect review. All 119 versioning-specific tests pass; 15 pre-existing unrelated failures unchanged.

## Files Changed

### Created
| File | Purpose |
| --- | --- |
| llm_pipeline/utils/versioning.py | compare_versions utility moved from prompts/yaml_sync.py |
| llm_pipeline/utils/__init__.py | Package init for new utils module |
| llm_pipeline/db/versioning.py | Generic versioning helper: save_new_version, get_latest, soft_delete_latest, _bump_minor, _utc_now |
| tests/test_versioning_helpers.py | 24 tests covering all helper behaviors |
| tests/test_migrations.py | 5 migration tests: dedupe of duplicate eval_cases, legacy index drops, idempotency |
| tests/test_eval_runner.py | 11 runner tests including step-target and pipeline-target snapshot shapes |
| tests/evals/test_yaml_sync.py | 5 tests: dataset YAML newer/older logic, writeback on PUT/DELETE |
| tests/evals/__init__.py | Package init for evals test subpackage |

### Modified
| File | Changes |
| --- | --- |
| llm_pipeline/db/prompt.py | Added is_latest column; replaced UniqueConstraint with partial unique index uq_prompts_active_latest; added supporting indexes |
| llm_pipeline/evals/models.py | Added version, is_active, is_latest, updated_at to EvaluationCase; added case_versions, prompt_versions, model_snapshot, instructions_schema_snapshot JSON columns to EvaluationRun |
| llm_pipeline/db/__init__.py | Extended _MIGRATIONS with 9 new column entries; added _migrate_partial_unique_indexes with dedupe pre-pass and idempotent index creation; wired into init_pipeline_db |
| llm_pipeline/prompts/yaml_sync.py | Replaced manual version logic with get_latest/save_new_version; ported write_prompt_to_yaml to atomic temp-file + Path.replace; WARNING no-op on version regression |
| llm_pipeline/prompts/__init__.py | Re-exports compare_versions from utils.versioning for backward compat |
| llm_pipeline/prompts/resolver.py | Added is_latest==True filter |
| llm_pipeline/prompts/service.py | Added is_latest==True to get_prompt and prompt_exists |
| llm_pipeline/pipeline.py | Added is_active==True AND is_latest==True to both prompt lookups |
| llm_pipeline/introspection.py | Added is_latest==True filter |
| llm_pipeline/ui/app.py | Added is_latest==True in _sync_variable_definitions |
| llm_pipeline/ui/routes/editor.py | Added is_latest==True to prompt query |
| llm_pipeline/ui/routes/prompts.py | Rewrote CRUD to use save_new_version/soft_delete_latest/get_latest; _apply_filters adds is_latest by default |
| llm_pipeline/ui/routes/evals.py | All read sites filtered by is_active+is_latest; write sites use versioning helpers; snapshot fields added to RunListItem and RunDetail; 409 guard on case rename |
| llm_pipeline/ui/routes/pipelines.py | Added is_active+is_latest prompt filters |
| llm_pipeline/evals/runner.py | Added is_active+is_latest to case query; implemented _build_run_snapshot pre-pass; added is_active filter to sandbox variant prompt queries (review fix) |
| llm_pipeline/evals/yaml_sync.py | Rewrote case insert/lookup to use get_latest/save_new_version; reads version from YAML with 1.0 default |
| llm_pipeline/sandbox.py | Seed query filtered to is_active+is_latest; seeded rows copy is_latest through |
| llm_pipeline/creator/prompts.py | Switched to get_latest + save_new_version with content-hash gating |
| llm_pipeline/creator/integrator.py | Switched to get_latest + save_new_version with 1.0 first-time fallback |
| tests/prompts/test_yaml_sync.py | Added tests 13 and 14: YAML newer inserts version+flips; older/equal logs WARNING+noop |
| tests/ui/test_evals_routes.py | Added 59 lines for null-snapshot legacy compat test |

## Commits Made
| Hash | Message |
| --- | --- |
| 8ac73d59 | feat(db): add is_latest to Prompt, replace unique constraint with partial unique index |
| 44a7b796 | docs(implementation-A): adhoc-20260420-versioning-snapshots |
| 0434a5a3 | docs(implementation-A): adhoc-20260420-versioning-snapshots |
| e11dfefa | docs(implementation-A): adhoc-20260420-versioning-snapshots |
| 9c1b8b41 | docs(implementation-A): adhoc-20260420-versioning-snapshots |
| 78cbae7b | docs(implementation-B): adhoc-20260420-versioning-snapshots |
| cbea8c12 | docs(implementation-C): adhoc-20260420-versioning-snapshots |
| ac1e6160 | docs(implementation-C): adhoc-20260420-versioning-snapshots |
| 340fca29 | docs(implementation-C): adhoc-20260420-versioning-snapshots |
| b8e0b72b | docs(implementation-C): adhoc-20260420-versioning-snapshots |
| fce91026 | docs(implementation-D): adhoc-20260420-versioning-snapshots |
| a2e7bb49 | docs(implementation-D): adhoc-20260420-versioning-snapshots |
| 40ab79c1 | docs(testing-A): adhoc-20260420-versioning-snapshots |
| c7ee3364 | docs(review-A): adhoc-20260420-versioning-snapshots |
| 61063bbc | docs(fixing-review-C): adhoc-20260420-versioning-snapshots |
| 89eab9da | docs(fixing-review-D): adhoc-20260420-versioning-snapshots |
| 8a7fd4f4 | docs(review-A): adhoc-20260420-versioning-snapshots |

## Deviations from Plan

- PLAN Step 5 assigned database-migrations:sql-migrations skill which does not exist; migration implemented using database-design:postgresql only. No functional impact.
- PLAN groups A/B listed Steps 2 and 5 in group A; STATE records them as group B. Code landed in same batch commits; ordering was a bookkeeping artifact, not a functional deviation.
- Schema partial-index commit (8ac73d59) predates grouped implementation doc commits, consistent with early Prompt model work in PLAN Step 3.

## Issues Encountered

### Case rename via direct mutation bypasses partial unique index
**Resolution:** Added get_latest(db, EvaluationCase, dataset_id=dataset_id, name=body.name) check before mutating case.name in update_case. Returns HTTP 409 Conflict with descriptive message on name collision. Fix committed in 61063bbc.

### Sandbox variant prompt queries omit is_active filter
**Resolution:** Added Prompt.is_active == True to both system and user prompt queries in _apply_variant_to_sandbox (runner.py L839, L869). Consistent with defense-in-depth pattern across all other prompt query sites. Fix committed in 89eab9da.

## Success Criteria
- [x] tests/test_versioning_helpers.py -- 24 passed (Steps 1, 2, 6)
- [x] tests/test_migrations.py -- 5 passed (Step 5)
- [x] tests/prompts/test_yaml_sync.py -- 27 passed (Step 7)
- [x] tests/evals/test_yaml_sync.py -- 5 passed (Steps 8, 10)
- [x] tests/test_eval_runner.py -- 11 passed (Step 9)
- [x] tests/ui/test_evals_routes.py -- 52 passed (Steps 8, 12)
- [x] Full uv run pytest -- 1554/1569 passed; 15 pre-existing failures confirmed identical on stashed branch
- [x] Architect review -- approved clean after 2 medium-severity fixes
- [ ] Manual: UI prompt edit -> new version row + YAML updated (human validation pending)
- [ ] Manual: eval run -> EvaluationRun.prompt_versions populated (human validation pending)
- [ ] Manual: soft-delete + recreate cycle (human validation pending)
- [ ] Grep audit for missed is_latest filter sites (not run in testing session)

## Recommendations for Follow-up
1. Run grep audit for missed is_latest filter sites in llm_pipeline/ -- mandated in PLAN Steps 6 and 8 but not executed during testing phase.
2. GET /prompts/{prompt_key} intentionally returns all versions without is_latest filter; PromptDetailResponse does not distinguish latest vs historical. Add is_latest field to response and implement frontend version history badge (deferred per PLAN Step 12).
3. _migrate_partial_unique_indexes dedupe SQL orders by created_at DESC, id DESC -- NULL created_at on legacy rows sorts differently in SQLite (last) vs PostgreSQL (first). Low risk for current SQLite-primary target but worth hardening before PostgreSQL support.
4. Frontend version history panel -- historical (is_latest=False) rows are queryable via existing API; no UI surfaces them yet.
5. Purge/archive policy for old non-latest rows -- schema is append-only with no TTL; consider a periodic archival job for large deployments.
