# Architecture Review

## Overall Assessment
**Status:** complete

Solid implementation of append-only versioning across Prompt and EvaluationCase with consistent use of `save_new_version`/`get_latest`/`soft_delete_latest` helpers. Schema design, partial unique indexes, flush-before-insert discipline, and call-site coverage are all well-executed. The snapshot pre-pass in `_build_run_snapshot` is deterministic and atomic. Minor issues found, no blockers.

## Project Guidelines Compliance
**CLAUDE.md:** `c:\Users\SamSG\Documents\claude-projects\llm-pipeline\.claude\CLAUDE.md`
| Guideline | Status | Notes |
| --- | --- | --- |
| TDD strict | pass | 51 tests pass covering helpers, yaml_sync, partial unique, sandbox |
| No hardcoded values | pass | All version defaults are "1.0" by convention, not magic strings |
| Error handling present | pass | ValueError on managed cols, version regression; IntegrityError catch on create |
| SQLModel/SQLAlchemy 2.0 | pass | Consistent `select()` style, proper `session.flush()` usage |
| Hatchling build | pass | No build changes needed |
| Bidirectional YAML sync | pass | Atomic writes via temp-file + Path.replace; version comparison gating |

## Issues Found
### Critical
None

### High
None

### Medium
#### Case rename via direct mutation bypasses partial unique index validation
**Step:** 8
**Details:** In `update_case` (evals.py L895-898), when `body.name` differs from `old_case.name`, the code mutates `case.name` directly after `save_new_version`. This bypasses the helper's version validation and could collide with the partial unique index if the target name already exists as an active+latest case in the same dataset. The 500 IntegrityError would surface to the user without a helpful message. Should add an existence check before the rename, or route name changes through `save_new_version` with the new name as key_filter.

#### Sandbox variant prompt queries omit `is_active` filter
**Step:** 6 (call-site updates)
**Details:** In `_apply_variant_to_sandbox` (runner.py L835-868), prompt lookups use `Prompt.is_latest == True` but not `Prompt.is_active == True`. This is functionally safe because the sandbox DB is seeded only with active+latest rows, so no inactive rows exist. However it breaks the "defense-in-depth" pattern used everywhere else and would silently regress if sandbox seeding logic changes. Low-effort fix to add the filter.

### Low
#### `get_prompt` detail endpoint returns all version rows without documentation in API response
**Step:** 6
**Details:** The `GET /prompts/{prompt_key}` endpoint (prompts.py L188-207) intentionally returns all variants/versions without `is_latest` filter. The inline comment explains intent, but the API response model (`PromptDetailResponse`) does not distinguish which variant is latest vs historical. Frontend consumers must infer from `is_active` field. Acceptable for now given frontend badge rendering is deferred.

#### Dedupe migration uses `created_at` which may be NULL on legacy rows
**Step:** 5
**Details:** The `_migrate_partial_unique_indexes` dedupe SQL orders by `created_at DESC, id DESC`. If legacy `eval_cases` rows have NULL `created_at` (possible if the column was added later without a DEFAULT), NULL sorts last in SQLite (first in PostgreSQL), making the tiebreak unpredictable. The `id DESC` fallback mitigates this for most cases but the behavior differs across engines. Since this project targets SQLite primarily and `created_at` has always been part of the schema per models.py, risk is very low.

