# Research: LLMCallResult Model Field Flow

## Summary
Traced model_name from LLM provider through LLMCallResult to pipeline execute(). Found critical gap: LLMCallResult is consumed inside execute_llm_step() and model_name is discarded before reaching _save_step_state().

## LLMCallResult (llm_pipeline/llm/result.py)

- Frozen dataclass with `model_name: str | None = None` (line 22)
- Factory classmethods `success()` and `failure()` both require model_name param
- model_name is set in all code paths

## GeminiProvider (llm_pipeline/llm/gemini.py)

- Constructor stores `self.model_name` (default: "gemini-2.0-flash-lite", line 48)
- `call_structured()` sets `model_name=self.model_name` in ALL 3 return paths:
  - Success path: `LLMCallResult.success(..., model_name=self.model_name)` (line 203)
  - Not-found path: `LLMCallResult(model_name=self.model_name, ...)` (line 123)
  - Failure path: `LLMCallResult(model_name=self.model_name, ...)` (line 241)
- model_name always reflects the constructor-provided or default model string

## execute_llm_step (llm_pipeline/llm/executor.py)

- Calls `provider.call_structured()` -> receives `result: LLMCallResult` (line 105)
- Checks `result.parsed is None` for failure (line 113)
- On success, returns `result_class(**result.parsed)` or `result_class.model_validate(result.parsed)` (lines 123-127)
- **LLMCallResult is consumed here and NOT returned** - only the Pydantic instruction model is returned
- model_name is effectively discarded at this point

## pipeline.py execute() (lines 529-562)

- Calls `execute_llm_step(**call_kwargs)` -> receives Pydantic instruction model (line 543)
- Appends to `instructions` list (line 544)
- Passes instructions to `_save_step_state()` (line 560-562)
- **No access to LLMCallResult at this level**

## pipeline.py _save_step_state() (lines 688-729)

- Signature: `(self, step, step_number, instructions, input_hash, execution_time_ms=None)`
- Creates PipelineStepState WITHOUT setting `model` field (lines 715-727)
- `model` field is omitted entirely from construction

## PipelineStepState (llm_pipeline/state.py)

- `model: Optional[str] = Field(default=None, max_length=50)` (line 87-91)
- Field exists but never populated

## The Gap

```
GeminiProvider.call_structured()
  -> returns LLMCallResult(model_name="gemini-2.0-flash-lite")
    -> execute_llm_step() consumes LLMCallResult, returns result_class(**result.parsed)
      -> pipeline.execute() receives Pydantic model (model_name LOST)
        -> _save_step_state() has no model_name to set
```

## Implementation Options

### Option A: Use self._provider.model_name directly (SIMPLE)
- In _save_step_state, access `self._provider.model_name` (or getattr with None fallback)
- Pro: Zero changes to executor, minimal diff
- Pro: self._provider is already available on PipelineConfig (line 152)
- Con: Assumes provider exposes model_name attribute (true for GeminiProvider, not enforced by ABC)
- Con: Doesn't capture per-call model if provider changes model dynamically (not current behavior)

### Option B: Modify execute_llm_step return type (ARCHITECTURAL)
- Return `(instruction, result)` tuple or a wrapper containing both
- Pro: Clean separation, full LLMCallResult data available
- Con: Breaking change to execute_llm_step signature
- Con: All callers including _execute_with_consensus need updating
- Con: Larger scope than task 16

### Option C: Add model_name to LLMProvider ABC
- Add `model_name: str` property to abstract LLMProvider
- Use in _save_step_state via self._provider.model_name
- Pro: Type-safe, enforced by interface
- Con: Requires ABC change + all provider implementations

## Recommendation

Option A is sufficient for task 16 scope. GeminiProvider.model_name is a plain attribute (line 48). Using `getattr(self._provider, 'model_name', None)` in _save_step_state is defensive and works.

Task 16's description code snippet (`result.model_name if hasattr(result, 'model_name')`) assumes LLMCallResult is available at pipeline level - it is NOT. The description's approach needs adaptation.

## Question for CEO

The task description's implementation approach references `result.model_name` at the pipeline execute() level, but LLMCallResult is consumed inside execute_llm_step() and not returned. Should we:

1. Use `self._provider.model_name` directly (simplest, same data source, no executor changes)
2. Modify execute_llm_step to return LLMCallResult alongside instruction (larger change, cleaner architecture)

## Consensus Polling Path

`_execute_with_consensus()` (lines 827-853) also calls execute_llm_step and returns Pydantic instructions. Same gap applies. With Option A, model_name would still come from self._provider regardless of path.

## Files Requiring Changes (for implementation phase)

- `llm_pipeline/pipeline.py`: _save_step_state() signature + body, execute() call site
- No changes to executor.py or provider needed if using Option A
