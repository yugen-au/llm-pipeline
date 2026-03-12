# Task Summary

## Work Completed

Rewrote `PipelineConfig.execute()` and `_execute_with_consensus()` to use pydantic-ai `agent.run_sync()` instead of the legacy `execute_llm_step()` function. Deleted the entire legacy LLM provider abstraction layer (7 files). Changed the constructor API from `provider=LLMProvider` to `model: str`. Updated all 14+ test files that referenced deleted symbols. Passed architecture review after fixing 1 HIGH + 4 MEDIUM issues.

## Files Changed

### Created
| File | Purpose |
| --- | --- |
| N/A | No new production files created |

### Modified
| File | Changes |
| --- | --- |
| `llm_pipeline/pipeline.py` | Constructor: `provider=LLMProvider` -> `model: str`. `execute()`: replaced `execute_llm_step()` with `agent.run_sync()`, added AGENT_REGISTRY validation, emit `LLMCallStarting`/`LLMCallCompleted` around call. `_execute_with_consensus()`: new signature `(agent, user_prompt, step_deps, output_type, ...)`, replaced `execute_llm_step(**call_kwargs)` with `agent.run_sync()`. `UnexpectedModelBehavior` -> `create_failure()` in both paths. `model_name` at state save uses `self._model`. |
| `llm_pipeline/step.py` | Deleted `create_llm_call()` method entirely. Removed `import warnings`. Removed `ExecuteLLMStepParams` from `TYPE_CHECKING` import. |
| `llm_pipeline/types.py` | Deleted `ExecuteLLMStepParams` class and `__all__` entry. |
| `llm_pipeline/agent_builders.py` | Added `array_validation: Any \| None = None` and `validation_context: Any \| None = None` optional fields to `StepDeps`. Updated stale docstring (post-review fix). |
| `llm_pipeline/extraction.py` | Updated stale docstring referencing `execute_llm_step()` (post-review fix). |
| `llm_pipeline/__init__.py` | Removed `LLMCallResult` export and `__all__` entry. Updated module docstring (removed `LLMProvider`, `GeminiProvider`, `LLMCallResult` usage examples). Added `AgentRegistry`, `StepDeps`, `build_step_agent` exports. |
| `llm_pipeline/events/__init__.py` | Removed `LLMCallResult` import and `__all__` entry. |
| `llm_pipeline/llm/__init__.py` | Gutted: all 5 exports removed, replaced with minimal comment (`# LLM subpackage - provider abstraction removed, use pydantic-ai agents via agent_builders.py`). |
| `llm_pipeline/llm/gemini.py` | Deleted entirely. |
| `llm_pipeline/llm/provider.py` | Deleted entirely. |
| `llm_pipeline/llm/result.py` | Deleted entirely. |
| `llm_pipeline/llm/executor.py` | Deleted entirely (includes dead `save_step_yaml`). |
| `llm_pipeline/llm/schema.py` | Deleted entirely (`format_schema_for_llm`, `flatten_schema`). |
| `llm_pipeline/llm/validation.py` | Deleted entirely (`validate_structured_output`, `validate_array_response`, `check_not_found_response`, `strip_number_prefix`). |
| `llm_pipeline/llm/rate_limiter.py` | Deleted entirely (`RateLimiter`). |
| `tests/test_pipeline.py` | Deleted `MockProvider` class. Deleted `TestImports.test_llm_imports`, `TestSchemaUtils`, `TestValidation`, `TestRateLimiter`, `TestStripNumberPrefix`. Added `AgentRegistry`, patched `Agent.run_sync`. Rewrote `WidgetDetectionStep.prepare_calls()` to return plain dict. |
| `tests/test_pipeline_run_tracking.py` | Deleted `MockProvider`. Added `AgentRegistry`. Patched `Agent.run_sync`. Rewrote `GadgetStep.prepare_calls()`. |
| `tests/test_pipeline_input_data.py` | Deleted `MockProvider`. Added `AgentRegistry`. Patched `Agent.run_sync`. |
| `tests/test_agent_registry_core.py` | Deleted `test_create_llm_call_deprecation_warning`, `test_create_llm_call_stacklevel`, `test_create_llm_call_still_works`. Updated stale section header comment (post-review fix). |
| `tests/test_introspection.py` | Rewrote `prepare_calls()` in `WidgetDetectionStep`, `ScanDetectionStep`, `GadgetDetectionStep` to return plain dicts. |
| `tests/events/conftest.py` | Deleted `MockProvider`. Added `AgentRegistry` to pipeline classes. Added `agent_run_sync_patch` fixture. Rewrote `prepare_calls()` for `SimpleStep`, `SkippableStep`, `ItemDetectionStep`, `TransformationStep`. Deleted dead `MockProvider` stub (post-review fix). |
| `tests/events/test_cache_events.py` | Replaced `provider=MockProvider(...)` with `model="mock-model"` in `_run_pipeline_with_cache()` and related helpers. Added `Agent.run_sync` patching. |
| `tests/events/test_consensus_events.py` | Replaced `provider=MockProvider(...)` in `_run_consensus_pipeline()`. Added `Agent.run_sync` patching. |
| `tests/events/test_ctx_state_events.py` | Replaced `provider=MockProvider(...)` in helpers. Rewrote local step `prepare_calls()`. Added `Agent.run_sync` patching. |
| `tests/events/test_event_types.py` | Replaced `provider=MockProvider(...)` in helpers. Added `Agent.run_sync` patching. |
| `tests/events/test_extraction_events.py` | Replaced `provider=MockProvider(...)` in helpers. Rewrote `FailingItemDetectionStep.prepare_calls()`. Added `Agent.run_sync` patching. |
| `tests/events/test_llm_call_events.py` | Deleted `test_no_event_params_in_call_kwargs`. Replaced `provider=MockProvider(...)` in `_run_success_pipeline()`, `_run_failure_pipeline()`. Added `Agent.run_sync` patching. |
| `tests/events/test_pipeline_lifecycle_events.py` | Replaced `provider=MockProvider(...)` in helpers. Added `Agent.run_sync` patching. |
| `tests/events/test_step_lifecycle_events.py` | Replaced `provider=MockProvider(...)` in helpers. Added `Agent.run_sync` patching. |
| `tests/events/test_transformation_events.py` | Replaced `provider=MockProvider(...)` in `_run_transformation_fresh()`, `_run_transformation_cached()`. Added `Agent.run_sync` patching. |
| `tests/benchmarks/conftest.py` | Deleted `_BenchmarkMockProvider`. Added `AgentRegistry`. Patched `Agent.run_sync`. |
| `tests/benchmarks/test_event_overhead.py` | Replaced `provider=MagicMock()` with `model="test-model"` in 3 fixtures (post-review fix). |
| `tests/test_llm_call_result.py` | Deleted entirely (tested `LLMCallResult` which is deleted). |
| `tests/events/test_retry_ratelimit_events.py` | Deleted entirely (tested `GeminiProvider` retry loop which is deleted). |

