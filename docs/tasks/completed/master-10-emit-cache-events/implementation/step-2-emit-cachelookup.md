# IMPLEMENTATION - STEP 2: EMIT CACHELOOKUP
**Status:** completed

## Summary
Added CacheLookup event emission inside `if use_cache:` block, before `_find_cached_state` call. Uses double-guard pattern: outer `if use_cache:` + inner `if self._event_emitter:`.

## Files
**Created:** none
**Modified:** llm_pipeline/pipeline.py
**Deleted:** none

## Changes
### File: `llm_pipeline/pipeline.py`
Inserted CacheLookup emission at L548-554 (after edit), between `if use_cache:` and `_find_cached_state` call.

```
# Before
cached_state = None
if use_cache:
    cached_state = self._find_cached_state(step, input_hash)

# After
cached_state = None
if use_cache:
    if self._event_emitter:
        self._emit(CacheLookup(
            run_id=self.run_id,
            pipeline_name=self.pipeline_name,
            step_name=step.step_name,
            input_hash=input_hash,
        ))
    cached_state = self._find_cached_state(step, input_hash)
```

## Decisions
None -- straightforward insertion following established pattern from tasks 9/11.

## Verification
[x] Import already present (Step 1 completed prior)
[x] Emission inside `if use_cache:` structural guard
[x] Inner `if self._event_emitter:` guard matches double-guard pattern
[x] Fields match CacheLookup dataclass: run_id, pipeline_name, step_name, input_hash
[x] Emission occurs before `_find_cached_state` call
[x] Module imports successfully
[x] All 150 tests pass, 0 failures
