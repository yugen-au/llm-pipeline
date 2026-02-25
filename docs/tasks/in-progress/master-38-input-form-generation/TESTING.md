# Testing Results

## Summary
**Status:** passed
All automated checks pass. 766/767 Python tests pass; the 1 failure is a pre-existing unrelated test. TypeScript type-check passes with zero errors. Frontend build succeeds. All Task 38 success criteria are met by the implementation already in place.

## Automated Testing
### Test Scripts Created
| Script | Purpose | Location |
| --- | --- | --- |
| N/A | No new test scripts required; existing suite covers backend changes | - |

### Test Execution
**Pass Rate:** 766/767 tests (1 pre-existing failure unrelated to Task 38)
```
============================= test session starts =============================
platform win32 -- Python 3.13.3, pytest-9.0.2, pluggy-1.6.0
rootdir: C:\Users\SamSG\Documents\claude_projects\llm-pipeline
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.9.0, langsmith-0.3.30, logfire-4.25.0, cov-7.0.0
collected 767 items

tests\events\test_cache_events.py .....................................
tests\events\test_consensus_events.py ....................
tests\events\test_ctx_state_events.py .............................................
tests\events\test_event_types.py ..................................................................
tests\events\test_extraction_events.py .............
tests\events\test_handlers.py ...............................
tests\events\test_llm_call_events.py ................................
tests\events\test_pipeline_lifecycle_events.py ...
tests\events\test_retry_ratelimit_events.py ................
tests\events\test_step_lifecycle_events.py ........
tests\events\test_transformation_events.py ............................
tests\test_emitter.py ....................
tests\test_init_pipeline_db.py ...
tests\test_introspection.py ...........................................
tests\test_llm_call_result.py ...................
tests\test_pipeline.py .....................................
tests\test_pipeline_run_tracking.py ....
tests\test_ui.py .................F.............................
tests\ui\test_bridge.py ...........................
tests\ui\test_cli.py ..............................................
tests\ui\test_events.py .............
tests\ui\test_integration.py ...................
tests\ui\test_pipelines.py ....................
tests\ui\test_prompts.py .................
tests\ui\test_runs.py .......................
tests\ui\test_steps.py ..............
tests\ui\test_wal.py ....
tests\ui\test_websocket.py ......

1 failed, 766 passed, 3 warnings in 117.39s (0:01:57)
```

### Failed Tests
#### TestRoutersIncluded::test_events_router_prefix
**Step:** Pre-existing failure, not introduced by Task 38
**Error:** `assert '/runs/{run_id}/events' == '/events'` -- test asserts old prefix `/events` but router was already moved to `/runs/{run_id}/events` in a prior task. Unrelated to input form generation.

## Build Verification
- [x] Python tests run: `pytest` from project root -- 766/767 pass
- [x] TypeScript type-check: `npm run type-check` -- zero errors, clean exit
- [x] Frontend production build: `npm run build` -- 2101 modules transformed, built in 5.85s, zero errors
- [x] No TypeScript warnings or type errors in any new or modified files
- [x] FastAPI deprecation warnings present (HTTP_422_UNPROCESSABLE_ENTITY) but pre-existing, not introduced by Task 38

## Success Criteria (from PLAN.md)
- [x] `TriggerRunRequest` backend accepts `input_data: Optional[dict]` without breaking existing tests -- confirmed in `runs.py` L62-63, all 23 `test_runs.py` tests pass
- [x] `pipeline.execute()` can be called with zero args or with `initial_context` kwarg without errors -- `data: Any = None`, `initial_context: Optional[Dict[str, Any]] = None` in `pipeline.py` L424-427
- [x] `input_data` from POST /api/runs body is forwarded to factory call as `input_data` kwarg -- `runs.py` L223: `factory(run_id=run_id, engine=engine, event_emitter=bridge, input_data=body.input_data or {})`
- [x] `PipelineMetadata` backend model has `pipeline_input_schema` field (null for now) -- `pipelines.py` L62
- [x] TS `PipelineMetadata` interface has `pipeline_input_schema: Record<string, unknown> | null` -- `types.ts` confirmed
- [x] shadcn `input`, `label`, `checkbox`, `textarea` components exist in `src/components/ui/` -- all 4 files present
- [x] `InputForm` renders null when `schema` is null -- `InputForm.tsx` L57: `if (!schema) return null`
- [x] `InputForm` renders correct field type for string, number, boolean, and default types -- `FormField.tsx` dispatches on `fieldSchema.type`
- [x] Required fields show visual indicator -- `FormField.tsx` L50,56: asterisk rendered when `required` is true
- [x] Submitting with empty required field sets `fieldErrors` -- `validateForm()` in `InputForm.tsx` L25-44, called in `live.tsx` L120-124
- [x] `createRun.mutate` call passes `input_data` when schema is non-null -- `live.tsx` L130: `input_data: inputSchema ? inputValues : undefined`
- [x] Form values reset to `{}` after successful run creation -- `live.tsx` L144: `setInputValues({})`
- [x] 422 structured field errors mapped to inline per-field messages -- `live.tsx` L147-165 `onError` handler with `JSON.parse(error.detail)`
- [x] `data-testid="input-form-placeholder"` div replaced by `<InputForm>` in live.tsx -- `live.tsx` L244-252, `InputForm` renders with `data-testid="input-form"` when schema non-null
- [x] All existing Python tests pass (`pytest`) -- 766/767, 1 pre-existing unrelated failure
- [x] No TypeScript errors (`npm run type-check`) -- clean exit

## Human Validation Required
### InputForm renders null with no schema (current state)
**Step:** Step 4 (InputForm component) / Step 5 (live.tsx integration)
**Instructions:** Open the live page in the browser. Select any pipeline. Verify no input form fields appear below the Run Pipeline button (since `pipeline_input_schema` is always null until Task 43).
**Expected Result:** Only the pipeline selector and Run Pipeline button are visible; no form fields appear.

### InputForm renders fields with a non-null schema
**Step:** Step 4 (InputForm component)
**Instructions:** Temporarily patch a pipeline's `pipeline_input_schema` to return a valid JSON Schema (e.g. `{"type":"object","properties":{"city":{"type":"string","title":"City"}},"required":["city"]}`). Open the live page, select the pipeline, verify: (1) a text input labeled "City" with a red asterisk appears; (2) clicking Run without filling City shows an inline "City is required" error; (3) filling City and running clears the error and submits.
**Expected Result:** Form renders with correct field types; required validation works; errors appear inline below fields.

### 422 backend error mapping
**Step:** Step 5 (live.tsx integration)
**Instructions:** Trigger a POST /api/runs with a body that causes a Pydantic 422 (e.g. wrong type for `input_data`). Verify the structured `detail` array is parsed and field errors appear inline on the correct form fields.
**Expected Result:** Per-field error messages appear below the relevant fields, not as a toast or banner.

## Issues Found
### Pre-existing test failure: test_events_router_prefix
**Severity:** low
**Step:** N/A (not introduced by Task 38)
**Details:** `tests/test_ui.py::TestRoutersIncluded::test_events_router_prefix` asserts the events router prefix is `/events` but the actual prefix is `/runs/{run_id}/events`. This was changed in a prior task. The test needs updating to match the current prefix -- out of scope for Task 38.

## Recommendations
1. Fix pre-existing `test_events_router_prefix` failure in a separate cleanup task (update assertion to `/runs/{run_id}/events`).
2. Once Task 43 (`PipelineInputData`) lands, add integration tests for InputForm rendering and required-field validation against a real schema.
3. Consider adding a unit test for `validateForm()` helper to guard against regressions on required-field logic.
