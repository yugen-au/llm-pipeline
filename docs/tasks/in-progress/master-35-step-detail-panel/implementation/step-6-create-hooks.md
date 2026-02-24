# IMPLEMENTATION - STEP 6: CREATE HOOKS
**Status:** completed

## Summary
Added `useStepEvents` hook to events.ts and `useStepInstructions` hook to pipelines.ts. Both delegate to existing patterns (useEvents for step-scoped event fetching, apiClient+useQuery for instruction content).

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/src/api/events.ts, llm_pipeline/ui/frontend/src/api/pipelines.ts
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/api/events.ts`
Added `useStepEvents(runId, stepName, runStatus?)` that delegates to `useEvents` with `{ step_name: stepName }` filter. Guards against empty stepName by passing empty runId to disable the underlying query.

```
# Before
(only useEvents exported)

# After
export function useStepEvents(runId, stepName, runStatus?) {
  const effectiveRunId = stepName ? runId : ''
  return useEvents(effectiveRunId, { step_name: stepName }, runStatus)
}
```

### File: `llm_pipeline/ui/frontend/src/api/pipelines.ts`
Added `StepPromptsResponse` import and `useStepInstructions(pipelineName, stepName)` hook. Fetches `GET /pipelines/{name}/steps/{stepName}/prompts` with `staleTime: Infinity` and `enabled: Boolean(pipelineName && stepName)`.

```
# Before
import type { PipelineListItem, PipelineMetadata } from './types'
(usePipelines, usePipeline exported)

# After
import type { PipelineListItem, PipelineMetadata, StepPromptsResponse } from './types'
(usePipelines, usePipeline, useStepInstructions exported)
```

## Decisions
### useStepEvents enabled guard via effectiveRunId
**Choice:** Pass empty runId when stepName is falsy instead of adding a separate enabled option to useEvents
**Rationale:** Leverages useEvents' existing `enabled: Boolean(runId)` guard without modifying its signature. Callers pass `step?.step_name ?? ''` and the query stays disabled until the step name resolves.

## Verification
[x] TypeScript type check passes (`npx tsc --noEmit` - clean)
[x] useStepEvents delegates to useEvents with step_name filter
[x] useStepEvents disabled when stepName is falsy
[x] useStepInstructions uses queryKeys.pipelines.stepPrompts
[x] useStepInstructions has staleTime: Infinity
[x] useStepInstructions disabled when pipelineName or stepName is falsy
[x] StepPromptsResponse type imported from types.ts
