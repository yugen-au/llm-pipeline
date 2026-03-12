# IMPLEMENTATION - STEP 9: REWRITE PREPARE_CALLS
**Status:** completed

## Summary
Replaced all `self.create_llm_call(variables=...)` calls in test step `prepare_calls()` methods with plain dict returns `{"variables": {...}}`. Deleted 3 `create_llm_call` deprecation test methods from `test_agent_registry_core.py`. Updated `StepDeps` field count assertion from 8 to 10 to reflect the 2 new fields added in Step 2 (`array_validation`, `validation_context`).

## Files
**Created:** none
**Modified:**
- tests/events/test_ctx_state_events.py
- tests/events/test_extraction_events.py
- tests/test_introspection.py
- tests/test_agent_registry_core.py
**Deleted:** none

## Changes

### File: `tests/events/test_ctx_state_events.py`
EmptyContextStep.prepare_calls() replaced create_llm_call with plain dict.
```
# Before
def prepare_calls(self) -> List[StepCallParams]:
    return [self.create_llm_call(variables={"data": "test"})]

# After
def prepare_calls(self) -> List[StepCallParams]:
    return [{"variables": {"data": "test"}}]
```

### File: `tests/events/test_extraction_events.py`
FailingItemDetectionStep.prepare_calls() replaced create_llm_call with plain dict.
```
# Before
def prepare_calls(self) -> List[StepCallParams]:
    return [self.create_llm_call(variables={"data": "test"})]

# After
def prepare_calls(self) -> List[StepCallParams]:
    return [{"variables": {"data": "test"}}]
```

### File: `tests/test_introspection.py`
Three steps updated: WidgetDetectionStep, ScanDetectionStep, GadgetDetectionStep.
```
# Before (WidgetDetectionStep)
return [self.create_llm_call(variables={"data": self.pipeline.get_sanitized_data()})]

# After
return [{"variables": {"data": self.pipeline.get_sanitized_data()}}]

# Before (ScanDetectionStep, GadgetDetectionStep)
return [self.create_llm_call(variables={})]

# After
return [{"variables": {}}]
```

### File: `tests/test_agent_registry_core.py`
- Removed `import warnings` (no longer used after method deletions).
- Deleted 3 test methods: `test_create_llm_call_deprecation_warning`, `test_create_llm_call_stacklevel`, `test_create_llm_call_still_works`.
- Updated `test_field_count` assertion from 8 to 10 (Step 2 added `array_validation` + `validation_context` to StepDeps).
- Updated `test_optional_field_names` and `test_optional_defaults_none` to assert the 2 new optional fields.

## Decisions

### Already-updated files
**Choice:** tests/events/conftest.py, tests/test_pipeline.py, tests/test_pipeline_run_tracking.py were already updated in a prior step (Step 8). No changes needed.
**Rationale:** These files already had plain dict returns in prepare_calls() by the time Step 9 ran.

### StepDeps field count update
**Choice:** Update test_field_count from 8 to 10 as part of Step 9.
**Rationale:** Step 2 added 2 new fields. The assertion was stale. Updating it is the correct fix regardless of which step owns it — the test was failing and the fix is trivial.

### Remaining event test failures
**Choice:** Not fixing failures in test_ctx_state_events.py and test_extraction_events.py helper functions that use `provider=`.
**Rationale:** Those failures are pre-existing Step 8 issues (MockProvider replacement). Step 9 scope is prepare_calls() only. The prepare_calls() changes in those files are correct.

## Verification
- [x] No `create_llm_call` calls remain in test prepare_calls() methods (only a comment in test_agent_registry_core.py section header)
- [x] `tests/test_agent_registry_core.py` has no `create_llm_call` test methods
- [x] `import warnings` removed from test_agent_registry_core.py
- [x] 124 tests pass across test_agent_registry_core.py, test_introspection.py, test_pipeline.py, test_pipeline_run_tracking.py
- [x] Remaining failures are pre-existing Step 8 provider= issues, not introduced by Step 9

## Review Fix Iteration 1
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
- [x] Stale section header comment references deleted method `create_llm_call()` in `tests/test_agent_registry_core.py` around line 250

### Changes Made
#### File: `tests/test_agent_registry_core.py`
Removed `create_llm_call() deprecation` from section header comment since the method was deleted, not merely deprecated.
```
# Before
# step.py - LLMStep.get_agent(), build_user_prompt(), create_llm_call() deprecation

# After
# step.py - LLMStep.get_agent(), build_user_prompt() deprecation
```

### Verification
- [x] Comment updated to reflect deletion (not deprecation) of create_llm_call()
- [x] No other references to update in this scope
