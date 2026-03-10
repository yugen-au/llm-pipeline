# IMPLEMENTATION - STEP 1: FIX TS INTERFACE MISMATCHES
**Status:** completed

## Summary
Fixed TypeScript interface mismatches in `src/api/types.ts` so PipelineStepMetadata and PipelineListItem match backend Pydantic models. Removed @provisional JSDoc tags from both interfaces.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/src/api/types.ts
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/api/types.ts`

PipelineStepMetadata: made system_key and user_key nullable, removed @provisional JSDoc block.

```
# Before
/**
 * Individual step metadata within a pipeline strategy.
 *
 * @provisional - shape from PipelineIntrospector.get_metadata().
 */
export interface PipelineStepMetadata {
  ...
  system_key: string
  user_key: string

# After
/** Individual step metadata within a pipeline strategy. */
export interface PipelineStepMetadata {
  ...
  system_key: string | null
  user_key: string | null
```

PipelineListItem: made strategy_count and step_count nullable, added registry_model_count and error fields, removed @provisional JSDoc block.

```
# Before
/**
 * Simplified pipeline list item (anticipated shape for GET /api/pipelines).
 *
 * @provisional - backend endpoint does not exist until task 24.
 */
export interface PipelineListItem {
  name: string
  strategy_count: number
  step_count: number
  has_input_schema: boolean
}

# After
/** Simplified pipeline list item for GET /api/pipelines. */
export interface PipelineListItem {
  name: string
  strategy_count: number | null
  step_count: number | null
  has_input_schema: boolean
  registry_model_count: number | null
  error: string | null
}
```

## Decisions
None

## Verification
[x] PipelineStepMetadata system_key and user_key are `string | null`
[x] PipelineListItem strategy_count and step_count are `number | null`
[x] PipelineListItem has registry_model_count and error fields
[x] @provisional tags removed from PipelineStepMetadata and PipelineListItem only
[x] Other @provisional tags (ExtractionMetadata, TransformationMetadata, PipelineStrategyMetadata, PipelineMetadata) left untouched
[x] prompts.tsx line 61 null guard (`if (!promptKey) continue`) handles nullable system_key/user_key
[x] TypeScript compiles with no new errors (`npx tsc --noEmit` passes clean)
