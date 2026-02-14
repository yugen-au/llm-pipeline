# IMPLEMENTATION - STEP 2: PIPELINE EVENTS
**Status:** completed

## Summary
Modified pipeline.py to emit LLMCallPrepared after prepare_calls() and inject event context (event_emitter, run_id, pipeline_name, step_name, call_index) into call_kwargs so executor.py can emit LLMCallStarting/LLMCallCompleted.

## Files
**Created:** none
**Modified:** llm_pipeline/pipeline.py
**Deleted:** none

## Changes
### File: `llm_pipeline/pipeline.py`
Added LLMCallPrepared to imports, emitted it after prepare_calls(), changed for-loop to enumerate, injected event context into call_kwargs.

```
# Before (import)
from llm_pipeline.events.types import (
    PipelineStarted, PipelineCompleted, PipelineError,
    StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted,
)

# After (import)
from llm_pipeline.events.types import (
    PipelineStarted, PipelineCompleted, PipelineError,
    StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted,
    LLMCallPrepared,
)
```

```
# Before (for-loop)
call_params = step.prepare_calls()
instructions = []

for params in call_params:
    call_kwargs = step.create_llm_call(**params)
    call_kwargs["provider"] = self._provider
    call_kwargs["prompt_service"] = prompt_service

# After (LLMCallPrepared emission + enumerate + event context injection)
call_params = step.prepare_calls()
instructions = []

if self._event_emitter:
    self._emit(LLMCallPrepared(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
        step_name=step.step_name,
        call_count=len(call_params),
        system_key=step.system_instruction_key,
        user_key=step.user_prompt_key,
    ))

for idx, params in enumerate(call_params):
    call_kwargs = step.create_llm_call(**params)
    call_kwargs["provider"] = self._provider
    call_kwargs["prompt_service"] = prompt_service

    if self._event_emitter:
        call_kwargs["event_emitter"] = self._event_emitter
        call_kwargs["run_id"] = self.run_id
        call_kwargs["pipeline_name"] = self.pipeline_name
        call_kwargs["step_name"] = step.step_name
        call_kwargs["call_index"] = idx
```

## Decisions
None - all decisions pre-made in PLAN.md.

## Verification
- [x] LLMCallPrepared import added
- [x] LLMCallPrepared emitted after prepare_calls with call_count, system_key, user_key
- [x] for-loop changed to enumerate for call_index
- [x] Event context injected into call_kwargs only when emitter present
- [x] Consensus path auto-receives event context via **call_kwargs unpacking
- [x] Zero overhead when no emitter (all guarded by `if self._event_emitter:`)
- [x] All 118 existing tests pass
