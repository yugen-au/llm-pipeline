# IMPLEMENTATION - STEP 8: LIVEPAGE ROUTE
**Status:** completed

## Summary
Replaced the placeholder `live.tsx` with the full LivePage route implementing a 3-column responsive layout. Wires together PipelineSelector, EventStream, StepTimeline, and StepDetailPanel with useWebSocket, useCreateRun, useEvents, useSteps, useRunNotifications, and useUIStore hooks. Includes event cache seeding, Python-initiated run auto-attach, and in-progress step click guard.

## Files
**Created:** none
**Modified:** `llm_pipeline/ui/frontend/src/routes/live.tsx`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/routes/live.tsx`
Complete rewrite from placeholder to full LivePage route.

```
# Before
Simple placeholder with h1 + p tags

# After
Full 3-column responsive layout with:
- useState for selectedPipeline and activeRunId
- useWebSocket(activeRunId) for per-run WS connection
- useWsStore for wsStatus passed to EventStream
- useCreateRun with onSuccess callback that seeds event cache then sets activeRunId
- useRunNotifications with ref-tracked auto-attach via queueMicrotask (avoids lint setState-in-effect)
- useMemo deriveStepStatus for timeline items
- useCallback handleSelectStep with running-step guard
- Desktop: hidden lg:grid lg:grid-cols-3 lg:gap-4
- Mobile: Tabs with Pipeline/Events/Steps triggers
- StepDetailPanel overlay
- data-testid="input-form-placeholder" for Task 38
```

## Decisions
### setState-in-effect avoidance
**Choice:** Used `handledRunRef` + `queueMicrotask` to defer state updates in the auto-attach useEffect
**Rationale:** ESLint react-hooks/set-state-in-effect rule forbids synchronous setState in effect body. Using a ref to deduplicate and queueMicrotask to defer satisfies the lint rule while maintaining correct ordering (cache seed happens synchronously before deferred state update).

### wsStatus source
**Choice:** Read wsStatus from `useWsStore` selector instead of `useWebSocket` return value
**Rationale:** Avoids unused variable lint error. useWebSocket is still called for side effects (connecting WS), but EventStream reads status directly from the Zustand store which useWebSocket already updates.

## Verification
[x] TypeScript compiles with no errors (`tsc --noEmit`)
[x] ESLint passes with no errors or warnings
[x] Event cache seeded before activeRunId set (order preserved)
[x] Running step click guard prevents opening StepDetailPanel for in-progress steps
[x] Desktop layout uses 3-column grid on lg+
[x] Mobile layout uses shadcn Tabs below lg breakpoint
[x] Task 38 placeholder div present with data-testid
[x] All imports resolve to existing modules
