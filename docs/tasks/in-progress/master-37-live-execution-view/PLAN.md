# PLANNING

## Summary

Implement the Live Execution View: a 3-column responsive page (`/live`) where users select a pipeline, trigger a run, watch real-time events in an event stream, and see a live step timeline. Backend adds a new global `/ws/runs` WebSocket endpoint that broadcasts `run_created` notifications so the UI can auto-attach to runs started by Python. Frontend builds `PipelineSelector`, `EventStream`, and `useRunNotifications` hook, composes them with the existing `StepTimeline`/`StepDetailPanel` from task 35, and replaces the live.tsx placeholder.

## Plugin & Agents

**Plugin:** frontend-mobile-development + backend-development
**Subagents:** frontend-mobile-development:frontend-developer, backend-development:backend-architect
**Skills:** none

## Phases

1. **Group A - Backend global WS**: Extend `ConnectionManager` with global subscribers and add `/ws/runs` endpoint + `run_created` broadcast in `trigger_run()`
2. **Group B - Frontend hooks & components**: Build `useRunNotifications` hook, `PipelineSelector` component, `EventStream` component (all concurrent, no file overlap)
3. **Group C - Route integration**: Assemble the 3-column responsive layout in `live.tsx`, wire all state together, seed event cache on run creation

## Architecture Decisions

### Global WS on ConnectionManager vs separate class
**Choice:** Extend `ConnectionManager` with a `_global_queues` list alongside per-run `_queues`; add `connect_global`/`disconnect_global`/`broadcast_global` methods (all sync, using `queue.Queue.put_nowait`).
**Rationale:** Follows existing pattern exactly (sync `put_nowait` is thread-safe from pipeline background thread). Keeps one singleton managing all WS state. No new imports or infrastructure.
**Alternatives:** Separate `GlobalConnectionManager` class -- unnecessary complexity, two singletons to import.

### run_created broadcast hook point
**Choice:** Broadcast `run_created` inside `trigger_run()` in `runs.py`, after `run_id` is generated and before `background_tasks.add_task()`. Import `manager` singleton from `websocket.py`.
**Rationale:** `trigger_run()` is the only place UI-initiated runs are created. Broadcast happens synchronously in the request handler before the background task starts, ensuring global subscribers receive the notification before WS events begin arriving.
**Alternatives:** Broadcast from inside `run_pipeline()` background task -- introduces a race where WS events could arrive before `run_created`; broadcast from UIBridge -- UIBridge only knows run_id, not pipeline_name/started_at.

### Event cache seeding
**Choice:** In the `useCreateRun` mutation `onSuccess` callback, call `queryClient.setQueryData(queryKeys.runs.events(run_id, {}), { items: [], total: 0, offset: 0, limit: 50 })` before `useWebSocket` connects.
**Rationale:** `appendEventToCache` in `websocket.ts` line 106 only updates if `old` data exists (returns `undefined` if no cache entry). Seeding prevents WS events from being silently dropped before the first REST `useEvents` fetch completes.
**Alternatives:** Change `appendEventToCache` to create an entry if none exists -- modifies shared hook used by `$runId.tsx`, riskier change to tested code.

### StepDetailPanel in-progress guard
**Choice:** Pass `runStatus` prop to `StepDetailPanel`; when `runStatus === 'running'` and the clicked step's status is `'running'`, disable the click handler and show a tooltip "Step in progress".
**Rationale:** `PipelineStepState` rows are written only after step completion (validated in VALIDATED_RESEARCH.md). Clicking a running step would show error/loading state in the Sheet. Guard maintains good UX without modifying `StepDetailPanel` internals (just the `onSelectStep` wrapper in live.tsx).
**Alternatives:** Modify `StepDetailPanel` to show "in progress" fallback -- broader change to a tested component; leave unguarded -- poor UX.

### Responsive layout strategy
**Choice:** `grid grid-cols-1 lg:grid-cols-3` for the 3-column layout. On `lg+`, all 3 columns show side by side. On smaller screens, use `Tabs` from shadcn/ui to switch between "Pipeline", "Events", and "Steps" panels.
**Rationale:** CEO confirmed responsive required. All shadcn/ui `Tabs` components already installed (validated in VALIDATED_RESEARCH.md). This matches existing codebase convention (shadcn/ui + Tailwind responsive prefixes).
**Alternatives:** CSS grid with `overflow-x: auto` scroll -- poor mobile UX; drawer/sheet for panels -- more complex, no need.

