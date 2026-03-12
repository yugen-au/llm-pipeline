# Step 1: Existing Validation Logic Analysis

## Overview

Task 3 ports custom validation logic to pydantic-ai `@agent.output_validator` decorators. This document maps all existing validation code, its current state post-Task-2, and the wiring points in the pipeline.

---

## 1. Deleted Validation Functions (llm_pipeline/llm/validation.py)

Deleted in Task 2 commit `4aae017f`. Original contents:

### check_not_found_response(response_text, not_found_indicators) -> bool
- **Purpose**: Check if LLM response text contains any "not found" indicator phrases.
- **Logic**: Case-insensitive substring matching. Returns True if any indicator found.
- **Callers**: `GeminiProvider.call_structured()` - checked response_text before JSON parsing. If True, returned None (no result).
- **Input**: `response_text: str`, `not_found_indicators: List[str]`
- **Migration target**: `not_found_validator(indicators)` factory -> `@agent.output_validator`

### validate_array_response(response_json, config, attempt) -> Tuple[bool, List[str]]
- **Purpose**: Validate LLM array response matches input array in length and order.
- **Logic**:
  1. Find first list in response_json where items have `config.match_field` key
  2. Optionally filter empty inputs from input_array
  3. Check length matches
  4. If `allow_reordering=True`: build match_field_map, reorder response to match input order, mutate response_json in-place
  5. If not reordering or reorder fails: sequential comparison with optional `strip_number_prefix`
  6. Returns (is_valid, errors[:5])
- **Callers**: `GeminiProvider.call_structured()` - after validate_structured_output, before Pydantic validation
- **Input**: `response_json: Dict`, `config: ArrayValidationConfig`, `attempt: int`
- **Migration target**: `array_length_validator(expected_length, match_field)` factory -> `@agent.output_validator`
- **NOTE**: The reordering logic mutates response_json. In pydantic-ai, the output is already a Pydantic model, so reordering needs a different approach.

### validate_structured_output(response_json, expected_schema, strict_types) -> Tuple[bool, List[str]]
- **Purpose**: Validate raw JSON dict against a Pydantic JSON schema.
- **Logic**: Manual type checking against JSON schema structure (required fields, type validation, nested objects/arrays).
- **Callers**: `GeminiProvider.call_structured()` - before array validation and Pydantic validation.
- **Migration**: DROP. pydantic-ai validates output against the Pydantic model natively. No custom schema validation needed.

### strip_number_prefix(text) -> str
- **Purpose**: Strip leading "1. ", "2) ", "3- " etc from text.
- **Logic**: Regex `^\d+[\.\)\-\s]+` strip.
- **Callers**: `validate_array_response()` only.
- **Migration**: Keep as utility in validators.py.

### validate_field_value(value, expected_type) -> bool
- **Purpose**: Simple type check for string/number/integer/boolean.
- **Callers**: `validate_structured_output()` only.
- **Migration**: DROP (covered by Pydantic).

### extract_retry_delay_from_error(error) -> Optional[float]
- **Purpose**: Parse retry delay from rate limit error messages.
- **Callers**: `GeminiProvider.call_structured()` retry loop.
- **Migration**: DROP (pydantic-ai handles retries internally).

---

## 2. Surviving Type Definitions (llm_pipeline/types.py)

### ArrayValidationConfig (dataclass)
```python
@dataclass
class ArrayValidationConfig:
    input_array: List[Any]
    match_field: str = "original"
    filter_empty_inputs: bool = False
    allow_reordering: bool = True
    strip_number_prefix: bool = True
```
- **Exported from**: `llm_pipeline/__init__.py`, `llm_pipeline/types.py`
- **Referenced by**: `StepCallParams` (optional field), `StepDeps` (optional field, unused)
- **Tested in**: `tests/test_pipeline.py::TestArrayValidationConfig`
- **Status**: Still a public API type. Used by downstream consumers (logistics-intelligence).

### ValidationContext (dataclass)
```python
@dataclass
class ValidationContext:
    data: Dict[str, Any]
    # __init__(**kwargs), get(), __getitem__, __contains__, to_dict()
```
- **Exported from**: `llm_pipeline/__init__.py`, `llm_pipeline/types.py`
- **Referenced by**: `StepCallParams` (optional field), `StepDeps` (optional field, unused)
- **Tested in**: `tests/test_pipeline.py::TestValidationContext`
- **Status**: Still a public API type. Wraps arbitrary key-value data for Pydantic model validators.
- **Old usage**: `model_validate(data, context=validation_context.to_dict())` passed to Pydantic's validation context.

