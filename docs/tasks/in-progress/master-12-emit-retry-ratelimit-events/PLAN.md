# PLANNING

## Summary
Add event emission for LLMCallRetry, LLMCallFailed, and LLMCallRateLimited to GeminiProvider's retry loop. Modify LLMProvider ABC to accept optional event_emitter + step_name params, thread these through executor.py call chain, emit 3 event types at 8 points in gemini.py retry loop (5 retry points, 2 rate-limit backoff paths, 1 post-loop failure), and fix existing accumulated_errors bug. Add google-generativeai to dev deps for testing with mocked Gemini API.

## Plugin & Agents
**Plugin:** backend-development
**Subagents:** code-modifier, test-writer
**Skills:** none

## Phases
1. Implementation: Modify ABC, thread event context, add emissions, fix bug
2. Testing: Verify event emissions with mocked Gemini API responses
3. Review: Code review (optional, based on risk assessment)

## Architecture Decisions

### ABC Signature Change
**Choice:** Add explicit optional `event_emitter` and `step_name` params to LLMProvider.call_structured() abstract method signature
**Rationale:** CEO decision for Option A (explicit params vs extracting from **kwargs). Clearer API contract, backward compatible (optional params), follows existing pattern from task 11 where run_id/pipeline_name are threaded as strings
**Alternatives:** Option B (extract from **kwargs) - less explicit, harder to document, rejected by CEO

### Rate Limit Event Emission
**Choice:** Emit ONLY LLMCallRateLimited for rate-limited retries (not LLMCallRetry + LLMCallRateLimited)
**Rationale:** CEO decision. Rate limit is semantically distinct from validation retry - separate event type conveys different handling (backoff vs immediate retry). Avoids double-emission noise
**Alternatives:** Emit both events - rejected, would duplicate information and complicate downstream event handling

### LLMCallRetry Timing
**Choice:** Emit LLMCallRetry only on non-last attempts (when retry actually happens). Last failed attempt emits only LLMCallFailed
**Rationale:** CEO decision. "Retry" event should fire when retry action occurs. Last attempt has no subsequent retry, so LLMCallFailed alone is semantically correct. Prevents confusing "retry" event followed immediately by "failed" event
**Alternatives:** Emit LLMCallRetry on all attempts including last - rejected, semantically incorrect when no retry happens

### accumulated_errors Bug Fix Scope
**Choice:** Fix accumulated_errors gap at gemini.py L230-235 in this task (append error_str before continue guard)
**Rationale:** CEO decision for in-scope. Bug is in same method being modified, affects LLMCallFailed.last_error accuracy. Low risk, high value - ensures last_error field has correct data when failure path is via non-rate-limit exception
**Alternatives:** Defer to separate task - rejected, would require re-testing same code paths

### Test Dependency Strategy
**Choice:** Add google-generativeai to dev optional deps, mock at Gemini API level (unittest.mock.patch on GenerativeModel.generate_content)
**Rationale:** CEO decision. Tests actual GeminiProvider retry loop behavior (not simplified MockProvider). Existing MockProvider in conftest.py returns single response, unsuitable for multi-attempt retry testing. Mocking at API level allows per-attempt response sequences
**Alternatives:** Use MockProvider - rejected, too simple. Create new test-specific provider - rejected, doesn't test production code path

## Implementation Steps

### Step 1: Modify LLMProvider ABC signature
**Agent:** backend-development:code-modifier
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Open `llm_pipeline/llm/provider.py`
2. Add two optional params to `call_structured()` abstract method signature at L32-43:
   - `event_emitter: Optional[Any] = None` (after validation_context param, before **kwargs)
   - `step_name: Optional[str] = None` (after event_emitter param, before **kwargs)
3. Update docstring Args section to document new params:
   - `event_emitter: Optional EventEmitter for emitting retry/failure events`
   - `step_name: Optional step name for event scoping`
4. Verify backward compatibility: existing **kwargs ensures no breaking changes to implementations

