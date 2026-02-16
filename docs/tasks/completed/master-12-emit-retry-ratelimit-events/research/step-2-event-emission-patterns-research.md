# Step 2: Event Emission Patterns Research

## 1. Retry Loop Structure (gemini.py L69-244)

### Outer Loop
```python
for attempt in range(max_retries):  # L90
```

### Retry Points (continue statements)

6 distinct `continue` paths inside the retry loop. Each is an LLMCallRetry emission candidate.

| # | Lines | Trigger | Error Type String | Error Source |
|---|-------|---------|------------------|-------------|
| 1 | L104-109 | Empty/no response from model | `empty_response` | `"Empty/no response from model"` |
| 2 | L143-148 | JSON decode error on response text | `json_decode_error` | `str(JSONDecodeError)` |
| 3 | L154-163 | Schema validation failure (validate_structured_output) | `validation_error` | `errors` list from validator |
| 4 | L170-179 | Array validation failure (validate_array_response) | `array_validation_error` | `array_errors` list |
| 5 | L189-197 | Pydantic model validation failure | `pydantic_validation_error` | `str(pydantic_error)` |
| 6 | L230-235 | Non-rate-limit exception, retries remaining | `exception` | `str(e)` |

Note: Retry points 3, 4, 5 have a pattern of `if attempt < max_retries - 1: continue` followed by bare `continue`. Both paths continue; the conditional check is redundant but harmless. LLMCallRetry fires regardless since both branches retry.

### Rate Limit Path (L208-229)

```python
except Exception as e:                              # L208
    error_str = str(e)
    is_rate_limit = (                                # L210-214
        "429" in error_str
        or "quota" in error_str.lower()
        or "rate limit" in error_str.lower()
    )
    if is_rate_limit and attempt < max_retries - 1:  # L216
        retry_delay = extract_retry_delay_from_error(e)  # L217
        if retry_delay:                              # L218
            time.sleep(retry_delay)                  # L222 - API-suggested
        else:
            wait_time = 2**attempt                   # L224
            time.sleep(wait_time)                    # L228 - exponential backoff
        continue                                     # L229
```

Two backoff types:
- `api_suggested`: when `extract_retry_delay_from_error()` returns a float
- `exponential`: fallback, `2**attempt` seconds

LLMCallRateLimited should emit BEFORE `time.sleep()` to announce the upcoming wait.

### Non-Rate-Limit Exception Path (L230-235)

```python
    else:                                            # L230
        logger.warning(...)                          # L231-233
        if attempt < max_retries - 1:                # L234
            continue                                 # L235
```

On non-last attempt: LLMCallRetry with error_type="exception".
On last attempt: falls through to post-loop (no continue), hits LLMCallFailed.

### Post-Loop Failure (L237-244)

```python
logger.error(f"  [ERROR] All {max_retries} attempts failed")  # L237
return LLMCallResult(                                          # L238
    parsed=None,
    raw_response=last_raw_response,
    model_name=self.model_name,
    attempt_count=max_retries,
    validation_errors=accumulated_errors,
)
```

This is the single LLMCallFailed emission point. `last_error` = last entry in `accumulated_errors` or a summary.

### Success Path (L199-206)

```python
return LLMCallResult.success(...)  # L200-206
```

No event emission here -- LLMCallCompleted is already emitted by executor.py after call_structured() returns.

### Not-Found Path (L114-126)

```python
return LLMCallResult(parsed=None, ...)  # L120-126
```

Early return, not a failure. No retry, no LLMCallFailed. No event emission needed.


## 2. Event Type Definitions (types.py L347-378)

All three event types are already defined and exported:

### LLMCallRetry (L347-357)
```python
@dataclass(frozen=True, slots=True, kw_only=True)
class LLMCallRetry(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_LLM_CALL
    attempt: int          # 1-based attempt number (attempt + 1)
    max_retries: int      # total allowed
    error_type: str       # classification string
    error_message: str    # human-readable error detail
```

