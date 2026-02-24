# Research Summary

## Executive Summary

Both research documents (step-1 codebase architecture, step-2 API & data layer) are verified accurate against actual source code. All frontend hooks, TypeScript types, Zustand store shape, route placeholder, and backend API endpoints match their documented descriptions exactly. The 4 non-blocking gaps identified in step-2 are confirmed real. Three scope ambiguities were resolved via CEO decisions: (1) StepTimeline WILL show running step via WS event correlation, (2) ContextEvolution shows raw JSON only -- diff deferred to task 36, (3) useWebSocket WILL be wired in task 34 for live updates.

## Domain Findings

### Frontend Architecture (Verified)
**Source:** research/step-1-codebase-architecture-research.md

- Route `runs/$runId.tsx` exists as placeholder with Zod search schema (`tab` param, default 'steps') -- will UPDATE, not create
- All 6 hooks verified in source: useRun, useRunContext, useSteps, useStep, useEvents, useWebSocket -- signatures and return types match exactly
- useUIStore: selectedStepId (number|null), stepDetailOpen (boolean), selectStep, closeStepDetail -- all verified
- All TypeScript interfaces in types.ts match research descriptions field-by-field
- Task 33 patterns confirmed: named function exports, Tailwind-only styling, cn() utility, loading/error/empty state pattern, route-agnostic callbacks
- Deviation correctly noted: task description says `useContextEvolution` but actual hook is `useRunContext`
- Deviation correctly noted: route file already exists (task 30), not to be created fresh

### Backend API & Data Layer (Verified)
**Source:** research/step-2-api-data-layer-research.md

- All 7 endpoints verified against source (runs.py, steps.py, events.py, websocket.ts): response models, query params, and shapes match exactly
- Backend Pydantic response models match frontend TypeScript interfaces field-by-field
- PipelineStepState DB model confirmed: no status column, steps only recorded post-completion
- Event system: 27 event types across 9 categories, step-scoped events carry step_name in event_data
- Events API confirmed: filters by event_type only, no step_name filter param

### Identified Gaps (All Confirmed)
**Source:** research/step-2-api-data-layer-research.md

1. **Events API lacks step_name filter** -- Confirmed in events.py. EventListParams only has event_type, offset, limit. Impact deferred to task 35 (client-side filtering).
2. **No explicit step status field** -- Confirmed. PipelineStepState has no status column. Steps appear in DB only after completion. Live status requires WS event correlation.
3. **Rendered prompts not in StepDetail** -- Confirmed. StepDetail has prompt keys (prompt_system_key, prompt_user_key) but NOT rendered text. Rendered prompts only in LLMCallStarting events. Impact deferred to task 35 Prompts tab.
4. **StepSummary vs StepListItem redundancy** -- Confirmed. StepSummary (in RunDetail) lacks `model` field. StepListItem (from /steps endpoint) has it. Use useSteps for richer data.

### Cross-Document Inconsistency Found
**Source:** Both research docs

- **useRunContext caching behavior**: Doc 1 implies similar polling behavior to useSteps. Actual code: `staleTime: Infinity` for terminal, `30_000` for active, NO refetchInterval (no polling). Context evolution for active runs only refreshes on manual refetch or query invalidation, not automatically. This means ContextEvolution panel for live runs will be stale up to 30s unless WS is wired.

### Missing from Research
**Source:** Cross-referencing source code

1. **formatDuration utility**: RunsTable has private `formatDuration(ms)`. StepTimeline will need the same. Should be extracted to `src/lib/time.ts` during task 34.
2. **WebSocket step cache invalidation**: websocket.ts already invalidates `queryKeys.runs.steps(runId)` on step-scoped events. If useWebSocket is wired in task 34, StepTimeline gets near-real-time updates for free.
3. **Pipeline introspection unavailable**: Pipelines API is empty stub (confirmed in Graphiti memory). Cannot determine expected step count for running pipelines. StepTimeline can only show completed steps, not "upcoming" steps.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| 1. Should StepTimeline show "currently running" step for live runs (via WS event correlation), or only show completed steps as they appear in DB? | INCLUDE RUNNING STEP -- correlate StepStarted/StepCompleted WS events to show in-progress step | Task 34 must derive step status from WS events: StepStarted without matching StepCompleted = "running". Adds WS event correlation logic to StepTimeline. |
| 2. Task 34 ContextEvolution: raw JSON snapshots only (no diff), or basic inline diff? Task description says "JSON diff panel" but task 36 is specifically for JsonDiff component. | RAW SNAPSHOTS ONLY -- task 36 explicitly creates JsonDiff with deep-diff/jsondiffpatch and upgrades ContextEvolution with color-coded diff | Task 34 ContextEvolution shows raw JSON per step. No diff logic. Task 36 adds diff highlighting as a separate component. |
| 3. Should task 34 wire useWebSocket(runId) for live step updates? Code exists, provides free real-time step list updates via query invalidation. | YES -- existing code, low effort, enables live updates | Wire useWebSocket(runId) in RunDetailPage. Steps query cache auto-invalidated on step-scoped WS events. Context query can also be invalidated on context_updated events. |

