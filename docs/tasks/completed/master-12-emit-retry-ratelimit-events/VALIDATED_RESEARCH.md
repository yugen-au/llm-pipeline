# Research Summary

## Executive Summary

Two research agents explored the codebase for Task 12 (emit LLMCallRetry, LLMCallFailed, LLMCallRateLimited events in GeminiProvider's retry loop). Both agents accurately mapped the retry loop structure, event type definitions, and call chain threading. Key contradictions surfaced around ABC modification strategy, double-emission for rate limits, and last-attempt retry semantics. All 5 ambiguities resolved via CEO decisions. One existing bug identified (accumulated_errors gap at gemini.py L230-235) will be fixed in-scope. All event types already defined in types.py and exported -- no new type definitions needed.

## Domain Findings

### Event Type Definitions
**Source:** step-1 (section 1), step-2 (section 2), types.py L347-378

All three event types already exist and are fully wired:
- `LLMCallRetry` (L347-357): attempt (int), max_retries (int), error_type (str), error_message (str)
- `LLMCallFailed` (L359-367): max_retries (int), last_error (str)
- `LLMCallRateLimited` (L369-378): attempt (int), wait_seconds (float), backoff_type (str)

All inherit `StepScopedEvent` which provides run_id, pipeline_name, step_name (str | None), timestamp. All in `__all__` (L575-577), events/__init__.py (L119-121), registered in `_EVENT_REGISTRY` via `__init_subclass__`, and mapped to `logging.INFO` via `CATEGORY_LLM_CALL` in handlers.py. **Verified: no changes needed to types.py, __init__.py, or handlers.py.**

### GeminiProvider Retry Loop Structure
**Source:** step-1 (section 2), step-2 (section 1), gemini.py L69-244

Retry loop: `for attempt in range(max_retries)` at L90. Six retry points (continue paths), two rate-limit paths, one post-loop failure path. **All line numbers verified against source code within +/-1 line.**

Verified retry points and proposed error_type strings:

| # | Lines | Trigger | error_type |
|---|-------|---------|------------|
| 1 | L104-109 | Empty/no response | `empty_response` |
| 2 | L143-148 | JSON decode error | `json_decode_error` |
| 3 | L154-163 | Schema validation failure | `validation_error` |
| 4 | L170-179 | Array validation failure | `array_validation_error` |
| 5 | L189-197 | Pydantic validation failure | `pydantic_validation_error` |
| 6 | L230-235 | Non-rate-limit exception (retries remaining) | `exception` |

**Correction:** Step 1 used `json_parse_error` for point 2. Step 2 used `json_decode_error`. Source code raises `json.JSONDecodeError`. Step 2 is correct: use `json_decode_error`.

Rate limit paths (L216-229): API-suggested delay (backoff_type="api_suggested") or exponential 2^attempt (backoff_type="exponential"). Both emit LLMCallRateLimited BEFORE `time.sleep()`.

Post-loop failure (L237-244): Returns LLMCallResult(parsed=None, ...). Single LLMCallFailed emission point.

### Call Chain Threading
**Source:** step-1 (section 3), step-2 (section 3), executor.py L134-140, pipeline.py L631-636

Current chain: pipeline.py injects event_emitter/run_id/pipeline_name/step_name/call_index into call_kwargs -> executor.py receives as explicit params -> executor calls provider.call_structured() at L134-140 **without** event params. **Verified: executor currently does NOT forward event context to provider.**

Required change: executor.py L134-140 must additionally pass event_emitter, run_id, pipeline_name, step_name to provider.call_structured(). call_index is NOT needed at provider level (it's a per-params-loop index managed by pipeline/executor).

### ABC Modification (Resolved Contradiction)
**Source:** step-1 (section 4), step-2 (section 3)

Step 1 recommended Option B (no ABC change, extract from **kwargs). Step 2 recommended Option A (explicit params on ABC). **CEO decision: Option A.** Add explicit optional `event_emitter` and `step_name` params to LLMProvider.call_structured() signature. run_id and pipeline_name already available as strings that can be threaded; event_emitter and step_name are the key contract additions.

**Implication:** provider.py L31-43 needs 2 new optional params. GeminiProvider.call_structured() L69-80 needs matching params. Both already have **kwargs so this is additive and backward compatible.

### accumulated_errors Bug (New Finding)
**Source:** Validator analysis during review, gemini.py L230-235

The non-rate-limit exception `else` block at L230-235 logs `error_str` but does NOT append it to `accumulated_errors`. On last attempt via this path, `accumulated_errors[-1]` would reference a previous attempt's error (or IndexError/fallback "Unknown error" if empty). Neither research agent flagged this gap.

**CEO decision: Fix in Task 12.** Append `error_str` to `accumulated_errors` in the else block before the `if attempt < max_retries - 1: continue` check.

### Emission Semantics (Resolved Contradictions)
**Source:** step-1 (section 6), step-2 (sections 1, 5, 6)

**Rate limit double-emission:** Step 1 proposed emitting BOTH LLMCallRateLimited AND LLMCallRetry for rate-limited retries. Step 2 proposed only LLMCallRateLimited. **CEO decision: LLMCallRateLimited only.** No LLMCallRetry for rate-limited retries.

**Last-attempt retry:** Both agents assumed LLMCallRetry fires on every failed attempt including the last (where no retry actually occurs). **CEO decision: Non-last only.** LLMCallRetry fires only when a retry actually happens (attempt < max_retries - 1). Final failed attempt triggers LLMCallFailed only.

This simplifies the emission map:
- Retry points 1-5 (validation failures): emit LLMCallRetry only when `attempt < max_retries - 1`. On last attempt, these paths still `continue` (exiting the loop), and post-loop LLMCallFailed fires alone.
- Retry point 6 (non-rate-limit exception): already guarded by `if attempt < max_retries - 1`. LLMCallRetry fires inside the guard.
- Rate limit path: emit LLMCallRateLimited (only, no LLMCallRetry) before sleep.
- Post-loop: emit LLMCallFailed with last_error from accumulated_errors[-1].

### Test Strategy
**Source:** step-1 (section 8), step-2 (section 8), pyproject.toml L19-24

google-generativeai is an optional dep (`[project.optional-dependencies].gemini`), NOT in dev deps. **CEO decision: Add google-generativeai to dev deps** and mock at Gemini API level (`unittest.mock.patch` on `google.generativeai.GenerativeModel.generate_content`) to test the actual retry loop in GeminiProvider.

Existing MockProvider in conftest.py (L31-57) is too simple for retry tests -- returns success or raises once. New tests need a mock that returns different responses per attempt.

### Files to Modify
**Source:** step-1 (section 7), step-2 (section 7), validated against source

| File | Changes |
|------|---------|
| `llm_pipeline/llm/provider.py` | Add optional `event_emitter` and `step_name` params to abstract call_structured() |
| `llm_pipeline/llm/gemini.py` | Add explicit event params to call_structured() signature. Emit LLMCallRetry at 5 non-last retry points, LLMCallRateLimited before sleep (2 backoff paths), LLMCallFailed post-loop. Fix accumulated_errors gap at L230-235. |
| `llm_pipeline/llm/executor.py` | Forward event_emitter, run_id, pipeline_name, step_name to provider.call_structured() at L134-140 |
| `pyproject.toml` | Add google-generativeai to dev optional deps |
| `tests/events/test_retry_ratelimit_events.py` (new) | Tests for all 3 event types with mocked Gemini API responses |

Unchanged: events/types.py, events/__init__.py, events/emitter.py, events/handlers.py, pipeline.py.

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| ABC change: Option A (explicit params on ABC) or B (extract from **kwargs)? | Option A -- add explicit optional event_emitter and step_name params to LLMProvider ABC | provider.py needs modification (was "no change" in step 1). Cleaner API contract. |
| Rate limit double-emission: emit both LLMCallRateLimited + LLMCallRetry, or RateLimited only? | RateLimited only | Simpler emission map. Rate limit path emits 1 event, not 2. |
| LLMCallRetry on last attempt (no actual retry) or non-last only? | Non-last only -- retry event fires only when retry actually happens | Retry points 1-5 need attempt guard. Last attempt -> LLMCallFailed only. |
| accumulated_errors gap at L230-235: fix in task 12 or out of scope? | Fix in task 12 | New code change: append error_str to accumulated_errors in else block. Ensures LLMCallFailed.last_error is accurate. |
| Test approach: add google-generativeai to dev deps + mock at Gemini API level? | Yes, add to dev deps and mock at Gemini API level | pyproject.toml change. Tests exercise actual GeminiProvider retry loop. |

## Assumptions Validated

- [x] All 3 event types (LLMCallRetry, LLMCallFailed, LLMCallRateLimited) already defined in types.py and exported -- verified L347-378, __all__ L575-577, events/__init__.py L119-121
- [x] StepScopedEvent provides run_id (str), pipeline_name (str), step_name (str | None = None) -- verified types.py L73-74, L162
- [x] GeminiProvider.call_structured() has **kwargs at L79 -- verified, can accept new explicit params additively
- [x] LLMProvider ABC has **kwargs at L42 -- verified, adding explicit params is backward compatible
- [x] executor.py does NOT currently forward event params to provider -- verified L134-140, only passes prompt, system_instruction, result_class, array_validation, validation_context
- [x] pipeline.py already injects event context into call_kwargs -- verified L631-636, no pipeline.py changes needed
- [x] Lazy import + `if event_emitter:` guard pattern established by task 11 -- verified executor.py L117-130
- [x] Zero overhead when event_emitter is None -- verified by task 11 tests (TestNoEmitterZeroOverhead)
- [x] Attempt is 0-indexed in range(max_retries), events use 1-based (attempt + 1) -- verified gemini.py L90, consistent with existing log messages
- [x] call_index NOT needed at provider level -- verified, it's a per-params-loop index from pipeline.py enumerate
- [x] Not-found path (L114-126) is early return, not failure -- verified, no retry/failure events needed
- [x] Rate limit on last attempt falls to else block (generic exception path) -- verified L216 condition `is_rate_limit and attempt < max_retries - 1` fails on last attempt
- [x] google-generativeai is optional dep, not in dev deps -- verified pyproject.toml L20-24

## Open Items

- Rate limit on last attempt: currently treated as generic exception (falls to else at L230). After fix, the error_str will be appended to accumulated_errors. LLMCallFailed.last_error will show the rate-limit error message. No separate LLMCallRateLimited fires on last attempt (by design -- no retry will happen). This is acceptable behavior but worth documenting in event type docstrings.
- Validation retry points 3-5 have redundant `if attempt < max_retries - 1: continue` followed by bare `continue`. Both branches continue. The LLMCallRetry guard (`if attempt < max_retries - 1`) should wrap the event emission BEFORE the first continue, and the bare continue handles the last-attempt case (no event, loop exits to LLMCallFailed). Implementation detail for planning phase.

## Recommendations for Planning

1. Modify provider.py ABC first (adding event_emitter and step_name optional params) since it's the smallest change and establishes the contract for GeminiProvider.
2. Modify executor.py next to forward event params to provider.call_structured() -- simple additive change at L134-140.
3. Modify gemini.py: (a) add explicit event params to signature, (b) fix accumulated_errors gap at L230-235, (c) add lazy import + guard pattern, (d) emit events at all identified points.
4. For retry points 3-5 (schema/array/pydantic validation), insert `if event_emitter and attempt < max_retries - 1:` guard BEFORE the existing `if attempt < max_retries - 1: continue` to emit LLMCallRetry only on non-last attempts.
5. For retry points 1-2 (empty response, JSON decode), the existing `continue` is unconditional. Insert `if event_emitter and attempt < max_retries - 1:` guard before the continue to emit LLMCallRetry.
6. For the rate limit path, insert LLMCallRateLimited emission inside both backoff branches (api_suggested and exponential) BEFORE time.sleep().
7. For post-loop, insert LLMCallFailed emission BEFORE the return statement.
8. Add google-generativeai to pyproject.toml dev deps.
9. Create test_retry_ratelimit_events.py mocking GenerativeModel.generate_content() with per-attempt response sequences to exercise all event emission paths.
10. Follow task 11's test pattern: verify event field values (attempt, error_type, wait_seconds, backoff_type, last_error), verify event ordering, verify zero-overhead when no emitter.
