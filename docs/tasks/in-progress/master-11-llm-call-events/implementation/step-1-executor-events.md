# IMPLEMENTATION - STEP 1: EXECUTOR EVENTS
**Status:** completed

## Summary
Modified `execute_llm_step()` in `llm_pipeline/llm/executor.py` to emit `LLMCallStarting` before `provider.call_structured()` and `LLMCallCompleted` after (both success and exception paths). All new parameters are optional with defaults, preserving full backward compatibility. Zero overhead when no emitter provided.

## Files
**Created:** none
**Modified:** llm_pipeline/llm/executor.py
**Deleted:** none

## Changes
### File: `llm_pipeline/llm/executor.py`

Added TYPE_CHECKING import for PipelineEventEmitter and 5 optional parameters to `execute_llm_step()` signature.

```python
# Before
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Type, TypeVar

# After
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional, Type, TypeVar

if TYPE_CHECKING:
    from llm_pipeline.events.emitter import PipelineEventEmitter
```

```python
# Before
def execute_llm_step(
    system_instruction_key: str,
    user_prompt_key: str,
    variables: Any,
    result_class: Type[T],
    provider: Optional[LLMProvider] = None,
    prompt_service: Any = None,
    context: Optional[Dict[str, Any]] = None,
    array_validation: Optional[ArrayValidationConfig] = None,
    system_variables: Optional[Any] = None,
    validation_context: Optional[ValidationContext] = None,
) -> T:

# After
def execute_llm_step(
    system_instruction_key: str,
    user_prompt_key: str,
    variables: Any,
    result_class: Type[T],
    provider: Optional[LLMProvider] = None,
    prompt_service: Any = None,
    context: Optional[Dict[str, Any]] = None,
    array_validation: Optional[ArrayValidationConfig] = None,
    system_variables: Optional[Any] = None,
    validation_context: Optional[ValidationContext] = None,
    event_emitter: Optional["PipelineEventEmitter"] = None,
    run_id: Optional[str] = None,
    pipeline_name: Optional[str] = None,
    step_name: Optional[str] = None,
    call_index: int = 0,
) -> T:
```

Added LLMCallStarting emission after user_prompt rendering, guarded by `if event_emitter:`.

```python
# Before
    # Call LLM via provider
    result: LLMCallResult = provider.call_structured(...)

# After
    # Emit LLMCallStarting before provider call
    if event_emitter:
        from llm_pipeline.events.types import LLMCallStarting
        event_emitter.emit(LLMCallStarting(
            run_id=run_id, pipeline_name=pipeline_name,
            step_name=step_name, call_index=call_index,
            rendered_system_prompt=system_instruction,
            rendered_user_prompt=user_prompt,
        ))

    # Call LLM via provider (now wrapped in try/except)
    try:
        result: LLMCallResult = provider.call_structured(...)
    except Exception as exc:
        if event_emitter:
            from llm_pipeline.events.types import LLMCallCompleted
            event_emitter.emit(LLMCallCompleted(
                run_id=run_id, pipeline_name=pipeline_name,
                step_name=step_name, call_index=call_index,
                raw_response=None, parsed_result=None,
                model_name=None, attempt_count=1,
                validation_errors=[str(exc)],
            ))
        raise

    # Emit LLMCallCompleted after successful provider call
    if event_emitter:
        from llm_pipeline.events.types import LLMCallCompleted
        event_emitter.emit(LLMCallCompleted(
            run_id=run_id, pipeline_name=pipeline_name,
            step_name=step_name, call_index=call_index,
            raw_response=result.raw_response,
            parsed_result=result.parsed,
            model_name=result.model_name,
            attempt_count=result.attempt_count,
            validation_errors=result.validation_errors,
        ))
```

## Decisions
### Lazy imports inside guard blocks
**Choice:** Import LLMCallStarting/LLMCallCompleted inside `if event_emitter:` blocks
**Rationale:** Zero import overhead when no emitter. Consistent with TYPE_CHECKING pattern -- events module only loaded when actually emitting.

### Exception path always emits Completed then re-raises
**Choice:** Emit LLMCallCompleted with error data in except block before `raise`
**Rationale:** Ensures Starting/Completed pairing is always maintained. Consumers can detect exception path via raw_response=None + parsed_result=None + validation_errors populated.

## Verification
[x] All 118 existing tests pass (backward compatibility confirmed)
[x] New params all optional with defaults (event_emitter=None, run_id=None, pipeline_name=None, step_name=None, call_index=0)
[x] All event emission guarded by `if event_emitter:` (zero overhead)
[x] LLMCallStarting emitted after prompt rendering, before provider call
[x] LLMCallCompleted emitted on success path with full LLMCallResult fields
[x] LLMCallCompleted emitted on exception path with error in validation_errors, then re-raises
[x] TYPE_CHECKING import avoids circular dependency
