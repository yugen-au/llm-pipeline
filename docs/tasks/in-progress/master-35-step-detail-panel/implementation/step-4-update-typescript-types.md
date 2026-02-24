# IMPLEMENTATION - STEP 4: UPDATE TYPESCRIPT TYPES
**Status:** completed

## Summary
Added step_name filter param to EventListParams, typed event_data interfaces for 4 event types, StepPromptsResponse/StepPromptItem types for instruction endpoint, and stepPrompts query key factory.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/src/api/types.ts, llm_pipeline/ui/frontend/src/api/query-keys.ts
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/api/types.ts`
Added `step_name?: string` to EventListParams. Added 4 typed event_data interfaces (LLMCallStartingData, LLMCallCompletedData, ContextUpdatedData, ExtractionCompletedData) after Events section. Added StepPromptItem and StepPromptsResponse interfaces for the instruction content endpoint.

```
# Before
export interface EventListParams {
  event_type?: string
  offset?: number
  limit?: number
}

# After
export interface EventListParams {
  event_type?: string
  step_name?: string
  offset?: number
  limit?: number
}
// + LLMCallStartingData, LLMCallCompletedData, ContextUpdatedData,
//   ExtractionCompletedData, StepPromptItem, StepPromptsResponse
```

### File: `llm_pipeline/ui/frontend/src/api/query-keys.ts`
Added `stepPrompts` factory to `queryKeys.pipelines`.

```
# Before
pipelines: {
  all: ['pipelines'] as const,
  detail: (name: string) => ['pipelines', name] as const,
},

# After
pipelines: {
  all: ['pipelines'] as const,
  detail: (name: string) => ['pipelines', name] as const,
  stepPrompts: (name: string, stepName: string) =>
    ['pipelines', name, 'steps', stepName, 'prompts'] as const,
},
```

## Decisions
None

## Verification
[x] TypeScript compilation passes (npx tsc --noEmit)
[x] step_name added to EventListParams
[x] All 4 event_data interfaces present with correct fields
[x] StepPromptItem and StepPromptsResponse interfaces present
[x] stepPrompts query key factory added to pipelines
