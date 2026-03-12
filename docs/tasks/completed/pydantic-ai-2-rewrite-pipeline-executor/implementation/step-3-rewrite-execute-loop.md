# IMPLEMENTATION - STEP 3: REWRITE EXECUTE LOOP
**Status:** completed

## Summary
Rewrote PipelineConfig constructor and execute() loop in pipeline.py to use pydantic-ai agent.run_sync() instead of legacy execute_llm_step(). Replaced provider= param with model: str. Added LLMCallStarting/LLMCallCompleted event emission around agent calls. Updated _execute_with_consensus call site to pass new params (agent, user_prompt, step_deps, output_type).

## Files
**Created:** none
**Modified:** llm_pipeline/pipeline.py
**Deleted:** none

## Changes
### File: `llm_pipeline/pipeline.py`

Removed LLMProvider import from TYPE_CHECKING block.
```
# Before
from llm_pipeline.llm.provider import LLMProvider

# After
(removed)
```

Replaced provider= constructor param with model: str (required positional).
```
# Before
def __init__(self, strategies=None, session=None, engine=None, provider=None, ...):
    self._provider = provider

# After
def __init__(self, model: str, strategies=None, session=None, engine=None, ...):
    self._model = model
```

Replaced execute() imports and validation: execute_llm_step -> build_step_agent/StepDeps/UnexpectedModelBehavior, provider None check -> AGENT_REGISTRY check.
```
# Before
from llm_pipeline.llm.executor import execute_llm_step
if self._provider is None:
    raise ValueError("LLMProvider required.")

# After
from llm_pipeline.agent_builders import build_step_agent, StepDeps
from pydantic_ai import UnexpectedModelBehavior
if self.AGENT_REGISTRY is None:
    raise ValueError(f"{self.__class__.__name__} must specify agent_registry= parameter.")
```

Replaced per-step create_llm_call()+execute_llm_step() block with agent-based flow: build agent once per step, build StepDeps, build_user_prompt, resolve system prompt for event, agent.run_sync() with UnexpectedModelBehavior -> create_failure() fallback.

Added LLMCallStarting/LLMCallCompleted event imports and emission around agent.run_sync() calls.

Updated _execute_with_consensus call site to pass (agent, user_prompt, step_deps, output_type) instead of call_kwargs.

Replaced model_name = getattr(self._provider, 'model_name', None) with self._model.

## Decisions
### System prompt resolution for LLMCallStarting event
**Choice:** Mirror _inject_system_prompt logic: check variable_resolver, call get_system_prompt() or get_prompt() as appropriate.
**Rationale:** Per PLAN.md architecture decision. pydantic-ai resolves system prompts internally during run_sync() so we duplicate resolution for the event.

### LLMCallCompleted.attempt_count
**Choice:** Set attempt_count=1 for non-consensus calls.
**Rationale:** pydantic-ai handles retries internally. Per VALIDATED_RESEARCH.md.

### LLMCallCompleted.raw_response
**Choice:** Set raw_response=None.
**Rationale:** pydantic-ai does not expose raw response text directly from run_sync().

## Verification
[x] Syntax check passes (ast.parse)
[x] No remaining references to _provider, execute_llm_step, LLMProvider, create_llm_call in pipeline.py
[x] LLMCallStarting and LLMCallCompleted imported and emitted
[x] _execute_with_consensus call site passes new params (agent, user_prompt, step_deps, output_type)
[x] model_name in _save_step_state uses self._model
[x] Constructor signature: model: str as required first param