### LLMCallFailed (L359-367)
```python
@dataclass(frozen=True, slots=True, kw_only=True)
class LLMCallFailed(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_LLM_CALL
    max_retries: int      # total attempts made
    last_error: str       # final error message
```

### LLMCallRateLimited (L369-378)
```python
@dataclass(frozen=True, slots=True, kw_only=True)
class LLMCallRateLimited(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_LLM_CALL
    attempt: int          # 1-based attempt number
    wait_seconds: float   # how long we'll sleep
    backoff_type: str     # "api_suggested" or "exponential"
```

All inherit `StepScopedEvent` which provides: `run_id`, `pipeline_name`, `timestamp`, `step_name` (str | None).

Already in `__all__` of types.py (L575-577) and events/__init__.py (L119-121). Already registered in `_EVENT_REGISTRY` via `__init_subclass__`. Already mapped to `logging.INFO` via `CATEGORY_LLM_CALL` in handlers.py `DEFAULT_LEVEL_MAP`.

No changes needed to types.py, __init__.py, or handlers.py.


## 3. Event Emitter Threading Pattern

### Current Chain: pipeline.py -> executor.py -> provider

**Pipeline (pipeline.py L631-636):**
```python
if self._event_emitter:
    call_kwargs["event_emitter"] = self._event_emitter
    call_kwargs["run_id"] = self.run_id
    call_kwargs["pipeline_name"] = self.pipeline_name
    call_kwargs["step_name"] = step.step_name
    call_kwargs["call_index"] = idx
```

**Executor (executor.py L35-39):**
```python
event_emitter: Optional["PipelineEventEmitter"] = None,
run_id: Optional[str] = None,
pipeline_name: Optional[str] = None,
step_name: Optional[str] = None,
call_index: int = 0,
```

**Executor -> Provider (executor.py L134-140):**
```python
result: LLMCallResult = provider.call_structured(
    prompt=user_prompt,
    system_instruction=system_instruction,
    result_class=result_class,
    array_validation=array_validation,
    validation_context=validation_context,
)
```

Currently NO event params are passed from executor to provider. Task 12 must add them.

### Required Change: Thread event_emitter through executor to provider

executor.py L134-140 needs to additionally pass:
- `event_emitter=event_emitter`
- `run_id=run_id`
- `pipeline_name=pipeline_name`
- `step_name=step_name`

`call_index` is NOT needed at provider level -- it's a per-params-loop index managed by pipeline/executor. Provider operates on a single call.

### Provider ABC Signature Change (provider.py)

LLMProvider.call_structured() abstract method currently has `**kwargs` (L42). Two options:

**Option A -- Explicit params on ABC:**
Add `event_emitter`, `run_id`, `pipeline_name`, `step_name` as optional params to both LLMProvider.call_structured() and GeminiProvider.call_structured(). Backward compatible since all default to None.

**Option B -- Pass via existing **kwargs:**
executor passes extra kwargs, GeminiProvider extracts from `**kwargs`. No ABC change. Less explicit but zero-touch on ABC.

**Recommendation:** Option A (explicit). Matches Task 11 pattern where executor.py got explicit params. Makes the API clear. Both ABC and GeminiProvider already have **kwargs so the change is additive.


## 4. Emission Pattern in GeminiProvider

### Guard Pattern
Same as executor.py and pipeline.py:
```python
if event_emitter:
    event_emitter.emit(LLMCallRetry(...))
```

### Lazy Import Pattern
Match executor.py L118-119:
```python
if event_emitter:
    from llm_pipeline.events.types import LLMCallRetry, LLMCallFailed, LLMCallRateLimited
```

Import once at first emission point. All subsequent `if event_emitter:` blocks reuse the already-imported names.

### StepScopedEvent Base Fields
Every emission needs:
```python
run_id=run_id,
pipeline_name=pipeline_name,
step_name=step_name,
```


## 5. Detailed Emission Map

### 5a. LLMCallRetry Emissions (6 points)

