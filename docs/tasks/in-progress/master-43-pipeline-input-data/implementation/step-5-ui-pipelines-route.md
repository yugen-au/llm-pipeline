# IMPLEMENTATION - STEP 5: UI PIPELINES ROUTE
**Status:** completed

## Summary
Updated has_input_schema logic in list_pipelines() to use pipeline-level INPUT_DATA via metadata.pipeline_input_schema instead of iterating step-level instruction schemas.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/routes/pipelines.py
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/pipelines.py`
Replaced step-level instruction schema iteration with direct pipeline_input_schema metadata check at L98.

```
# Before
has_input_schema = any(
    step.get("instructions_schema") is not None
    for strategy in strategies
    for step in strategy.get("steps", [])
)

# After
has_input_schema = metadata.get("pipeline_input_schema") is not None
```

## Decisions
None

## Verification
[x] has_input_schema now checks metadata.pipeline_input_schema (set by Step 4 introspection)
[x] No other references to step-level instructions_schema in this route for has_input_schema
[x] PipelineMetadata response model already has pipeline_input_schema field (L62)
