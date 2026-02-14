# Research Summary

## Executive Summary

Cross-referenced both research documents against actual source code in executor.py (L21-131), pipeline.py (L571-615 fresh path, L916-942 consensus path), events/types.py (L304-344), result.py, and provider.py. All three LLM call event type definitions verified correct. LLMCallResult field mapping to LLMCallCompleted confirmed. Core data-visibility problem (executor discards rendered prompts + LLMCallResult) confirmed.

Critical finding: the two research documents **contradict each other** on architecture. Step-1 recommends Option D (enriched return from executor, all emission in pipeline.py). Step-2 recommends Option B (pass emitter into executor, emit LLMCallStarting/Completed inside executor). Additionally, Option D has a semantic timing flaw: LLMCallStarting would fire AFTER the LLM call completes because pipeline only gets data back after execute_llm_step returns. Four questions require CEO resolution before planning.

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

### Research Contradiction: Option B vs Option D
**Source:** step-1 Section 5, step-2 Sections "LLMCallStarting" and "LLMCallCompleted"

**Step-1 recommends Option D**: New `execute_llm_step_with_metadata()` returning enriched result. Pipeline unpacks and emits all events. "All emission stays in pipeline.py" -- consistent with Task 9 pattern.

**Step-2 recommends Option B**: Pass `event_emitter` + context params into `execute_llm_step()`. Executor emits LLMCallStarting (after prompt render, before provider call) and LLMCallCompleted (after provider call). "Why executor not pipeline: Rendered prompts are local variables."

These are architecturally incompatible. Step-2 even provides a full signature change for execute_llm_step with event_emitter, run_id, pipeline_name, step_name, call_index parameters.

### Option D Timing Flaw (Gap)
**Source:** analysis of executor.py call flow

Option D returns enriched metadata AFTER execute_llm_step_with_metadata() completes. Pipeline would then emit LLMCallStarting. But the LLM call already happened inside the function. LLMCallStarting.timestamp would reflect post-call time, not pre-call time.

For performance profiling: `LLMCallCompleted.timestamp - LLMCallStarting.timestamp` would show ~0ms instead of actual LLM API latency (typically 1-30 seconds).

Workaround: enrich result could include pre_call_timestamp and post_call_timestamp, and pipeline constructs events with overridden timestamps. Feasible but adds complexity.

### LLMCallPrepared Emission Point (Verified)
**Source:** both research docs, pipeline.py L580

Both docs agree: emit after `call_params = step.prepare_calls()` (L580), before the for-loop (L583). Data available: `len(call_params)`, `step.system_instruction_key`, `step.user_prompt_key`. This is unambiguous and pipeline-owned regardless of Option B vs D. Correct.

### Consensus Path (Partially Verified)
**Source:** research/step-1 Section 6, step-2 Section "Consensus Polling Path", pipeline.py L916-942

Confirmed `_execute_with_consensus()` calls `execute_llm_step()` at L922 in a loop. Each attempt is a separate LLM call. Both docs correctly identify this needs events.

**Gap: call_index semantics in consensus**. The consensus path is invoked from the main params loop (L590-592) where `params` is one entry from `call_params`. The `call_index` in LLMCallStarting/Completed has one field. For non-consensus: call_index = params loop index (0, 1, 2...). For consensus: each params entry triggers MULTIPLE calls. What does call_index represent? The event type has no `consensus_attempt` field.

### Error Path (Gap)
**Source:** executor.py L105-130, pipeline.py L648-660

Neither research doc addresses what happens when `provider.call_structured()` raises an exception (network error, API timeout, unhandled error). In this case:
- executor.py propagates the exception (no try/catch around L105-111)
- pipeline.py catches at L648 and emits PipelineError
- No LLMCallCompleted fires for the failed call
- If LLMCallStarting was already emitted (Option B), there's an unmatched Starting without Completed

For validation failures (result.parsed is None), executor returns `create_failure()` normally -- this IS a completed call, just with empty parsed_result.

### Backward Compatibility (Verified)
**Source:** step-1 Section 5, executor.py __all__

`execute_llm_step` is in `__all__` of executor.py -- public API. Both research docs correctly flag this. Option D preserves backward compat by keeping the old function as a thin wrapper. Option B adds optional params (backward compat via defaults).

### Test Infrastructure (Partially Verified)
**Source:** step-1 Section 7, tests/events/conftest.py

- MockProvider returns LLMCallResult.success() with all needed fields -- verified
- seeded_session has prompts with "Process: {data}" template -- verified
- Rendered prompt would be "Process: test" (from variables={"data": "test"}) -- sufficient for testing LLMCallStarting.rendered_user_prompt
- InMemoryEventHandler available -- verified
- SuccessPipeline has 2 steps (2 LLM calls) -- suitable for call_index testing

**Gap**: If Option D introduces a new dataclass (LLMStepExecutionResult), tests need to import it. Minor, but conftest.py claim of "no changes needed" is slightly inaccurate for Option D.

### Scope Boundary Verification (Verified)
**Source:** downstream Task 12

Task 12 (LLMCallRetry/LLMCallFailed/LLMCallRateLimited) is OUT OF SCOPE. However, the architecture decision here (Option B vs D) constrains Task 12:
- Option B (emitter threading): Task 12 naturally passes emitter deeper to provider
- Option D (enriched return): Task 12 can't use same pattern since provider-level retry events happen INSIDE provider.call_structured(), not in executor

### Files Requiring Changes (Verified with Caveats)
**Source:** both research docs

Agreed regardless of option:
- `llm_pipeline/llm/executor.py` -- modified (new function or new params)
- `llm_pipeline/pipeline.py` -- add LLMCallPrepared emission + either other events (Option D) or pass emitter (Option B)
- `tests/events/test_llm_call_events.py` -- new test file

Agreed no changes needed:
- `events/types.py` -- all 3 events already defined
- `events/__init__.py` -- already exports all LLM call events
- `events/handlers.py` -- CATEGORY_LLM_CALL already mapped

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| (pending) | (pending) | (pending) |

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

## Open Items

- Research docs use slightly different line numbers for pipeline.py execution flow (step-1: L571-615, step-2: L410-660 for full method). Non-blocking; code structure verified regardless.
- Step-2 references a "Compatibility with Task 12" section but makes assumptions about event_emitter threading that depend on which option is chosen. Defer until Q1 resolved.

## Recommendations for Planning

1. Resolve the Option B vs D contradiction FIRST -- this is the foundational architecture decision affecting all implementation work
2. LLMCallPrepared emission is unambiguous: emit from pipeline.py after prepare_calls(), before the for-loop. Implement this regardless of B vs D decision.
3. For the enriched-return approach (Option D), a pre_call_timestamp field in the result dataclass resolves the timing flaw without breaking the "all emission in pipeline" pattern
4. Consider a hybrid: LLMCallPrepared from pipeline, LLMCallStarting/Completed from executor via optional emitter. This gives correct timing AND keeps LLMCallPrepared in pipeline (it only needs data pipeline already has). Trade-off: mixed emission pattern.
5. Consensus path needs explicit call_index strategy decided before implementation. Simplest: call_index = params loop index, same value for all consensus attempts of that params entry. Consumers correlate with ConsensusAttempt events (Task 13) for per-attempt detail.
6. Error path recommendation: do NOT emit LLMCallCompleted for provider exceptions (unmatched Starting is acceptable -- consumers check for PipelineError). DO emit LLMCallCompleted for validation failures (result.parsed is None) since executor handles these gracefully.
7. Task 12 downstream impact: document chosen architecture decision so Task 12 can extend naturally.