**Point 1: Empty response (L108-109)**
```python
accumulated_errors.append("Empty/no response from model")
if event_emitter:
    event_emitter.emit(LLMCallRetry(
        run_id=run_id, pipeline_name=pipeline_name, step_name=step_name,
        attempt=attempt + 1, max_retries=max_retries,
        error_type="empty_response",
        error_message="Empty/no response from model",
    ))
continue
```

**Point 2: JSON decode error (L147-148)**
```python
accumulated_errors.append(f"JSON decode error: {e}")
if event_emitter:
    event_emitter.emit(LLMCallRetry(
        run_id=run_id, pipeline_name=pipeline_name, step_name=step_name,
        attempt=attempt + 1, max_retries=max_retries,
        error_type="json_decode_error",
        error_message=str(e),
    ))
continue
```

**Point 3: Schema validation failure (L160-163)**
```python
accumulated_errors.extend(errors)
if event_emitter:
    event_emitter.emit(LLMCallRetry(
        run_id=run_id, pipeline_name=pipeline_name, step_name=step_name,
        attempt=attempt + 1, max_retries=max_retries,
        error_type="validation_error",
        error_message="; ".join(errors),
    ))
# existing: if attempt < max_retries - 1: continue / continue
```

**Point 4: Array validation failure (L176-179)**
```python
accumulated_errors.extend(array_errors)
if event_emitter:
    event_emitter.emit(LLMCallRetry(
        run_id=run_id, pipeline_name=pipeline_name, step_name=step_name,
        attempt=attempt + 1, max_retries=max_retries,
        error_type="array_validation_error",
        error_message="; ".join(array_errors),
    ))
```

**Point 5: Pydantic validation failure (L194-197)**
```python
accumulated_errors.append(str(pydantic_error))
if event_emitter:
    event_emitter.emit(LLMCallRetry(
        run_id=run_id, pipeline_name=pipeline_name, step_name=step_name,
        attempt=attempt + 1, max_retries=max_retries,
        error_type="pydantic_validation_error",
        error_message=str(pydantic_error),
    ))
```

**Point 6: Non-rate-limit exception with retries remaining (L234-235)**
```python
if attempt < max_retries - 1:
    if event_emitter:
        event_emitter.emit(LLMCallRetry(
            run_id=run_id, pipeline_name=pipeline_name, step_name=step_name,
            attempt=attempt + 1, max_retries=max_retries,
            error_type="exception",
            error_message=error_str,
        ))
    continue
```

### 5b. LLMCallRateLimited Emission (1 point, before sleep)

```python
if is_rate_limit and attempt < max_retries - 1:
    retry_delay = extract_retry_delay_from_error(e)
    if retry_delay:
        if event_emitter:
            event_emitter.emit(LLMCallRateLimited(
                run_id=run_id, pipeline_name=pipeline_name, step_name=step_name,
                attempt=attempt + 1, wait_seconds=retry_delay,
                backoff_type="api_suggested",
            ))
        time.sleep(retry_delay)
    else:
        wait_time = 2**attempt
        if event_emitter:
            event_emitter.emit(LLMCallRateLimited(
                run_id=run_id, pipeline_name=pipeline_name, step_name=step_name,
                attempt=attempt + 1, wait_seconds=float(wait_time),
                backoff_type="exponential",
            ))
        time.sleep(wait_time)
    continue
```

### 5c. LLMCallFailed Emission (1 point, post-loop)

```python
logger.error(f"  [ERROR] All {max_retries} attempts failed")
if event_emitter:
    last_error = accumulated_errors[-1] if accumulated_errors else "Unknown error"
    event_emitter.emit(LLMCallFailed(
        run_id=run_id, pipeline_name=pipeline_name, step_name=step_name,
        max_retries=max_retries,
        last_error=last_error,
    ))
return LLMCallResult(...)
```


## 6. Edge Cases

### Last-Attempt Validation Failures (Points 3-5)
On last attempt (attempt == max_retries - 1), the validation retry points still `continue` which exits the for-loop naturally. Post-loop LLMCallFailed fires. So on last attempt: LLMCallRetry fires (documenting the error), THEN LLMCallFailed fires (documenting exhaustion). Both events fire. This is correct: the retry event captures the specific error, the failed event captures overall exhaustion.

