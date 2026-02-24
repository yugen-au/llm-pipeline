# Research Summary

## Executive Summary

Cross-referenced both research files against actual source code. 11 claims validated via code inspection. 3 blocking architectural decisions require CEO input before planning: (1) factory execute() argument binding pattern, (2) input form scope boundary between Task 37 and 38, (3) Python-initiated run detection mechanism. Additionally identified 5 engineering-level gaps the research did not explicitly surface: event cache seeding race condition, StepDetailPanel degraded UX for in-progress steps, WS status naming inconsistency, premature virtualization assumption, and mobile responsiveness scope.

## Domain Findings

### Backend API & Pipeline Execution
**Source:** step-2-backend-websocket-research.md, runs.py, pipeline.py

- `trigger_run()` (runs.py L214) calls `pipeline.execute()` with NO arguments
- `pipeline.execute()` (pipeline.py L424) requires positional `data: Any` and `initial_context: Dict[str, Any]`
- Factory docstring says returned object exposes `.execute()` and `.save()` -- unclear if factories pre-bind args
- `TriggerRunRequest` (runs.py L60-61) only has `pipeline_name` field -- no input_data or initial_context
- Frontend `TriggerRunRequest` type (types.ts L62-64) mirrors backend exactly -- only pipeline_name

### WebSocket Infrastructure
**Source:** step-2-backend-websocket-research.md, websocket.py, bridge.py, websocket.ts

- ConnectionManager singleton at module level with sync broadcast_to_run() -- VALIDATED
- UIBridge sync adapter implementing PipelineEventEmitter protocol -- VALIDATED
- Three WS behaviors (not-found/replay/live-stream) -- VALIDATED per websocket.py L106-149
- Frontend WsMessage 5-variant union matches backend message types -- VALIDATED
- useWebSocket reconnect logic with exponential backoff -- VALIDATED

### Frontend Component Reuse
**Source:** step-1-frontend-architecture-research.md, StepTimeline.tsx, StepDetailPanel.tsx

- StepTimeline props: `{ items, isLoading, isError, selectedStepId, onSelectStep }` -- VALIDATED, directly reusable
- deriveStepStatus merges DB steps + events -- VALIDATED, logic correct
- StepDetailPanel props: `{ runId, stepNumber, open, onClose, runStatus? }` -- VALIDATED
- StepDetailPanel fetches from DB internally (useStep -> GET /api/runs/{run_id}/steps/{step_number}) -- in-progress steps have no DB row yet, will show error/loading state

### Event Cache Integration
**Source:** websocket.ts L102-110

- `appendEventToCache()` only updates existing cache entries (returns undefined if no old data)
- For UI-triggered runs, WS events may arrive before `useEvents()` has populated the cache
- Live View must call `useEvents(runId)` to seed cache before WS connection streams events

### Existing Route & Component State
**Source:** live.tsx, types.ts, project structure

- `/live` route exists as placeholder (live.tsx) -- ready for replacement
- All needed shadcn/ui components installed: select, scroll-area, button, card, badge, sheet, tabs
- No EventStream component exists -- must be created from scratch
- No PipelineSelector component exists -- must be created from scratch

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Q1: Do registered factories pre-bind data/initial_context into execute(), or must trigger_run() forward these as args? | PENDING | Determines if Task 37 needs backend TriggerRunRequest extension or just a simple "Run" button |
| Q2: Should Task 37 build just a placeholder slot for the input form (with simple "Run Pipeline" button), leaving Task 38 to add the actual dynamic form? | PENDING | Determines left-column scope and whether backend changes are needed in Task 37 |
| Q3: For Python-initiated run detection, which mechanism: (a) poll GET /api/runs?status=running, (b) new global WS endpoint, (c) defer to later task? | PENDING | Determines if Task 37 needs backend work for a global WS endpoint or can use simple polling |
| Q4: Is mobile responsiveness required for the Live View, or is desktop-first acceptable? | PENDING | Determines layout complexity and responsive breakpoint work |

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
- [x] TriggerRunRequest only has pipeline_name (confirmed backend + frontend types match)

## Open Items
- Factory execute() argument binding -- determines entire input form + backend extension scope
- Python-initiated run detection mechanism -- no current infrastructure for real-time discovery
- StepDetailPanel shows error/loading for in-progress steps (PipelineStepState written only after step completion) -- needs UX decision: disable click on running steps, or show "in progress" message
- useWebSocket sets status to 'replaying' on first pipeline_event even during live streams (naming inconsistency) -- cosmetic, but may confuse UI state consumers
- Event cache race condition -- useEvents() must populate cache before WS events arrive via appendEventToCache
- react-window virtualization may be premature -- typical pipeline runs have <100 events

## Recommendations for Planning
1. Get CEO answers to Q1-Q3 before creating implementation plan -- they materially affect scope
2. If factories pre-bind execute() args: Task 37 needs only a "Run Pipeline" button, no backend changes
3. If factories do NOT pre-bind: Task 37 needs at minimum a JSON textarea + TriggerRunRequest.input_data extension, blurring boundary with Task 38
4. For Python-initiated runs: start with polling (simplest, no backend changes), upgrade to global WS later if needed
5. Seed event cache by calling useEvents(runId) before/alongside useWebSocket(runId)
6. Add "Step in progress" guard in Live View when user clicks a running step in timeline
7. Start EventStream as simple scrolling div; add react-window only if performance testing warrants it
8. Desktop-first layout; add responsive breakpoints only if CEO confirms mobile need
