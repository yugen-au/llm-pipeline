# PLANNING

## Summary
Add LLM call event emission (LLMCallPrepared, LLMCallStarting, LLMCallCompleted) to llm-pipeline framework using hybrid approach: pipeline.py emits LLMCallPrepared, executor.py emits LLMCallStarting/Completed. Maintains backward compatibility via optional parameters with zero overhead when no emitter present.

## Plugin & Agents
**Plugin:** python-development
**Subagents:** python-pro
**Skills:** none

## Phases
1. Implementation - code changes to executor.py and pipeline.py
2. Testing - integration tests for event emission
3. Review - code review and validation

## Architecture Decisions

### Hybrid Event Emission Pattern
**Choice:** LLMCallPrepared emitted from pipeline.py, LLMCallStarting/Completed emitted from executor.py
**Rationale:** Correct timestamps for profiling (Starting before call, Completed after). LLMCallPrepared data (call_count, system_key, user_key) naturally available at pipeline level. Rendered prompts and LLMCallResult local to executor only.
**Alternatives:** All emission from pipeline (Option D - timing flaw: Starting would fire post-call), All emission from executor (Option B - requires passing more data down)

### Event Context Threading via call_kwargs
**Choice:** Inject event_emitter, run_id, pipeline_name, step_name, call_index into call_kwargs dict after create_llm_call() (same pattern as provider/prompt_service)
**Rationale:** Consistent with existing pipeline injection pattern. Zero overhead when no emitter. Flows naturally to consensus path via **call_kwargs unpacking.
**Alternatives:** Separate method parameters (verbose, breaks consensus path), Global/thread-local state (non-deterministic in concurrent scenarios)

### call_index Semantics
**Choice:** call_index = params loop index (enumerate on call_params)
**Rationale:** Represents which prompt pair in the step (0-indexed). Consensus attempts are internal detail, not reflected in call_index. Consumers correlate with ConsensusAttempt events (Task 13) for per-attempt detail.
**Alternatives:** Running counter across all LLM calls in step (confusing for consensus where multiple attempts share same params)

### Error Path Event Pairing
**Choice:** Always emit LLMCallCompleted even on exception. Exception message in validation_errors field.
**Rationale:** Starting always paired with Completed for clean consumer logic. Consumers distinguish scenarios via field combinations (raw_response=None + parsed_result=None + validation_errors=[exception] = provider exception).
**Alternatives:** Leave Starting unmatched on exception (asymmetric, consumers need complex pairing logic), Add new LLMCallError event (schema bloat, redundant with existing validation_errors field)

### Backward Compatibility
**Choice:** All new executor params optional with defaults (event_emitter=None, run_id=None, pipeline_name=None, step_name=None, call_index=0)
**Rationale:** execute_llm_step is public API. Existing callers pass no event params, get no event emission. Zero behavioral change.
**Alternatives:** New execute_llm_step_with_events() wrapper (API fragmentation), Required params (breaks existing callers)

## Implementation Steps

### Step 1: Modify executor.py for Event Emission
**Agent:** python-development:python-pro
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Add TYPE_CHECKING import for PipelineEventEmitter at top of file (L7-14 import block)
2. Add 5 new optional parameters to execute_llm_step() signature (L21-32): event_emitter, run_id, pipeline_name, step_name, call_index (all default None/0)
3. After user_prompt rendering (L102), add LLMCallStarting emission guarded by `if event_emitter:` with fields: run_id, pipeline_name, step_name, call_index, rendered_system_prompt, rendered_user_prompt
4. Wrap provider.call_structured() call (L105-111) in try/except block: catch all exceptions, emit LLMCallCompleted with raw_response=None, parsed_result=None, model_name=None, attempt_count=1, validation_errors=[str(e)], then re-raise
5. After successful provider.call_structured() (after L111 check), emit LLMCallCompleted with raw_response=result.raw_response, parsed_result=result.parsed, model_name=result.model_name, attempt_count=result.attempt_count, validation_errors=result.validation_errors, all guarded by `if event_emitter:`

