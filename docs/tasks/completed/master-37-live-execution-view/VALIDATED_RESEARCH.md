# Research Summary

## Executive Summary

Cross-referenced both research files against actual source code. 11 claims validated via code inspection. All 4 blocking architectural questions answered by CEO. Key outcomes: (1) factories pre-bind execute() args -- no backend TriggerRunRequest extension needed, (2) Task 37 builds placeholder input slot with simple Run button -- Task 38 handles dynamic form, (3) new global WS endpoint `/ws/runs` needed for Python-initiated run detection, (4) responsive layout required (mobile + tablet). Additionally identified 5 engineering-level gaps not flagged by research: event cache seeding race condition, StepDetailPanel degraded UX for in-progress steps, WS status naming inconsistency, global WS limitation for external Python runs, and premature virtualization assumption.

## Domain Findings

### Backend API & Pipeline Execution
**Source:** step-2-backend-websocket-research.md, runs.py, pipeline.py

- `trigger_run()` (runs.py L214) calls `pipeline.execute()` with NO arguments -- CONFIRMED INTENTIONAL
- Factory contract: returns object with no-arg `.execute()` and `.save()` -- factories pre-bind data/initial_context at construction
- `TriggerRunRequest` (runs.py L60-61) only has `pipeline_name` -- sufficient for Task 37, Task 38 extends if needed
- Research flagged this as "CRITICAL GAP" -- actually intentional design, not a gap
- `app.py` docstring (L30-33) confirms factory signature: `(run_id, engine) -> pipeline` with no data/context args

### WebSocket Infrastructure
**Source:** step-2-backend-websocket-research.md, websocket.py, bridge.py, websocket.ts

- ConnectionManager singleton at module level with sync broadcast_to_run() -- VALIDATED
- UIBridge sync adapter implementing PipelineEventEmitter protocol -- VALIDATED
- Three WS behaviors (not-found/replay/live-stream) -- VALIDATED per websocket.py L106-149
- Frontend WsMessage 5-variant union matches backend message types -- VALIDATED
- useWebSocket reconnect logic with exponential backoff -- VALIDATED
- ConnectionManager keyed by run_id only -- no global subscriber support yet (new work for Task 37)

### Global WS Endpoint (NEW -- CEO decision)
**Source:** CEO answer Q3, websocket.py, bridge.py analysis

- CEO decided: new `/ws/runs` global WS endpoint broadcasting run-creation notifications
- ConnectionManager needs extension: separate "global subscribers" list alongside per-run subscribers
- Message format needed: `{ type: "run_created", run_id, pipeline_name, started_at }`
- Hook point: when PipelineRun row is created (inside pipeline.execute() via event emitter, or in trigger_run())
- LIMITATION: Global WS only detects runs going through the FastAPI server (via trigger_run). Runs started by external Python processes (direct pipeline.execute() calls writing to same SQLite DB) have no in-process UIBridge -- global WS cannot detect these without DB polling fallback
- Frontend needs new hook: `useRunNotifications()` consuming `/ws/runs`

### Frontend Component Reuse
**Source:** step-1-frontend-architecture-research.md, StepTimeline.tsx, StepDetailPanel.tsx

- StepTimeline props: `{ items, isLoading, isError, selectedStepId, onSelectStep }` -- VALIDATED, directly reusable
- deriveStepStatus merges DB steps + events -- VALIDATED, logic correct
- StepDetailPanel props: `{ runId, stepNumber, open, onClose, runStatus? }` -- VALIDATED, reusable
- StepDetailPanel caveat: fetches from DB internally (useStep -> GET /api/.../steps/{step_number}). PipelineStepState rows are written only AFTER step completion. Clicking a "running" step shows error/loading state -- needs graceful handling
- StatusBadge -- VALIDATED, directly reusable

### Event Cache Integration
**Source:** websocket.ts L102-110

- `appendEventToCache()` only updates existing cache entries (returns undefined if no old data)
- Race condition: for UI-triggered runs, WS events may arrive before `useEvents()` has populated the cache
- Fix: seed cache with empty `{ items: [], total: 0 }` entry immediately when run is created, before WS connects

### Layout & Responsiveness
**Source:** CEO answer Q4, step-1-frontend-architecture-research.md

- CEO confirmed: responsive required -- must work on mobile and tablet
- Research mentioned "collapse to single column on mobile" -- correct direction
- Recommended approach: `grid grid-cols-1 lg:grid-cols-3` with tab-based navigation on small screens to switch between pipeline selector, event stream, and step timeline panels
- Existing pattern: root layout uses sidebar (240px) + main content. Live view goes in main content area.

### Existing Route & Component State
**Source:** live.tsx, types.ts, project structure

