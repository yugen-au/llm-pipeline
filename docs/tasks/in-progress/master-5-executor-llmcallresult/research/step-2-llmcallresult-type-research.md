# Step 2: LLMCallResult Type Research

## LLMCallResult Model Structure

**File:** `llm_pipeline/llm/result.py`
**Type:** Frozen dataclass (NOT Pydantic), `@dataclass(frozen=True, slots=True)`

### Fields
| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `parsed` | `dict[str, Any] \| None` | `None` | Validated JSON dict from LLM response |
| `raw_response` | `str \| None` | `None` | Raw text from LLM before JSON extraction |
| `model_name` | `str \| None` | `None` | Model identifier (e.g. "gemini-2.0-flash-lite") |
| `attempt_count` | `int` | `1` | Number of attempts used |
| `validation_errors` | `list[str]` | `[]` | Errors from failed attempts (diagnostic only) |

### Properties
- `is_success` -> `bool`: `self.parsed is not None`
- `is_failure` -> `bool`: `self.parsed is None`

### Factory Methods
- `LLMCallResult.success(parsed, raw_response, model_name, attempt_count, validation_errors)` - enforces parsed not None
- `LLMCallResult.failure(raw_response, model_name, attempt_count, validation_errors, parsed=None)` - enforces parsed is None

### Serialization
- `to_dict()` -> `dict[str, Any]` via `dataclasses.asdict()`
- `to_json()` -> `str` via `json.dumps(to_dict())`

---

## GeminiProvider Construction of LLMCallResult

**File:** `llm_pipeline/llm/gemini.py`

### Three Exit Points

1. **Not-found exit** (line 120-126): `LLMCallResult(parsed=None, ...)` -- plain constructor, not-found indicators matched
2. **Success exit** (line 200-206): `LLMCallResult.success(parsed=response_json, ...)` -- factory, all validations passed
3. **Exhaustion exit** (line 238-244): `LLMCallResult(parsed=None, ...)` -- plain constructor, all retries failed

### Validation Pipeline in GeminiProvider (before success exit)
Provider runs three validation layers sequentially:
1. **Schema validation** (line 151): `validate_structured_output(response_json, expected_schema, strict_types)` - JSON structure check
2. **Array validation** (line 167): `validate_array_response(response_json, array_validation, attempt)` - conditional, array length/match
3. **Pydantic validation** (line 182-188): `result_class.model_validate(response_json, context=...)` or `result_class(**response_json)` - full Pydantic model construction

**Critical finding:** When `LLMCallResult.parsed` is not None (success), the dict has ALREADY passed all three validation layers including Pydantic validation inside the provider.

---

## Executor.py Current Validation Logic

**File:** `llm_pipeline/llm/executor.py`, lines 102-124

### Current Flow
```python
result_dict = provider.call_structured(...)      # line 103 -- was Optional[Dict], now LLMCallResult

if result_dict is None:                           # line 111 -- BROKEN: LLMCallResult is never None
    return result_class.create_failure(...)        # line 112

# Pydantic validation + construction              # lines 114-124
try:
    if validation_context:
        return result_class.model_validate(result_dict, context=validation_context.to_dict())
    else:
        return result_class(**result_dict)
except Exception as e:
    return result_class.create_failure(f"Validation failed: {str(e)}")
```

### Why 3 Tests Fail (Task 4 documented)
- `test_full_execution`, `test_save_persists_to_db`, `test_step_state_saved`
- executor receives LLMCallResult object, tries `if result_dict is None` (never true for LLMCallResult), then passes LLMCallResult object to `result_class(**result_dict)` which fails because Pydantic can't unpack a dataclass as kwargs

---

## Required Changes for Task 5

### Change 1: Variable naming
```python
# Before
result_dict = provider.call_structured(...)
# After
result = provider.call_structured(...)
```

### Change 2: Failure check
```python
# Before
if result_dict is None:
# After
if result.parsed is None:
```
Note: `result.is_failure` is equivalent but `result.parsed is None` matches task 5 spec verbatim.

### Change 3: Pydantic construction from result.parsed
```python
# Before
result_class.model_validate(result_dict, context=...)
result_class(**result_dict)
# After
result_class.model_validate(result.parsed, context=...)
result_class(**result.parsed)
```

### Change 4: Import (not needed)
No new imports required in executor.py -- LLMCallResult type is implicit (received from provider, not type-annotated in executor).

### Validation Redundancy Analysis
- Provider already validates with Pydantic before setting `parsed`
- Executor validation is redundant for validation PURPOSE but necessary for CONSTRUCTION
- Executor must return `T` (Pydantic model instance), not dict
- Provider discards the validated model instance, stores only the dict in `.parsed`
- **Keep executor validation as defensive safety net + model construction**

---

## Return Type Preservation

### executor.py signature: `def execute_llm_step(...) -> T`
- Returns Pydantic model instance (T bound to BaseModel)
- Task 5 scope: "Ensure backward compatibility with existing pipeline execution flow"
- Return type does NOT change in task 5

### Downstream Task Needs
- **Task 11**: Needs `result.raw_response`, `result.model_name`, `result.validation_errors` for event emission at pipeline.py level
- **Task 16**: Needs `result.model_name` for `PipelineStepState.model` field

### How "Store result" is Satisfied
Task 5 says: "Store result (LLMCallResult) for potential event emission in later tasks"
- The `result` variable exists in executor.py scope
- Task 11 will add event emission plumbing (event_emitter param, or return type change)
- Task 5 only needs to ensure the LLMCallResult is captured in a named variable, not discarded
- No structural storage mechanism needed in task 5 scope

---

## Integration Pattern Summary

Minimal, backward-compatible change:
1. `result = provider.call_structured(...)` (rename variable)
2. `if result.parsed is None:` (check parsed field)
3. `result_class.model_validate(result.parsed, ...)` / `result_class(**result.parsed)` (use .parsed for construction)
4. Keep try/except for defensive safety
5. Return type unchanged: `-> T`
6. No new imports needed
7. Fixes all 3 failing tests from task 4

---

## Files Analyzed
| File | Lines | Purpose |
|------|-------|---------|
| `llm_pipeline/llm/result.py` | 1-103 | LLMCallResult frozen dataclass definition |
| `llm_pipeline/llm/gemini.py` | 69-244 | GeminiProvider.call_structured() with triple validation |
| `llm_pipeline/llm/provider.py` | 1-64 | LLMProvider ABC, return type annotation |
| `llm_pipeline/llm/executor.py` | 1-140 | execute_llm_step() current implementation |
| `llm_pipeline/llm/__init__.py` | 1-16 | LLMCallResult already exported |
| `tests/test_pipeline.py` | 1-467 | MockProvider returning LLMCallResult, 3 failing tests |
| `llm_pipeline/pipeline.py` | 490-550, 813-839 | Call sites: execute() and _execute_with_consensus() |
| `llm_pipeline/step.py` | 215-222 | create_failure() on LLMResultMixin |

## Upstream Context (Task 4)
- Task 4 completed, no deviations from plan
- 2 HIGH issues fixed: JSON decode and no-response error accumulation
- 3 test failures are expected and documented for task 5 resolution
