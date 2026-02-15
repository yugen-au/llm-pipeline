# IMPLEMENTATION - STEP 4: EMIT CACHEMISS
**Status:** completed

## Summary
Added CacheMiss event emission in pipeline.py execute() method, inside the else branch of `if cached_state:`, guarded by `if use_cache:` (structural) and `if self._event_emitter:` (double-guard). Emits before the logger call with run_id, pipeline_name, step_name, and input_hash fields.

## Files
**Created:** none
**Modified:** llm_pipeline/pipeline.py
**Deleted:** none

## Changes
### File: `llm_pipeline/pipeline.py`
Added CacheMiss emission at L583-589 inside the cache-miss path, before the logger.info("[FRESH]") call.

```
# Before
                else:
                    if use_cache:
                        logger.info("  [FRESH] No cache found, running fresh")

# After
                else:
                    if use_cache:
                        if self._event_emitter:
                            self._emit(CacheMiss(
                                run_id=self.run_id,
                                pipeline_name=self.pipeline_name,
                                step_name=step.step_name,
                                input_hash=input_hash,
                            ))
                        logger.info("  [FRESH] No cache found, running fresh")
```

## Decisions
None -- straightforward insertion following established double-guard pattern.

## Verification
[x] CacheMiss emission inside `if use_cache:` block (structural confinement)
[x] Inner `if self._event_emitter:` guard prevents construction cost when no emitter
[x] Fields match CacheMiss dataclass: run_id, pipeline_name, step_name, input_hash
[x] input_hash available from L544 `_hash_step_inputs()` call
[x] All 150 tests pass, 1 warning (pre-existing)