### Step 2: Thread event context through executor
**Agent:** backend-development:code-modifier
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. Open `llm_pipeline/llm/executor.py`
2. Locate provider.call_structured() call at L134-140
3. Add 4 params to call (after validation_context param):
   - `event_emitter=event_emitter`
   - `step_name=step_name`
   - `run_id=run_id`
   - `pipeline_name=pipeline_name`
4. Verify run_id/pipeline_name are already available in function scope (passed as params to execute_llm_step at L47-62)

### Step 3: Add event emissions to GeminiProvider
**Agent:** backend-development:code-modifier
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. Open `llm_pipeline/llm/gemini.py`
2. Add explicit event params to call_structured() signature at L69-80 (matching provider.py ABC):
   - `event_emitter: Optional[Any] = None`
   - `step_name: Optional[str] = None`
   - `run_id: Optional[str] = None`
   - `pipeline_name: Optional[str] = None`
3. Add lazy import + guard pattern at top of method body (after L82):
   ```python
   if event_emitter:
       from llm_pipeline.events.types import LLMCallRetry, LLMCallFailed, LLMCallRateLimited
   ```
4. Fix accumulated_errors bug at L230-235:
   - In else block (non-rate-limit exception), after logger.warning at L231-233
   - Before `if attempt < max_retries - 1: continue` guard at L234
   - Insert: `accumulated_errors.append(error_str)`
5. Add LLMCallRetry emissions at 5 validation retry points (only when `attempt < max_retries - 1`):
   - **Point 1 (L104-109, empty response):** Insert after L108 `accumulated_errors.append()`, before L109 `continue`:
     ```python
     if event_emitter and attempt < max_retries - 1:
         event_emitter.emit(LLMCallRetry(
             run_id=run_id, pipeline_name=pipeline_name, step_name=step_name,
             attempt=attempt + 1, max_retries=max_retries,
             error_type="empty_response", error_message="Empty/no response from model"
         ))
     ```
   - **Point 2 (L143-148, JSON decode):** Insert after L147 `accumulated_errors.append()`, before L148 `continue`:
     ```python
     if event_emitter and attempt < max_retries - 1:
         event_emitter.emit(LLMCallRetry(
             run_id=run_id, pipeline_name=pipeline_name, step_name=step_name,
             attempt=attempt + 1, max_retries=max_retries,
             error_type="json_decode_error", error_message=f"JSON decode error: {e}"
         ))
     ```
   - **Point 3 (L154-163, schema validation):** Insert after L160 `accumulated_errors.extend()`, before L161 `if attempt < max_retries - 1: continue`:
     ```python
     if event_emitter and attempt < max_retries - 1:
         event_emitter.emit(LLMCallRetry(
             run_id=run_id, pipeline_name=pipeline_name, step_name=step_name,
             attempt=attempt + 1, max_retries=max_retries,
             error_type="validation_error", error_message="; ".join(errors)
         ))
     ```
   - **Point 4 (L170-179, array validation):** Insert after L176 `accumulated_errors.extend()`, before L177 `if attempt < max_retries - 1: continue`:
     ```python
     if event_emitter and attempt < max_retries - 1:
         event_emitter.emit(LLMCallRetry(
             run_id=run_id, pipeline_name=pipeline_name, step_name=step_name,
             attempt=attempt + 1, max_retries=max_retries,
             error_type="array_validation_error", error_message="; ".join(array_errors)
         ))
     ```
   - **Point 5 (L189-197, Pydantic validation):** Insert after L194 `accumulated_errors.append()`, before L195 `if attempt < max_retries - 1: continue`:
     ```python
     if event_emitter and attempt < max_retries - 1:
         event_emitter.emit(LLMCallRetry(
             run_id=run_id, pipeline_name=pipeline_name, step_name=step_name,
             attempt=attempt + 1, max_retries=max_retries,
             error_type="pydantic_validation_error", error_message=str(pydantic_error)
         ))
     ```
   - **Point 6 (L230-235, non-rate-limit exception):** Already guarded by `if attempt < max_retries - 1: continue` at L234. Insert after bug fix (accumulated_errors.append), before L234 `if` statement:
     ```python
     if event_emitter:
         event_emitter.emit(LLMCallRetry(
             run_id=run_id, pipeline_name=pipeline_name, step_name=step_name,
             attempt=attempt + 1, max_retries=max_retries,
             error_type="exception", error_message=error_str
         ))
     ```