## Review Checklist
[x] Architecture patterns followed
[x] Code quality and maintainability
[x] Error handling present
[x] No hardcoded values
[x] Project conventions followed
[x] Security considerations
[x] Properly scoped (DRY, YAGNI, no over-engineering)

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| llm_pipeline/db/prompt.py | pass | is_latest column, partial unique index, proper __table_args__ |
| llm_pipeline/evals/models.py | pass | 4 new cols on EvaluationCase, 4 snapshot cols on EvaluationRun |
| llm_pipeline/utils/versioning.py | pass | Clean compare_versions with zero-padding |
| llm_pipeline/db/versioning.py | pass | Flush-before-insert, forbidden cols guard, version regression check |
| llm_pipeline/db/__init__.py | pass | 9 migration entries, dedupe logic, partial unique creation |
| llm_pipeline/prompts/resolver.py | pass | is_active + is_latest filters |
| llm_pipeline/prompts/service.py | pass | Both get_prompt and prompt_exists filtered |
| llm_pipeline/prompts/yaml_sync.py | pass | get_latest + save_new_version, atomic write |
| llm_pipeline/prompts/__init__.py | pass | Re-exports compare_versions for backward compat |
| llm_pipeline/pipeline.py | pass | is_active + is_latest on both prompt lookups |
| llm_pipeline/introspection.py | pass | Filtered by is_active + is_latest |
| llm_pipeline/sandbox.py | pass | Seed query filters active+latest, copies is_latest |
| llm_pipeline/evals/runner.py | pass | Case query filtered, _build_run_snapshot correct |
| llm_pipeline/evals/yaml_sync.py | pass | get_latest + save_new_version, writeback filtered |
| llm_pipeline/ui/routes/prompts.py | pass | _apply_filters adds is_latest, CRUD uses helpers |
| llm_pipeline/ui/routes/evals.py | pass | All read sites filtered; write sites use helpers |
| llm_pipeline/ui/routes/pipelines.py | pass | is_active + is_latest |
| llm_pipeline/ui/routes/editor.py | pass | Prompt queries filtered |
| llm_pipeline/ui/app.py | pass | _sync_variable_definitions uses is_latest |
| llm_pipeline/creator/prompts.py | pass | get_latest + content-hash gating |
| llm_pipeline/creator/integrator.py | pass | get_latest + save_new_version |
| tests/test_versioning_helpers.py | pass | 8+ test classes covering all helper behaviors |
| tests/prompts/test_yaml_sync.py | pass | Newer/older logic, atomic write |

## New Issues Introduced
- Case rename mutation (medium) could cause unhandled IntegrityError on name collision
- No other new issues detected; existing test suite passes with 0 new failures

## Recommendation
**Decision:** APPROVE
Implementation is architecturally sound with consistent patterns across all 20+ call sites. The single medium issue (case rename) is an edge case that surfaces as a 500 rather than silent data corruption — acceptable for current iteration. All core review concerns from the task description are satisfied: is_latest filtering complete, flush-before-insert correct, partial unique indexes properly specified, soft-delete semantics consistent, snapshot pre-pass handles both target types.

---

# Architecture Review (Follow-up)

## Overall Assessment
**Status:** complete

Both medium issues from the initial review have been fixed correctly. The case rename now returns a clean 409 Conflict on name collision, and the sandbox variant prompt queries include `is_active == True` for defense-in-depth consistency. No regressions detected.

## Fix Verification

### Issue 1: Case rename bypasses partial unique index validation
**Commit:** 61063bbc
**Fix:** Added `get_latest(db, EvaluationCase, dataset_id=dataset_id, name=body.name)` check before mutating `case.name`. Returns 409 with descriptive message on conflict.
**Verdict:** Correct. `get_latest` already applies `is_active == True` and `is_latest == True` internally, so this catches active name collisions. If the check fails and raises HTTPException, the `WritableDBSession` context manager rolls back the already-flushed `save_new_version` row. No orphan risk.

### Issue 2: Sandbox variant prompt queries omit `is_active` filter
**Commit:** 89eab9da
**Fix:** Added `Prompt.is_active == True` filter to both system and user prompt queries in `_apply_variant_to_sandbox` (runner.py L839, L869).
**Verdict:** Correct. Consistent with all other prompt query sites. `# noqa: E712` comment preserved for linter compliance.

## Issues Found
### Critical
None

### High
None

### Medium
None

### Low
None

## Review Checklist
[x] Architecture patterns followed
[x] Code quality and maintainability
[x] Error handling present
[x] No hardcoded values
[x] Project conventions followed
[x] Security considerations
[x] Properly scoped (DRY, YAGNI, no over-engineering)

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| llm_pipeline/ui/routes/evals.py | pass | 409 conflict guard before rename, correct use of get_latest |
| llm_pipeline/evals/runner.py | pass | is_active filter added to both prompt queries in _apply_variant_to_sandbox |

## New Issues Introduced
- None detected

## Recommendation
**Decision:** APPROVE
Both fixes are minimal, correct, and consistent with project patterns. No new issues introduced. Implementation is ready to proceed.
