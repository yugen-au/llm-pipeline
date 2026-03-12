# IMPLEMENTATION - STEP 6: TOKEN CAPTURE CONSENSUS PATH
**Status:** completed

## Summary
Added token usage accumulation across all consensus attempts in `_execute_with_consensus()`. The method now returns a tuple including aggregate token totals. Each consensus attempt emits a per-call `LLMCallCompleted` event with individual token values. The call site in `execute()` unpacks the tuple and merges consensus totals into step-level accumulators.

## Files
**Created:** none
**Modified:** `llm_pipeline/pipeline.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/pipeline.py`

**1. `_execute_with_consensus()` - token accumulation and return type**

Added docstring documenting the new return type. Initialized token accumulators (`_consensus_input_tokens`, `_consensus_output_tokens`, `_consensus_requests`, `_has_any_usage`). After each `agent.run_sync()`, captures `run_result.usage()` defensively and accumulates into totals. Returns a 4-tuple instead of bare result.

```
# Before
def _execute_with_consensus(self, ...):
    ...
    return matched_group[0]

# After
def _execute_with_consensus(self, ...):
    """... Returns tuple of (result, total_input_tokens, total_output_tokens, total_requests) ..."""
    _consensus_input_tokens = 0
    _consensus_output_tokens = 0
    _consensus_requests = 0
    _has_any_usage = False
    ...
    return (
        matched_group[0],
        _consensus_input_tokens if _has_any_usage else None,
        _consensus_output_tokens if _has_any_usage else None,
        _consensus_requests,
    )
```

**2. Per-attempt `LLMCallCompleted` emission inside consensus loop**

Each consensus attempt now emits its own `LLMCallCompleted` event with per-call token values (`input_tokens`, `output_tokens`, `total_tokens`). Previously no per-attempt events were emitted.

**3. Call site in `execute()` - tuple unpacking and accumulator merge**

The consensus branch now unpacks the 4-tuple and merges totals into `_step_input_tokens`, `_step_output_tokens`, `_step_total_requests`. The post-call `LLMCallCompleted` emission was moved inside the `else` branch (non-consensus only) since consensus emits its own per-attempt events.

```
# Before
if use_consensus:
    instruction = self._execute_with_consensus(...)
else:
    ...
if self._event_emitter:
    self._emit(LLMCallCompleted(...))  # fired for both paths

# After
if use_consensus:
    instruction, _c_input, _c_output, _c_requests = self._execute_with_consensus(...)
    _step_input_tokens += _c_input or 0
    _step_output_tokens += _c_output or 0
    _step_total_requests += _c_requests
else:
    ...
    if self._event_emitter:
        self._emit(LLMCallCompleted(...))  # non-consensus only
```

## Decisions
### Defensive usage() handling
**Choice:** Check `_usage.input_tokens is not None` individually rather than trusting the object
**Rationale:** Some providers may return a usage object with None fields; matches Step 5 defensive pattern

### _has_any_usage flag for None vs 0 distinction
**Choice:** Track whether any attempt returned usage data; return None totals when no usage available
**Rationale:** Distinguishes "no provider returned usage" (None) from "all attempts used 0 tokens" (0); consistent with Optional[int] field semantics

### Per-attempt LLMCallCompleted inside _execute_with_consensus
**Choice:** Emit LLMCallCompleted per consensus attempt inside the method, skip the post-call emit at call site for consensus path
**Rationale:** Each consensus attempt is a distinct LLM call deserving its own event with per-call tokens; the old shared emit would have fired once with None tokens for consensus

## Verification
[x] `_execute_with_consensus` returns 4-tuple on both consensus-reached and consensus-failed paths
[x] Per-attempt `LLMCallCompleted` emitted with per-call token values inside consensus loop
[x] Call site unpacks tuple and merges into step-level accumulators (`_step_input_tokens`, etc.)
[x] `_consensus_requests` incremented even when `UnexpectedModelBehavior` is caught (true cost)
[x] All 37 consensus tests pass
[x] All 297 non-cache event tests pass
[x] Pre-existing failure in cache test is from Step 5/7 dependency (`_save_step_state` token kwargs), not this change
