# Step 1: Provider Architecture Research

## Executive Summary

`LLMProvider.call_structured()` returns `Optional[Dict[str, Any]]` with 9 parameters. GeminiProvider implements a retry loop with 2 success exit points (dict return, None for not-found) and 1 failure exit point (None after exhausted retries), plus 6 retry triggers. Single production call site in `executor.py:103`. MockProvider in tests also needs updating. All data needed for LLMCallResult fields is available inside GeminiProvider. No blocking ambiguities found.

## LLMProvider ABC (`provider.py`)

### Signature

```python
@abstractmethod
def call_structured(
    self,
    prompt: str,
    system_instruction: str,
    result_class: Type[BaseModel],
    max_retries: int = 3,
    not_found_indicators: Optional[List[str]] = None,
    strict_types: bool = True,
    array_validation: Optional[Any] = None,
    validation_context: Optional[Any] = None,
    **kwargs,
) -> Optional[Dict[str, Any]]:
```

### Contract
- Returns validated JSON dict on success, None on failure
- No retry semantics specified in ABC (left to implementations)
- `result_class` is Pydantic BaseModel for validation
- `**kwargs` allows provider-specific extensions

## GeminiProvider (`gemini.py`) - Full Flow Analysis

### Constructor
- `api_key`: from param or `GEMINI_API_KEY` env
- `model_name`: default `"gemini-2.0-flash-lite"` -- available as `self.model_name` for LLMCallResult
- `rate_limiter`: default RateLimiter(max_requests=8, time_window_seconds=60)
- Lazy SDK config via `_ensure_configured()`

### Retry Loop Structure (lines 86-216)

```
for attempt in range(max_retries):          # 0-indexed
    try:
        rate_limiter.wait_if_needed()
        model = GenerativeModel(...)
        response = model.generate_content(prompt_with_schema)

        [A] No response check              -> continue (retry)
        [B] Not-found check                -> return None (early exit)
        [C] JSON extraction from response
        [D] JSON parse                     -> continue on error (retry)
        [E] Schema validation              -> continue on error (retry)
        [F] Array validation               -> continue on error (retry)
        [G] Pydantic validation            -> continue on error (retry)
        [H] All validations passed         -> return response_json (SUCCESS)

    except Exception:
        [I] Rate limit error               -> sleep + continue (retry)
        [J] Other error                    -> continue (retry)

[K] All retries exhausted                  -> return None (FAILURE)
```

### Exit Points (require LLMCallResult construction)

| # | Line | Current Return | Condition | LLMCallResult Construction |
|---|------|---------------|-----------|---------------------------|
| 1 | 114 | `None` | not_found_indicators match | `failure(raw_response=response_text, model_name=self.model_name, attempt_count=attempt+1, validation_errors=[])` |
| 2 | 184 | `response_json` | All validations pass | `success(parsed=response_json, raw_response=response_text, model_name=self.model_name, attempt_count=attempt+1, validation_errors=accumulated)` |
| 3 | 216 | `None` | All retries exhausted | `failure(raw_response=last_raw, model_name=self.model_name, attempt_count=max_retries, validation_errors=accumulated)` |

### Retry Triggers (continue points)

| # | Line | Trigger | Error Data for validation_errors |
|---|------|---------|--------------------------------|
| A | 104 | No response from Gemini | `"No response from Gemini"` |
| D | 131-135 | JSON parse error | `str(JSONDecodeError)` |
| E | 138-149 | Schema validation failed | `errors` list from `validate_structured_output()` |
| F | 153-164 | Array validation failed | `array_errors` list from `validate_array_response()` |
| G | 174-181 | Pydantic validation failed | `str(pydantic_error)` |
| I | 194-207 | Rate limit (429/quota) | `str(exception)` |
| J | 209-213 | Other exceptions | `str(exception)` |

### Data Available for LLMCallResult Fields

| Field | Source | Notes |
|-------|--------|-------|
| `parsed` | `response_json` (line 184) | Only set on success exit |
| `raw_response` | `response.text` -> `response_text` (line 106) | Per-attempt; need outer variable to track last value |
| `model_name` | `self.model_name` (instance attr) | Always available |
| `attempt_count` | `attempt + 1` (loop is 0-indexed) | 1-based in LLMCallResult spec |
| `validation_errors` | Multiple sources (see table above) | Must accumulate across all attempts |

