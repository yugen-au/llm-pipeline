# IMPLEMENTATION - STEP 4: UPDATE PIPELINE.PY
**Status:** completed

## Summary
Updated pipeline.py to import validators, build validators list per step, pass to build_step_agent, and rebuild StepDeps per-call inside the loop so per-call params (array_validation, validation_context) flow into deps correctly.

## Files
**Created:** none
**Modified:** llm_pipeline/pipeline.py
**Deleted:** none

## Changes
### File: `llm_pipeline/pipeline.py`

**Import added** (line 464, inside execute method's lazy imports):
```python
# Before
from llm_pipeline.agent_builders import build_step_agent, StepDeps
from llm_pipeline.prompts.service import PromptService
from llm_pipeline.state import PipelineRun
from pydantic_ai import UnexpectedModelBehavior

# After
from llm_pipeline.agent_builders import build_step_agent, StepDeps
from llm_pipeline.prompts.service import PromptService
from llm_pipeline.state import PipelineRun
from llm_pipeline.validators import not_found_validator, array_length_validator
from pydantic_ai import UnexpectedModelBehavior
```

**Validators list built before agent** (lines 733-743):
```python
# Before
agent = build_step_agent(
    step_name=step.step_name,
    output_type=output_type,
)

# After
step_validators = [
    not_found_validator(step_def.not_found_indicators),
    array_length_validator(),
]
agent = build_step_agent(
    step_name=step.step_name,
    output_type=output_type,
    validators=step_validators,
)
```

**StepDeps moved inside for loop** (lines 746-758):
```python
# Before: StepDeps built once before the loop (no array_validation/validation_context)
step_deps = StepDeps(
    session=self.session,
    pipeline_context=self._context,
    prompt_service=prompt_service,
    run_id=self.run_id,
    pipeline_name=self.pipeline_name,
    step_name=step.step_name,
    event_emitter=self._event_emitter,
    variable_resolver=self._variable_resolver,
)
for idx, params in enumerate(call_params):

# After: StepDeps rebuilt per-call with per-call params
for idx, params in enumerate(call_params):
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

## Decisions
### Validators always registered
**Choice:** Both not_found_validator and array_length_validator registered for every step
**Rationale:** Both are no-ops when not applicable (not_found passes non-string output, array_length is no-op when deps.array_validation is None). Simpler than conditional registration.

### StepDeps per-call, agent per-step
**Choice:** Agent built once before loop, StepDeps rebuilt each iteration
**Rationale:** CEO decision. Agent is expensive to build (prompt registration etc). StepDeps is cheap dataclass. Per-call params must flow without shared mutable state.

## Verification
[x] Import added inside execute method's lazy import block (avoids circular imports)
[x] step_validators built after step_def resolved, before build_step_agent
[x] validators=step_validators passed to build_step_agent
[x] StepDeps construction moved inside for loop
[x] array_validation and validation_context populated from params.get()
[x] _execute_with_consensus receives per-call step_deps (already parameterized)
[x] 583 tests pass, 1 pre-existing UI test failure (unrelated router prefix)