### Rate Limit on Last Attempt
`is_rate_limit and attempt < max_retries - 1` -- on last attempt the condition fails, falls to `else` block (L230-235). Last attempt with rate limit is treated as a generic exception. No LLMCallRateLimited, just falls through to LLMCallFailed. This matches the existing behavior (no retry on last rate limit).

### Not-Found Response (L114-126)
Early return with parsed=None. Not a failure in the retry sense. No retry events emitted. This is intentional behavior (LLM correctly indicates "not found").

### Zero Overhead
When `event_emitter is None` (default), all event blocks are skipped. No imports, no object creation. Matches Task 11 pattern.


## 7. Files Requiring Changes

### Modified
| File | Changes |
|------|---------|
| `llm_pipeline/llm/provider.py` | Add optional event params to abstract call_structured() signature: event_emitter, run_id, pipeline_name, step_name |
| `llm_pipeline/llm/gemini.py` | Add optional event params to call_structured() signature. Emit LLMCallRetry at 6 retry points, LLMCallRateLimited before sleep, LLMCallFailed after loop. |
| `llm_pipeline/llm/executor.py` | Forward event params (event_emitter, run_id, pipeline_name, step_name) to provider.call_structured() call at L134-140 |

### New
| File | Purpose |
|------|---------|
| `tests/events/test_retry_ratelimit_events.py` | Tests for all 3 event types with mocked Gemini API responses |

### Unchanged
| File | Reason |
|------|--------|
| `llm_pipeline/events/types.py` | All 3 event types already defined |
| `llm_pipeline/events/__init__.py` | Already exports all 3 |
| `llm_pipeline/events/handlers.py` | CATEGORY_LLM_CALL already mapped |
| `llm_pipeline/pipeline.py` | No changes needed, event_emitter already injected into call_kwargs |


## 8. Test Strategy

### MockProvider Enhancements for Retry Tests
The existing MockProvider in conftest.py is too simple (returns success or raises once). Need a provider that:
- Can return different responses per attempt (to test retry then success)
- Can raise rate limit errors (to test LLMCallRateLimited)
- Can exhaust all retries (to test LLMCallFailed)

Options:
A. Extend MockProvider with attempt-based behavior
B. Test at GeminiProvider level by mocking `genai.GenerativeModel.generate_content()`
C. New RetryMockProvider specifically for these tests

**Recommendation:** Option B (mock at Gemini API level). This tests the actual retry loop in GeminiProvider, not a mock. Use `unittest.mock.patch` on `google.generativeai.GenerativeModel.generate_content` to return controlled responses per attempt. But this requires google-generativeai to be installed in test env.

Alternative: Option C -- create a TestableProvider that extends GeminiProvider but overrides the API call. Or test the retry logic by calling GeminiProvider.call_structured() directly with a patched API.

### Test Cases
1. Single retry then success -> 1 LLMCallRetry event
2. Multiple retries then success -> N LLMCallRetry events with incrementing attempt
3. All retries exhausted -> N LLMCallRetry + 1 LLMCallFailed
4. Rate limit with API-suggested delay -> 1 LLMCallRateLimited(backoff_type="api_suggested")
5. Rate limit with exponential backoff -> 1 LLMCallRateLimited(backoff_type="exponential")
6. Rate limit then success -> LLMCallRateLimited + no LLMCallFailed
7. No event_emitter -> zero events, zero overhead
8. JSON decode error -> LLMCallRetry(error_type="json_decode_error")
9. Validation error -> LLMCallRetry(error_type="validation_error")
10. Empty response -> LLMCallRetry(error_type="empty_response")


## 9. Backward Compatibility

All new params on provider.call_structured() are optional with None defaults. Existing callers (executor.py explicit call, any direct provider users) will see no behavior change. GeminiProvider already accepts **kwargs, so unknown kwargs are absorbed.

The executor.py change is additive: it passes extra kwargs to a method that already accepts them via **kwargs.
