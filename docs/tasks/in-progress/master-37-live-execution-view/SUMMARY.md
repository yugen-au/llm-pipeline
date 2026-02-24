# Task Summary

## Work Completed

Implemented the Live Execution View at `/live`: a 3-column responsive page where users select a pipeline, trigger a run, watch real-time events in a scrolling event stream, and see a live-updating step timeline. Backend extended `ConnectionManager` with global subscriber support and a new `/ws/runs` WebSocket endpoint; `trigger_run()` broadcasts `run_created` notifications so the UI auto-attaches to runs started externally by Python. Frontend built `useRunNotifications`, `PipelineSelector`, and `EventStream` from scratch, then wired them with the existing `StepTimeline`/`StepDetailPanel` in a replacement `live.tsx`. A review fix cycle addressed 5 issues (1 medium thread safety, 4 low UX/optimization), including derived run status for polling, `cursor-not-allowed` on in-progress steps, and an ES2020 compatibility fix for `Array.findLast`.

## Files Changed

### Created

| File | Purpose |
| --- | --- |
| `llm_pipeline/ui/frontend/src/api/useRunNotifications.ts` | WebSocket hook connecting to `/ws/runs`; returns `latestRun` for auto-attach to Python-initiated runs |
| `llm_pipeline/ui/frontend/src/components/live/PipelineSelector.tsx` | Pipeline selector using `usePipelines()` with loading/empty/error states and shadcn Select |
| `llm_pipeline/ui/frontend/src/components/live/EventStream.tsx` | Scrollable event stream with auto-scroll-to-bottom, pause-on-scroll-up, connection status indicator, and event type badges |

### Modified

| File | Changes |
| --- | --- |
| `llm_pipeline/ui/routes/websocket.py` | Added `_global_queues` list, `connect_global`/`disconnect_global`/`broadcast_global` methods, `/ws/runs` WebSocket endpoint; thread-safety fix (list copy before iteration in all broadcast paths) |
| `llm_pipeline/ui/routes/runs.py` | Added `ws_manager.broadcast_global(run_created_payload)` call in `trigger_run()` after `run_id` generation, before background task |
| `llm_pipeline/ui/frontend/src/api/types.ts` | Added `WsRunCreated` interface (standalone, not part of `WsMessage` union) |
| `llm_pipeline/ui/frontend/src/routes/live.tsx` | Full replacement of placeholder: 3-column responsive layout, all state wiring, event cache seeding, `deriveRunStatus()` for derived run status, Task 38 input form placeholder |
| `llm_pipeline/ui/frontend/src/components/runs/StepTimeline.tsx` | Added `cursor-not-allowed opacity-70` and `title="Step still in progress"` native tooltip for running steps |

## Commits Made

| Hash | Message |
| --- | --- |
| `3377245` | docs(implementation-A): master-37-live-execution-view |
| `733e053` | docs(implementation-A): master-37-live-execution-view |
| `bbe7b33` | docs(implementation-A): master-37-live-execution-view |
| `4a464e5` | docs(implementation-B): master-37-live-execution-view |
| `1c25c35` | docs(implementation-B): master-37-live-execution-view |
| `1befe99` | docs(implementation-B): master-37-live-execution-view |
| `167025e` | docs(implementation-C): master-37-live-execution-view |
| `59021af` | docs(fixing-review-A): master-37-live-execution-view |
| `ac2b86a` | docs(fixing-review-B): master-37-live-execution-view |
| `8813b6f` | docs(fixing-review-C): master-37-live-execution-view |
| `16fdbac` | chore(state): master-37-live-execution-view -> testing |
| `6e81d76` | chore(state): master-37-live-execution-view -> review |
| `384c635` | chore(state): master-37-live-execution-view -> review |
| `b8d0aee` | chore(state): master-37-live-execution-view -> summary |

## Deviations from Plan

- PLAN.md step 8 specified showing a tooltip "Step in progress" on running step click via a `runStatus` prop to `StepDetailPanel`. Implementation instead added `cursor-not-allowed opacity-70` and a native `title` tooltip to `StepTimeline.tsx` directly (shared component), which also benefits the run detail page. The `StepDetailPanel` receives derived `runStatus` via a new `deriveRunStatus()` function added in the fix cycle.
- PLAN.md specified seeding the event cache with `queryClient.setQueryData` in `useCreateRun` `onSuccess`. Implementation placed this in a `handleRunPipeline` handler in `live.tsx` instead, which calls `queryClient.setQueryData` then `setActiveRunId` in order -- semantically identical, slightly cleaner separation.
- `Array.findLast` (ES2023) appeared in `deriveRunStatus()` in the initial implementation; replaced with a reverse `for` loop for ES2020 compatibility during the testing phase.

## Issues Encountered

### Thread safety of `_global_queues` list iteration during concurrent mutation (MEDIUM)
**Resolution:** All three iteration sites in `websocket.py` (`broadcast_to_run`, `signal_run_complete`, `broadcast_global`) now copy the list with `list(...)` before iterating. This is a snapshot immune to concurrent append/remove and is the standard Python pattern for thread-safe iteration.

