# IMPLEMENTATION - STEP 5: TOKEN CAPTURE NORMAL PATH
**Status:** completed

## Summary
Capture token usage from `run_result.usage()` after every `agent.run_sync()` call in the normal (non-consensus) execution path. Propagate per-call tokens to `LLMCallCompleted` events and step-level aggregates to `_save_step_state()` and `StepCompleted` events.

## Files
**Created:** none
**Modified:** `llm_pipeline/pipeline.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/pipeline.py`

**1. Step-level accumulators initialized before cache branch (line ~632)**

Moved accumulators before `if cached_state:` so they are always in scope for `StepCompleted` emission (which fires after both cached and non-cached paths).

```python
# Before
if cached_state:

# After
_step_input_tokens = 0
_step_output_tokens = 0
_step_total_requests = 0
_step_total_tokens: int | None = None

if cached_state:
```

**2. Per-call token vars initialized at top of call loop (line ~757)**

```python
for idx, params in enumerate(call_params):
    _call_input_tokens: int | None = None
    _call_output_tokens: int | None = None
    _call_total_tokens: int | None = None
```

**3. Token capture after `instruction = run_result.output` (line ~831)**

```python
# Before
instruction = run_result.output

# After
instruction = run_result.output
_usage = run_result.usage()
if _usage:
    _call_input_tokens = _usage.input_tokens
    _call_output_tokens = _usage.output_tokens
    _call_total_tokens = (
        (_call_input_tokens or 0) + (_call_output_tokens or 0)
    )
    _step_input_tokens += _call_input_tokens or 0
    _step_output_tokens += _call_output_tokens or 0
_step_total_requests += 1
```

**4. Token fields added to LLMCallCompleted emission (line ~860)**

```python
input_tokens=_call_input_tokens,
output_tokens=_call_output_tokens,
total_tokens=_call_total_tokens,
```

**5. Step-level totals passed to _save_step_state (line ~909)**

```python
_step_total_tokens = _step_input_tokens + _step_output_tokens if _step_total_requests > 0 else None
self._save_step_state(
    step, step_num, instructions, input_hash, execution_time_ms, self._model,
    input_tokens=_step_input_tokens if _step_total_requests > 0 else None,
    output_tokens=_step_output_tokens if _step_total_requests > 0 else None,
    total_tokens=_step_total_tokens,
    total_requests=_step_total_requests if _step_total_requests > 0 else None,
)
```

**6. Step-level totals passed to StepCompleted emission (line ~934)**

```python
input_tokens=_step_input_tokens if _step_total_requests > 0 else None,
output_tokens=_step_output_tokens if _step_total_requests > 0 else None,
total_tokens=_step_total_tokens if _step_total_requests > 0 else None,
```

**7. `_save_step_state` signature accepts `**kwargs` (line ~1110)**

Added `**kwargs` so new token kwargs don't cause TypeError before Step 7 adds explicit params.

## Decisions
### Accumulator placement
**Choice:** Initialize before `if cached_state:` branch, not inside `else`
**Rationale:** `StepCompleted` emission is after both branches; accumulators must be in scope. Cached steps get None tokens (correct: no LLM calls made).

### `_save_step_state` **kwargs bridge
**Choice:** Add `**kwargs` to `_save_step_state` signature temporarily
**Rationale:** Step 7 will add explicit token params. Without `**kwargs`, passing token kwargs causes TypeError now. This is the minimal non-breaking bridge.

### Guard with `_step_total_requests > 0`
**Choice:** Token fields are None when no requests were made (cached path)
**Rationale:** Avoids reporting 0 tokens when the step was served from cache (no LLM calls occurred).

## Verification
[x] All 588 existing tests pass (1 pre-existing UI test failure unrelated to changes)
[x] Token accumulators in scope for both cached and non-cached paths
[x] Per-call tokens populated only in non-consensus path (consensus handled in Step 6)
[x] `_save_step_state` accepts new kwargs without error
[x] `StepCompleted` gets None tokens on cached path
