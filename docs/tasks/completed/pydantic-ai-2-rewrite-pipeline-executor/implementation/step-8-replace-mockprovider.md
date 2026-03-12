# IMPLEMENTATION - STEP 8: REPLACE MOCKPROVIDER
**Status:** completed (verified)

## Summary
Removed `MockProvider(LLMProvider)` pattern from all 5 specified test files. Replaced `provider=MockProvider(...)` with `model="test-model"`. Added `AgentRegistry` subclasses to pipelines that execute LLM steps. Used `unittest.mock.patch("pydantic_ai.Agent.run_sync")` returning `MagicMock(output=instruction_instance)` for tests that actually call `execute()` with steps. Added backward-compat `MockProvider` stub in `events/conftest.py` so other event test files continue to import-collect (they will fail at runtime until Step 9 updates them).

## Files
**Created:** `docs/tasks/in-progress/pydantic-ai-2-rewrite-pipeline-executor/implementation/step-8-replace-mockprovider.md`
**Modified:**
- `tests/benchmarks/conftest.py`
- `tests/test_pipeline_input_data.py`
- `tests/test_pipeline_run_tracking.py`
- `tests/test_pipeline.py`
- `tests/events/conftest.py`
**Deleted:** none

## Changes

### File: `tests/benchmarks/conftest.py`
Removed `LLMProvider`, `LLMCallResult` imports. Deleted `_BenchmarkMockProvider(LLMProvider)` class. Changed `minimal_pipeline` fixture from `provider=_BenchmarkMockProvider()` to `model="test-model"`. `MinimalPipeline` uses no steps, so no AGENT_REGISTRY needed.
```
# Before
from llm_pipeline.llm.provider import LLMProvider
from llm_pipeline.llm.result import LLMCallResult
class _BenchmarkMockProvider(LLMProvider): ...
pipeline = MinimalPipeline(..., provider=_BenchmarkMockProvider())

# After
pipeline = MinimalPipeline(..., model="test-model")
```

### File: `tests/test_pipeline_input_data.py`
Removed `LLMProvider`, `LLMCallResult` imports. Deleted `MockProvider(LLMProvider)` class. Added `AgentRegistry` import. Added `ValidateAgentRegistry(AgentRegistry, agents={})` and `NoInputAgentRegistry(AgentRegistry, agents={})`. Wired both to their respective pipelines via `agent_registry=` param. Both pipelines use `EmptyStrategy` (no steps), so `agents={}` is sufficient. Replaced all `provider=MockProvider()` with `model="test-model"`.
```
# Before
from llm_pipeline.llm.provider import LLMProvider
from llm_pipeline.llm.result import LLMCallResult
class MockProvider(LLMProvider): ...
class ValidatePipeline(PipelineConfig, registry=ValidateRegistry, strategies=ValidateStrategies): ...
pipeline = ValidatePipeline(session=input_session, provider=MockProvider())

# After
from llm_pipeline.agent_registry import AgentRegistry
class ValidateAgentRegistry(AgentRegistry, agents={}): pass
class ValidatePipeline(PipelineConfig, registry=ValidateRegistry, strategies=ValidateStrategies, agent_registry=ValidateAgentRegistry): ...
pipeline = ValidatePipeline(session=input_session, model="test-model")
```

### File: `tests/test_pipeline_run_tracking.py`
Full rewrite. Removed `json`, `LLMProvider`, `LLMCallResult` imports. Added `unittest.mock` imports. Deleted `MockProvider(LLMProvider)` class. Added `TrackingAgentRegistry(AgentRegistry, agents={"gadget": GadgetInstructions})`. Wired to `TrackingPipeline` via `agent_registry=`. Updated `GadgetStep.prepare_calls()` to return plain dict instead of `self.create_llm_call(...)`. Added `_make_run_result()` helper that builds `MagicMock(output=GadgetInstructions(...))`. Each test that calls `execute()` wrapped in `patch("pydantic_ai.Agent.run_sync", return_value=_make_run_result(...))`. `test_failed_execute_writes_failed_run` uses `BrokenStrategy` which raises in `prepare_calls()` before `run_sync` is called, so no patch needed there.
```
# Before
class MockProvider(LLMProvider): ...
pipeline = TrackingPipeline(session=..., provider=MockProvider(responses=[{...}]))
pipeline.execute(...)

# After
class TrackingAgentRegistry(AgentRegistry, agents={"gadget": GadgetInstructions}): pass
def _make_run_result(count=2, label="widget"):
    mock_result = MagicMock()
    mock_result.output = GadgetInstructions(count=count, label=label, ...)
    return mock_result

pipeline = TrackingPipeline(session=..., model="test-model")
with patch("pydantic_ai.Agent.run_sync", return_value=_make_run_result()):
    pipeline.execute(...)
```

