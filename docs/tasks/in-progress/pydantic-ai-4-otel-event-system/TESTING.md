# Testing Results

## Summary
**Status:** passed
All 445 tests in the targeted suites pass. The full suite (866 total) has 1 pre-existing failure in `tests/test_ui.py::TestRoutersIncluded::test_events_router_prefix` unrelated to this task (router prefix mismatch from a prior UI task). No regressions introduced.

## Automated Testing
### Test Scripts Created
| Script | Purpose | Location |
| --- | --- | --- |
| test_token_tracking.py | Token capture in normal/consensus paths, event enrichment, PipelineStepState persistence, None-safe usage, instrumentation threading | tests/test_token_tracking.py |

### Test Execution
**Pass Rate:** 445/445 (targeted suites); 865/866 full suite (1 pre-existing unrelated failure)

```
============================= test session starts =============================
platform win32 -- Python 3.13.3, pytest-9.0.2
collected 445 items

tests/test_token_tracking.py - 27 passed
tests/test_pipeline.py - 20 passed
tests/test_pipeline_run_tracking.py - 4 passed
tests/events/ - 394 passed

============================== warnings summary ===============================
tests\test_pipeline.py:114
  PytestCollectionWarning: cannot collect test class 'TestPipeline' because it
  has a __init__ constructor (from: tests/test_pipeline.py)

======================= 445 passed, 1 warning in 6.33s ========================

Full suite: 865 passed, 6 skipped, 1 failed (pre-existing), 1 warning in 118.20s
```

### Failed Tests
None (within scope of this task)

Pre-existing failure outside scope:
- `tests/test_ui.py::TestRoutersIncluded::test_events_router_prefix` - asserts prefix `/events`, actual `/runs/{run_id}/events` - predates this task (last modified in `master-28-ui-deps-pyproject`)

## Build Verification
- [x] `pip install -e ".[dev]"` succeeds (no errors, only unrelated version conflicts from transformers/huggingface-hub)
- [x] `import llm_pipeline` succeeds at runtime
- [x] `PipelineStepState` model fields include `input_tokens`, `output_tokens`, `total_tokens`, `total_requests`
- [x] `LLMCallCompleted` dataclass fields include `input_tokens`, `output_tokens`, `total_tokens`
- [x] `StepCompleted` dataclass fields include `input_tokens`, `output_tokens`, `total_tokens`
- [x] `build_step_agent()` signature includes `instrument` parameter
- [x] `PipelineConfig.__init__` signature includes `instrumentation_settings` parameter
- [x] `pyproject.toml` `[otel]` group contains `opentelemetry-sdk>=1.20.0` and `opentelemetry-exporter-otlp-proto-http>=1.20.0`
- [x] `pyproject.toml` `[dev]` group also contains both otel deps
- [x] `docs/observability.md` exists

## Success Criteria (from PLAN.md)
- [x] `build_step_agent()` accepts optional `instrument` parameter; `Agent(instrument=settings)` called when not None - verified via `TestInstrumentationSettingsThreading::test_agent_constructor_receives_instrument`
- [x] `PipelineConfig.__init__` accepts `instrumentation_settings` parameter; threaded to every `build_step_agent()` call - verified via `TestInstrumentationSettingsThreading::test_instrumentation_settings_stored_on_pipeline`
- [x] Default `InstrumentationSettings` (if created internally) uses `include_content=False` - architecture decision; no internal construction in current impl (passed through from consumer)
- [x] `PipelineStepState` has `input_tokens`, `output_tokens`, `total_tokens`, `total_requests` columns - verified via `TestPipelineStepStateTokens` (4 tests)
- [x] `LLMCallCompleted` event includes `input_tokens`, `output_tokens`, `total_tokens` - verified via `TestLLMCallCompletedTokens` (4 tests)
- [x] `StepCompleted` event includes `input_tokens`, `output_tokens`, `total_tokens` (step aggregate) - verified via `TestStepCompletedTokens` (2 tests)
- [x] Consensus path accumulates tokens across all attempts; `PipelineStepState.total_requests` = number of consensus calls - verified via `TestConsensusTokenAggregation::test_consensus_total_requests_equals_attempts`
- [x] `pyproject.toml` has `[otel]` group with `opentelemetry-sdk>=1.20.0` and `opentelemetry-exporter-otlp-proto-http>=1.20.0` - verified by runtime introspection
- [x] `docs/observability.md` covers installation, configuration, include_content opt-in, token fields, SQL cost query example - file exists
- [x] All new token fields are `Optional[int]`; None when `run_result.usage()` returns no data - verified via `TestNullAndZeroUsage` (4 tests)
- [x] Existing tests pass without modification (backward-compatible schema + event changes) - 418 pre-existing tests pass
- [x] New unit tests cover: normal path token capture, consensus accumulation, None-safe usage, no-instrumentation path - all 27 new tests pass

## Human Validation Required
### docs/observability.md content review
**Step:** Step 9
**Instructions:** Open `docs/observability.md` and verify it contains: Overview, Installation (`pip install llm-pipeline[otel]`), Configuration with `InstrumentationSettings` + `PipelineConfig(instrumentation_settings=...)`, `include_content` opt-in section, Token tracking section with `PipelineStepState` fields, SQL cost query example, and a minimal working example with console span exporter.
**Expected Result:** All listed sections present with accurate code examples.

### DB migration ADD COLUMN verification
**Step:** Step 1
**Instructions:** Run the pipeline against a DB that was created before this migration (missing token columns). Verify the migration adds columns without error and token values persist correctly after a step executes.
**Expected Result:** No migration error; new columns present; token values stored.

## Issues Found
None

## Recommendations
1. Fix pre-existing `tests/test_ui.py::TestRoutersIncluded::test_events_router_prefix` failure - not related to this task but will surface in CI.
2. Consider adding an integration test that exercises OTel with a real `InstrumentationSettings` object to verify the full OTel span creation path end-to-end.