- `/live` route exists as placeholder (live.tsx) -- ready for replacement
- All needed shadcn/ui components installed: select, scroll-area, button, card, badge, sheet, tabs
- No EventStream component exists -- must be created from scratch
- No PipelineSelector component exists -- must be created from scratch

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Q1: Do registered factories pre-bind data/initial_context into execute(), or must trigger_run() forward these as args? | Factories pre-bind. Evidence: trigger_run() calls execute() with zero args, factory contract documented as no-arg .execute(), all test factories confirm. | No backend TriggerRunRequest extension needed for Task 37. Research "CRITICAL GAP" reclassified as intentional design. Task 38 extends factory signature if user input needed. |
| Q2: Should Task 37 build just a placeholder slot for the input form (simple "Run Pipeline" button), leaving Task 38 to add the actual dynamic form? | Placeholder only. Simple "Run Pipeline" button with no input fields. | Left column scope is minimal: PipelineSelector + Run button. Clean scope boundary with Task 38. No schema introspection or form generation in Task 37. |
| Q3: For Python-initiated run detection: (a) poll, (b) new global WS, (c) defer? | Global WS endpoint. Build new /ws/runs that broadcasts run-creation notifications. | Adds backend scope: extend ConnectionManager with global subscribers, new WS endpoint, new message type. Frontend needs new useRunNotifications() hook. Most complex new backend work in Task 37. |
| Q4: Is mobile responsiveness required for Live View, or desktop-first acceptable? | Responsive required. Must work well on mobile and tablet. | 3-column grid must collapse responsively. Recommend tab-based navigation on small screens. Adds UI complexity but standard Tailwind responsive work. |

## Assumptions Validated
- [x] WebSocket endpoint at /ws/runs/{run_id} exists and works per research description
- [x] ConnectionManager singleton with sync broadcast_to_run/signal_run_complete
- [x] UIBridge auto-detects terminal events and sends None sentinel
- [x] WsMessage discriminated union (5 variants) matches backend message format
- [x] StepTimeline component reusable with documented props interface
- [x] deriveStepStatus correctly merges DB steps with WS events
- [x] StepDetailPanel reusable as Sheet overlay with documented props
- [x] Pipeline list data available via GET /api/pipelines with usePipelines() hook
- [x] /live route exists as placeholder ready for replacement
- [x] All needed shadcn/ui components already installed
- [x] TriggerRunRequest only has pipeline_name -- sufficient for Task 37 (factories pre-bind args)
- [x] Factory execute() pre-binds data/initial_context -- no-arg .execute() is intentional design
- [x] useCreateRun() mutation exists and returns { run_id, status } -- ready for Live View integration
- [x] Vite proxy config routes /ws to backend -- WS connections work in dev

## Open Items
- Global WS endpoint scope: only detects runs through FastAPI server, not external Python processes writing directly to SQLite. If external detection is needed later, DB polling fallback would supplement global WS
- StepDetailPanel shows error/loading for in-progress steps (PipelineStepState written only after step completion) -- Live View should either disable click on running steps or show "Step in progress" message derived from events
- useWebSocket sets status to 'replaying' on first pipeline_event even during live streams -- cosmetic naming inconsistency, low priority
- Event cache must be seeded (empty entry) before WS connection to avoid appendEventToCache silently dropping events
- react-window virtualization likely premature -- typical pipeline runs have <100 events, start with simple ScrollArea
- Responsive layout detail: how to handle StepDetailPanel Sheet overlay on mobile (full-screen sheet vs inline panel)

## Recommendations for Planning
1. Split Task 37 into clear sub-tasks: (a) backend global WS, (b) PipelineSelector + Run button, (c) EventStream component, (d) 3-column responsive layout + integration, (e) Python-initiated run auto-attach flow
2. Backend first: extend ConnectionManager with global subscriber support, add /ws/runs endpoint, wire run_created broadcast into trigger_run()
3. Frontend new hook: useRunNotifications() connecting to /ws/runs, returning latest run_created notifications
4. Left column: PipelineSelector dropdown (usePipelines) + "Run Pipeline" button (useCreateRun) + placeholder div for Task 38 InputForm
5. Center column: new EventStream component with auto-scroll, pause-on-scroll-up, event type badges. Start simple with ScrollArea, add virtualization only if profiling shows need
6. Right column: reuse StepTimeline + StepDetailPanel from Task 35. Guard in-progress step clicks with "Step in progress" state
7. Seed event cache with empty entry immediately on run creation, before useWebSocket connects
8. Responsive: 3-col grid on lg+, tabbed panel switcher on md/sm with tab labels "Pipeline" / "Events" / "Steps"
9. Wire Python-initiated run flow: useRunNotifications detects new run -> prompt user or auto-attach -> setRunId -> useWebSocket connects
10. No TriggerRunRequest backend changes -- factories handle data binding
