# IMPLEMENTATION - STEP 9: TEST CACHERECONSTRUCTION
**Status:** completed

## Summary
Added 10 integration tests for CacheReconstruction event in test_cache_events.py. Added extraction domain fixtures (Item model, ItemExtraction, ItemDetectionStep, ExtractionPipeline) to conftest.py. Tests verify emission after CacheHit, field accuracy (model_count, instance_count), guard behavior (no emission without extractions), and event ordering.

## Files
**Created:** none
**Modified:** tests/events/conftest.py, tests/events/test_cache_events.py
**Deleted:** none

## Changes
### File: `tests/events/conftest.py`
Added extraction domain fixtures for CacheReconstruction tests:

- `Item(SQLModel, table=True)` -- minimal DB model with name/value fields
- `ItemDetectionInstructions(LLMResultMixin)` -- instruction model with item_count, category
- `ItemDetectionContext(PipelineContext)` -- context with category field
- `ItemExtraction(PipelineExtraction, model=Item)` -- creates `item_count` Item instances
- `ItemDetectionStep(LLMStep)` -- step with `default_extractions=[ItemExtraction]`
- `ExtractionStrategy`, `ExtractionRegistry(models=[Item])`, `ExtractionStrategies`, `ExtractionPipeline`
- Prompts for `item_detection.system` and `item_detection.user` added to `seeded_session`

### File: `tests/events/test_cache_events.py`
Added helpers and 3 test classes (10 tests total):

**Helpers:**
- `_run_extraction_pipeline()` -- single run, cache-miss path
- `_two_run_extraction()` -- run 1 populates cache + calls `save()` for PipelineRunInstance records; run 2 hits cache and captures events

**TestCacheReconstructionEmitted (5 tests):**
- `test_reconstruction_emitted_on_cache_hit` -- exactly 1 CacheReconstruction on second run
- `test_reconstruction_model_count` -- model_count == 1 (single ItemExtraction)
- `test_reconstruction_instance_count` -- instance_count == 3 (item_count=3 in mock response)
- `test_reconstruction_has_run_id` -- run_id matches pipeline.run_id
- `test_reconstruction_has_step_name` -- step_name == "item_detection"

**TestCacheReconstructionNotEmittedWithoutExtractions (2 tests):**
- `test_no_reconstruction_for_simple_pipeline` -- SuccessPipeline has no extractions, no CacheReconstruction on cache-hit
- `test_no_reconstruction_on_cache_miss` -- ExtractionPipeline first run (cache miss), no CacheReconstruction

**TestCacheReconstructionOrdering (3 tests):**
- `test_hit_before_reconstruction` -- CacheHit index < CacheReconstruction index
- `test_reconstruction_before_step_completed` -- CacheReconstruction index < StepCompleted index
- `test_full_cache_hit_sequence` -- CacheLookup -> CacheHit -> CacheReconstruction -> StepCompleted

## Decisions
### Two-run pattern with save()
**Choice:** Run 1 calls `pipeline1.save()` after execute to persist PipelineRunInstance records
**Rationale:** `_reconstruct_extractions_from_cache` queries PipelineRunInstance to find cached model instances. Without `save()`, no PipelineRunInstance rows exist and instance_count would be 0.

### Separate extraction domain in conftest
**Choice:** New Item/ItemExtraction/ExtractionPipeline rather than reusing SuccessPipeline
**Rationale:** SuccessPipeline has `models=[]` and no extractions. CacheReconstruction guard `if step_def.extractions:` requires a step with non-empty extractions to trigger emission.

## Verification
[x] 10 new CacheReconstruction tests pass
[x] All 188 tests pass (1 pre-existing Step 8 timezone failure unrelated)
[x] 1 pre-existing warning (PytestCollectionWarning on TestPipeline)
[x] Emission verified on cache-hit path with extractions
[x] No emission verified on cache-miss path
[x] No emission verified when step has no extractions (guard test)
[x] Ordering: CacheHit -> CacheReconstruction -> StepCompleted verified
[x] model_count == len(step_def.extractions) == 1 verified
[x] instance_count == reconstructed_count == 3 verified
