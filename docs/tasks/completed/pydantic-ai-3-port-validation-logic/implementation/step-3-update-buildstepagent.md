# IMPLEMENTATION - STEP 3: UPDATE BUILD_STEP_AGENT
**Status:** completed

## Summary
Updated build_step_agent() to accept validators param, wire validation_context lambda into Agent constructor, and register validators via agent.output_validator() loop.

## Files
**Created:** none
**Modified:** llm_pipeline/agent_builders.py
**Deleted:** none

## Changes
### File: `llm_pipeline/agent_builders.py`
Added validators param, validation_context lambda, and validator registration loop.

```
# Before
def build_step_agent(
    step_name: str,
    output_type: type,
    model: str | None = None,
    system_instruction_key: str | None = None,
    retries: int = 3,
    model_settings: Any | None = None,
) -> Agent[StepDeps, Any]:

    agent: Agent[StepDeps, Any] = Agent(
        model=model,
        output_type=output_type,
        deps_type=StepDeps,
        name=step_name,
        retries=retries,
        model_settings=model_settings,
        defer_model_check=True,
    )
    # ... instructions block ...
    return agent

# After
def build_step_agent(
    step_name: str,
    output_type: type,
    model: str | None = None,
    system_instruction_key: str | None = None,
    retries: int = 3,
    model_settings: Any | None = None,
    validators: list[Any] | None = None,
) -> Agent[StepDeps, Any]:

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
    # ... instructions block ...

    # Register output validators (from validator factories)
    for v in (validators or []):
        agent.output_validator(v)

    return agent
```

## Decisions
### validation_context as lambda
**Choice:** `validation_context=lambda ctx: ctx.deps.validation_context` passed to Agent constructor
**Rationale:** Confirmed via Context7 docs and pydantic-ai source that Agent accepts validation_context as static value or Callable[[RunContext], Any]. Lambda defers resolution to run_sync() time, reading per-call StepDeps.validation_context. This enables Pydantic field_validators in output types to access ValidationContext via info.context.

### Programmatic output_validator registration
**Choice:** `agent.output_validator(v)` in a loop after instructions block
**Rationale:** Confirmed via Context7 docs that agent.output_validator() works both as decorator and programmatic registration. Loop preserves caller-specified order (not_found first, array_length second).

## Verification
[x] validators param added to build_step_agent signature
[x] validation_context lambda passed to Agent constructor
[x] Validator loop registers after instructions block
[x] Docstring updated with validators param and validation_context docs
[x] All 48 existing tests pass (test_agent_registry_core.py)
[x] No new fields added to StepDeps (test_field_count unaffected)

## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
[x] Stale comments in StepDeps referencing "reserved for Task 3" / "unused in Task 2" (MEDIUM)

### Changes Made
#### File: `llm_pipeline/agent_builders.py`
Updated docstring and inline comments for array_validation/validation_context fields.

```
# Before (docstring lines 31-32)
    Note: array_validation and validation_context are reserved for
    Task 3 output_validators. Unused in Task 2, default to None.

# After
    Validation fields (array_validation, validation_context) are per-call
    config passed to output validators via ctx.deps. Default to None
    when the step has no validation requirements.

# Before (inline comment line 49)
    # Forward-compat: Task 3 output_validators (unused in Task 2)
    array_validation: Any | None = None
    validation_context: Any | None = None

# After
    # Per-call validation config, read by output validators via ctx.deps
    array_validation: Any | None = None  # ArrayValidationConfig
    validation_context: Any | None = None  # ValidationContext for Pydantic field_validators
```

### Verification
[x] All 53 tests pass (test_agent_registry_core.py)
[x] No functional changes, comment-only fix
