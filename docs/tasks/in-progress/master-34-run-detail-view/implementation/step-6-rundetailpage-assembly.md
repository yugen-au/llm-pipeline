# IMPLEMENTATION - STEP 6: RUNDETAILPAGE ASSEMBLY
**Status:** completed

## Summary
Replaced placeholder RunDetailPage with full Run Detail View wiring all Group A/B components: StepTimeline, ContextEvolution, StepDetailPanel, plus data hooks, WebSocket, and UI store.

## Files
**Created:** none
**Modified:** `llm_pipeline/ui/frontend/src/routes/runs/$runId.tsx`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/routes/runs/$runId.tsx`
Replaced placeholder with full implementation. Preserved Route export with Zod search schema and createFileRoute call.

```
# Before
Simple div with runId and tab text

# After
- useWebSocket(runId) at top for live updates
- useRun, useSteps, useEvents, useRunContext data hooks with run?.status threading
- useUIStore for selectedStepId, stepDetailOpen, selectStep, closeStepDetail
- deriveStepStatus in useMemo for timeline items
- RunDetailSkeleton for loading state (header + body skeleton)
- RunNotFound for 404 with back link
- Card header: ArrowLeft back link, pipeline_name, run_id (8-char truncated + Tooltip), StatusBadge, relative time (+ absolute tooltip), formatDuration
- Flex body: StepTimeline (flex-1) + ContextEvolution (w-80 right column with header)
- StepDetailPanel as overlay at page level
- TooltipProvider wrapping entire page
- run?.status as string for hooks; cast to RunStatus only for useRunContext
```

## Decisions
### CardContent for StepTimeline wrapper
**Choice:** Used CardContent with border+rounded for step timeline container instead of full Card
**Rationale:** Avoids nested Card padding; CardContent provides the px-6 slot but we override with p-0 since StepTimeline has its own padding

### Separator between pipeline name and run ID
**Choice:** Added vertical Separator between pipeline_name and truncated run_id in header
**Rationale:** Visual clarity between the two text elements without additional markup complexity

### Combined loading for StepTimeline
**Choice:** StepTimeline isLoading is `stepsLoading || eventsLoading`
**Rationale:** Both data sources feed deriveStepStatus; showing skeleton until both are ready prevents flash of incomplete timeline

## Verification
[x] Route `/runs/:runId` renders run header with pipeline_name, status badge, run_id, and timing
[x] StepTimeline receives derived items from deriveStepStatus
[x] Clicking step calls selectStep from useUIStore
[x] StepDetailPanel wired with runId, selectedStepId, stepDetailOpen, closeStepDetail
[x] ContextEvolution receives context?.snapshots
[x] useWebSocket(runId) called at top level
[x] Back link to '/' using TanStack Router Link
[x] Loading skeleton shown while useRun loading
[x] 404 "Run not found" with back link on error
[x] run?.status as string for useSteps/useEvents; cast to RunStatus for useRunContext
[x] TypeScript build passes with no errors
