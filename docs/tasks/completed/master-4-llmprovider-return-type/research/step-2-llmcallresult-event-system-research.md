# Step 2: LLMCallResult & Event System Research

## Executive Summary

LLMCallResult is a frozen stdlib dataclass at `llm_pipeline/llm/result.py` with 5 fields, 6 helper methods, and factory classmethods with invariant enforcement. It is NOT a PipelineEvent subclass -- it's a plain value object that Task 4 will construct inside GeminiProvider. The event system's LLMCallCompleted has overlapping but non-identical fields (notably `parsed_result` vs `parsed` naming). GeminiProvider has 3 return sites to convert.

## LLMCallResult Definition

**Location:** `llm_pipeline/llm/result.py`
**Import paths:**
- Direct: `from llm_pipeline.llm.result import LLMCallResult`
- Package: `from llm_pipeline.llm import LLMCallResult`
- Re-export: `from llm_pipeline.events import LLMCallResult`
- **NOT valid:** `from events.result` (no events/result.py exists -- Task 4 spec has wrong import path)

**Class:** `@dataclass(frozen=True, slots=True)` with `from __future__ import annotations`

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| parsed | dict[str, Any] \| None | None | Validated JSON dict (same as current call_structured return) |
| raw_response | str \| None | None | Original LLM response text before JSON extraction |
| model_name | str \| None | None | Model identifier (e.g. "gemini-2.0-flash-lite") |
| attempt_count | int | 1 | Number of attempts (1 = first try success) |
| validation_errors | list[str] | [] | Accumulated validation errors across attempts |

### Helper Methods

| Method | Signature | Purpose |
|--------|-----------|---------|
| to_dict() | -> dict[str, Any] | asdict-based serialization (no datetime conversion needed) |
| to_json() | -> str | JSON string via json.dumps(to_dict()) |
| is_success | @property -> bool | True when parsed is not None |
| is_failure | @property -> bool | True when parsed is None |
| success() | @classmethod -> LLMCallResult | Factory; raises ValueError if parsed is None |
| failure() | @classmethod -> LLMCallResult | Factory; raises ValueError if parsed is not None |

### Factory Signatures

```python
@classmethod
def success(cls, parsed: dict[str, Any], raw_response: str, model_name: str,
            attempt_count: int = 1, validation_errors: list[str] | None = None) -> LLMCallResult

@classmethod
def failure(cls, raw_response: str, model_name: str, attempt_count: int,
            validation_errors: list[str], parsed: None = None) -> LLMCallResult
```

**Key constraint:** failure() requires `raw_response: str` (not Optional). For no-response cases (line 103), pass empty string or whatever text is available.

## Event System Architecture

### How LLMCallResult relates to events

LLMCallResult is NOT a PipelineEvent. Relationship is data-flow:

```
GeminiProvider.call_structured() -> LLMCallResult (Task 4)
    |
    v
executor.py uses result.parsed (Task 5)
    |
    v
executor emits LLMCallCompleted event with data FROM result (future task)
```

### PipelineEventEmitter Protocol

```python
@runtime_checkable
class PipelineEventEmitter(Protocol):
    def emit(self, event: PipelineEvent) -> None: ...
```

- CompositeEmitter dispatches to multiple handlers with error isolation
- Events are frozen dataclasses with auto-derived event_type strings
- All events inherit from PipelineEvent (base) or StepScopedEvent (step-scoped)

### LLMCallCompleted Event (the consumer of LLMCallResult data)

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class LLMCallCompleted(StepScopedEvent):
    call_index: int                          # NOT in LLMCallResult
    raw_response: str | None                 # same
    parsed_result: dict[str, Any] | None     # NAMED "parsed" in LLMCallResult
    model_name: str | None                   # same
    attempt_count: int                       # same
    validation_errors: list[str]             # same
