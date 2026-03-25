# IMPLEMENTATION - STEP 10: CREATE PIPELINE.PY
**Status:** completed

## Summary
Created `llm_pipeline/creator/pipeline.py` with all 6 public classes: StepCreatorInputData, StepCreatorRegistry, StepCreatorAgentRegistry, DefaultCreatorStrategy, StepCreatorStrategies, StepCreatorPipeline. Follows demo/pipeline.py patterns exactly.

## Files
**Created:** llm_pipeline/creator/pipeline.py
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/creator/pipeline.py`
New file. Defines all pipeline wiring classes.
```
# Before
[file did not exist]

# After
StepCreatorInputData(PipelineInputData) - 4 fields: description, target_pipeline, include_extraction, include_transformation
StepCreatorRegistry(PipelineDatabaseRegistry, models=[GenerationRecord]) - pass-through
StepCreatorAgentRegistry(AgentRegistry, agents={4 step keys -> Instructions classes})
DefaultCreatorStrategy(PipelineStrategy) - can_handle always True; get_steps() imports inline
StepCreatorStrategies(PipelineStrategies, strategies=[DefaultCreatorStrategy]) - pass-through
StepCreatorPipeline(PipelineConfig, ...) - INPUT_DATA=StepCreatorInputData, seed_prompts classmethod
```

## Decisions
### Inline imports in get_steps()
**Choice:** Import step classes inside get_steps() method body.
**Rationale:** Avoids circular import: steps.py will import schemas.py; pipeline.py imports schemas.py; if pipeline.py also imported steps.py at module level it would create a cycle.

### seed_prompts delegation
**Choice:** `_seed(cls, engine)` passing `cls` (StepCreatorPipeline) as first arg.
**Rationale:** Matches demo/pipeline.py L287 pattern exactly: `seed_prompts(cls, engine)`.

## Verification
- [x] `from llm_pipeline.creator.pipeline import StepCreatorPipeline` imports cleanly
- [x] StepCreatorInputData fields default correctly (target_pipeline=None, include_extraction=True, include_transformation=False)
- [x] StepCreatorRegistry.MODELS contains GenerationRecord
- [x] StepCreatorAgentRegistry.get_output_type() resolves all 4 step names
- [x] DefaultCreatorStrategy.can_handle({}) returns True
- [x] DefaultCreatorStrategy.NAME == 'default_creator'
- [x] StepCreatorStrategies.STRATEGIES contains DefaultCreatorStrategy
- [x] StepCreatorPipeline.INPUT_DATA is StepCreatorInputData
