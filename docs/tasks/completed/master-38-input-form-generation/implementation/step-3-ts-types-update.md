# IMPLEMENTATION - STEP 3: TS TYPES UPDATE
**Status:** completed

## Summary
Extended TypeScript interfaces in types.ts to match new backend shapes: added `input_data` to TriggerRunRequest, `pipeline_input_schema` to PipelineMetadata, and introduced `JsonSchema` type alias for InputForm consumption.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/src/api/types.ts
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/api/types.ts`

Added optional `input_data` field to TriggerRunRequest, updated JSDoc to reflect task 38 context.

```
# Before
export interface TriggerRunRequest {
  pipeline_name: string
}

# After
export interface TriggerRunRequest {
  pipeline_name: string
  input_data?: Record<string, unknown>
}
```

Added `pipeline_input_schema` field to PipelineMetadata (null until task 43 provides real schemas).

```
# Before
export interface PipelineMetadata {
  pipeline_name: string
  registry_models: string[]
  strategies: PipelineStrategyMetadata[]
  execution_order: string[]
}

# After
export interface PipelineMetadata {
  pipeline_name: string
  registry_models: string[]
  strategies: PipelineStrategyMetadata[]
  execution_order: string[]
  pipeline_input_schema: Record<string, unknown> | null
}
```

Added JsonSchema type alias after PipelineListItem, before WebSocket types section.

```
# Before
(no JsonSchema type)

# After
export type JsonSchema = Record<string, unknown>
```

## Decisions
### JsonSchema placement
**Choice:** Placed in Pipelines section after PipelineListItem, before WebSocket section
**Rationale:** JsonSchema is semantically tied to pipeline input schemas; co-locating with pipeline types keeps related types together

### JsonSchema as Record<string, unknown>
**Choice:** Minimal type alias, no structural JSON Schema typing
**Rationale:** Per plan -- full JSON Schema typing out of scope. Consumers cast properties as needed.

## Verification
[x] `npm run type-check` passes with zero errors
[x] TriggerRunRequest has optional input_data field
[x] PipelineMetadata has pipeline_input_schema field (nullable)
[x] JsonSchema type alias exported
[x] No other interfaces or existing code affected