### useRunNotifications hook
**Choice:** New hook at `src/api/useRunNotifications.ts` connecting to `/ws/runs` global endpoint. Returns `{ latestRun: RunCreatedNotification | null }` where `RunCreatedNotification = { type: 'run_created', run_id: string, pipeline_name: string, started_at: string }`. Manages its own WebSocket lifecycle (connect on mount, reconnect with backoff).
**Rationale:** Follows existing `useWebSocket` pattern but simpler -- no TanStack Query cache integration, just state. Isolated in its own file for clarity and testability.
**Alternatives:** Extend `useWebSocket` to optionally connect to global endpoint -- overcomplicates a hook already handling per-run state.

## Implementation Steps

### Step 1: Extend ConnectionManager with global subscriber support
**Agent:** backend-development:backend-architect
**Skills:** none
**Context7 Docs:** /fastapi/fastapi
**Group:** A

1. In `llm_pipeline/ui/routes/websocket.py`, add `_global_queues: list[thread_queue.Queue]` to `ConnectionManager.__init__` (alongside existing `_connections` and `_queues`).
2. Add method `connect_global(ws: WebSocket) -> thread_queue.Queue`: creates queue, appends to `_global_queues`, returns it.
3. Add method `disconnect_global(queue: thread_queue.Queue) -> None`: removes queue from `_global_queues`; safe to call if not present.
4. Add method `broadcast_global(event_data: dict) -> None`: calls `q.put_nowait(event_data)` for each queue in `_global_queues`. Sync, thread-safe.

### Step 2: Add /ws/runs global WebSocket endpoint
**Agent:** backend-development:backend-architect
**Skills:** none
**Context7 Docs:** /fastapi/fastapi
**Group:** A

1. In `llm_pipeline/ui/routes/websocket.py`, add `@router.websocket("/ws/runs")` handler `async def global_websocket_endpoint(websocket: WebSocket)`.
2. On connect: `await websocket.accept()`, call `manager.connect_global(ws)` to get queue.
3. Stream global events using `_stream_events()` pattern (or inline equivalent): loop reading from queue with heartbeat timeout; `None` sentinel closes the stream.
4. On `WebSocketDisconnect` or error: call `manager.disconnect_global(queue)` in `finally` block.
5. Global stream never sends `None` sentinel (no terminal event for global channel) -- heartbeats keep connection alive until client disconnects.

### Step 3: Wire run_created broadcast into trigger_run
**Agent:** backend-development:backend-architect
**Skills:** none
**Context7 Docs:** /fastapi/fastapi
**Group:** A

1. In `llm_pipeline/ui/routes/runs.py`, import `manager` singleton: `from llm_pipeline.ui.routes.websocket import manager as ws_manager`.
2. After `run_id = str(uuid.uuid4())` is generated and `engine = request.app.state.engine` is obtained, call `ws_manager.broadcast_global({"type": "run_created", "run_id": run_id, "pipeline_name": body.pipeline_name, "started_at": datetime.now(timezone.utc).isoformat()})` before `background_tasks.add_task(run_pipeline)`.
3. Add `RunCreatedNotification` type to `types.ts` frontend: `{ type: 'run_created'; run_id: string; pipeline_name: string; started_at: string }`.

### Step 4: Add WsRunCreated type to frontend types
**Agent:** frontend-mobile-development:frontend-developer
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. In `llm_pipeline/ui/frontend/src/api/types.ts`, add interface `WsRunCreated` at the bottom of the WebSocket message types section: `export interface WsRunCreated { type: 'run_created'; run_id: string; pipeline_name: string; started_at: string }`.
2. This type is standalone (not added to `WsMessage` union which is per-run only).

### Step 5: Implement useRunNotifications hook
**Agent:** frontend-mobile-development:frontend-developer
**Skills:** none
**Context7 Docs:** /tanstack/query, /pmndrs/zustand
**Group:** B