### Radix ScrollArea internal `data-slot` selector coupling (LOW)
**Resolution:** Replaced `node.querySelector('[data-slot="scroll-area-viewport"]')` in `EventStream.tsx` with a `contentRef` on the inner div and `parentElement` traversal. No Radix-internal selectors remain; approach is reliable per Radix DOM structure.

### `StepDetailPanel` receiving `runStatus={undefined}` (LOW)
**Resolution:** Added `deriveRunStatus()` function in `live.tsx` that maps `WsConnectionStatus` and cached event data to `RunStatus`. Passed to `StepDetailPanel` so staleTime optimization and polling apply correctly.

### Silent no-op on running step click (LOW)
**Resolution:** Added `cursor-not-allowed opacity-70` styling and `title="Step still in progress"` native tooltip to running step rows in `StepTimeline.tsx`. `console.info` in `live.tsx` provides dev-level feedback.

### `useEvents`/`useSteps` REST polling disabled (LOW)
**Resolution:** Both hooks now receive `runStatus` from `deriveRunStatus`. When status is `'running'`, hooks enable `refetchInterval: 3_000` as a REST polling safety net alongside WebSocket updates.

### `Array.findLast` ES2023 incompatibility (HIGH, blocked build)
**Resolution:** Replaced with a reverse `for` loop equivalent in `deriveRunStatus()`. TypeScript compiles cleanly against the ES2020 `tsconfig.app.json` target.

## Success Criteria

- [x] `ConnectionManager` extended with `connect_global`/`disconnect_global`/`broadcast_global` (sync, thread-safe via list copy)
- [x] `/ws/runs` WebSocket endpoint registered before `/ws/runs/{run_id}` to avoid route shadowing
- [x] `trigger_run()` broadcasts `run_created` after `run_id` generation, before background task start
- [x] `WsRunCreated` interface added to `types.ts`, standalone (not in `WsMessage` union)
- [x] `useRunNotifications` hook manages its own WebSocket with exponential backoff reconnect
- [x] `PipelineSelector` handles loading/empty/error/data states using `usePipelines()`
- [x] "Run Pipeline" button disabled when `!selectedPipeline || createRun.isPending`
- [x] Event cache seeded before `setActiveRunId` to prevent WS events dropped by `appendEventToCache`
- [x] `EventStream` auto-scrolls to bottom; pauses on scroll-up, resumes on scroll-to-bottom
- [x] Running step click guard: `handleSelectStep` returns early when `item?.status === 'running'`
- [x] 3-column desktop layout (`hidden lg:grid lg:grid-cols-3`); tab-based mobile layout (`flex lg:hidden`)
- [x] Python-initiated run auto-attach via `useEffect` watching `latestRun` from `useRunNotifications`
- [x] Task 38 input form placeholder (`data-testid="input-form-placeholder"`) present in live.tsx
- [x] No TypeScript errors (0 errors, `npm run type-check`)
- [x] No new ESLint warnings in task 37 files (0 errors, 0 warnings)
- [x] Circular import check passes (`from llm_pipeline.ui.routes.runs import trigger_run`)
- [x] 766/767 Python tests pass (1 pre-existing unrelated failure in `test_events_router_prefix`)
- [ ] `/ws/runs` heartbeat delivery (requires live server - human validation)
- [ ] `run_created` broadcast timing vs POST /api/runs response (requires live server - human validation)
- [ ] EventStream real-time events and auto-scroll behavior (requires live server - human validation)
- [ ] StepTimeline live updates during pipeline execution (requires live server - human validation)
- [ ] Python-initiated run auto-attach end-to-end (requires live server - human validation)

## Recommendations for Follow-up

1. Fix pre-existing `test_events_router_prefix` failure in `tests/test_ui.py`: update assertion from `'/events'` to `'/runs/{run_id}/events'` to match actual router prefix set in task 19/28.
2. Add unit tests for `ConnectionManager.connect_global`, `disconnect_global`, and `broadcast_global` -- the methods are functional but have no dedicated test coverage.
3. Add a vitest unit test for `useRunNotifications` hook to verify reconnect backoff logic and message parsing without a real WebSocket server (mirrors existing tests for `useWebSocket`).
4. Task 38 input form: the placeholder `<div data-testid="input-form-placeholder" />` in `live.tsx` at column 1 is ready for the input form component. Column 1 currently shows only the pipeline selector and run button.
5. Consider adding a `threading.Lock` to `ConnectionManager` for the `_global_queues` list if subscriber counts scale beyond a handful of concurrent clients. Current list-copy approach handles CPython GIL-level safety; an explicit lock would be language-agnostic and audit-friendly.
6. The `Radix ScrollArea parentElement` traversal in `EventStream.tsx` is reliable for current Radix UI versions but should be noted in code review: if Radix changes its viewport DOM nesting depth, auto-scroll detection would silently break. A ref on a sentinel div at list bottom (without ScrollArea viewport detection) would be the most robust long-term approach.
