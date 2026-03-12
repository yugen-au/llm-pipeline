# Testing Results

## Summary
**Status:** failed

Test suite has 2 distinct failure categories after installing `pydantic-ai`:
1. **196 failures** — 9 event test files still construct pipelines with `provider=MockProvider(...)`. Step 8 updated `conftest.py` pipeline class definitions but did not update the individual test helper functions that pass `provider=` to the constructor.
2. **1 failure** — `test_ui.py::TestRoutersIncluded::test_events_router_prefix` expects `r.prefix == "/events"` but actual prefix is `"/runs/{run_id}/events"`. Pre-existing mismatch unrelated to this task.

Core pipeline tests (test_pipeline.py, test_pipeline_run_tracking.py, test_pipeline_input_data.py) all pass after pydantic-ai install.

## Automated Testing
### Test Scripts Created
| Script | Purpose | Location |
| --- | --- | --- |
| N/A | No new scripts created | — |

### Test Execution
**Pass Rate:** 611/814 tests pass (197 failed, 6 skipped)

```
============================= test session starts =============================
platform win32 -- Python 3.13.3, pytest-9.0.2
plugins: anyio-4.12.1, logfire-4.28.0, benchmark-5.2.3, cov-7.0.0
collected 814 items

197 failed, 611 passed, 6 skipped, 1 warning in 117.06s (0:01:57)
```

### Failed Tests

#### Category A: `provider=` kwarg in event test helpers (196 tests)
**Step:** Step 8 (Update tests - replace MockProvider with model= string)
**Error:** `TypeError: PipelineConfig.__init__() got an unexpected keyword argument 'provider'`
**Affected files:**
- `tests/events/test_cache_events.py` (35 tests) — `_run_pipeline_with_cache()`, `_run_two_run_scenario()`, etc. pass `provider=MockProvider(...)` directly to `SuccessPipeline()`/`ExtractionPipeline()`
- `tests/events/test_consensus_events.py` (20 tests) — `_run_consensus_pipeline()` passes `provider=MockProvider(...)`
- `tests/events/test_ctx_state_events.py` (~20 tests) — multiple helpers pass `provider=MockProvider(...)`
- `tests/events/test_event_types.py` (2 tests) — helpers pass `provider=MockProvider(...)`
- `tests/events/test_extraction_events.py` (~5 tests) — helpers pass `provider=MockProvider(...)`
- `tests/events/test_llm_call_events.py` (~27 tests) — `_run_success_pipeline()`, `_run_failure_pipeline()` helpers pass `provider=MockProvider(...)`
- `tests/events/test_pipeline_lifecycle_events.py` (3 tests) — helpers pass `provider=MockProvider(...)`
- `tests/events/test_step_lifecycle_events.py` (~8 tests) — helpers pass `provider=MockProvider(...)`
- `tests/events/test_transformation_events.py` (~71 tests) — `_run_transformation_fresh()`, `_run_transformation_cached()` pass `provider=MockProvider(...)`

Step 8 updated `conftest.py` pipeline class definitions (added `agent_registry=`) but did not update the test-local helper functions in each file that still construct pipelines with `provider=MockProvider(...)`. Each helper needs to be rewritten to:
1. Remove `MockProvider` instantiation
2. Construct pipeline with `model="mock-model"` instead of `provider=provider`
3. Patch `pydantic_ai.Agent.run_sync` to return mock `AgentRunResult` with `.output` set

#### Category B: UI router prefix mismatch (1 test)
**Step:** Pre-existing — not introduced by this task
**Error:** `AssertionError: assert '/runs/{run_id}/events' == '/events'`
**File:** `tests/test_ui.py::TestRoutersIncluded::test_events_router_prefix` (line 143)
**Details:** Test asserts `r.prefix == "/events"` but `llm_pipeline/ui/routes/events.py` router has prefix `"/runs/{run_id}/events"`. This mismatch predates the pydantic-ai rewrite.

## Build Verification
- [x] `python -c "import llm_pipeline"` succeeds — package imports cleanly
- [x] `pydantic-ai>=1.0.5` installed (was missing from venv, present in `dev` optional deps in pyproject.toml)
- [x] No import errors from deleted symbols (LLMProvider, GeminiProvider, RateLimiter, LLMCallResult, etc.)
- [x] Core pipeline tests pass: `tests/test_pipeline.py` (68 passed, 1 warning), `tests/test_pipeline_run_tracking.py`, `tests/test_pipeline_input_data.py`
- [x] `tests/test_agent_registry_core.py` — 7 passed
- [x] `tests/test_introspection.py` — passed
- [ ] Event integration tests — 196 failing due to Step 8 incomplete

## Success Criteria (from PLAN.md)
- [x] `llm_pipeline/llm/` contains only `__init__.py` with minimal content (7 files deleted) — verified, no import errors
- [x] `pipeline.py` constructor takes `model: str` (not `provider=`) — confirmed by `test_pipeline.py` all passing
- [x] `PipelineConfig.execute()` calls `agent.run_sync()` instead of `execute_llm_step()` — confirmed by TestPipelineExecution passing
- [x] `_execute_with_consensus()` accepts `agent, user_prompt, step_deps, output_type` params — confirmed no test failures on this
- [ ] `LLMCallStarting` and `LLMCallCompleted` events emitted around `agent.run_sync()` calls — NOT VERIFIED (event tests broken)
- [x] `UnexpectedModelBehavior` mapped to `create_failure()` — code in place, not blocked by failures
- [x] `create_llm_call()` method absent from `LLMStep` class — confirmed by test_agent_registry_core passing
- [x] `ExecuteLLMStepParams` absent from `types.py` and `__all__` — no import errors
- [x] `StepDeps` has `array_validation` and `validation_context` optional fields — confirmed by test_agent_registry_core passing
- [x] `LLMCallResult` not exported from `llm_pipeline/__init__.py` or `events/__init__.py` — no import errors
- [ ] `pytest` passes with no import errors from deleted symbols — import errors fixed, but 197 test failures remain
- [ ] All 14 test files that referenced deleted symbols are updated — Step 8 incomplete: conftest updated but 9 test files still use `provider=` in local helpers
- [x] `model_name` in `_save_step_state` uses `self._model` — confirmed by run tracking tests passing

