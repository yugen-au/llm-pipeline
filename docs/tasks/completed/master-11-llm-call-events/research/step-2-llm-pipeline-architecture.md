# Step 2: LLM Pipeline Architecture - Call Chain & Event Emission Points

## Full Call Chain

```
pipeline.execute()                          # pipeline.py L410-660
  -> step.prepare_calls()                   # pipeline.py L580 -> step.py L299
  -> for params in call_params:             # pipeline.py L583
       step.create_llm_call(**params)       # pipeline.py L584 -> step.py L262-296
       execute_llm_step(**call_kwargs)      # pipeline.py L594 -> executor.py L21-131
         -> prompt_service.get_system_prompt()  # executor.py L82-94
         -> prompt_service.get_user_prompt()    # executor.py L97-102
         -> provider.call_structured()          # executor.py L105-111
         -> result_class(**result.parsed)       # executor.py L127
```

## Data Available at Each Point

### 1. After prepare_calls() [pipeline.py L580]
- `call_params`: List[StepCallParams] -- just `variables`, optional `array_validation`/`validation_context`
- `step.system_instruction_key`, `step.user_prompt_key` -- prompt DB keys (NOT rendered text)
- `len(call_params)` -- number of LLM calls this step will make

### 2. After create_llm_call() [pipeline.py L584]
- `call_kwargs`: ExecuteLLMStepParams dict with keys, variables, result_class, system_variables
- Still NO rendered prompts (keys only)

### 3. Inside execute_llm_step() after prompt render [executor.py L103]
- `system_instruction`: str -- RENDERED system prompt (template + variables resolved)
- `user_prompt`: str -- RENDERED user prompt (template + variables resolved)
- These are LOCAL to execute_llm_step, NOT returned to pipeline.py

### 4. Inside execute_llm_step() after provider call [executor.py L111]
- `result`: LLMCallResult with parsed, raw_response, model_name, attempt_count, validation_errors
- LLMCallResult consumed internally; function returns result_class instance (T), NOT LLMCallResult

## Event Emission Points

### LLMCallPrepared -- emit from pipeline.py
- **Where**: After `call_params = step.prepare_calls()` (L580), before the for-loop (L583)
- **Scope**: Once per step execution (not per call)
- **Data**: call_count=len(call_params), system_key=step.system_instruction_key, user_key=step.user_prompt_key
- **Cache path**: Naturally excluded -- L580 is inside `else` branch at L571 (fresh execution only)

### LLMCallStarting -- emit from executor.py
- **Where**: After prompts rendered (after L102), before provider.call_structured (L105)
- **Why executor not pipeline**: Rendered prompts are local variables in execute_llm_step; pipeline never sees them
- **Data**: rendered_system_prompt=system_instruction, rendered_user_prompt=user_prompt, call_index
- **Required**: Add event_emitter + context params to execute_llm_step() signature

### LLMCallCompleted -- emit from executor.py
- **Where**: After provider.call_structured returns (L111), before Pydantic re-validation (L121)
- **Why executor not pipeline**: LLMCallResult consumed inside executor; pipeline only gets result_class instance
- **Data**: All LLMCallResult fields (raw_response, parsed, model_name, attempt_count, validation_errors), call_index
- **Note**: Emit regardless of success/failure (result.parsed may be None for failures)

## Signature Changes Required

### execute_llm_step() -- new optional params
```python
def execute_llm_step(
    # ... existing params ...
    event_emitter: Optional["PipelineEventEmitter"] = None,
    run_id: Optional[str] = None,
    pipeline_name: Optional[str] = None,
    step_name: Optional[str] = None,
    call_index: int = 0,
) -> T:
```

Pipeline passes these when calling (pipeline.py L594):
```python
instruction = execute_llm_step(
    **call_kwargs,
    event_emitter=self._event_emitter,
    run_id=self.run_id,
    pipeline_name=self.pipeline_name,
    step_name=step.step_name,
    call_index=idx,
)
```

## Consensus Polling Path

_execute_with_consensus() (pipeline.py L916-942) also calls execute_llm_step(). Same event params must be passed. Each consensus attempt fires its own LLMCallStarting/LLMCallCompleted. call_index stays same (params index); consensus events are separate scope.

## Key Files Modified

| File | Change |
|------|--------|
| `llm_pipeline/llm/executor.py` | Add event params, emit LLMCallStarting + LLMCallCompleted |
| `llm_pipeline/pipeline.py` | Emit LLMCallPrepared, pass event context to execute_llm_step |
| `llm_pipeline/events/types.py` | No changes needed (all 3 event types already defined) |

## Existing Event Types (no changes needed)

```python
# events/types.py L307-345
LLMCallPrepared(StepScopedEvent):    call_count, system_key, user_key
LLMCallStarting(StepScopedEvent):    call_index, rendered_system_prompt, rendered_user_prompt
LLMCallCompleted(StepScopedEvent):   call_index, raw_response, parsed_result, model_name, attempt_count, validation_errors
```

All inherit from StepScopedEvent which has: run_id, pipeline_name, step_name, timestamp, event_type.

## Compatibility with Task 12 (downstream, OUT OF SCOPE)

Task 12 adds LLMCallRetry/LLMCallFailed/LLMCallRateLimited inside GeminiProvider retry loop. The event_emitter threading pattern established here extends naturally: executor passes event_emitter to provider.call_structured(), provider emits retry/rate-limit events.

## LLMCallResult Dataclass Reference

```python
# llm_pipeline/llm/result.py
@dataclass(frozen=True, slots=True)
class LLMCallResult:
    parsed: dict[str, Any] | None = None
    raw_response: str | None = None
    model_name: str | None = None
    attempt_count: int = 1
    validation_errors: list[str] = field(default_factory=list)
```

Maps directly to LLMCallCompleted event fields.