### File: `tests/test_pipeline.py`
Full rewrite. Removed MockProvider (which didn't exist in the file but was referenced). Added `AgentRegistry` import. Added `TestAgentRegistry(AgentRegistry, agents={"widget_detection": WidgetDetectionInstructions})`. Wired to `TestPipeline` via `agent_registry=`. Updated `WidgetDetectionStep.prepare_calls()` to return plain dict. Added `_make_widget_run_result()` helper. Replaced all `provider=MockProvider(...)` with `model="test-model"`. Replaced `TestPipelineInit.test_requires_provider_for_execute` with `test_requires_agent_registry_for_execute` using a properly-named pipeline. Wrapped all `TestPipelineExecution` tests in `patch("pydantic_ai.Agent.run_sync", ...)`. All `TestEventEmitter` and `TestPipelineNaming` and `TestPipelineInit` tests just construct the pipeline (no execute), so only need `model="test-model"`.
```
# Before
class TestPipeline(PipelineConfig, registry=TestRegistry, strategies=TestStrategies): pass
pipeline = TestPipeline(session=session, provider=MockProvider())
pipeline.execute(...)

# After
class TestAgentRegistry(AgentRegistry, agents={"widget_detection": WidgetDetectionInstructions}): pass
class TestPipeline(PipelineConfig, registry=TestRegistry, strategies=TestStrategies, agent_registry=TestAgentRegistry): pass
pipeline = TestPipeline(session=session, model="test-model")
with patch("pydantic_ai.Agent.run_sync", return_value=_make_widget_run_result()):
    pipeline.execute(...)
```

### File: `tests/events/conftest.py`
Removed `LLMProvider`, `LLMCallResult` imports. Deleted `MockProvider(LLMProvider)` class. Added `AgentRegistry` import. Added agent registry classes for each pipeline: `SuccessAgentRegistry`, `FailureAgentRegistry`, `SkipAgentRegistry`, `ExtractionAgentRegistry`, `TransformationAgentRegistry`. Wired each to its pipeline via `agent_registry=`. Updated all step `prepare_calls()` to return plain dicts. Added `make_simple_run_result()`, `make_item_detection_run_result()`, `make_transformation_run_result()` helper functions. Added `mock_simple_run_result` and `agent_run_sync_patch` fixtures. Added backward-compat `MockProvider` stub class (no LLMProvider base) so other event test files that `from conftest import MockProvider` continue to collect without import errors.
```
# Before
class MockProvider(LLMProvider):
    def call_structured(self, ...): ...
class SuccessPipeline(PipelineConfig, registry=SuccessRegistry, strategies=SuccessStrategies): pass

# After
class MockProvider:
    """Stub retained for import compatibility."""
    def __init__(self, responses=None, should_fail=False): ...

class SuccessAgentRegistry(AgentRegistry, agents={"simple": SimpleInstructions}): pass
class SuccessPipeline(PipelineConfig, registry=SuccessRegistry, strategies=SuccessStrategies, agent_registry=SuccessAgentRegistry): pass
```

## Decisions

### MockProvider stub in events/conftest.py
**Choice:** Keep a non-functional `MockProvider` stub class (not subclassing `LLMProvider`) in `events/conftest.py` after removing the real implementation.
**Rationale:** Multiple event test files (`test_llm_call_events.py`, `test_cache_events.py`, `test_ctx_state_events.py`, etc.) import `MockProvider` from conftest. Removing it entirely would cause collection-time ImportError, blocking all tests in those files. The stub preserves import compatibility while making clear the class is deprecated. Those files will fail at runtime (provider= arg no longer accepted) and are updated in Step 9.

### patch target: pydantic_ai.Agent.run_sync
**Choice:** `patch("pydantic_ai.Agent.run_sync", return_value=MagicMock(output=instruction))` rather than `pydantic_ai.models.test.TestModel`.
**Rationale:** `TestModel` requires `agent.override(model=TestModel())` context manager, which only works if the agent instance is accessible to the test. Since `pipeline.execute()` builds agents internally, the test has no reference to them. Patching `Agent.run_sync` at the class level intercepts all calls regardless of which agent instance makes them. `TestModel` would be cleaner if agents were injectable, but patching is the correct approach for this architecture.

### agents={} for empty-strategy pipelines
**Choice:** `AgentRegistry` with `agents={}` for `ValidatePipeline` and `NoInputPipeline` which use `EmptyStrategy`.
**Rationale:** These pipelines never execute LLM steps (strategy returns `[]`), so the registry is only needed to satisfy the `AGENT_REGISTRY is None` check in `execute()`. An empty dict is valid per `AgentRegistry.__init_subclass__` (only raises when `agents is None` for non-underscore-prefixed concrete classes).

## Verification
- [x] `pytest tests/test_pipeline.py tests/test_pipeline_run_tracking.py tests/test_pipeline_input_data.py tests/benchmarks/` passes (68 passed, 6 skipped)
- [x] `pytest tests/events/ --collect-only` succeeds (388 tests collected, 0 errors)
- [x] All 5 specified files no longer import `LLMProvider` or `LLMCallResult`
- [x] All 5 specified files no longer define a `MockProvider(LLMProvider)` class
- [x] All pipeline constructors use `model="test-model"` instead of `provider=MockProvider()`
- [x] Tests calling `execute()` with LLM steps use `patch("pydantic_ai.Agent.run_sync")`
- [x] Each pipeline with LLM steps has a matching `{Prefix}AgentRegistry`

---

## Fix Iteration 1
**Issues Source:** [TESTING.md]
**Status:** fixed

### Issues Addressed
- [x] 196 test failures in 9 event test files due to `provider=MockProvider(...)` in local helper functions

### Changes Made
All 9 event test files were inspected. A previous agent pass had already completed the fix — all local helper functions in all 9 files already use `model="test-model"` and `patch("pydantic_ai.Agent.run_sync")`. No code changes were required in this iteration.

Files inspected (all already correct):
- `tests/events/test_cache_events.py` — `_run_pipeline_with_cache`, `_two_run_success`, `_run_extraction_pipeline`, `_two_run_extraction` all use `model="test-model"` + patch
- `tests/events/test_consensus_events.py` — `_run_consensus_pipeline` uses `model="test-model"` + patch
- `tests/events/test_ctx_state_events.py` — `_run_fresh`, `_run_cached`, `_run_empty_ctx_fresh` all use `model="test-model"` + patch
- `tests/events/test_event_types.py` — integration tests use `model="test-model"` + patch
- `tests/events/test_extraction_events.py` — `_run_extraction_pipeline`, `TestExtractionError` tests use `model="test-model"` + patch
- `tests/events/test_llm_call_events.py` — `_run_success_pipeline` uses `model="test-model"` + patch
- `tests/events/test_pipeline_lifecycle_events.py` — inline tests use `model="test-model"` + patch
- `tests/events/test_step_lifecycle_events.py` — inline tests use `model="test-model"` + patch
- `tests/events/test_transformation_events.py` — `_run_transformation_fresh`, `_run_transformation_cached` use `model="test-model"` + patch

### Verification
- [x] `uv run pytest tests/events/ -x --tb=short` — 384 passed in 5.23s

---

## Review Fix Iteration 2
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
- [x] `tests/benchmarks/test_event_overhead.py`: 3 fixtures using `provider=MagicMock()` — constructor no longer accepts `provider=`
- [x] `tests/events/conftest.py`: dead `MockProvider` stub class no longer imported by any test file

### Changes Made
#### File: `tests/benchmarks/test_event_overhead.py`
Removed `MagicMock` import. Replaced `provider=MagicMock()` with `model="test-model"` in all 3 fixtures (`minimal_pipeline`, `pipeline_with_logging`, `pipeline_with_inmemory`). No Agent.run_sync patch needed — `BenchmarkStrategies` has no steps so no LLM calls occur.
```
# Before
from unittest.mock import MagicMock
pipeline = BenchmarkPipeline(strategies=[], session=session, provider=MagicMock())

# After
pipeline = BenchmarkPipeline(strategies=[], session=session, model="test-model")
```

#### File: `tests/events/conftest.py`
Deleted the backward-compat `MockProvider` stub block (lines 371-381). Confirmed via grep that no test file imports `MockProvider` — the stub was truly dead.
```
# Before
# -- Backward-compat stub ...
class MockProvider:
    """Stub retained for import compatibility. Do not use in new tests."""
    def __init__(self, responses=None, should_fail=False):
        self._responses = responses or []
        self._should_fail = should_fail

# After
# (block removed)
```

### Verification
- [x] `pytest tests/benchmarks/test_event_overhead.py --benchmark-skip` — 3 skipped (collected without error)
- [x] `pytest tests/events/ --collect-only` — 384 tests collected, 0 errors
- [x] `grep -r MockProvider tests/` — only match is conftest.py itself (now gone)
