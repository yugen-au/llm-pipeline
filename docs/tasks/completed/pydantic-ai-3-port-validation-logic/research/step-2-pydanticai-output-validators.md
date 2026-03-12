# Step 2: pydantic.ai Output Validator System Research

## Overview

Research into pydantic.ai (v1.62.0, installed; docs from v1.0.5 via Context7) output validator system for implementing validator factories that replace custom validation logic deleted in Task 2.

---

## 1. Agent.output_validator() API

### Method Signature
```python
def output_validator(
    self, func: OutputValidatorFunc[AgentDepsT, OutputDataT], /
) -> OutputValidatorFunc[AgentDepsT, OutputDataT]:
```

### Internal Storage
```python
# In Agent.__init__:
self._output_validators = []

# In output_validator():
self._output_validators.append(OutputValidator[AgentDepsT, Any](func))
return func
```

### Key Behaviors
- Works as **both** `@decorator` and **direct method call** (`agent.output_validator(fn)`)
- Multiple validators can be stacked; appended to list in registration order
- Returns the original function (pass-through), enabling decorator chaining
- Validators execute in registration order during agent.run_sync()

### Verified Programmatic Registration
```python
agent = Agent('test', output_type=str, defer_model_check=True)

def my_validator(output: str) -> str:
    if 'bad' in output:
        raise ModelRetry('bad output')
    return output

agent.output_validator(my_validator)  # works without @decorator syntax
len(agent._output_validators)  # 1
```

---

## 2. OutputValidator Internals

```python
@dataclass
class OutputValidator(Generic[AgentDepsT, OutputDataT_inv]):
    function: OutputValidatorFunc[AgentDepsT, OutputDataT_inv]
    _takes_ctx: bool = field(init=False)  # auto-detected via inspect
    _is_async: bool = field(init=False)   # auto-detected

    def __post_init__(self):
        self._takes_ctx = len(inspect.signature(self.function).parameters) > 1
        self._is_async = _utils.is_async_callable(self.function)
```

### Context Detection
- **1 param** `(output)`: no RunContext injected
- **2 params** `(ctx, output)`: RunContext injected as first arg
- Detection is automatic via `inspect.signature().parameters` count

### Sync vs Async
- Sync validators run via `run_in_executor` (thread pool)
- Async validators awaited directly
- Both work with `agent.run_sync()` -- sync callers can register async validators

### Validator Execution Flow
```
agent.run_sync(prompt, deps=step_deps)
  -> LLM generates response
  -> Pydantic model validation (schema enforcement)
  -> For each validator in _output_validators:
       result = validator.validate(output, run_context)
       If ModelRetry raised -> send retry prompt to LLM
       If returns modified output -> use as new output
  -> Return final output
```

---

## 3. ModelRetry Exception

```python
from pydantic_ai import ModelRetry

raise ModelRetry("Error message sent to LLM for retry")
```

### Behavior
- Message becomes `RetryPromptPart` sent back to LLM
- LLM sees the error message and generates a new response
- Retry count limited by `_max_result_retries` on agent
- On max retries exceeded, raises `UnexpectedModelBehavior`

### Retry Configuration
```python
agent = Agent(
    model='...',
    retries=3,              # default for tools AND output validators
    output_retries=None,    # override for output validators only (defaults to retries)
)
```

Current `build_step_agent()` sets `retries=3`. This means output validators get 3 retries by default. Can be overridden per-agent via `output_retries` param.

### Exception Chain
```
ModelRetry raised in validator
  -> Caught by OutputValidator.validate()
  -> Wrapped in ToolRetryError(RetryPromptPart)
  -> Agent retry loop sends RetryPromptPart back to LLM
  -> LLM generates new response
  -> Validation cycle repeats
```

---

## 4. RunContext[StepDeps] Pattern

```python
from pydantic_ai import RunContext

def validator(ctx: RunContext[StepDeps], output: OutputType) -> OutputType:
    # Access dependencies:
    config = ctx.deps.array_validation    # ArrayValidationConfig | None
    vc = ctx.deps.validation_context      # ValidationContext | None
    session = ctx.deps.session            # Session
    pipeline_ctx = ctx.deps.pipeline_context  # dict

    # Raise on failure:
    raise ModelRetry("Fix this: ...")

    # Return (possibly modified) output on success:
    return output
```

### What RunContext Provides
- `ctx.deps` - the StepDeps instance passed to `agent.run_sync(deps=...)`
- `ctx.retry` - current retry count (int)
- `ctx.tool_name` - name of the output tool (may be None for output validators)
- `ctx.messages` - message history so far

### Important: deps are runtime, not build-time
Validators are registered on agent at build time, but `ctx.deps` is the StepDeps passed at `run_sync()` call time. This means:
- Agent built once per step (before call loop)
- Validators registered once per step
- StepDeps can differ per call (different array_validation, validation_context)
- Validators read per-call config from deps at execution time

---

## 5. Validator Factory Pattern