### StepCallParams (TypedDict)
```python
class StepCallParams(TypedDict, total=False):
    variables: Any
    array_validation: Optional[Any]
    validation_context: Optional[Any]
```
- **Status**: Active. Used as return type of `LLMStep.prepare_calls()`.
- **Note**: `array_validation` and `validation_context` are declared but never read by pipeline.execute() (gap from Task 2).

---

## 3. StepDeps Fields (llm_pipeline/agent_builders.py)

```python
@dataclass
class StepDeps:
    # ... core fields ...
    array_validation: Any | None = None      # line 50
    validation_context: Any | None = None    # line 51
```
- **Status**: Reserved for Task 3. Default None. Never set by pipeline.execute().
- **Tested**: `tests/test_agent_registry_core.py` asserts fields exist and default to None.

---

## 4. Validation Flow in Old Code (Pre-Task-2)

```
Step.prepare_calls()
  -> returns [StepCallParams{variables, array_validation?, validation_context?}]

Step.create_llm_call(**params)
  -> returns ExecuteLLMStepParams{..., array_validation?, validation_context?}

pipeline.execute() loop:
  call_kwargs = step.create_llm_call(**params)
  call_kwargs["provider"] = self._provider
  call_kwargs["prompt_service"] = prompt_service
  instruction = execute_llm_step(**call_kwargs)

execute_llm_step():
  -> provider.call_structured(prompt, system_instruction, result_class,
                              array_validation=array_validation,
                              validation_context=validation_context)
  -> if validation_context: model_validate(data, context=vc.to_dict())

GeminiProvider.call_structured():
  for attempt in range(max_retries):
    1. response = model.generate_content(prompt_with_schema)
    2. if not_found_indicators: check_not_found_response() -> return None
    3. JSON extraction from response text
    4. validate_structured_output(response_json, schema, strict_types)
    5. if array_validation: validate_array_response(response_json, config, attempt)
    6. if validation_context: model_validate(response_json, context=vc.to_dict())
    7. else: result_class(**response_json)
    -> return response_json on success, retry on failure
```

---

## 5. Validation Flow in New Code (Post-Task-2)

```
Step.prepare_calls()
  -> returns [StepCallParams{variables, array_validation?, validation_context?}]

pipeline.execute() loop:
  agent = build_step_agent(step_name, output_type)
  step_deps = StepDeps(session, context, prompt_service, ...)
  # NOTE: array_validation and validation_context from call_params NOT wired to StepDeps

  for params in call_params:
    user_prompt = step.build_user_prompt(variables=params.get("variables"))
    # params["array_validation"] and params["validation_context"] are IGNORED
    run_result = agent.run_sync(user_prompt, deps=step_deps, model=self._model)
    instruction = run_result.output
```

**Gap**: `call_params` fields `array_validation` and `validation_context` are not wired into `StepDeps` before `agent.run_sync()`.

---

## 6. pydantic-ai Output Validator Pattern

From Context7 docs (v1.0.5):

```python
@agent.output_validator
async def validate_output(ctx: RunContext[StepDeps], output: OutputType) -> OutputType:
    # Access deps via ctx.deps
    # Raise ModelRetry("message") to trigger LLM retry
    # Return output if valid
```

Key facts:
- Output validators run AFTER pydantic model validation succeeds
- `ModelRetry` triggers a retry with the error message sent to the LLM
- Validators access deps via `RunContext[StepDeps]`
- Agent's `retries` parameter controls max retry count (default 1, build_step_agent sets 3)
- Validators are registered at agent-build time but execute at call time
- Validators can be sync or async

---

## 7. Migration Mapping

| Old Function | New Implementation | Notes |
|---|---|---|
| `check_not_found_response()` | `not_found_validator(indicators)` factory | Returns output_validator function. Checks string fields for indicator phrases, raises ModelRetry. |
| `validate_array_response()` | `array_length_validator()` factory | Returns output_validator function. Reads ArrayValidationConfig from ctx.deps.array_validation, validates length/order, raises ModelRetry. |
| `validate_structured_output()` | DROP | pydantic-ai handles natively |
| `strip_number_prefix()` | Keep in validators.py | Utility for array validator |
| `validate_field_value()` | DROP | pydantic-ai handles natively |
| `extract_retry_delay_from_error()` | DROP | pydantic-ai handles retries |
| `ValidationContext` usage | `StepDeps.validation_context` via `RunContext[StepDeps]` | Validators access ctx.deps.validation_context |
| `ArrayValidationConfig` | Keep type, move to validators.py or keep in types.py | Used by array_length_validator via StepDeps |

---

## 8. Wiring Points Requiring Changes