## Commits Made

| Hash | Message |
| --- | --- |
| `4aae017f` | `docs(implementation-A): pydantic-ai-2-rewrite-pipeline-executor` |
| `2c6a8f33` | `docs(implementation-B): pydantic-ai-2-rewrite-pipeline-executor` |
| `46197244` | `docs(implementation-C): pydantic-ai-2-rewrite-pipeline-executor` |
| `0ce2acda` | `docs(implementation-C): pydantic-ai-2-rewrite-pipeline-executor` |
| `ad39b29d` | `docs(implementation-C): pydantic-ai-2-rewrite-pipeline-executor` |
| `2e45c011` | `docs(fixing-review-C): pydantic-ai-2-rewrite-pipeline-executor` |
| `0a2ee157` | `docs(implementation-D): pydantic-ai-2-rewrite-pipeline-executor` |
| `6d36c8b0` | `docs(implementation-E): pydantic-ai-2-rewrite-pipeline-executor` |
| `b02fac1e` | `docs(implementation-F): pydantic-ai-2-rewrite-pipeline-executor` |
| `900d4c9f` | `docs(fixing-tests-F): pydantic-ai-2-rewrite-pipeline-executor` |
| `4941f584` | `docs(fixing-review-F): pydantic-ai-2-rewrite-pipeline-executor` |
| `46297335` | `docs(implementation-G): pydantic-ai-2-rewrite-pipeline-executor` |
| `eea5aa55` | `docs(fixing-review-G): pydantic-ai-2-rewrite-pipeline-executor` |
| `d9d855c6` | `chore(state): pydantic-ai-2-rewrite-pipeline-executor -> review` |
| `49042fd4` | `chore(state): pydantic-ai-2-rewrite-pipeline-executor -> review` |

## Deviations from Plan

- Step 8 scope was broader than planned: PLAN.md listed 5 files to update for MockProvider replacement (`test_pipeline.py`, `test_pipeline_run_tracking.py`, `test_pipeline_input_data.py`, `events/conftest.py`, `benchmarks/conftest.py`). Nine additional event test files had local helper functions passing `provider=MockProvider(...)` directly to pipeline constructors — these were discovered during testing and required a separate fix pass.
- `tests/benchmarks/test_event_overhead.py` was not listed in PLAN.md as a target but still used `provider=MagicMock()` in 3 fixtures. Fixed during review fix pass.
- `LLMCallCompleted.raw_response` is `None` permanently: pydantic-ai does not expose raw response text from `run_sync()`. PLAN.md implied this field would be populated from `run_result`; accepted as architectural limitation.
- `LLMCallCompleted.attempt_count` is always `1`: pydantic-ai manages retries internally without exposing the count. PLAN.md implied attempt count would come from `run_result.usage()`; confirmed as accepted behavior.

## Issues Encountered

