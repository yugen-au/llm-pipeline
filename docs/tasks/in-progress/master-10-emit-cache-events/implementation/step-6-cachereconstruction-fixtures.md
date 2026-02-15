# IMPLEMENTATION - STEP 6: CACHERECONSTRUCTION FIXTURES
**Status:** completed

## Summary
Added CacheReconstruction test fixtures to tests/events/conftest.py: extraction domain models (Item, ItemDetectionInstructions, ItemDetectionContext, ItemExtraction), extraction pipeline (ItemDetectionStep, ExtractionStrategy, ExtractionRegistry, ExtractionStrategies, ExtractionPipeline), and seeded_cache_session fixture that runs ExtractionPipeline once to populate PipelineStepState + PipelineRunInstance + Item records for cache-hit scenario.

## Files
**Created:** none
**Modified:** tests/events/conftest.py
**Deleted:** none

## Changes
### File: `tests/events/conftest.py`
Added import for PipelineStepState and PipelineRunInstance from llm_pipeline.state. Previous subagent had already added the extraction domain classes and pipeline scaffolding; this step completed the fixture by adding the state imports and the `seeded_cache_session` fixture.

```python
# Added import (L24)
from llm_pipeline.state import PipelineStepState, PipelineRunInstance

# Added fixture (L384-440)
@pytest.fixture
def seeded_cache_session(engine):
    """Session with prompts + cached extraction state from a completed first run."""
    # Seeds prompts with version="1.0", runs ExtractionPipeline once with
    # use_cache=True to populate PipelineStepState + PipelineRunInstance + Item rows.
    # Returns (session, first_run_id) for second-run cache-hit tests.
```

## Decisions
### First-run seeding approach
**Choice:** Run ExtractionPipeline once in fixture rather than manually constructing PipelineStepState/PipelineRunInstance records
**Rationale:** Avoids fragile coupling to internal hash computation (_hash_step_inputs), serialization format, and state-saving logic. The pipeline's own code seeds the exact records needed for cache reconstruction. Second run from test code will produce identical input_hash because same step class + same variables + same data.

### Prompt version alignment
**Choice:** All prompts seeded with version="1.0" in seeded_cache_session
**Rationale:** _find_cached_state filters by prompt_version. Must match between first run (saves state) and second run (looks up cache). version="1.0" matches seeded_session default.

## Verification
[x] PipelineStepState and PipelineRunInstance imported
[x] seeded_cache_session fixture seeds all prompts (including item_detection) with version="1.0"
[x] First run uses ExtractionPipeline with use_cache=True (saves state via _save_step_state)
[x] First run creates Item instances via ItemExtraction (item_count=2)
[x] session.commit() ensures state persisted for second run
[x] Fixture returns (session, first_run_id) for test assertions
[x] All 189 tests pass, 1 pre-existing warning
[x] Extraction domain: Item model, ItemExtraction, ItemDetectionStep with default_extractions=[ItemExtraction]
[x] ExtractionRegistry includes Item model (required for PipelineExtraction.__init__ validation)
