# IMPLEMENTATION - STEP 5: EMIT CACHERECONSTRUCTION
**Status:** completed

## Summary
Added CacheReconstruction event emission in pipeline.py execute() method, caller-side after `_reconstruct_extractions_from_cache` returns and before the zero-count check. Guarded by compound condition: `if self._event_emitter and step_def.extractions:`.

## Files
**Created:** none
**Modified:** llm_pipeline/pipeline.py
**Deleted:** none

## Changes
### File: `llm_pipeline/pipeline.py`
Inserted CacheReconstruction emission at L585-592, between `_reconstruct_extractions_from_cache` return and the `reconstructed_count == 0` check.

```python
# Before (L582-585)
reconstructed_count = self._reconstruct_extractions_from_cache(
    cached_state, step_def
)
if reconstructed_count == 0 and step_def.extractions:

# After (L582-593)
reconstructed_count = self._reconstruct_extractions_from_cache(
    cached_state, step_def
)
if self._event_emitter and step_def.extractions:
    self._emit(CacheReconstruction(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
        step_name=step.step_name,
        model_count=len(step_def.extractions),
        instance_count=reconstructed_count,
    ))
if reconstructed_count == 0 and step_def.extractions:
```

## Decisions
### Compound guard condition
**Choice:** `if self._event_emitter and step_def.extractions:`
**Rationale:** CEO decision to skip emission when extractions empty (no meaningful data). Combines emitter check with extractions check per PLAN.md and VALIDATED_RESEARCH.md.

### Caller-side emission location
**Choice:** Emit from execute() after helper returns, not inside `_reconstruct_extractions_from_cache`
**Rationale:** CEO decision for consistency with tasks 9/11 pattern. Provides access to `step.step_name` (snake_case) and avoids helper signature changes.

## Verification
[x] CacheReconstruction emission inserted after _reconstruct_extractions_from_cache return
[x] Emission occurs before zero-count check
[x] Guard: `if self._event_emitter and step_def.extractions:`
[x] Fields: run_id, pipeline_name, step_name, model_count, instance_count
[x] model_count = len(step_def.extractions), instance_count = reconstructed_count
[x] All 150 tests pass, 1 warning (pre-existing)
[x] Structurally confined inside `if cached_state:` block (cache-hit path only)
