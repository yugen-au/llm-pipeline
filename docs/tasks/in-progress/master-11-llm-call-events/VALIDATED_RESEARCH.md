# Research Summary

## Executive Summary

Cross-referenced both research documents against actual source code in executor.py (L21-131), pipeline.py (L571-615 fresh path, L916-942 consensus path), events/types.py (L304-344), result.py, and emitter.py. All three LLM call event type definitions verified correct. LLMCallResult field mapping to LLMCallCompleted confirmed. Core data-visibility problem (executor discards rendered prompts + LLMCallResult) confirmed.

Critical finding resolved: research docs contradicted on architecture (Option B vs D). CEO chose **HYBRID**: LLMCallPrepared from pipeline.py, LLMCallStarting+Completed from executor.py via passed event_emitter. call_index = params loop index. Always fire LLMCallCompleted (even on exception). All gaps analyzed and resolved -- research is validated and ready for planning.

## Domain Findings

### Event Type Definitions (Verified)
**Source:** research/step-1-codebase-event-patterns.md, events/types.py L304-344

All three event types verified against types.py:

| Event | Lines | Fields (beyond StepScopedEvent) | kw_only | Verified |
|-------|-------|-------------------------------|---------|----------|
| LLMCallPrepared | 307-315 | call_count: int, system_key: str\|None, user_key: str\|None | Yes | Yes |
| LLMCallStarting | 318-326 | call_index: int, rendered_system_prompt: str, rendered_user_prompt: str | Yes | Yes |
| LLMCallCompleted | 329-344 | call_index: int, raw_response: str\|None, parsed_result: dict\|None, model_name: str\|None, attempt_count: int, validation_errors: list[str] | Yes | Yes |

All inherit StepScopedEvent -> PipelineEvent. EVENT_CATEGORY = CATEGORY_LLM_CALL for all three. All exported in `__all__` and auto-registered. CATEGORY_LLM_CALL mapped to logging.INFO in handlers.py DEFAULT_LEVEL_MAP. No changes needed to types.py or handlers.py.

### LLMCallResult -> LLMCallCompleted Field Mapping (Verified)
**Source:** research/step-1-codebase-event-patterns.md, result.py, types.py

| LLMCallResult field | LLMCallCompleted field | Match |
|---------------------|----------------------|-------|
| parsed: dict\|None | parsed_result: dict\|None | Yes (name differs) |
| raw_response: str\|None | raw_response: str\|None | Exact |
| model_name: str\|None | model_name: str\|None | Exact |
| attempt_count: int | attempt_count: int | Exact |
| validation_errors: list[str] | validation_errors: list[str] | Exact |