```

**Field name asymmetry:** `LLMCallCompleted.parsed_result` vs `LLMCallResult.parsed`. Mapping is trivial but must be handled explicitly when emitting events.

### Other Related LLM Call Events

| Event | Key Fields | When Emitted |
|-------|-----------|--------------|
| LLMCallPrepared | call_count, system_key, user_key | Before LLM calls for a step |
| LLMCallStarting | call_index, rendered prompts | Each individual call begins |
| LLMCallCompleted | call_index, raw_response, parsed_result, model_name, attempt_count, validation_errors | Call finishes (success or partial) |
| LLMCallRetry | attempt, max_retries, error_type, error_message | Retry after failure |
| LLMCallFailed | max_retries, last_error | All retries exhausted |
| LLMCallRateLimited | attempt, wait_seconds, backoff_type | Rate limit triggered |

## GeminiProvider Return Sites Analysis

### Current return points in call_structured()

| Line | Condition | Current Return | LLMCallResult Construction |
|------|-----------|---------------|---------------------------|
| 114 | not_found_indicators match | `return None` | `LLMCallResult(parsed=None, raw_response=response_text, model_name=self.model_name, attempt_count=attempt+1, validation_errors=[])` |
| 184 | Validation passed | `return response_json` | `LLMCallResult.success(parsed=response_json, raw_response=response_text, model_name=self.model_name, attempt_count=attempt+1, validation_errors=accumulated_errors)` |
| 216 | All retries exhausted | `return None` | `LLMCallResult.failure(raw_response=last_raw or "", model_name=self.model_name, attempt_count=max_retries, validation_errors=accumulated_errors)` |

### Data to track through retry loop

| Variable | Source | When Captured |
|----------|--------|---------------|
| raw_response | `response.text` (line 106) | Each attempt; keep last for failure case |
| attempt_count | `attempt + 1` | Derived from loop counter (0-indexed) |
| validation_errors | JSON parse errors, validate_structured_output errors, Pydantic errors | Accumulate across all attempts |
| model_name | `self.model_name` | Constant; available from constructor |

### Error accumulation points

1. **No response** (line 100-104): `f"Attempt {attempt+1}: No response from Gemini"`
2. **JSON parse error** (line 131-135): `f"Attempt {attempt+1}: JSON parse error: {e}"`
3. **Schema validation** (line 138-149): errors from `validate_structured_output()`
4. **Array validation** (line 152-164): errors from `validate_array_response()`
5. **Pydantic validation** (line 167-181): `f"Attempt {attempt+1}: Pydantic validation failed: {pydantic_error}"`
6. **Rate limit/API error** (line 186-213): `str(e)` from general exception

### Not-Found Indicator Special Case

The not-found return (line 114) is semantically "valid response, no data" not "call failed." However:
- executor.py treats `parsed is None` as failure regardless
- success() factory rejects parsed=None (ValueError)
- Current behavior: returns None -> executor calls create_failure()

**Resolution:** Use plain constructor `LLMCallResult(parsed=None, ...)` (not failure() factory, since it's not truly a retry-exhaustion failure, and not success() since parsed is None). Downstream behavior unchanged: executor checks `result.parsed is None`.

## Task 4 Spec Corrections Needed

1. **Import path:** Task 4 says "Import LLMCallResult from events.result" -- should be `from llm_pipeline.llm.result import LLMCallResult`
2. **Line references:** Task 4 says "Track raw_response from response.text at line ~106" -- confirmed accurate
3. **Return type:** Task 4 says change from `Optional[Dict[str, Any]]` to `LLMCallResult` -- confirmed correct

## Downstream Impact (Task 5 - OUT OF SCOPE)

Task 5 changes executor.py to use `result.parsed` instead of `result_dict`. Current executor.py:
- Line 103: `result_dict = provider.call_structured(...)`
- Line 111: `if result_dict is None:`
- Lines 117-121: Pydantic validation using result_dict

Task 5 will change these to use `result.parsed`. Not our concern for Task 4.

## Test Implications for Task 4

GeminiProvider tests must verify:
- First-try success returns LLMCallResult with parsed set, attempt_count=1, validation_errors=[]
- Retry success returns LLMCallResult with parsed set, attempt_count>1, accumulated validation_errors
- All retries failed returns LLMCallResult with parsed=None, attempt_count=max_retries, all errors
- Not-found returns LLMCallResult with parsed=None, raw_response captured, validation_errors=[]
- raw_response always captured from response.text
- model_name always set to self.model_name