1. Create `llm_pipeline/ui/frontend/src/api/useRunNotifications.ts`.
2. Hook `useRunNotifications()` manages its own WebSocket to `/ws/runs` (build URL using same `buildWsUrl`-style helper but path `/ws/runs`, no run_id segment).
3. Internal state via `useState<WsRunCreated | null>(null)` for `latestRun`.
4. On `onmessage`: parse JSON, if `msg.type === 'run_created'` set `latestRun`. Ignore heartbeats.
5. Reconnect with exponential backoff on unexpected close (same pattern as `useWebSocket`: `hadConnection` ref, backoff timer).
6. Cleanup on unmount: clear timer, close WebSocket.
7. Return `{ latestRun }`.

### Step 6: Implement PipelineSelector component
**Agent:** frontend-mobile-development:frontend-developer
**Skills:** none
**Context7 Docs:** /tanstack/query
**Group:** B

1. Create `llm_pipeline/ui/frontend/src/components/live/PipelineSelector.tsx`.
2. Props: `{ selectedPipeline: string | null; onSelect: (name: string) => void; disabled?: boolean }`.
3. Use `usePipelines()` hook (already exists in `src/api/pipelines.ts`) to fetch pipeline list.
4. Render shadcn/ui `Select` component with pipeline names from `data?.pipelines ?? []`.
5. Show loading skeleton while `isLoading`, error message if `isError`.
6. If `data?.pipelines` is empty, show "No pipelines registered" message.

### Step 7: Implement EventStream component
**Agent:** frontend-mobile-development:frontend-developer
**Skills:** none
**Context7 Docs:** /tanstack/query
**Group:** B

1. Create `llm_pipeline/ui/frontend/src/components/live/EventStream.tsx`.
2. Props: `{ events: EventItem[]; wsStatus: WsConnectionStatus; runId: string | null }`.
3. Use shadcn/ui `ScrollArea` for event list container with fixed height (fills column).
4. Auto-scroll to bottom on new events: use `useRef` on a sentinel div at bottom of list, call `scrollIntoView({ behavior: 'smooth' })` in `useEffect` when `events` length changes.
5. Pause auto-scroll when user scrolls up: detect scroll position in `onScroll` handler; resume when user scrolls to bottom.
6. Each event row: timestamp (formatted with `formatRelative` from `src/lib/time.ts`), event type badge (shadcn `Badge` with variant by type category), step name if present from `event_data`.
7. Show connection status indicator at top: color-coded dot using `wsStatus` (idle=gray, connecting=yellow, connected/replaying=green, closed=muted, error=red).
8. Empty state: "Waiting for run..." when `runId` is null, "No events yet" when connected with no events.

### Step 8: Implement LivePage route with 3-column responsive layout
**Agent:** frontend-mobile-development:frontend-developer
**Skills:** none
**Context7 Docs:** /tanstack/router, /tanstack/query, /pmndrs/zustand
**Group:** C