### Step 2: Modify pipeline.py for Event Preparation and Context Injection
**Agent:** python-development:python-pro
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. After call_params = step.prepare_calls() (L580), before for-loop (L583), emit LLMCallPrepared guarded by `if self._event_emitter:` with fields: run_id=self.run_id, pipeline_name=self.pipeline_name, step_name=step.step_name, call_count=len(call_params), system_key=step.system_instruction_key, user_key=step.user_prompt_key
2. Change for-loop (L583) to enumerate: `for idx, params in enumerate(call_params):`
3. After call_kwargs["prompt_service"] = prompt_service (L587), add event context injection block guarded by `if self._event_emitter:`: inject event_emitter=self._event_emitter, run_id=self.run_id, pipeline_name=self.pipeline_name, step_name=step.step_name, call_index=idx into call_kwargs

### Step 3: Create Integration Tests
**Agent:** python-development:python-pro
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. Create tests/events/test_llm_call_events.py
2. Add TestLLMCallPrepared class: verify emitted after prepare_calls, check call_count=2 for SuccessPipeline (2 steps), verify system_key and user_key present
3. Add TestLLMCallStarting class: verify emitted before provider call, check rendered_system_prompt is str (not template key), check rendered_user_prompt contains "Process: test" (from seeded_session "Process: {data}" template), verify call_index=0 for first param
4. Add TestLLMCallCompleted class: verify emitted after provider call, check raw_response contains MockProvider response, check parsed_result is dict, verify model_name="test-model", verify attempt_count from LLMCallResult
5. Add TestLLMCallEventPairing class: verify Starting.call_index matches Completed.call_index, verify Starting.timestamp before Completed.timestamp, count total events matches expected (2 steps * 3 events per step = 6)
6. Add TestLLMCallErrorPath class: mock provider to raise exception, verify LLMCallCompleted emitted with raw_response=None, parsed_result=None, validation_errors containing exception message
7. Add TestNoEmitterZeroOverhead class: execute pipeline without event_emitter, verify no event params injected into call_kwargs (via monkeypatch spy on execute_llm_step)

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Exception in executor prevents Completed emission | High | Wrap provider.call_structured() in try/catch, emit Completed in except block before re-raise |
| call_kwargs injection breaks consensus path | High | Verify _execute_with_consensus() unpacks **call_kwargs (L922 confirmed in research), test consensus path explicitly |
| Backward compatibility break for external callers | Medium | All new params optional with defaults, verified execute_llm_step in __all__ |
| Rendered prompts unavailable at pipeline level | Medium | Emit Starting from executor where prompts are local variables (research confirmed L82-102) |
| Zero-overhead violated when no emitter | Low | Guard all emissions with `if event_emitter:`, guard injection with `if self._event_emitter:` |
| call_index confusion in consensus scenarios | Low | Document call_index = params loop index in docstring, add consensus test verifying same call_index for multiple attempts |

## Success Criteria

- [ ] LLMCallPrepared emitted from pipeline.py after prepare_calls with correct call_count, system_key, user_key
- [ ] LLMCallStarting emitted from executor.py before provider call with rendered prompts (not template keys)
- [ ] LLMCallCompleted emitted from executor.py after provider call with LLMCallResult fields mapped correctly
- [ ] LLMCallCompleted emitted even on exception with error data in validation_errors
- [ ] Event context (run_id, pipeline_name, step_name, call_index) flows from pipeline to executor via call_kwargs
- [ ] call_index = params loop index (enumerate output), verified in tests
- [ ] Consensus path emits events correctly (same call_index for multiple attempts)
- [ ] Zero overhead when no emitter: no params injected, no event logic executed
- [ ] Backward compatibility: existing callers work unchanged (all new params optional)
- [ ] All integration tests pass: prepared, starting, completed, pairing, error path, no-emitter

## Phase Recommendation

**Risk Level:** low
**Reasoning:** Well-defined task with validated research, all architectural questions resolved. Event types already exist. Changes isolated to executor and pipeline with clear injection points. Comprehensive test coverage planned. Zero-overhead pattern proven in Tasks 8+9.
**Suggested Exclusions:** testing, review