### Implementation Notes

1. **`last_raw_response`**: Need variable outside retry loop. Some attempts fail before getting `response.text` (e.g., rate limit exceptions at API call), so last_raw_response may be from a previous attempt.

2. **`validation_errors` accumulation**: Initialize `accumulated_errors: list[str] = []` before loop. Append error strings at each continue point. On success, these capture prior-attempt errors (diagnostic only).

3. **Not-found exit (line 114)**: Currently returns None. With LLMCallResult, returns failure with empty validation_errors. This preserves existing executor behavior (`result.parsed is None` -> `create_failure()`).

4. **Import path**: Task 4 spec references `from events.result import LLMCallResult`. Correct path is `from llm_pipeline.llm.result import LLMCallResult` (within same llm package: `from .result import LLMCallResult`).

## Call Sites

### Production: `executor.py` (lines 103-124)

```python
# Line 103 - THE call site
result_dict = provider.call_structured(
    prompt=user_prompt,
    system_instruction=system_instruction,
    result_class=result_class,
    array_validation=array_validation,
    validation_context=validation_context,
)

# Line 111 - None check
if result_dict is None:
    return result_class.create_failure("LLM call failed")

# Lines 116-121 - Pydantic re-validation (redundant with GeminiProvider's internal validation)
try:
    if validation_context:
        return result_class.model_validate(result_dict, context=validation_context.to_dict())
    else:
        return result_class(**result_dict)
except Exception as e:
    return result_class.create_failure(f"Validation failed: {str(e)}")
```

**Migration (Task 5 scope):**
- `result_dict` -> `result`
- `if result_dict is None` -> `if result.parsed is None`
- `result_dict` usage in Pydantic validation -> `result.parsed`

### Test: `test_pipeline.py` (lines 34-46)

```python
class MockProvider(LLMProvider):
    def call_structured(self, prompt, system_instruction, result_class, **kwargs):
        if self._call_count < len(self._responses):
            response = self._responses[self._call_count]
            self._call_count += 1
            return response  # returns raw dict
        return None  # returns None
```

**Migration (Task 4 scope):** MockProvider must return `LLMCallResult` instead of raw dict/None. Wrapping: `LLMCallResult.success(parsed=response, ...)` or `LLMCallResult.failure(...)`.

## Public API Exports (`llm/__init__.py`)

```python
from llm_pipeline.llm.provider import LLMProvider
from llm_pipeline.llm.rate_limiter import RateLimiter
from llm_pipeline.llm.result import LLMCallResult
from llm_pipeline.llm.schema import flatten_schema, format_schema_for_llm
```

LLMCallResult already exported from both `llm_pipeline.llm` and `llm_pipeline.events`.

## Upstream Task 3 Deviations

From Task 3's VALIDATED_RESEARCH.md:
- **Import path mismatch**: Task 4 spec says `from events.result` but file is at `llm_pipeline/llm/result.py`. Use `from .result import LLMCallResult` in provider.py and gemini.py.
- **Field name asymmetry**: LLMCallCompleted event uses `parsed_result` while LLMCallResult uses `parsed`. Mapping is trivial but worth noting for future event emission (Task 6+ scope).
- **failure() factory**: Accepts empty validation_errors list. Valid for not-found and timeout/network cases.

## Downstream Task 5 Scope (OUT OF SCOPE for Task 4)

Task 5 updates `executor.py` to handle LLMCallResult. Task 4 only changes provider.py ABC + gemini.py implementation + MockProvider (which is part of the test suite and must match the ABC).

## Assumptions Validated

- [x] LLMCallResult exists at llm/result.py with all fields, factory methods, and properties (Task 3 complete)
- [x] Single production call site in executor.py (line 103)
- [x] GeminiProvider has 3 exit points needing LLMCallResult construction
- [x] All data for LLMCallResult fields is available inside GeminiProvider
- [x] Import path is `from .result import LLMCallResult` (not events.result)
- [x] MockProvider in tests returns raw dict, must be updated to return LLMCallResult
- [x] No other LLMProvider subclasses exist in the codebase
- [x] frozen=True on LLMCallResult means fields set at construction only

## Open Items

None. All findings are clear for implementation planning.