6. Add LLMCallRateLimited emissions at 2 rate-limit backoff paths (L216-229):
   - **API-suggested delay path (L217-222):** Insert after L217 `retry_delay = extract_retry_delay_from_error(e)`, before L222 `time.sleep(retry_delay)`:
     ```python
     if event_emitter:
         event_emitter.emit(LLMCallRateLimited(
             run_id=run_id, pipeline_name=pipeline_name, step_name=step_name,
             attempt=attempt + 1, wait_seconds=retry_delay, backoff_type="api_suggested"
         ))
     ```
   - **Exponential backoff path (L223-228):** Insert after L224 `wait_time = 2**attempt`, before L228 `time.sleep(wait_time)`:
     ```python
     if event_emitter:
         event_emitter.emit(LLMCallRateLimited(
             run_id=run_id, pipeline_name=pipeline_name, step_name=step_name,
             attempt=attempt + 1, wait_seconds=float(wait_time), backoff_type="exponential"
         ))
     ```
7. Add LLMCallFailed emission at post-loop failure (L237-244):
   - Insert after L237 `logger.error()`, before L238 `return LLMCallResult()`:
     ```python
     if event_emitter:
         last_error = accumulated_errors[-1] if accumulated_errors else "Unknown error"
         event_emitter.emit(LLMCallFailed(
             run_id=run_id, pipeline_name=pipeline_name, step_name=step_name,
             max_retries=max_retries, last_error=last_error
         ))
     ```
8. Verify all emissions use 1-based attempt indexing (`attempt + 1`) to match existing log messages

### Step 4: Add google-generativeai to dev dependencies
**Agent:** backend-development:code-modifier
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. Open `pyproject.toml`
2. Locate `[project.optional-dependencies]` dev list at L21-24
3. Add `"google-generativeai>=0.3.0",` to dev list (after pytest-cov line)
4. Verify gemini optional dep at L20 has same version constraint (consistency)

### Step 5: Create retry/rate-limit event tests
**Agent:** backend-development:test-writer
**Skills:** none
**Context7 Docs:** /google/generativeai
**Group:** C

