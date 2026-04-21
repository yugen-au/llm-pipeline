# IMPLEMENTATION - STEP 8: EVALUATIONCASE READ/WRITE SITES
**Status:** completed

## Summary
Updated all EvaluationCase read sites to filter by is_active==True AND is_latest==True, replaced all write sites (create, update, delete) to route through versioning helpers, added DB->YAML writeback triggers, and exposed run snapshot columns in API responses.

## Files
**Created:** tests/evals/__init__.py, tests/evals/test_yaml_sync.py
**Modified:** llm_pipeline/evals/runner.py, llm_pipeline/evals/yaml_sync.py, llm_pipeline/ui/routes/evals.py, tests/ui/test_evals_routes.py
**Deleted:** none

## Changes
### File: `llm_pipeline/evals/runner.py`
C1: Added is_active==True AND is_latest==True filters to case query in run_dataset.

### File: `llm_pipeline/evals/yaml_sync.py`
C2: Replaced manual EvaluationCase query with get_latest() from versioning helpers.
C3: Added is_active==True AND is_latest==True to writeback query in write_dataset_to_yaml.
CW5: Replaced raw insert with version-aware logic: first-time -> save_new_version; YAML newer -> save_new_version with explicit version; same/older -> WARNING log + no-op.

### File: `llm_pipeline/ui/routes/evals.py`
C4: Added is_active/is_latest filters to case-count subquery.
C5: Added filters to get_dataset cases query.
C6: Added filters to update_dataset reload query.
CW1: create_case routes through save_new_version + triggers writeback.
CW2: update_case creates new version via save_new_version + triggers writeback.
CW3: delete_case uses soft_delete_latest instead of hard delete + triggers writeback.
Added _trigger_evals_writeback helper.
Added snapshot columns to RunListItem/RunDetail response models and threaded through list/detail endpoints.

### File: `tests/ui/test_evals_routes.py`
Test #12: test_run_detail_null_snapshots_returns_200 + test_list_runs_null_snapshots_returns_200.

### File: `tests/evals/test_yaml_sync.py`
Test #15: test_yaml_newer_inserts_and_flips
Test #16: test_yaml_older_logs_warning_noop, test_yaml_equal_version_logs_warning_noop
Test #17: test_put_case_triggers_yaml_writeback
Test #18: test_delete_case_triggers_yaml_writeback

## Decisions
### Cascade delete remains unfiltered
**Choice:** delete_dataset still fetches ALL case rows (no is_active/is_latest filter) for hard-delete cascade.
**Rationale:** When entire dataset is deleted, all historical version rows must be removed too.

### RunListItem/RunDetail snapshot fields added in this step
**Choice:** Exposed case_versions, prompt_versions, model_snapshot, instructions_schema_snapshot in response models here (Step 12 scope partially).
**Rationale:** Test #12 requires these fields in the response to verify null-tolerance; adding them here avoids a circular dependency with Step 12.

## Verification
[x] tests/evals/test_yaml_sync.py: 5 passed
[x] tests/ui/test_evals_routes.py: 47 passed
[x] tests/test_versioning_helpers.py + tests/prompts/test_yaml_sync.py: all passed
[x] grep audit: no missed select(EvaluationCase) sites (cascade delete intentionally unfiltered)