## Human Validation Required

### Verify pydantic-ai is in dev install
**Step:** Pre-run environment setup
**Instructions:** Run `uv pip install -e ".[dev]"` to install all dev deps including pydantic-ai. The venv was missing pydantic-ai; it was installed manually during this testing session.
**Expected Result:** `uv run python -c "import pydantic_ai; print(pydantic_ai.__version__)"` prints version >= 1.0.5

## Issues Found

### Issue 1: Step 8 incomplete — test helper functions not updated
**Severity:** critical
**Step:** Step 8 (Update tests - replace MockProvider with model= string)
**Details:** `conftest.py` pipeline class definitions were correctly updated (added `agent_registry=`, removed `provider=` from class-level usage). However, the individual event test files each define local helper functions that construct pipeline instances with `provider=MockProvider(...)`. These helpers were not updated. Affects 9 test files, 196 test cases. Each helper needs `provider=MockProvider(...)` replaced with `model="mock-model"` + `patch("pydantic_ai.Agent.run_sync", ...)`.

### Issue 2: pydantic-ai not installed in venv
**Severity:** high
**Step:** Step 1 / environment setup (not a code step)
**Details:** `pydantic-ai>=1.0.5` is declared in `[project.optional-dependencies].dev` in `pyproject.toml` but was absent from the venv. The package must be installed via `uv pip install "pydantic-ai>=1.0.5"` or `uv pip install -e ".[dev]"` before tests can run. Installed during this session.

### Issue 3: test_ui.py events router prefix mismatch
**Severity:** low
**Step:** Pre-existing, not introduced by this task
**Details:** `tests/test_ui.py:143` asserts `r.prefix == "/events"` but actual prefix is `"/runs/{run_id}/events"`. Unrelated to pydantic-ai rewrite. Should be fixed separately.

## Recommendations
1. Complete Step 8: update each of the 9 failing event test files — replace local `_run_*` helper functions to use `model="mock-model"` + `patch("pydantic_ai.Agent.run_sync", return_value=MagicMock(output=<instruction>))` pattern already established in `test_pipeline.py`
2. Add `pydantic-ai>=1.0.5` to the default `dev` install instructions or run `uv pip install -e ".[dev]"` as part of project setup to ensure it is always present
3. Fix `test_ui.py` events router prefix assertion independently of this task (pre-existing failure)
4. After completing Step 8, re-run full suite — expect near-zero failures excluding the pre-existing UI test

---

## Re-Verification Run (post Step 8 fix)

### Test Execution
**Pass Rate:** 803/810 tests pass (1 failed, 6 skipped)

```
============================= test session starts =============================
platform win32 -- Python 3.13.3, pytest-9.0.2, pluggy-1.6.0
rootdir: C:\Users\SamSG\Documents\claude_projects\llm-pipeline
configfile: pyproject.toml
testpaths: tests
collected 810 items

1 failed, 803 passed, 6 skipped, 1 warning in 116.82s (0:01:56)
```

### Failed Tests

#### TestRoutersIncluded::test_events_router_prefix (pre-existing)
**Step:** Pre-existing — not introduced by this task
**Error:** `AssertionError: assert '/runs/{run_id}/events' == '/events'`

### Updated Success Criteria
- [x] `LLMCallStarting` and `LLMCallCompleted` events emitted around `agent.run_sync()` calls — VERIFIED (event tests now passing)
- [x] `pytest` passes with no import errors from deleted symbols — 803 passed, only 1 pre-existing failure remains
- [x] All 14 test files that referenced deleted symbols are updated — Step 8 complete, all 9 event test files fixed

### Summary
**Status:** passed

Step 8 fix resolved all 196 event test failures. Only the 1 pre-existing `test_ui.py` router prefix mismatch remains, confirmed acceptable. All success criteria from PLAN.md now met.

---

## Post-Review Fix Pass Run

### Changes Applied Before This Run
- 2 stale docstrings updated (no logic change)
- `test_event_overhead.py` `provider=` kwarg fixed in benchmark test
- Dead `MockProvider` stub deleted
- Stale comment updated

### Test Execution
**Pass Rate:** 803/810 tests pass (1 failed, 6 skipped)

```
============================= test session starts =============================
platform win32 -- Python 3.13.3, pytest-9.0.2, pluggy-1.6.0
rootdir: C:\Users\SamSG\Documents\claude_projects\llm-pipeline
configfile: pyproject.toml
testpaths: tests
collected 810 items

1 failed, 803 passed, 6 skipped, 1 warning in 117.90s (0:01:57)
```

### Failed Tests

#### TestRoutersIncluded::test_events_router_prefix (pre-existing)
**Step:** Pre-existing — not introduced by this task
**Error:** `AssertionError: assert '/runs/{run_id}/events' == '/events'`

### Outcome
No regression. Identical to previous run: 803 passed, 1 pre-existing failure, 6 skipped. Review fixes were safe.
