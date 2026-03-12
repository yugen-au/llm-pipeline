# IMPLEMENTATION - STEP 3: INSTRUMENT= IN BUILD_STEP_AGENT
**Status:** completed

## Summary
Added `instrument: Any | None = None` parameter to `build_step_agent()` for per-agent OTel instrumentation. Uses conditional kwargs dict pattern to pass `instrument=` to `Agent()` only when not None.

## Files
**Created:** none
**Modified:** `llm_pipeline/agent_builders.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/agent_builders.py`
Added `InstrumentationSettings` to TYPE_CHECKING imports, added `instrument` parameter to signature, refactored Agent construction to use conditional kwargs dict.

```python
# Before (TYPE_CHECKING)
if TYPE_CHECKING:
    from pydantic_ai import Agent, RunContext

# After (TYPE_CHECKING)
if TYPE_CHECKING:
    from pydantic_ai import Agent, InstrumentationSettings, RunContext
```

```python
# Before (signature)
def build_step_agent(
    step_name: str,
    output_type: type,
    model: str | None = None,
    system_instruction_key: str | None = None,
    retries: int = 3,
    model_settings: Any | None = None,
    validators: list[Any] | None = None,
) -> Agent[StepDeps, Any]:

# After (signature)
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

```python
# Before (Agent construction)
agent: Agent[StepDeps, Any] = Agent(
    model=model,
    output_type=output_type,
    deps_type=StepDeps,
    name=step_name,
    retries=retries,
    model_settings=model_settings,
    defer_model_check=True,
    validation_context=lambda ctx: ctx.deps.validation_context,
)

# After (Agent construction)
agent_kwargs: dict[str, Any] = dict(
    model=model,
    output_type=output_type,
    deps_type=StepDeps,
    name=step_name,
    retries=retries,
    model_settings=model_settings,
    defer_model_check=True,
    validation_context=lambda ctx: ctx.deps.validation_context,
)
if instrument is not None:
    agent_kwargs["instrument"] = instrument

agent: Agent[StepDeps, Any] = Agent(**agent_kwargs)
```

## Decisions
### Import path for InstrumentationSettings
**Choice:** `from pydantic_ai import InstrumentationSettings` (top-level re-export)
**Rationale:** Context7 docs for pydantic-ai v1.0.5 confirm `InstrumentationSettings` is importable from `pydantic_ai` directly. Placed under `TYPE_CHECKING` to avoid runtime import (OTel deps may not be installed).

### Conditional kwargs dict pattern
**Choice:** Build kwargs dict, conditionally add `instrument` key, then `Agent(**agent_kwargs)`
**Rationale:** Avoids passing `instrument=None` to Agent constructor which could trigger unexpected behavior. Matches plan specification exactly.

### Parameter type annotation
**Choice:** `instrument: Any | None = None` (not `InstrumentationSettings | None`)
**Rationale:** `InstrumentationSettings` only available under TYPE_CHECKING. Using `Any` at runtime avoids import errors when OTel deps not installed. Consistent with existing codebase pattern (e.g. `model_settings: Any | None`).

## Verification
[x] `InstrumentationSettings` imported under TYPE_CHECKING only
[x] `instrument` parameter added after `validators` in signature
[x] Conditional kwargs dict pattern used (instrument not passed when None)
[x] Docstring updated with instrument parameter documentation
[x] All 588 existing tests pass (1 pre-existing UI test failure unrelated)
[x] No runtime import of InstrumentationSettings
