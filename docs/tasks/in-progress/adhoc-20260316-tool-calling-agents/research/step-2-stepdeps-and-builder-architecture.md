# Step 2: StepDeps and build_step_agent() Architecture

## StepDeps Dataclass

**File:** `llm_pipeline/agent_builders.py` (lines 22-52)

```python
@dataclass
class StepDeps:
    # Core pipeline deps
    session: Any              # Session (sqlmodel)
    pipeline_context: dict[str, Any]
    prompt_service: Any       # PromptService

    # Execution metadata
    run_id: str
    pipeline_name: str
    step_name: str

    # Optional deps
    event_emitter: Any | None = None       # PipelineEventEmitter
    variable_resolver: Any | None = None   # VariableResolver

    # Per-call validation config
    array_validation: Any | None = None    # ArrayValidationConfig
    validation_context: Any | None = None  # ValidationContext
```

**Purpose:** Dependency injection container for pydantic-ai agents. Typed as `Agent[StepDeps, Any]`. Tools/instructions/validators access deps via `RunContext[StepDeps]`.

**Key design notes:**
- Uses `Any` for runtime types to avoid circular imports; real types under `TYPE_CHECKING`
- Per-call fields (`array_validation`, `validation_context`) are rebuilt each call iteration
- Exported in `__init__.py` as public API

## build_step_agent() Function

**File:** `llm_pipeline/agent_builders.py` (lines 55-152)

```python
def build_step_agent(
    step_name: str,
    output_type: type,
    model: str | None = None,
    system_instruction_key: str | None = None,
    retries: int = 3,
    model_settings: Any | None = None,
    validators: list[Any] | None = None,
    instrument: Any | None = None,
) -> Agent[StepDeps, Any]:
```

**Construction flow:**
1. Builds `agent_kwargs` dict: model, output_type, deps_type=StepDeps, name, retries, model_settings, defer_model_check=True, validation_context lambda
2. Optionally adds `instrument` for OTel
3. Creates `Agent(**agent_kwargs)`
4. Registers `@agent.instructions` for dynamic system prompt resolution via PromptService
5. Registers output validators from `validators` list via `agent.output_validator(v)`
6. Returns `Agent[StepDeps, Any]`

**Notable:** No `tools` parameter exists. No tool registration logic.

## StepDeps Construction Site

**File:** `llm_pipeline/pipeline.py` (lines 759-770)

**Single construction site** in entire codebase:

```python
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
```

**Context:** Inside `_execute_steps()` method, within `for idx, params in enumerate(call_params)` loop. StepDeps is rebuilt per-call so per-call params (array_validation, validation_context) flow correctly.

## Agent Invocation Sites

Two `run_sync` call sites, both pass `deps=step_deps`:

1. **Normal path** (pipeline.py:829): `agent.run_sync(user_prompt, deps=step_deps, model=self._model)`
2. **Consensus path** (pipeline.py:1256): `agent.run_sync(user_prompt, deps=step_deps, model=self._model)`

Both are identical in how they pass deps. pydantic-ai's `run_sync()` handles tool-call loops internally -- no executor changes needed for tool-calling agents.

## StepCallParams TypedDict

**File:** `llm_pipeline/types.py` (lines 55-68)

```python
class StepCallParams(TypedDict, total=False):
    variables: Any
    array_validation: Optional[Any]
    validation_context: Optional[Any]
```

Returned by `LLMStep.prepare_calls()`. Per-call params thread through to StepDeps construction. This is the natural place to add `extra_deps` for domain-specific deps.

## build_step_agent() Call Site

**File:** `llm_pipeline/pipeline.py` (lines 745-750)

```python
agent = build_step_agent(
    step_name=step.step_name,
    output_type=output_type,
    validators=step_validators,
    instrument=self._instrumentation_settings,
)
```

Built once per step, reused across all calls and consensus iterations.

## Data Flow Summary

```
LLMStep.prepare_calls()
  -> List[StepCallParams]        # per-call params (variables, array_validation, validation_context)
     -> StepDeps(...)            # rebuilt per-call from params + pipeline state
        -> agent.run_sync(deps=step_deps)
           -> RunContext[StepDeps]
              -> @agent.instructions reads ctx.deps.prompt_service
              -> @agent.tool reads ctx.deps.* (future: ctx.deps.extra["key"])
              -> @agent.output_validator reads ctx.deps.array_validation
```

## Extension Plan for Tool-Calling

### 1. Add `extra` to StepDeps

```python
extra: dict[str, Any] = field(default_factory=dict)
```

- Backward-compatible: defaults to empty dict
- Tools access domain deps via `ctx.deps.extra["workbook_context"]`
- No existing code breaks (single construction site doesn't pass it)

### 2. Add `tools` to build_step_agent()

```python
tools: list[Any] | None = None
```

- Pass directly to `Agent()` constructor as `tools=[...]`
- pydantic-ai accepts `list[Callable | Tool]` in constructor
- Simpler than post-construction `@agent.tool` registration (aligns with existing kwargs pattern)

### 3. Thread extra_deps through StepCallParams

```python
class StepCallParams(TypedDict, total=False):
    variables: Any
    array_validation: Optional[Any]
    validation_context: Optional[Any]
    extra_deps: Optional[dict[str, Any]]  # NEW
```

- `prepare_calls()` can populate domain-specific deps per-call
- Pipeline construction site: `extra=params.get("extra_deps", {})`

### 4. No executor/run_sync changes

- pydantic-ai handles tool-call loops internally in `run_sync()`
- Token usage from tool calls included in `RunResult.usage()`
- Both normal and consensus paths work unchanged

## Backward Compatibility

All changes are additive with defaults:
- `StepDeps.extra` defaults to `{}`
- `build_step_agent(tools=...)` defaults to `None`
- `StepCallParams.extra_deps` is optional (total=False)
- Existing call sites pass no new params -- behavior unchanged