## Assumptions Validated
- [x] Route file `runs/$runId.tsx` exists as placeholder ready to populate (verified in source)
- [x] All TanStack Query hooks exist with correct signatures and return types (verified: useRun, useRunContext, useSteps, useStep, useEvents, useWebSocket)
- [x] TypeScript interfaces in types.ts mirror backend Pydantic models exactly (verified field-by-field)
- [x] useUIStore has selectStep(number|null) and closeStepDetail() for panel state (verified in source)
- [x] Dynamic staleTime pattern (Infinity for terminal, shorter for active) is implemented consistently across hooks (verified)
- [x] StatusBadge accepts `RunStatus | (string & {})` and can be reused for step status indicators (verified)
- [x] Task 33 established patterns: named function exports, interface above component, Tailwind-only, cn(), loading/error/empty states (verified via RunsTable, StatusBadge source)
- [x] shadcn/ui components installed: table, badge, button, select, tooltip. NOT installed: Card, Separator, ScrollArea, Sheet, Tabs, Skeleton (verified via components/ui/ directory listing)
- [x] Backend steps are only written to DB after completion -- no in-progress step state in DB (verified in step-2 research and PipelineStepState model)
- [x] Events API filters by event_type only, no step_name filter (verified in events.py)
- [x] Scope split: task 35 = full 7-tab StepDetailPanel, task 36 = JsonDiff component (verified via Task Master task descriptions)

## Open Items
- formatDuration extraction to shared utility (non-blocking, implement during task 34)
- StatusBadge extension for step-specific statuses like 'skipped', 'pending', 'running' (design decision, non-blocking -- extend existing component)
- shadcn/ui component installation: Card, Separator, ScrollArea needed for task 34; Sheet/Tabs deferred to task 35
- WS event correlation logic for step status derivation: need to track StepStarted events that lack a matching StepCompleted to derive "running" state. Implementation detail to resolve during planning.

## Recommendations for Planning
1. Extract `formatDuration(ms)` from RunsTable to `src/lib/time.ts` as first implementation step -- both RunsTable and StepTimeline need it
2. Wire `useWebSocket(runId)` in RunDetailPage (CEO approved) -- provides free real-time step list updates via existing query cache invalidation in websocket.ts
3. Use `useSteps(runId, run.status)` (not `useRun.steps`) for StepTimeline data source -- StepListItem includes `model` field that StepSummary lacks
4. Install shadcn Card + Separator for run header layout; ScrollArea for ContextEvolution panel; defer Sheet + Tabs to task 35
5. StepDetailPanel in task 34 should be a minimal slide-over container (step name, number, model, timing) that task 35 replaces with full tabbed implementation
6. Step status derivation (CEO approved): terminal runs = all DB steps "completed", derive "skipped" from StepSkipped events. Active runs = correlate StepStarted/StepCompleted WS events to show "running" step. Steps not yet started are "pending" (only meaningful if pipeline step count is known -- currently unavailable from pipelines API stub).
7. ContextEvolution: show step_name headers with collapsible raw JSON per snapshot. NO diff logic -- task 36 adds JsonDiff component with color-coded diff highlighting.
8. Follow task 33 testing patterns: component-level tests with vitest + testing-library, fake timers for timestamps, polyfills for Radix components in jsdom
9. WS event correlation for step status: subscribe to WS event cache (useEvents query data), scan for step_started/step_completed event_types, derive which step is currently running. Consider a small `useStepStatuses(runId)` hook or inline derivation in StepTimeline.
