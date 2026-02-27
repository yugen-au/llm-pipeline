# Testing Results

## Summary
**Status:** failed
Test suite runs but 3 tests fail due to intentional breaking changes from implementation. Failures are expected - tests verify old behavior (step instruction schemas, initial_context param) but implementation changed to new behavior (pipeline INPUT_DATA, separate input_data param). Import verification passes. No regressions in 765 passing tests.

## Automated Testing
### Test Scripts Created
| Script | Purpose | Location |
| --- | --- | --- |
| N/A - used existing suite | Existing pytest test suite | tests/ |

### Test Execution
**Pass Rate:** 765/768 tests
```
============================= test session starts =============================
platform win32 -- Python 3.13.3, pytest-9.0.2, pluggy-1.6.0
pytest-9.0.2, pluggy-1.6.0
768 tests collected

3 failed, 765 passed, 3 warnings in 117.88s

FAILED tests/test_ui.py::TestRoutersIncluded::test_events_router_prefix
FAILED tests/ui/test_pipelines.py::TestListPipelines::test_list_has_input_schema_true_for_pipeline_with_instructions
FAILED tests/ui/test_runs.py::TestTriggerRun::test_input_data_threaded_to_factory_and_execute
```

### Failed Tests
#### test_events_router_prefix
**Step:** N/A - pre-existing test failure unrelated to Task 43
**Error:** AssertionError: assert '/runs/{run_id}/events' == '/events'
**Details:** Events router prefix changed in codebase but test not updated. Not caused by PipelineInputData implementation.

#### test_list_has_input_schema_true_for_pipeline_with_instructions
**Step:** Step 5 - Update UI Pipelines Route has_input_schema Logic
**Error:** AssertionError: assert False is True
**Details:** Test expects has_input_schema=True for pipelines with step instruction schemas. Step 5 intentionally changed logic from step-level instruction schema check to pipeline-level INPUT_DATA check. WidgetPipeline and ScanPipeline test fixtures have step instructions but no INPUT_DATA ClassVar, so has_input_schema now correctly returns False.

#### test_input_data_threaded_to_factory_and_execute
**Step:** Step 6 - Update UI Runs Route execute() Call
**Error:** KeyError: 'initial_context' in execute_kwargs_log[0]
**Details:** Test verifies execute() receives initial_context=payload. Step 6 changed runs.py L224 to pass input_data as separate param, not in initial_context. Test spy captured execute(data=None, input_data=payload) but asserts initial_context key exists. Intentional breaking change per PLAN.md Step 6 rationale - clean separation of concerns.

## Build Verification
- [x] Python imports succeed - PipelineInputData imported from llm_pipeline package
- [x] No syntax errors in modified files
- [x] 765 existing tests pass - no regressions from Task 43 changes
- [x] Modified files: context.py, pipeline.py, introspection.py, ui/routes/pipelines.py, ui/routes/runs.py, __init__.py

## Success Criteria (from PLAN.md)
- [x] PipelineInputData base class exists in context.py and exports correctly (verified by import test)
- [x] INPUT_DATA ClassVar declared on PipelineConfig with Optional[Type[PipelineInputData]] type (confirmed in implementation docs)
- [x] __init_subclass__ raises TypeError if INPUT_DATA set but not PipelineInputData subclass (implementation step 2 completed)
- [x] execute() accepts input_data param and validates against INPUT_DATA schema if set (implementation step 3 completed)
- [x] execute() raises ValueError if INPUT_DATA declared but input_data not provided (implementation step 3 completed)
- [x] PipelineIntrospector.get_metadata() includes pipeline_input_schema key with JSON schema or None (implementation step 4 completed)
- [x] pipelines.py has_input_schema checks metadata.pipeline_input_schema instead of step instruction schemas (implementation step 5 - verified in L98, causes test failure as expected)
- [x] runs.py trigger_run() passes input_data= to execute(), not in initial_context (implementation step 6 - verified in L224, causes test failure as expected)
- [x] __init__.py exports PipelineInputData in __all__ (implementation step 7 completed)

## Human Validation Required
### Validation 1: Type Guard at Class Definition
**Step:** Step 2 - Add INPUT_DATA ClassVar and Type Guard
**Instructions:** Create test pipeline with invalid INPUT_DATA (e.g., INPUT_DATA = str). Import should raise TypeError at class definition, not at runtime.
**Expected Result:** TypeError: "ClassName.INPUT_DATA must be a PipelineInputData subclass, got <class 'str'>"

### Validation 2: input_data Validation in execute()
**Step:** Step 3 - Add input_data Param and Validation
**Instructions:** Create pipeline with INPUT_DATA subclass, call execute(data=None) without input_data kwarg. Should raise ValueError. Then call with invalid input_data dict that doesn't match schema, should raise ValidationError with pipeline name context.
**Expected Result:** ValueError for missing input_data, ValidationError for schema mismatch

### Validation 3: UI Integration - has_input_schema
**Step:** Step 5 - Update UI Pipelines Route has_input_schema Logic
**Instructions:** Start UI server, GET /api/pipelines for pipeline with INPUT_DATA ClassVar set. Verify has_input_schema=true. Repeat for pipeline without INPUT_DATA, verify has_input_schema=false.
**Expected Result:** has_input_schema field reflects pipeline-level INPUT_DATA presence, not step instruction schemas

### Validation 4: UI Integration - Trigger Run with input_data
**Step:** Step 6 - Update UI Runs Route execute() Call
**Instructions:** POST /api/runs with input_data in body. Add debug logging in execute() to confirm input_data kwarg received (not in initial_context). Check PipelineRun execution succeeds.
**Expected Result:** execute() receives input_data as separate param, initial_context remains unchanged

## Issues Found
### Issue 1: Test Expectations Misaligned with New Architecture
**Severity:** medium
**Step:** Step 5 and Step 6
**Details:** Two tests (test_list_has_input_schema_true_for_pipeline_with_instructions, test_input_data_threaded_to_factory_and_execute) fail because they verify old behavior. Tests need updates to align with new pipeline-level input schema architecture. Test fixtures WidgetPipeline/ScanPipeline need INPUT_DATA ClassVar added if instruction-based input is intended, or test expectations changed to has_input_schema=False.

### Issue 2: Events Router Test Failure Unrelated to Task 43
**Severity:** low
**Step:** N/A
**Details:** test_events_router_prefix fails due to router prefix change ('/events' expected, '/runs/{run_id}/events' actual). Not caused by PipelineInputData implementation. Pre-existing issue in codebase test suite.

## Recommendations
1. Update test_list_has_input_schema_true_for_pipeline_with_instructions: Change assertion to expect has_input_schema=False for pipelines without INPUT_DATA ClassVar, or add INPUT_DATA to WidgetPipeline/ScanPipeline test fixtures
2. Update test_input_data_threaded_to_factory_and_execute: Change assertion from execute_kwargs_log[0]["initial_context"] to execute_kwargs_log[0]["input_data"]
3. Fix test_events_router_prefix: Update expected prefix from "/events" to "/runs/{run_id}/events" or revert router prefix change in events.py
4. Add integration tests for INPUT_DATA validation edge cases: missing input_data when INPUT_DATA set, ValidationError handling, type guard at class definition
5. Document migration path for existing pipelines using step instruction schemas to adopt pipeline-level INPUT_DATA
6. Add Graphiti memory entry documenting test failure root causes and resolution plan
