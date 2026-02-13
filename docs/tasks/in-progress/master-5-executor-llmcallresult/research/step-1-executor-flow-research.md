# Step 1: Executor Flow Research

## Execution Flow: execute_llm_step()

**File:** `llm_pipeline/llm/executor.py`, lines 19-124

### Full Flow

```
execute_llm_step(system_instruction_key, user_prompt_key, variables, result_class, provider, prompt_service, ...)
  1. Validate provider and prompt_service are not None (lines 55-64)
  2. Convert PromptVariables to dicts via model_dump() (lines 67-77)
  3. Retrieve system instruction via prompt_service (lines 80-92)
  4. Retrieve user prompt via prompt_service (lines 95-100)
  5. Call provider.call_structured() (line 103)          <-- TOUCHPOINT 1: receives LLMCallResult now
  6. Check if result is None (line 111)                  <-- TOUCHPOINT 2: broken, LLMCallResult never None
  7. Pydantic validate + construct T instance (lines 116-121)  <-- TOUCHPOINT 3-4: passes LLMCallResult where dict expected
  8. Return T or create_failure() on exception (line 124)
```

### Return Type
`-> T` where `T = TypeVar("T", bound=BaseModel)` -- returns Pydantic model instance, NOT LLMCallResult.

---

## Provider Invocation (Line 103)

### Before (pre-Task 4)
```python
result_dict = provider.call_structured(
    prompt=user_prompt,
    system_instruction=system_instruction,
    result_class=result_class,
    array_validation=array_validation,
    validation_context=validation_context,
)
# result_dict was Optional[Dict[str, Any]]
```

### After Task 4
Same call, but `provider.call_structured()` now returns `LLMCallResult` (frozen dataclass).
Variable `result_dict` holds LLMCallResult, not dict. Name is misleading.

---

## Result Handling (Lines 111-124)

### Current (broken) logic
```python
if result_dict is None:                                    # BROKEN: LLMCallResult is never None
    return result_class.create_failure("LLM call failed")  # Never reached

try:
    if validation_context:
        return result_class.model_validate(
            result_dict, context=validation_context.to_dict()   # BROKEN: passes LLMCallResult, not dict
        )
    else:
        return result_class(**result_dict)                       # BROKEN: can't unpack LLMCallResult as kwargs
except Exception as e:
    logger.error(f"[ERROR] Pydantic validation failed: {e}")
    return result_class.create_failure(f"Validation failed: {str(e)}")
```

### Failure modes
1. `result_dict is None` -- never True, failure path unreachable
2. `result_class(**result_dict)` -- TypeError: can't unpack frozen dataclass as kwargs
3. `result_class.model_validate(result_dict, ...)` -- ValidationError: unexpected type

---

## Pydantic Validation Layer

### In Provider (GeminiProvider lines 182-197)
Provider already does Pydantic validation before setting `.parsed`:
```python
if validation_context:
    result_class.model_validate(response_json, context=validation_context.to_dict())
else:
    result_class(**response_json)
```
Validates dict against result_class, but **discards the constructed instance**. Only stores dict in `parsed`.

### In Executor (lines 116-121)
Executor re-validates and **constructs the actual T instance** to return:
```python
if validation_context:
    return result_class.model_validate(result_dict, context=validation_context.to_dict())
else:
    return result_class(**result_dict)
```

### Redundancy Analysis
- Provider validation: needed for retry logic (retry on validation failure)
- Executor validation: needed for T construction (must return Pydantic model, not dict)
- Both use same logic but serve different purposes
- **Keep both** -- executor validation is defensive safety net + model construction

---

## Downstream Consumption of execute_llm_step() Return Value

### Caller 1: pipeline.py execute() (line 529)
```python
instruction = execute_llm_step(**call_kwargs)
instructions.append(instruction)
```
`instruction` is T (Pydantic model instance). Consumed by:
- `step.process_instructions(instructions)` -- extracts derived context values
- `step.log_instructions(instructions)` -- logs to console
- `step.extract_data(instructions)` -- extracts DB models
- `_save_step_state(step, step_num, instructions, ...)` -- serializes via model_dump()
- `transformation.transform(current_data, instructions)` -- data transformation

### Caller 2: pipeline.py _execute_with_consensus() (line 819)
```python
instruction = execute_llm_step(**call_kwargs)
results.append(instruction)
```
`instruction` is T. Used for consensus matching via `_instructions_match()` which calls `model_dump()`.

### Impact on Callers
**None.** execute_llm_step() still returns T. Internal change only. All callers receive same type.

---

## Touchpoints Affected by Change

| # | File | Line | Current Code | Required Change |
|---|------|------|-------------|-----------------|
| 1 | executor.py | 103 | `result_dict = provider.call_structured(...)` | Rename to `result = provider.call_structured(...)` |
| 2 | executor.py | 111 | `if result_dict is None:` | `if result.parsed is None:` |
| 3 | executor.py | 118 | `result_class.model_validate(result_dict, ...)` | `result_class.model_validate(result.parsed, ...)` |
| 4 | executor.py | 121 | `result_class(**result_dict)` | `result_class(**result.parsed)` |

### Not Affected
| Component | Reason |
|-----------|--------|
| pipeline.py execute() line 529 | Receives T, unchanged |
| pipeline.py _execute_with_consensus() line 819 | Receives T, unchanged |
| _save_step_state() | Receives list of T, unchanged |
| process_instructions() | Receives list of T, unchanged |
| extract_data() | Receives list of T, unchanged |
| log_instructions() | Receives list of T, unchanged |
| create_failure() | Called on result_class, unchanged |
| Return type of execute_llm_step() | Still `-> T`, unchanged |

---

## "Store result" Requirement

Task 5 details: "Store result (LLMCallResult) for potential event emission in later tasks"

### Resolution
- After rename, `result` variable holds LLMCallResult in executor.py scope
- No structural storage needed -- variable exists in function scope
- Task 11 will add event_emitter parameter or change return type to plumb LLMCallResult to pipeline.py
- Task 16 will access result.model_name for PipelineStepState.model field
- Task 5 only ensures the LLMCallResult is captured in named variable, not discarded

---

## Upstream Task 4 Deviations
None. Task 4 completed as planned. 2 HIGH issues (error accumulation) were identified in review and fixed. 3 test failures are intentional and expected for task 5 resolution.

---

## Files Analyzed
| File | Lines | Purpose |
|------|-------|---------|
| `llm_pipeline/llm/executor.py` | 1-140 | execute_llm_step() full implementation |
| `llm_pipeline/llm/provider.py` | 1-64 | LLMProvider ABC, return type now LLMCallResult |
| `llm_pipeline/llm/gemini.py` | 69-244 | GeminiProvider.call_structured(), 3 exit points |
| `llm_pipeline/llm/result.py` | 1-103 | LLMCallResult frozen dataclass |
| `llm_pipeline/pipeline.py` | 391-549 | execute() caller of execute_llm_step |
| `llm_pipeline/pipeline.py` | 813-839 | _execute_with_consensus() caller |
| `llm_pipeline/pipeline.py` | 674-715 | _save_step_state() downstream consumer |
| `llm_pipeline/step.py` | 215-222 | create_failure() on LLMResultMixin |
| `llm_pipeline/step.py` | 303-320 | process_instructions, log_instructions, extract_data |
| `llm_pipeline/types.py` | 74-97 | ExecuteLLMStepParams TypedDict |
| `tests/test_pipeline.py` | 37-60 | MockProvider returning LLMCallResult |
