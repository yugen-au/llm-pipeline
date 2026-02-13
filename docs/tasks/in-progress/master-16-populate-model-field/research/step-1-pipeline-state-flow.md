# Research: Pipeline State Flow for model_name Population

## Data Flow: LLM Call -> State Persistence

### Layer 1: Provider (LLMCallResult creation)
- `GeminiProvider.call_structured()` returns `LLMCallResult` with `model_name=self.model_name`
- File: `llm_pipeline/llm/gemini.py` lines 123, 203, 241
- `LLMCallResult.model_name` is `str | None` (field at `llm_pipeline/llm/result.py:22`)
- `LLMProvider` abstract (`llm_pipeline/llm/provider.py`) does NOT define `model_name` attribute; only `call_structured() -> LLMCallResult` is required

### Layer 2: Executor (model_name discarded)
- `execute_llm_step()` at `llm_pipeline/llm/executor.py`
- Line 105: `result: LLMCallResult = provider.call_structured(...)`
- Lines 121-130: Returns validated Pydantic `T` from `result.parsed`, NOT the `LLMCallResult`
- **model_name is discarded here** -- return type is `T` (Pydantic model), not `LLMCallResult`

### Layer 3: Pipeline execute() (no model_name available)
- `PipelineConfig.execute()` at `llm_pipeline/pipeline.py:405-572`
- Line 543: `instruction = execute_llm_step(**call_kwargs)` -- receives `T`, not `LLMCallResult`
- Line 544: `instructions.append(instruction)` -- list of `T`
- Lines 560-562: `self._save_step_state(step, step_num, instructions, input_hash, execution_time_ms)` -- no model_name param

### Layer 4: _save_step_state() (model field unset)
- `_save_step_state()` at `llm_pipeline/pipeline.py:688-729`
- Signature: `(self, step, step_number, instructions, input_hash, execution_time_ms=None)`
- PipelineStepState construction at lines 715-727: `model` field NOT passed, defaults to `None`

### Layer 5: PipelineStepState (field exists, never populated)
- `PipelineStepState.model` at `llm_pipeline/state.py:87-91`
- `Optional[str]`, `max_length=50`, `default=None`

## Call Sites of _save_step_state()

Only ONE call site:
- `pipeline.py:560-562` inside `execute()`, in the fresh (non-cached) execution branch

## Consensus Path
- `_execute_with_consensus()` at `pipeline.py:827-853` also calls `execute_llm_step()` and returns `T`
- Same model_name loss applies

## The Gap

```
GeminiProvider.call_structured() -> LLMCallResult(model_name="gemini-2.0-flash-lite")
                                         |
                                    execute_llm_step()
                                         |
                                    returns T (Pydantic model) -- model_name DISCARDED
                                         |
                                    pipeline.execute()
                                         |
                                    _save_step_state() -- no model_name available
                                         |
                                    PipelineStepState(model=None) -- NEVER SET
```

## Approaches to Thread model_name

### A) Use self._provider.model_name (simplest, no executor change)
- `self._provider` available in `execute()` -- pass `getattr(self._provider, 'model_name', None)` to `_save_step_state()`
- Pro: Zero changes to executor, non-breaking
- Con: `LLMProvider` abstract does NOT define `model_name` as attribute; only `GeminiProvider` has it. Requires `getattr` safety. All future providers must remember to set `self.model_name`.

### B) Change execute_llm_step() return type to include model_name
- Return `tuple[T, str | None]` or `tuple[T, LLMCallResult]`
- Pro: model_name comes from actual LLM response, most accurate
- Con: BREAKING change to executor return type. All call sites (`pipeline.execute()`, `_execute_with_consensus()`, any external consumers) must update.

### C) Add model_name property to LLMProvider abstract
- Add `model_name: str` abstract property to `LLMProvider`
- Then use approach A safely without `getattr`
- Pro: Clean contract, all providers must implement
- Con: Breaking change to LLMProvider interface (existing implementations must add property)

## Ambiguity Identified

Task 16 details reference `result.model_name` implying `LLMCallResult` access, but `execute_llm_step()` returns `T` not `LLMCallResult`. The code snippet in the task was written assuming `result` is `LLMCallResult`, which it is NOT in current code.

**CEO decision needed: which approach (A, B, or C) to use for sourcing model_name.**