Note: `parsed` -> `parsed_result` rename is intentional (avoids collision with Pydantic's `.parsed` if any).

### Core Data-Visibility Problem (Verified)
**Source:** research/step-1-codebase-event-patterns.md, executor.py L21-131

Confirmed against actual executor.py:
- L82-94: `system_instruction` rendered (local variable, never returned)
- L97-102: `user_prompt` rendered (local variable, never returned)
- L105-111: `result: LLMCallResult` captured (local variable)
- L113-118: failure path returns `result_class.create_failure(...)` -- LLMCallResult lost
- L121-127: success path returns `result_class(**result.parsed)` -- LLMCallResult lost

Pipeline at L594 receives only the Pydantic model instance (T). Both research docs correctly identify this as the central problem.

### Architecture Decision: HYBRID (CEO Resolved)
**Source:** step-1 Section 5, step-2 Sections "LLMCallStarting" and "LLMCallCompleted", CEO answer

**Contradiction found:** Step-1 recommended Option D (enriched return, all emission in pipeline.py). Step-2 recommended Option B (pass emitter into executor, emit from executor). Option D had a timing flaw (LLMCallStarting timestamp would be post-call).

**CEO Decision: HYBRID approach.**
- LLMCallPrepared: emitted from pipeline.py (after prepare_calls, before for-loop). Pipeline owns this data naturally.
- LLMCallStarting: emitted from executor.py (after prompt render, before provider.call_structured). Correct timing. Rendered prompts are local to executor.
- LLMCallCompleted: emitted from executor.py (after provider.call_structured, or in exception handler). Correct timing. LLMCallResult is local to executor.

This gives correct timestamps for profiling (Starting.timestamp before call, Completed.timestamp after call) while keeping LLMCallPrepared at pipeline level where its data (call_count, system_key, user_key) is naturally available.

### Executor Signature Change (Derived from CEO Decision)
**Source:** analysis of executor.py, pipeline.py L583-594

execute_llm_step() needs new optional parameters for event context:
- `event_emitter: PipelineEventEmitter | None = None`
- `run_id: str | None = None`
- `pipeline_name: str | None = None`
- `step_name: str | None = None`
- `call_index: int = 0`

All default to None/0. Backward compatible -- existing callers unaffected.

Pipeline injects these into call_kwargs after create_llm_call(), same pattern as existing provider/prompt_service injection (L586-587):
```python
call_kwargs["provider"] = self._provider
call_kwargs["prompt_service"] = prompt_service
# NEW: inject event context
if self._event_emitter:
    call_kwargs["event_emitter"] = self._event_emitter
    call_kwargs["run_id"] = self.run_id
    call_kwargs["pipeline_name"] = self.pipeline_name
    call_kwargs["step_name"] = step.step_name
    call_kwargs["call_index"] = idx  # params loop index
```

Zero overhead when no emitter: params not injected, executor skips all event logic.

### Executor Event Emission Pattern (Derived)
**Source:** executor.py L82-131, CEO error-path decision

Executor emit pattern:
```python
# After L102 (prompts rendered):
if event_emitter:
    event_emitter.emit(LLMCallStarting(...))

try:
    result = provider.call_structured(...)
except Exception as e:
    if event_emitter:
        event_emitter.emit(LLMCallCompleted(
            ..., raw_response=None, parsed_result=None,
            model_name=None, attempt_count=1,
            validation_errors=[str(e)]
        ))
    raise  # re-raise for pipeline's outer try/except

# After successful call:
if event_emitter:
    event_emitter.emit(LLMCallCompleted(
        ..., raw_response=result.raw_response,
        parsed_result=result.parsed,
        model_name=result.model_name,
        attempt_count=result.attempt_count,
        validation_errors=result.validation_errors
    ))
```

Key points:
- try/catch around provider.call_structured() emits Completed then re-raises
- Exception message goes in validation_errors (no schema change needed, existing list[str] field)
- Consumers distinguish exception from normal failure: raw_response=None + parsed_result=None + validation_errors contains exception text

### call_index Semantics (CEO Resolved)
**Source:** pipeline.py L583-594, L916-942, CEO answer

**call_index = params loop index** (which prompt pair in the step, 0-indexed).

- Non-consensus: `for idx, params in enumerate(call_params)` -- call_index = idx
- Consensus: same call_index for all attempts within one params entry. ConsensusAttempt events (Task 13 scope) provide per-attempt detail.

Consensus path flows naturally: pipeline injects call_index into call_kwargs before branching at L589. _execute_with_consensus() unpacks via `**call_kwargs` at L922, so each consensus attempt inherits the same call_index.

### Error Path (CEO Resolved)
**Source:** executor.py L105-111, pipeline.py L648-660, CEO answer

**Always fire LLMCallCompleted.** Starting always paired with Completed. Three scenarios:

| Scenario | raw_response | parsed_result | validation_errors | How consumer detects |
|----------|-------------|---------------|-------------------|---------------------|
| Success | str | dict | [] or prior-attempt errors | parsed_result is not None |
| Validation failure | str | None | [error messages] | parsed_result is None, raw_response present |
| Provider exception | None | None | [exception str] | raw_response is None |

No schema change to LLMCallCompleted needed. validation_errors carries exception message for the exception case.

### LLMCallPrepared Emission Point (Verified, Unchanged)
**Source:** both research docs, pipeline.py L580

Emit after `call_params = step.prepare_calls()` (L580), before the for-loop (L583). Data available: `len(call_params)`, `step.system_instruction_key`, `step.user_prompt_key`. Pipeline-owned, unambiguous.

### Consensus Path (Fully Verified)
**Source:** research/step-1 Section 6, step-2 Section "Consensus Polling Path", pipeline.py L916-942

_execute_with_consensus() at L916 unpacks call_kwargs via `**call_kwargs` at L922. Event params flow through naturally -- no modification to _execute_with_consensus() needed. Each consensus attempt calls execute_llm_step() which handles its own LLMCallStarting/Completed emission.

### Backward Compatibility (Verified)
**Source:** step-1 Section 5, executor.py __all__

execute_llm_step is public API (__all__). All new params are optional with defaults (None/0). Existing callers pass no event params, get no event emission. Zero behavioral change.

### Test Infrastructure (Verified)
**Source:** step-1 Section 7, tests/events/conftest.py

- MockProvider returns LLMCallResult.success() with all fields -- verified
- seeded_session has "Process: {data}" template -- rendered_user_prompt testable as "Process: test"
- InMemoryEventHandler available for event capture
- SuccessPipeline has 2 steps -> 2 LLM calls -> suitable for call_index testing
- No new test fixtures needed beyond existing conftest.py infrastructure
- New test file: tests/events/test_llm_call_events.py

### Scope Boundary Verification (Verified)
**Source:** downstream Task 12

Task 12 (LLMCallRetry/LLMCallFailed/LLMCallRateLimited) is OUT OF SCOPE. The hybrid approach (emitter threading) naturally extends for Task 12: pass emitter deeper from executor to provider. No architectural conflict.

### Files Requiring Changes (Final)
**Source:** both research docs, CEO decisions

Modified:
- `llm_pipeline/llm/executor.py` -- add event params, emit LLMCallStarting/Completed, try/catch for error path
- `llm_pipeline/pipeline.py` -- emit LLMCallPrepared, inject event params into call_kwargs

New:
- `tests/events/test_llm_call_events.py` -- integration tests

No changes:
- `events/types.py` -- all 3 events already defined
- `events/__init__.py` -- already exports all LLM call events
- `events/handlers.py` -- CATEGORY_LLM_CALL already mapped
- `events/emitter.py` -- PipelineEventEmitter protocol unchanged

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| Research contradiction: Step-1 recommends Option D (enriched return, all emission in pipeline). Step-2 recommends Option B (emit from executor). Option D has timing flaw (LLMCallStarting fires post-call). Which approach? | HYBRID: LLMCallPrepared from pipeline.py, LLMCallStarting+Completed from executor.py via passed event_emitter. Correct timing for Starting (before actual LLM call). | Resolves contradiction. Executor gets new optional params. Mixed emission pattern (pipeline + executor) instead of single-owner. Task 12 extends naturally via emitter threading. |
| call_index in consensus path: params loop index or running counter of all LLM calls in step? | call_index = params loop index (0-indexed). Consensus attempts are internal detail, not reflected in call_index. | Same call_index for all consensus attempts of one params entry. Consumers correlate with ConsensusAttempt events (Task 13) for per-attempt detail. No special handling in _execute_with_consensus(). |
| Error path: when provider.call_structured() raises, should LLMCallCompleted fire or leave LLMCallStarting unmatched? | Always fire LLMCallCompleted, even on exceptions. Starting always paired with Completed. Include error data. | Executor needs try/catch around provider.call_structured() that emits Completed then re-raises. Exception message goes in validation_errors (no schema change). Consumers get clean paired events. |

## Assumptions Validated

- [x] All 3 LLM call event types exist in types.py with correct field signatures (L307-344)
- [x] All 3 inherit StepScopedEvent -> PipelineEvent with step_name: str | None = None
- [x] All 3 use kw_only=True and EVENT_CATEGORY = CATEGORY_LLM_CALL
- [x] CATEGORY_LLM_CALL constant exists (types.py L30) and is mapped in handlers.py
- [x] LLMCallResult fields map 1:1 to LLMCallCompleted fields (with parsed->parsed_result rename)
- [x] execute_llm_step() discards rendered prompts and LLMCallResult, returns only T
- [x] pipeline.py L594 (main path) and L922 (consensus path) both call execute_llm_step()
- [x] prepare_calls() returns List[StepCallParams] with variables (pipeline.py L580)
- [x] step.system_instruction_key and step.user_prompt_key available after step creation (step.py L241-242)
- [x] MockProvider returns LLMCallResult.success() with all fields needed by LLMCallCompleted
- [x] Zero-overhead guard pattern (if self._event_emitter:) established by Tasks 8+9
- [x] events/__init__.py already exports LLMCallPrepared, LLMCallStarting, LLMCallCompleted
- [x] execute_llm_step is public API (__all__ in executor.py)
- [x] HYBRID approach: new optional params on execute_llm_step() are backward compatible (all default None/0)
- [x] Event context (run_id, pipeline_name, step_name, call_index) injectable via call_kwargs dict same as provider/prompt_service
- [x] Consensus path: call_kwargs unpacked at L922, event params flow through without modification to _execute_with_consensus()
- [x] rendered_system_prompt: str (not Optional) is safe -- executor only reaches emit point after successful prompt retrieval
- [x] Exception in provider.call_structured() can be caught, Completed emitted, then re-raised without changing pipeline error handling
- [x] validation_errors: list[str] can carry exception message without schema change
- [x] PipelineEventEmitter is a Protocol (duck typed) -- executor can use TYPE_CHECKING import, call .emit() directly

## Open Items

- None. All questions resolved by CEO. Research fully validated.

## Recommendations for Planning

1. Emit LLMCallPrepared from pipeline.py after `call_params = step.prepare_calls()` (L580), before for-loop (L583), guarded by `if self._event_emitter:`
2. Inject event params (event_emitter, run_id, pipeline_name, step_name, call_index) into call_kwargs after create_llm_call(), alongside existing provider/prompt_service injection (L586-587)
3. Add 5 new optional params to execute_llm_step() signature: event_emitter, run_id, pipeline_name, step_name, call_index (all defaulting None/0)
4. In executor: emit LLMCallStarting after prompt render (L102), before provider.call_structured() (L105)
5. In executor: wrap provider.call_structured() in try/catch -- emit LLMCallCompleted in both success and exception paths, re-raise on exception
6. In executor: emit LLMCallCompleted after provider.call_structured() returns normally (after L111), using LLMCallResult fields
7. For exception-path LLMCallCompleted: raw_response=None, parsed_result=None, model_name=None, attempt_count=1, validation_errors=[str(exception)]
8. All executor emissions guarded by `if event_emitter:` for zero-overhead when no emitter
9. Use enumerate() on call_params loop in pipeline.py for call_index
10. No changes to _execute_with_consensus() -- event params flow through call_kwargs naturally
11. Tests: verify LLMCallPrepared emitted with correct call_count, verify LLMCallStarting contains rendered prompts (not template keys), verify LLMCallCompleted contains LLMCallResult data, verify error-path pairing, verify no-emitter zero-overhead path
