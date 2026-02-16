# IMPLEMENTATION - STEP 3: ADD EVENT EMISSIONS
**Status:** completed

## Summary
Added LLMCallRetry, LLMCallFailed, and LLMCallRateLimited event emissions to GeminiProvider's call_structured() retry loop. Fixed accumulated_errors bug where non-rate-limit exceptions weren't appended to the error list.

## Files
**Created:** none
**Modified:** llm_pipeline/llm/gemini.py
**Deleted:** none

## Changes
### File: `llm_pipeline/llm/gemini.py`

**Signature change** - Added 4 optional params matching ABC + executor threading:
```python
# Before
def call_structured(self, ..., validation_context=None, **kwargs):

# After
def call_structured(self, ..., validation_context=None, event_emitter=None, step_name=None, run_id=None, pipeline_name=None, **kwargs):
```

**Lazy import guard** - Added at top of method body:
```python
if event_emitter:
    from llm_pipeline.events.types import LLMCallRetry, LLMCallFailed, LLMCallRateLimited
```

**Bug fix** - accumulated_errors gap in else block (non-rate-limit exception):
```python
# Before (error_str NOT appended)
else:
    logger.warning(...)
    if attempt < max_retries - 1:
        continue

# After (error_str appended before continue guard)
else:
    logger.warning(...)
    accumulated_errors.append(error_str)
    if event_emitter and attempt < max_retries - 1:
        event_emitter.emit(LLMCallRetry(...))
    if attempt < max_retries - 1:
        continue
```

**8 emission points added:**
| # | Type | Location | Guard | error_type/backoff_type |
|---|------|----------|-------|------------------------|
| 1 | LLMCallRetry | Empty response (L116) | `event_emitter and attempt < max_retries - 1` | empty_response |
| 2 | LLMCallRetry | JSON decode (L161) | `event_emitter and attempt < max_retries - 1` | json_decode_error |
| 3 | LLMCallRetry | Schema validation (L180) | `event_emitter and attempt < max_retries - 1` | validation_error |
| 4 | LLMCallRetry | Array validation (L202) | `event_emitter and attempt < max_retries - 1` | array_validation_error |
| 5 | LLMCallRetry | Pydantic validation (L226) | `event_emitter and attempt < max_retries - 1` | pydantic_validation_error |
| 6 | LLMCallRetry | Non-rate-limit exception (L282) | `event_emitter and attempt < max_retries - 1` | exception |
| 7 | LLMCallRateLimited | API-suggested delay (L259) | `event_emitter` | api_suggested |
| 8 | LLMCallRateLimited | Exponential backoff (L270) | `event_emitter` | exponential |
| 9 | LLMCallFailed | Post-loop failure (L292) | `event_emitter` | N/A (last_error field) |

## Decisions
### LLMCallRetry guard on Point 6 (exception path)
**Choice:** Used `event_emitter and attempt < max_retries - 1` as combined guard, placed before the existing `if attempt < max_retries - 1: continue`
**Rationale:** Follows same pattern as points 1-5. The existing continue guard remains separate for clarity.

### Rate limit emissions have no attempt guard
**Choice:** LLMCallRateLimited emits on all rate-limited attempts (no `attempt < max_retries - 1` check)
**Rationale:** Rate limit path already guarded by `if is_rate_limit and attempt < max_retries - 1` at outer scope. Last-attempt rate limits fall to else block (generic exception path).

## Verification
[x] Syntax check passes (ast.parse)
[x] All 8+1 emission points match PLAN.md specification
[x] All LLMCallRetry emissions use `attempt < max_retries - 1` guard (non-last only)
[x] All emissions use 1-based attempt indexing (attempt + 1)
[x] Lazy import + guard pattern follows task 11 pattern
[x] accumulated_errors bug fixed (error_str appended in else block)
[x] LLMCallFailed uses accumulated_errors[-1] with "Unknown error" fallback
[x] Rate limit paths emit ONLY LLMCallRateLimited (not LLMCallRetry)
[x] Signature matches ABC: event_emitter, step_name, run_id, pipeline_name (all Optional)