### Pattern A: Static config baked into closure

```python
def not_found_validator(indicators: list[str]):
    """Factory: config baked into closure at agent-build time."""
    def validator(ctx: RunContext[StepDeps], output: Any) -> Any:
        # indicators captured from enclosing scope
        for field_name, value in _string_fields(output):
            if any(ind.lower() in str(value).lower() for ind in indicators):
                raise ModelRetry(f"Response contains 'not found' indicator in {field_name}")
        return output
    return validator
```

- Config is **static** per agent instance
- Good for: not_found_indicators (same indicators for all calls of a step)

### Pattern B: Dynamic config from deps at runtime

```python
def array_length_validator():
    """Factory: config read from deps at call time."""
    def validator(ctx: RunContext[StepDeps], output: Any) -> Any:
        config = ctx.deps.array_validation
        if config is None:
            return output  # no array validation for this call
        # validate using config
        return output
    return validator
```

- Config is **dynamic** per `run_sync()` call
- Good for: array_validation (different config per call_params from prepare_calls)

### Pattern C: Hybrid (static + dynamic)

```python
def array_length_validator(match_field: str = "original"):
    """Factory: some config static, some from deps."""
    def validator(ctx: RunContext[StepDeps], output: Any) -> Any:
        config = ctx.deps.array_validation
        if config is None:
            return output
        # match_field from closure, input_array from deps
        ...
    return validator
```

### Verified All Patterns Work
```
$ python -c "... test code ..."
Validators: 2
Both factories registered successfully
```

---

## 6. Registration in build_step_agent()

### Current Signature
```python
def build_step_agent(
    step_name: str,
    output_type: type,
    model: str | None = None,
    system_instruction_key: str | None = None,
    retries: int = 3,
    model_settings: Any | None = None,
) -> Agent[StepDeps, Any]:
```

### Proposed Extension
```python
def build_step_agent(
    step_name: str,
    output_type: type,
    model: str | None = None,
    system_instruction_key: str | None = None,
    retries: int = 3,
    model_settings: Any | None = None,
    validators: list[Callable] | None = None,   # NEW
) -> Agent[StepDeps, Any]:
    ...
    agent = Agent(...)

    @agent.instructions
    def _inject_system_prompt(ctx): ...

    # Register output validators
    if validators:
        for validator_fn in validators:
            agent.output_validator(validator_fn)

    return agent
```

### Registration Order
Validators execute in registration order. Recommendation:
1. not_found_validator first (cheap string check, fast rejection)
2. array_length_validator second (more complex, needs array traversal)

---

## 7. Composing Multiple Validators on a Single Agent

### Multiple Registration
```python
agent.output_validator(not_found_validator(['not found', 'no data']))
agent.output_validator(array_length_validator())
# Both validators run in sequence on every output
```

### Execution Semantics
- Validators run sequentially in registration order
- If validator 1 passes, output passes to validator 2
- If any validator raises ModelRetry, LLM retries and ALL validators re-run on new output
- If a validator returns modified output, the modified version passes to next validator
- All validators must pass for output to be accepted

### No-op Pattern
Validators that don't apply to a particular call should return output unchanged:
```python
def array_length_validator():
    def validator(ctx: RunContext[StepDeps], output: Any) -> Any:
        if ctx.deps.array_validation is None:
            return output  # no-op for this call
        ...
    return validator
```

This is safe: the validator is registered at agent-build time but conditionally executes based on per-call deps.

---

## 8. Agent.__init__ validation_context Parameter

### Discovery
pydantic-ai Agent has a `validation_context` constructor parameter:

```python
agent = Agent(
    model='...',
    validation_context=my_context,  # passed to Pydantic model validators
)
```

This is **Pydantic's** validation context (for `info.context` in Pydantic field validators), NOT our `ValidationContext` class. It flows through to `model.model_validate(data, context=validation_context)`.

### Relevance to Task 3
Step 1 research identified question #4: "If downstream consumers have Pydantic field validators that use `info.context`, how do they get the context data?"

**Answer**: pydantic-ai Agent supports `validation_context` param. It can be:
- A static value: `validation_context={"key": "value"}`
- A callable: `validation_context=lambda ctx: ctx.deps.validation_context.to_dict()`

The callable form receives `RunContext[StepDeps]`, enabling dynamic context per call:
```python
agent = Agent(
    model='...',
    validation_context=lambda ctx: (
        ctx.deps.validation_context.to_dict()
        if ctx.deps.validation_context
        else None
    ),
)
```

This resolves the semantic gap: `ValidationContext` data flows to Pydantic field validators via the Agent's `validation_context` param, while output_validators handle the not_found and array_length checks.

---

## 9. Per-Call StepDeps Wiring

### Current Code (pipeline.py lines 730-798)
```python
# Agent built once per step (correct - validators registered here)
agent = build_step_agent(step_name, output_type)

# StepDeps built once per step (NEEDS FIX - must be per-call)
step_deps = StepDeps(session, pipeline_context, prompt_service, ...)

for idx, params in enumerate(call_params):
    # params may contain array_validation, validation_context
    # but step_deps doesn't receive them
    run_result = agent.run_sync(user_prompt, deps=step_deps, model=self._model)
```

