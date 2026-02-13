# Research Summary

## Executive Summary

Both research files independently confirmed the same architectural gap: `execute_llm_step()` returns `T` (Pydantic model), not `LLMCallResult`, so `model_name` is discarded before reaching `_save_step_state()`. All code references verified against actual codebase -- no factual errors in either research file. The task description's code snippet (`result.model_name if hasattr(result, 'model_name')`) assumes `LLMCallResult` is accessible at `pipeline.execute()` level, which is false. Three approaches identified; both researchers independently recommend Approach A (use `self._provider.model_name`).

## Domain Findings

### The model_name Discard Gap
**Source:** step-1-pipeline-state-flow.md, step-2-llmcallresult-model-field.md

- `GeminiProvider.call_structured()` returns `LLMCallResult(model_name=self.model_name)` -- verified gemini.py lines 123, 203, 241
- `execute_llm_step()` at executor.py line 105 receives `LLMCallResult`, but returns `result_class(**result.parsed)` at line 127 -- only `T` returned, `LLMCallResult` consumed
- `pipeline.execute()` line 543 receives `T`, passes to `_save_step_state()` line 560-562 with no model_name param
- `PipelineStepState.model` field exists at state.py line 87-91: `Optional[str]`, `max_length=50`, `default=None` -- never populated

### Provider Architecture
**Source:** step-1-pipeline-state-flow.md, step-2-llmcallresult-model-field.md, verified against provider.py and gemini.py

- `LLMProvider` ABC (provider.py) defines only `call_structured() -> LLMCallResult`. No `model_name` attribute/property.
- `GeminiProvider` (gemini.py line 48) stores `self.model_name` as plain instance attribute. Default: `"gemini-2.0-flash-lite"`.
- `self._provider` is available on `PipelineConfig` at pipeline.py line 152.

### Consensus Path
**Source:** step-1-pipeline-state-flow.md, verified at pipeline.py lines 827-853

- `_execute_with_consensus()` also calls `execute_llm_step()` and returns `T`. Same model_name loss applies.
- With Approach A, model_name sourced from `self._provider` regardless of execution path (direct or consensus).

### Upstream Task 5 Context
**Source:** master-5-executor-llmcallresult/SUMMARY.md

- Task 5 deliberately kept `execute_llm_step()` return type as `T` -- no signature change.
- Task 5 summary line 108 anticipated: "Task 16 will need result.model_name access at pipeline.py level." This implied Approach B, but Approach A makes it unnecessary.
- No deviations in task 5 that impact task 16.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Task description assumes `result.model_name` at pipeline level, but `execute_llm_step()` returns `T` not `LLMCallResult`. Use Approach A (`self._provider.model_name` with `getattr` fallback) instead? | **APPROVED** -- CEO confirmed Approach A. Use `self._provider.model_name` directly. Non-breaking, pipeline.py-only. | Locks implementation to Approach A. No executor or provider changes needed. Simplest possible diff. |

## Assumptions Validated
- [x] `PipelineStepState.model` field exists and is `Optional[str]`, `max_length=50`, `default=None` (state.py:87-91)
- [x] `_save_step_state()` has exactly one call site at pipeline.py:560-562
- [x] `self._provider` is available in `execute()` scope (pipeline.py:152, used at line 535)
- [x] `GeminiProvider.model_name` is a plain instance attribute set in `__init__` (gemini.py:48)
- [x] `LLMProvider` ABC does NOT define `model_name` attribute or property (provider.py)
- [x] `execute_llm_step()` return type is `T`, not `LLMCallResult` (executor.py:32, line 127)
- [x] Consensus path (`_execute_with_consensus`) has same model_name loss (pipeline.py:833)
- [x] Task 5 deliberately kept executor return type as `T` (SUMMARY.md line 130)
- [x] Task description's code snippet assumes `LLMCallResult` access at pipeline level -- confirmed FALSE, CEO approved Approach A as alternative

## Open Items
- `max_length=50` on `PipelineStepState.model` -- current Gemini model names fit (24 chars max), but future models with longer names could truncate. Low risk, monitor only.
- Cached step states saved pre-task-16 will retain `model=None`. No migration needed but worth noting for data consistency awareness.
- Future consideration: add `model_name` property to `LLMProvider` ABC (Approach C) as a separate task to enforce contract for all providers.

## Recommendations for Planning
1. **Use Approach A** -- `getattr(self._provider, 'model_name', None)` in `_save_step_state()`. Zero executor changes, non-breaking, minimal diff. Both researchers independently recommend this.
2. **Changes scoped to pipeline.py only** -- add `model_name` param to `_save_step_state()` signature, pass `getattr(self._provider, 'model_name', None)` from the call site at line 560, set `model=model_name` in `PipelineStepState` construction at line 715.
3. **Do NOT modify executor.py or provider.py** -- out of scope for task 16. Approach B/C are future refactoring tasks if needed.
4. **Consider a follow-up task** to add `model_name` abstract property to `LLMProvider` (Approach C) -- makes the contract explicit without breaking executor return type.
5. **Test strategy**: execute pipeline with `GeminiProvider`, query `PipelineStepState` from DB, assert `model` field equals provider's `model_name`. Also test with a mock provider lacking `model_name` attribute to verify `getattr` fallback returns `None`.