### pipeline.py execute()
- **Line 735-744**: StepDeps construction must read `array_validation` and `validation_context` from `params` per-call. Currently built once before call loop.
- **Option A**: Rebuild StepDeps per call inside the `for idx, params` loop (move lines 735-744 inside).
- **Option B**: Update StepDeps fields per-call before `agent.run_sync()` (dataclass is mutable).
- **Line 731-734**: `build_step_agent()` must accept validators list. Validators registered at build time. Agent built once per step, before call loop.

### agent_builders.py build_step_agent()
- Accept optional `validators: list[Callable]` parameter.
- Register each validator with `@agent.output_validator`.

### agent_builders.py StepDeps
- `array_validation` and `validation_context` fields already exist. No structural change needed.

### types.py
- `ArrayValidationConfig`: Keep or move to validators.py.
- `ValidationContext`: Keep or move to validators.py.
- `StepCallParams`: Keep as-is (already declares the optional fields).

### New file: llm_pipeline/validators.py
- `not_found_validator(indicators: list[str])` -> returns validator function
- `array_length_validator()` -> returns validator function (reads config from StepDeps)
- `strip_number_prefix(text: str)` -> utility

---

## 9. Critical Design Considerations

### Array Reordering Side Effect
Old `validate_array_response()` mutated `response_json` in-place to reorder items. In pydantic-ai, the output is already a validated Pydantic model. The output_validator receives the model instance, not raw JSON. Reordering would require:
- Returning a modified model instance from the validator (pydantic-ai output_validators can return modified output)
- Or: converting model to dict, reordering, re-validating

### not_found_indicators Source
Old code: `not_found_indicators` was a param on `LLMProvider.call_structured()`, NOT in `StepCallParams`. The indicators were provider-call-level config, likely hardcoded per consumer step in logistics-intelligence.
New code: Must come from step configuration since validators are registered at agent-build time.
**Options**: (a) StepDefinition field, (b) parameter to build_step_agent, (c) on the step class itself.

### Per-Call vs Per-Step Agent
Agent is built once per step, reused across calls. Output validators are registered at build time. But StepDeps (with array_validation) changes per call. This works because validators read StepDeps at call time via RunContext, not at registration time.

### not_found on Output Model vs Raw Text
Old `check_not_found_response()` checked raw response TEXT before JSON parsing. In pydantic-ai, output_validators receive the parsed Pydantic model, not raw text. The validator would need to check string fields on the model for indicator phrases. This is a semantic change: checking model field values vs. raw response text.

---

## 10. Files Inventory

| File | Status | Action |
|---|---|---|
| `llm_pipeline/llm/validation.py` | Deleted (Task 2) | No action |
| `llm_pipeline/types.py` | Exists | Keep ArrayValidationConfig, ValidationContext, StepCallParams |
| `llm_pipeline/agent_builders.py` | Exists | Update build_step_agent to accept validators |
| `llm_pipeline/pipeline.py` | Exists | Wire array_validation/validation_context into StepDeps per-call |
| `llm_pipeline/validators.py` | Does not exist | CREATE: validator factories + strip_number_prefix |
| `llm_pipeline/__init__.py` | Exists | Export new validators |
| `tests/test_pipeline.py` | Exists | TestArrayValidationConfig, TestValidationContext still passing |
| `tests/test_agent_registry_core.py` | Exists | StepDeps field existence tests still passing |

---

## 11. Questions / Ambiguities

1. **not_found_indicators source**: Where do indicators come from in the new design? The factory `not_found_validator(indicators)` bakes them into the closure at agent-build time. Should they be:
   (a) A field on StepDefinition (strategy.py)
   (b) A parameter to build_step_agent (passed by pipeline.execute())
   (c) Declared on the LLMStep subclass itself
   (d) Part of the step's prepare_calls() return (but this conflicts with per-step agent build)

2. **Array reordering in output_validator**: Old code mutated raw JSON dict to reorder. Output validators receive Pydantic model instances. Should the array_length_validator:
   (a) Return a modified model with reordered arrays (output_validators can return modified output)
   (b) Only validate length/order and raise ModelRetry if wrong (let LLM fix ordering)
   (c) Both: validate and reorder without ModelRetry if reordering succeeds

3. **not_found semantic shift**: Old code checked raw response text. Output validator checks parsed model fields. Should not_found_validator:
   (a) Check all string fields on the model
   (b) Check specific fields (configurable via factory params)
   (c) Check model's `notes` field only (if using LLMResultMixin)

4. **ValidationContext as Pydantic context**: Old code passed `validation_context.to_dict()` to `model_validate(data, context=...)` for Pydantic field-level validators. pydantic-ai runs Pydantic validation before output_validators. If downstream consumers have Pydantic field validators that use `info.context`, how do they get the context data? Does pydantic-ai pass context through, or do we need a different approach?