1. Replace `llm_pipeline/ui/frontend/src/routes/live.tsx` content entirely.
2. State: `const [selectedPipeline, setSelectedPipeline] = useState<string | null>(null)` and `const [activeRunId, setActiveRunId] = useState<string | null>(null)`.
3. Hooks: `useCreateRun()`, `useWebSocket(activeRunId)`, `useEvents(activeRunId ?? '', {}, undefined)`, `useSteps(activeRunId ?? '', undefined)`, `useRunNotifications()`, `useUIStore()`.
4. Event cache seeding: in `useCreateRun` `onSuccess` callback, call `queryClient.setQueryData(queryKeys.runs.events(data.run_id, {}), { items: [], total: 0, offset: 0, limit: 50 })` then `setActiveRunId(data.run_id)`.
5. Python-initiated run detection: `useEffect` watching `latestRun` from `useRunNotifications` -- when `latestRun` changes and `latestRun.run_id !== activeRunId`, set `activeRunId` to `latestRun.run_id` and `selectedPipeline` to `latestRun.pipeline_name` (auto-attach to externally-started runs).
6. In-progress step click guard: wrap `selectStep` -- if `timelineItems.find(i => i.step_number === stepNum)?.status === 'running'`, skip the call (or show a toast); otherwise call `selectStep(stepNum)`.
7. Desktop layout (`lg+`): `grid grid-cols-3 gap-4 h-full`. Column 1 (left): pipeline selector + run button + placeholder div for Task 38 input form. Column 2 (center): `EventStream`. Column 3 (right): `StepTimeline` + `StepDetailPanel`.
8. Mobile/tablet layout (below `lg`): wrap the 3 columns in shadcn `Tabs` with triggers "Pipeline", "Events", "Steps". Each `TabsContent` renders the corresponding column content.
9. Run button: shadcn `Button` labeled "Run Pipeline", `disabled` when `!selectedPipeline || createRun.isPending`. `onClick` calls `createRun.mutate({ pipeline_name: selectedPipeline })`.
10. Placeholder div for Task 38: `{/* Task 38: InputForm will render here */}` comment with `<div data-testid="input-form-placeholder" />`.
11. Timeline items derived with `useMemo(() => deriveStepStatus(steps?.items ?? [], events?.items ?? []), [steps?.items, events?.items])` -- same pattern as `$runId.tsx`.

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Circular import: `runs.py` importing `manager` from `websocket.py` | Medium | `websocket.py` already imports from `llm_pipeline.state` not from `runs.py`; no cycle exists. Validate with a quick `python -c "from llm_pipeline.ui.routes.runs import trigger_run"` after change. |
| `appendEventToCache` drops events if cache not seeded before WS connects | High | Seed cache with empty `EventListResponse` in `useCreateRun` `onSuccess` before `setActiveRunId` (which triggers `useWebSocket` connection). Order matters -- seeding must precede state update. |
| Global WS `/ws/runs` endpoint path conflicts with per-run `/ws/runs/{run_id}` | Low | FastAPI routes are matched in registration order; exact path `/ws/runs` registered before parameterized `/ws/runs/{run_id}`. Verify router registration order in `websocket.py`. |
| `useRunNotifications` reconnects loop if backend not yet deployed | Low | Same exponential backoff pattern as `useWebSocket`. Global endpoint returns 1011 on error which triggers backoff, not infinite tight-loop. |
| StepDetailPanel shows error state for running steps | Medium | Guard in `onSelectStep` wrapper in `live.tsx` prevents opening panel for running steps. Document this behavior in code comment. |
| `usePipelines()` returns 404 until backend task 24 is fully deployed | Low | `usePipelines` already exists and handles loading/error states. `PipelineSelector` renders "No pipelines registered" on empty response. Not a blocker for Live View functionality. |
| routeTree.gen.ts needs regeneration after live.tsx changes | Low | TanStack Router file-based routing auto-generates `routeTree.gen.ts` via Vite plugin on dev server restart. Route already exists in tree (placeholder), so regeneration is minimal. |

## Success Criteria

- [ ] GET `/ws/runs` WebSocket connection accepted and keeps alive with heartbeats
- [ ] POST `/api/runs` response followed by `run_created` message on connected global WS clients within same request cycle
- [ ] `PipelineSelector` renders list from `GET /api/pipelines`, shows loading/empty/error states
- [ ] "Run Pipeline" button disabled when no pipeline selected or mutation in-flight
- [ ] Clicking "Run Pipeline" triggers `POST /api/runs`, receives `run_id`, seeds event cache, connects per-run WS
- [ ] Events appear in `EventStream` in real time as pipeline executes (auto-scroll to bottom)
- [ ] `StepTimeline` updates live as steps start/complete (via WS events + step invalidation)
- [ ] Clicking completed step opens `StepDetailPanel`; clicking running step does NOT open panel
- [ ] Layout is 3 columns on `lg+` screens; switches to tab-based single panel on smaller screens
- [ ] Python-initiated runs (started via POST /api/runs from another client) auto-attach to `EventStream` via `useRunNotifications`
- [ ] No TypeScript compiler errors or ESLint warnings introduced

## Phase Recommendation

**Risk Level:** medium
**Reasoning:** Most components reuse validated existing patterns (StepTimeline, useWebSocket, usePipelines, shadcn/ui). New backend work (global WS endpoint) is contained and follows existing ConnectionManager pattern. Main risks are the event cache seeding order dependency and the circular import check. The responsive tab layout adds UI complexity but is standard Tailwind. No schema changes or breaking API modifications.
**Suggested Exclusions:** testing
