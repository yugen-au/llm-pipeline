# IMPLEMENTATION - STEP 3: WRITE TESTS
**Status:** completed

## Summary
Created `tests/test_introspection.py` with 32 test cases covering all 12 scenarios from PLAN.md Step 3.

## Files
**Created:** `tests/test_introspection.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `tests/test_introspection.py`
32 tests across 8 test classes using minimal WidgetPipeline domain (no DB/LLM needed):

```
TestGetMetadataTopLevel   - returns dict, correct pipeline_name, required keys
TestStrategiesList        - length, required keys, class_name, snake_case name
TestStepEntries           - required keys, step_name, system_key, user_key, instructions_class, schema
TestExtractionEntries     - required keys, class_name, model_class, methods list, 'default' present
TestExecutionOrder        - is list, contains step names, deduplicated, items are strings
TestRegistryModels        - is list, contains model class names
TestCaching               - same object identity (is), cross-instance cache sharing
TestGetSchemaNonPydantic  - non-Pydantic returns {"type": name}, no raise, Pydantic full schema, None->None
TestBrokenStrategy        - error dict not exception, broken+ok strategy coexist correctly
```

## Decisions
### Naming convention enforcement
**Choice:** Each inline pipeline class in tests uses fully matched Registry/Strategies/Pipeline names (e.g. `DedupeRegistry`/`DedupeStrategies`/`DedupePipeline`).
**Rationale:** `PipelineConfig.__init_subclass__` enforces `{Prefix}Registry` naming at class definition time. Initially reused `WidgetRegistry` for all helper pipelines which raised `ValueError`. Required unique prefixes per test.

### Cache isolation via autouse fixture
**Choice:** `autouse=True` fixture clears `PipelineIntrospector._cache` before and after each test.
**Rationale:** ClassVar cache persists across tests; without clearing, caching identity test would pass spuriously and broken-strategy tests could hit stale entries.

### Context class naming
**Choice:** Renamed `WidgetContext` -> `WidgetDetectionContext` to match step prefix.
**Rationale:** `step_definition` decorator enforces `{StepPrefix}Context` naming; `WidgetContext` raised `ValueError` at collection time.

## Verification
- [x] `pytest tests/test_introspection.py` -> 32 passed, 0 failed
- [x] All 12 PLAN.md test cases covered
- [x] No DB, LLM, or FastAPI imports in test file
- [x] Cache isolation via autouse fixture

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
- [x] No test coverage for transformation code path: `PipelineIntrospector` transformation dict (input_type, input_schema, output_type, output_schema) never exercised

### Changes Made
#### File: `tests/test_introspection.py`
Added two new pipeline fixtures (ScanPipeline with Pydantic types, GadgetPipeline with plain types) and a `TestTransformation` class with 11 tests covering:
- transformation key present in step dict
- transformation is not None when configured
- class_name correct
- Pydantic input/output type names
- Pydantic input/output schemas contain `properties`
- non-Pydantic input/output schemas return `{"type": class_name}`
- non-Pydantic type names
- step without transformation has `transformation=None`

Also added `PipelineTransformation` import and per-step instruction classes (`ScanDetectionInstructions`, `GadgetDetectionInstructions`) to satisfy `step_definition` `{StepPrefix}Instructions` naming enforcement.

### Verification
- [x] `pytest tests/test_introspection.py` -> 43 passed, 0 failed (was 32)