1. Create `tests/events/test_retry_ratelimit_events.py`
2. Import test dependencies: pytest, unittest.mock, GeminiProvider, EventEmitter, event types (LLMCallRetry, LLMCallFailed, LLMCallRateLimited)
3. Create test class `TestRetryRateLimitEvents` with setUp creating: provider (GeminiProvider with test API key), event_emitter (EventEmitter), test_schema (simple Pydantic BaseModel)
4. Test case: `test_empty_response_retry` - Mock GenerativeModel.generate_content to return empty response 2 times, then success. Verify 2 LLMCallRetry events with error_type="empty_response", attempt=1,2, then success result
5. Test case: `test_json_decode_retry` - Mock to return invalid JSON 2 times, then valid. Verify 2 LLMCallRetry with error_type="json_decode_error"
6. Test case: `test_validation_failure_retry` - Mock to return schema-invalid JSON 2 times, then valid. Verify 2 LLMCallRetry with error_type="validation_error"
7. Test case: `test_all_attempts_fail` - Mock to return empty response max_retries times. Verify max_retries-1 LLMCallRetry events, then 1 LLMCallFailed with last_error from accumulated_errors
8. Test case: `test_rate_limit_api_suggested` - Mock to raise rate limit exception with Retry-After header, then success. Verify 1 LLMCallRateLimited with backoff_type="api_suggested", wait_seconds=<extracted>, then success result
9. Test case: `test_rate_limit_exponential` - Mock to raise rate limit exception (no Retry-After), then success. Verify 1 LLMCallRateLimited with backoff_type="exponential", wait_seconds=2^attempt
10. Test case: `test_non_rate_limit_exception_retry` - Mock to raise generic exception, then success. Verify 1 LLMCallRetry with error_type="exception"
11. Test case: `test_no_emitter_zero_overhead` - Call provider.call_structured with event_emitter=None. Verify no events emitted, no performance overhead (follow task 11 pattern)
12. Test case: `test_event_field_values` - For each event type, verify all fields populated correctly (run_id, pipeline_name, step_name, attempt, max_retries, error_type, error_message, wait_seconds, backoff_type, last_error)
13. Test case: `test_event_ordering` - Multi-attempt scenario with retries + final success. Verify events emitted in correct order (LLMCallRetry x N, no LLMCallFailed on success)
14. Test case: `test_accumulated_errors_bug_fix` - Mock non-rate-limit exception on last attempt. Verify LLMCallFailed.last_error contains exception message (not previous attempt's error)
15. Use `unittest.mock.patch('google.generativeai.GenerativeModel.generate_content')` with side_effect list for multi-attempt sequences
16. Follow task 11 test pattern: capture events via event_emitter, assert on event types/fields/ordering

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Missing emission point in 8-point gemini.py modification | High | Follow validated research line-number mapping precisely. Each point has clear before/after location and guard condition from research table. |
| LLMCallRetry on last attempt (violates CEO decision) | Medium | Add explicit `attempt < max_retries - 1` guard to all 5 validation retry emissions. Point 6 (exception else) already has guard at L234. |
| Rate limit on last attempt has no LLMCallRateLimited event | Low | Research confirms acceptable - falls to generic exception path. accumulated_errors bug fix ensures LLMCallFailed.last_error is accurate. Document in test case. |
| accumulated_errors bug fix forgotten | Medium | Make explicit substep in Step 3.4. Insert `accumulated_errors.append(error_str)` BEFORE continue guard at L234. |
| Test mock complexity - multi-attempt sequences | Medium | Use unittest.mock side_effect list for per-attempt responses. Follow task 11 test pattern for event capture/verification. Add test case for each emission path. |
| ABC signature change breaks existing code | Low | Optional params are backward compatible. Existing implementations have **kwargs. No breaking changes. |
| Import overhead when no emitter | Low | Lazy import inside `if event_emitter:` guard (task 11 pattern). Zero overhead when event_emitter=None. |

## Success Criteria

- [ ] LLMProvider ABC call_structured() has optional event_emitter + step_name params with docstring
- [ ] executor.py forwards event_emitter, step_name, run_id, pipeline_name to provider.call_structured()
- [ ] GeminiProvider call_structured() signature matches ABC with event params
- [ ] Lazy import + guard pattern for event types in gemini.py (zero overhead when no emitter)
- [ ] accumulated_errors bug fixed at L230-235 (error_str appended before continue guard)
- [ ] 5 LLMCallRetry emissions at validation retry points (only when attempt < max_retries - 1)
- [ ] 2 LLMCallRateLimited emissions at rate-limit backoff paths (before time.sleep)
- [ ] 1 LLMCallFailed emission at post-loop failure (with last_error from accumulated_errors)
- [ ] All emissions use 1-based attempt indexing (attempt + 1)
- [ ] google-generativeai added to dev optional deps in pyproject.toml
- [ ] test_retry_ratelimit_events.py created with 14+ test cases covering all emission paths
- [ ] Tests mock at Gemini API level (GenerativeModel.generate_content)
- [ ] Tests verify event field values (attempt, error_type, wait_seconds, backoff_type, last_error)
- [ ] Tests verify event ordering for multi-attempt scenarios
- [ ] Tests verify zero overhead when event_emitter=None
- [ ] Tests verify accumulated_errors bug fix (last_error correct on exception path)

## Phase Recommendation

**Risk Level:** medium
**Reasoning:** Implementation has 8 emission points with conditional guards in complex retry loop, plus existing bug fix in same method. Well-researched with precise line numbers and clear CEO decisions reduces risk, but insertion point density and guard conditions warrant thorough testing. ABC change and executor threading are low risk (simple additive changes). Test strategy is solid (mock at API level, cover all paths).
**Suggested Exclusions:** review
