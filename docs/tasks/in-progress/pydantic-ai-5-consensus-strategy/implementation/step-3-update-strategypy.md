# IMPLEMENTATION - STEP 3: UPDATE STRATEGY.PY
**Status:** completed

## Summary
Added `consensus_strategy` field to `StepDefinition` dataclass with TYPE_CHECKING import for `ConsensusStrategy` from `llm_pipeline.consensus`.

## Files
**Created:** none
**Modified:** llm_pipeline/strategy.py
**Deleted:** none

## Changes
### File: `llm_pipeline/strategy.py`
Added TYPE_CHECKING import for ConsensusStrategy and new optional field on StepDefinition.

```python
# Before
if TYPE_CHECKING:
    from llm_pipeline.extraction import PipelineExtraction
    from llm_pipeline.transformation import PipelineTransformation

# After
if TYPE_CHECKING:
    from llm_pipeline.consensus import ConsensusStrategy
    from llm_pipeline.extraction import PipelineExtraction
    from llm_pipeline.transformation import PipelineTransformation
```

```python
# Before
    not_found_indicators: list[str] | None = None

# After
    not_found_indicators: list[str] | None = None
    consensus_strategy: 'ConsensusStrategy | None' = None
```

## Decisions
None

## Verification
[x] No circular imports (`python -c "import llm_pipeline"` succeeds)
[x] Field present on StepDefinition dataclass (verified via `dataclasses.fields()`)
[x] Default value is None (no breaking change for existing usage)
[x] No changes needed to `step_definition` decorator or `create_definition()` - kwargs pass-through handles it