### Step 8 incomplete — event test helper functions not updated (testing phase discovery)
**Resolution:** After the initial testing run showed 196 failures with `TypeError: PipelineConfig.__init__() got an unexpected keyword argument 'provider'`, a dedicated fix pass updated all 9 failing event test files. Each local `_run_*` helper was rewritten to use `model="mock-model"` and patch `pydantic_ai.Agent.run_sync` to return a `MagicMock(output=<instruction>)`. After fix, 803/810 tests pass.

### pydantic-ai not installed in venv
**Resolution:** `pydantic-ai>=1.0.5` is declared in `[project.optional-dependencies].dev` in `pyproject.toml` but was absent from the venv. Installed manually via `uv pip install "pydantic-ai>=1.0.5"` during the testing session. Recommend running `uv pip install -e ".[dev]"` as standard setup step.

### review HIGH — benchmarks/test_event_overhead.py still used provider= kwarg
**Resolution:** All 3 fixtures updated to use `model="test-model"`. Tests were auto-skipped via `--benchmark-skip` in `pyproject.toml` so the failure was invisible during normal test runs.

### review MEDIUM — stale docstrings referencing deleted symbols
**Resolution:** Three stale references fixed: `extraction.py` docstring updated to reference "pipeline execution" instead of `execute_llm_step()`. `agent_builders.py` docstring updated to reference "former prompt resolution pattern" instead of `create_llm_call()`. `test_agent_registry_core.py` section header comment updated to remove `create_llm_call()` deprecation reference.

### review MEDIUM — dead MockProvider stub in events/conftest.py
**Resolution:** Non-functional `MockProvider` stub (lines 376-381) retained from multi-step implementation deleted. No test file imported it.

### LLMCallStarting rendered_system_prompt — pydantic-ai resolves internally
**Resolution:** Identified during VALIDATED_RESEARCH phase. Workaround applied: resolve system prompt manually before `agent.run_sync()` using the same logic as `build_step_agent`'s `_inject_system_prompt` callback (calling `prompt_service.get_system_prompt()` or `get_prompt()` directly), then emit `LLMCallStarting` with the resolved string. This duplicates resolution but provides accurate rendered text for the event.

## Success Criteria

- [x] `llm_pipeline/llm/` contains only `__init__.py` with minimal content (7 files deleted) — verified, no import errors
- [x] `pipeline.py` constructor takes `model: str` (not `provider=`) — confirmed by `test_pipeline.py` all passing
- [x] `PipelineConfig.execute()` calls `agent.run_sync()` instead of `execute_llm_step()` — confirmed by `TestPipelineExecution` passing
- [x] `_execute_with_consensus()` accepts `agent, user_prompt, step_deps, output_type` params — confirmed, no test failures
- [x] `LLMCallStarting` and `LLMCallCompleted` events emitted around `agent.run_sync()` calls — verified by event tests now passing
- [x] `UnexpectedModelBehavior` mapped to `create_failure()` in both `execute()` and consensus — code in place, confirmed
- [x] `create_llm_call()` method absent from `LLMStep` class — confirmed by `test_agent_registry_core` passing
- [x] `ExecuteLLMStepParams` absent from `types.py` and `__all__` — no import errors
- [x] `StepDeps` has `array_validation` and `validation_context` optional fields — confirmed by `test_agent_registry_core` passing
- [x] `LLMCallResult` not exported from `llm_pipeline/__init__.py` or `llm_pipeline/events/__init__.py` — no import errors
- [x] `pytest` passes with no import errors from deleted symbols — 803/810 pass, 1 pre-existing failure (`test_ui.py` router prefix), 6 skipped
- [x] All 14 test files that referenced deleted symbols are updated — all 9 event test files fixed in Step 8 fix pass
- [x] `model_name` in `_save_step_state` uses `self._model` — confirmed by run tracking tests passing

## Recommendations for Follow-up

1. **Deferred: orphaned event types** — `LLMCallRetry`, `LLMCallFailed`, `LLMCallRateLimited` remain defined in `events/types.py` and exported from `events/__init__.py` but no code path emits them (deleted with `executor.py` and `gemini.py`). These are dead public API symbols. Removing them requires a separate task as it is a breaking events API change. Accepted per CEO decision; deferred explicitly.
2. **Pre-existing: test_ui.py events router prefix** — `tests/test_ui.py:143` asserts `r.prefix == "/events"` but actual prefix is `"/runs/{run_id}/events"`. Unrelated to this task; should be fixed in a separate PR.
3. **Environment setup doc** — `pydantic-ai` was missing from the venv despite being declared in `[project.optional-dependencies].dev`. Add `uv pip install -e ".[dev]"` to project setup instructions (README or onboarding doc) to prevent silent test environment issues.
4. **Task 3: output_validators** — `StepDeps.array_validation` and `StepDeps.validation_context` fields added in this task are unused until Task 3 implements output validators. Task 3 can consume these fields without a breaking `StepDeps` change.
5. **LLMCallCompleted fields** — `attempt_count` is always `1` and `raw_response` is always `None` due to pydantic-ai API constraints. If frontend consumers of these fields need accurate data in the future, investigate pydantic-ai usage tracking or post-run usage hooks.
