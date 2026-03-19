# IMPLEMENTATION - STEP 5: TESTS INTEGRATOR
**Status:** completed

## Summary
Created `tests/test_step_integrator.py` with 17 integration tests for `StepIntegrator` across 4 test classes. Uses in-memory SQLite engine via `create_engine("sqlite://") + init_pipeline_db()`. All 17 tests pass in 1.10s.

## Files
**Created:** `tests/test_step_integrator.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `tests/test_step_integrator.py`
New file. 4 test classes, 17 tests total.

```
# Before
(file did not exist)

# After
tests/test_step_integrator.py
  TestStepIntegratorFileWrites (5 tests)
  TestStepIntegratorPromptRegistration (4 tests)
  TestStepIntegratorRollback (4 tests)
  TestStepIntegratorDraftStatusUpdate (4 tests)
```

## Decisions

### Session.commit monkey-patching
**Choice:** Replace `session.commit` with a failing callable directly on the instance rather than using `unittest.mock.patch`.
**Rationale:** SQLModel Session.commit is a bound method; patching it at instance level avoids import-path issues and works cleanly across SQLModel versions.

### Separate engine per test method
**Choice:** Each test creates its own `create_engine("sqlite://")` and calls `engine.dispose()` at end.
**Rationale:** In-memory SQLite engines are isolated per connection; no shared state between tests. Mirrors pattern in `tests/test_draft_tables.py`.

### Rollback .bak test uses patch on ast_modifier
**Choice:** `patch("llm_pipeline.creator.integrator.ast_modifier.modify_pipeline_file", side_effect=Exception(...))` rather than writing a real pipeline file that would fail AST parse.
**Rationale:** Testing rollback behaviour only, not AST modifier correctness (covered by separate test module). Patch is the minimal reliable approach.

### Extra tests beyond spec
**Choice:** Added `test_file_contents_match_artifacts`, `test_integration_result_target_dir_str`, `test_prompts_registered_count_in_result`, `test_rollback_does_not_remove_preexisting_dir`, `test_draft_updated_at_refreshed_on_accept`, `test_draft_status_in_same_transaction_as_files`.
**Rationale:** These cover important edge cases: content correctness, pre-existing dir preservation, updated_at refresh, single-commit atomicity. All directly testable without additional mocking.

## Verification
- [x] `pytest tests/test_step_integrator.py -v` → 17 passed, 0 failed, 1.10s
- [x] All 4 spec classes implemented: FileWrites, PromptRegistration, Rollback, DraftStatusUpdate
- [x] All 10 spec test cases implemented plus 7 additional edge-case tests
- [x] In-memory SQLite used (no file DB created)
- [x] No hardcoded paths; all use tmp_path fixture
- [x] engine.dispose() called in each test to release in-memory connection