### Required Change
```python
# Agent built once per step (unchanged)
agent = build_step_agent(step_name, output_type, validators=[...])

for idx, params in enumerate(call_params):
    # StepDeps built per call, populated from params
    step_deps = StepDeps(
        session=self.session,
        pipeline_context=self._context,
        prompt_service=prompt_service,
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
        step_name=step.step_name,
        event_emitter=self._event_emitter,
        variable_resolver=self._variable_resolver,
        array_validation=params.get("array_validation"),
        validation_context=params.get("validation_context"),
    )
    run_result = agent.run_sync(user_prompt, deps=step_deps, model=self._model)
```

---

## 10. Semantic Differences from Old Validation

### not_found: raw text vs model fields
- **Old**: `check_not_found_response(response_text, indicators)` checked raw LLM text before JSON parsing
- **New**: output_validator receives parsed Pydantic model. Must check model's string field values.
- **Impact**: If LLM wraps "not found" in JSON structure like `{"notes": "Data not found"}`, new validator catches it. If "not found" was in non-JSON text around the response, old code caught it but new code won't (pydantic-ai strips non-JSON parts).
- **Acceptable**: pydantic-ai's structured output means the LLM MUST return valid JSON. "not found" phrasing will appear in model fields if the LLM uses it.

### array_validation: raw dict vs Pydantic model
- **Old**: `validate_array_response(response_json, config, attempt)` operated on raw dict, mutated in-place for reordering
- **New**: output_validator receives Pydantic model instance. Reordering requires:
  1. Find list fields on the model
  2. Check items for match_field
  3. Reorder and reconstruct model: `output.model_copy(update={field_name: reordered_list})`
- **Impact**: `model_copy(update=...)` creates new model instance (immutable pattern vs. old mutation). Cleaner.

### validate_structured_output: DROP
- **Old**: Manual JSON schema validation before Pydantic
- **New**: pydantic-ai validates against Pydantic model natively. No custom schema validation needed.
- **Impact**: None. Redundant validation removed.

---

## 11. Summary of Findings

| Aspect | Finding |
|---|---|
| Registration | `agent.output_validator(fn)` works programmatically and as decorator |
| Multiple validators | Stack via repeated calls; execute in registration order |
| Retry mechanism | `raise ModelRetry("message")` triggers LLM retry with message |
| Max retries | Controlled by `retries` (default 3 in build_step_agent) or `output_retries` |
| Context access | `RunContext[StepDeps]` provides deps at call time via `ctx.deps` |
| Factory pattern | Closures work perfectly; capture static config + read dynamic config from deps |
| Sync/async | Both supported; auto-detected by parameter count |
| Pydantic validation_context | Agent constructor param; supports callable `lambda ctx: ...` for dynamic context |
| Per-call deps | StepDeps must move inside per-call loop to populate array_validation/validation_context |
| Reordering | Use `model_copy(update={...})` to return modified model from validator |

---

## 12. Answers to Step 1 Questions

### Q1: not_found_indicators source
**Answer**: Factory pattern `not_found_validator(indicators)` bakes indicators into closure. Indicators are passed to `build_step_agent()` by the pipeline execution code or step definition. Since this is a reusable library, the downstream consumer (logistics-intelligence) provides indicators when defining their step or strategy. The factory is a public API tool; llm-pipeline does not need to know the indicators itself.

### Q2: Array reordering in output_validator
**Answer**: Output validators CAN return modified output. Use `model_copy(update={field_name: reordered_list})` to produce a new model with reordered arrays. The validator should:
1. Validate length (raise ModelRetry if mismatch)
2. If allow_reordering and order differs: reorder and return modified model
3. If not allow_reordering and order differs: raise ModelRetry

### Q3: not_found semantic shift
**Answer**: Check all string fields on the model instance. Use `model.model_dump()` to get dict, iterate values, check strings. This is the only viable approach since output_validators don't have access to raw response text.

### Q4: ValidationContext as Pydantic context
**Answer**: pydantic-ai Agent supports `validation_context` constructor param. Use callable form to pass `ctx.deps.validation_context.to_dict()` dynamically. This flows into Pydantic's `info.context` during model validation, preserving the old behavior.

---

## 13. Remaining Questions for CEO

1. **ArrayValidationConfig / ValidationContext location**: These are currently public API exports from `types.py` and `__init__.py`. Task description says "Delete schemas/validation.py and move ArrayValidationConfig if still needed to validators.py or StepDeps." Since `schemas/validation.py` doesn't exist (it's `types.py`), should these types:
   (a) Stay in `types.py` (backward compatible, no import changes for downstream consumers)
   (b) Move to `validators.py` (breaking change, requires import updates)
   (c) Stay in `types.py` with re-exports from `validators.py`
