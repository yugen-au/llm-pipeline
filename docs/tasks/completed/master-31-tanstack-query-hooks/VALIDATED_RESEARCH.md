# Research Summary

## Executive Summary

Cross-referenced findings from both research agents (API surface + frontend patterns). Both agents independently confirmed the same critical gap: prompts and pipelines API endpoints are empty stubs with zero route handlers. The 8 implemented endpoints (4 runs, 2 steps, 1 events, 1 websocket) are well-documented with consistent type shapes across both reports. The frontend has TanStack Query v5 + Router v1 already configured with no existing API client code.

**Revision 1 (CEO Q&A complete):** All 6 questions resolved. Scope confirmed as ALL hooks including prompts/pipelines (type against existing Pydantic/SQLModel models). WebSocket architecture decided: TanStack Query cache integration + thin Zustand for connection status. Shared apiClient + DevTools mount confirmed. Dynamic staleTime confirmed (Infinity for completed, shorter for active). Backend tasks 22 (Prompts) and 24 (Pipelines) already exist. Research is now complete for planning.

## Domain Findings

### Backend API Surface
**Source:** step-1-api-surface-research.md

Verified 8 working endpoints across 4 route files:
- Runs: GET list (paginated, filtered), GET detail (with step summaries), POST trigger (202 async), GET context evolution
- Steps: GET list (by run), GET detail (by run + step_number)
- Events: GET list (paginated, filtered by event_type)
- WebSocket: WS /ws/runs/{run_id} with 3 behavioral modes (not-found, replay, live)

Two routers are mounted but contain zero endpoints:
- `/api/prompts` - empty router, Prompt DB model exists
- `/api/pipelines` - empty router, PipelineIntrospector exists but unexposed

### Frontend Architecture
**Source:** step-2-frontend-patterns-research.md

TanStack Query v5 configured with staleTime: 30s, retry: 2, refetchOnWindowFocus: false. DevTools installed but not mounted. TanStack Router file-based routing complete (task 30). Zod 4 with zod-adapter for search params. TypeScript strict mode with verbatimModuleSyntax. No `src/api/`, `src/hooks/`, `src/types/` directories exist yet.

Conventions confirmed: no semicolons, single quotes, named function declarations, kebab-case files, design tokens only, dark mode default.

### WebSocket Architecture
**Source:** both research files (consistent findings)

Three distinct server behaviors per run state:
1. Unknown run_id: error message + close(4004)
2. Completed/failed: replay all persisted events + replay_complete + close(1000)
3. Running: live stream via ConnectionManager queue fan-out, 30s heartbeat, stream_complete on finish

ConnectionManager is a module-level singleton with sync broadcast_to_run() called from pipeline code. The replay mode for completed runs effectively duplicates GET /api/runs/{run_id}/events data.

### Dependency Chain Analysis
**Source:** Task Master tasks 24, 30, 31, 33, 37, 39, 40

- Task 30 (done): routes set up, recommends task 31 wire Route.useSearch() in index.tsx
- Task 24 (pending): implements pipelines backend endpoints. Task 40 depends on both 24 and 31
- No task exists for prompts backend endpoints. Task 39 (Prompt Browser) depends on task 31 for usePrompts hook
- Task 37 (Live Execution) expects passing input_data in TriggerRunRequest, but current backend only accepts pipeline_name
- Task 33 (Run List) references `data?.runs.map(...)` but actual response shape is `data?.items.map(...)`

### Query Key Strategy
**Source:** step-2-frontend-patterns-research.md

Proposed hierarchical keys enabling targeted invalidation:
- `['runs', { filters }]` -> list
- `['runs', runId]` -> detail
- `['runs', runId, 'steps' | 'context' | 'events']` -> nested resources
- `['prompts', { filters }]` and `['pipelines']` -> future

This pattern is sound and standard for TanStack Query v5. No concerns.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Should task 31 create hooks for prompts/pipelines (stub endpoints) or limit to working endpoints only? | Create ALL hooks. Tasks 22 + 24 exist for backend. Type against existing Pydantic/SQLModel models. | Scope includes prompts.ts + pipelines.ts hook files. Types derived from Prompt model and PipelineIntrospector.get_metadata() shape. Hooks will 404 until backend tasks complete. |
| WebSocket state architecture: standalone, query cache integration, or Zustand? | TanStack Query cache integration + thin Zustand for connection status. | WS events update query cache via setQueryData (runs, steps, events get real-time updates). Zustand store for connection state (connected/disconnected/reconnecting). Task 37 consumes both. |
| Shared fetch wrapper or raw fetch()? | Yes, create shared apiClient with base URL, error handling, typed responses. | First subtask creates apiClient; all hooks depend on it. Consistent error handling, JSON parsing, type safety across all endpoints. |
| No backend task for prompts endpoints? | Already exists as Task 22 (Prompts API). Task 24 covers Pipelines API. | No new tasks needed. Dependency chain: task 22 -> task 39 (via backend), task 31 -> task 39 (via hooks). |
| Mount ReactQuery DevTools? | Yes, mount in main.tsx as part of task 31. | Quick early subtask. Dev-mode only mount aids debugging all subsequent hook work. |
| Dynamic staleTime or global 30s default? | Dynamic staleTime. Infinity for completed runs (immutable), shorter polling for active/running. | Hooks need status-aware staleTime logic. Completed run detail + its steps/events = Infinity. Active runs need refetchInterval or shorter stale window. |

## Assumptions Validated
- [x] TanStack Query v5 is installed and QueryClientProvider is wired in main.tsx
- [x] TanStack Router file-based routing is complete with all 6 routes (task 30 done)
- [x] No existing API client code -- src/api/ directory does not exist
- [x] Backend uses ReadOnlySession (API layer is read-only except POST /api/runs trigger)
- [x] WebSocket endpoint is at /ws/runs/{run_id} (no /api prefix), Vite proxy configured for /ws
- [x] All route handlers are sync (SQLite), FastAPI wraps in threadpool
- [x] Vite proxy forwards /api -> localhost:8642 and /ws -> ws://localhost:8642
- [x] Response shapes for runs, steps, events are stable (implemented in code, not just spec)
- [x] Task 30 recommends task 31 add Route.useSearch() to index.tsx for page/status params
- [x] Task 31 scope includes ALL 6 hook files: runs.ts, steps.ts, events.ts, prompts.ts, pipelines.ts, websocket.ts (CEO confirmed)
- [x] Prompts/pipelines hooks typed against existing Pydantic/SQLModel models, will 404 until tasks 22/24 complete (CEO accepted)
- [x] WebSocket hook integrates with TanStack Query cache via setQueryData + thin Zustand store for connection status (CEO decided)
- [x] Shared apiClient with base URL, error handling, typed responses required (CEO confirmed)
- [x] ReactQuery DevTools mounted in main.tsx dev-mode only (CEO confirmed)
- [x] Dynamic staleTime: Infinity for completed runs (immutable data), shorter/polling for active runs (CEO confirmed)

## Open Items
- TriggerRunRequest only accepts pipeline_name; task 37 expects input_data field (backend change needed, out of scope for task 31 -- task 37 or a prerequisite must add this)
- Task 33 code example references `data?.runs` but actual API returns `data?.items` (minor downstream fix needed in task 33)
- Exact Pydantic response models for prompts/pipelines don't exist yet; task 31 must infer TypeScript types from SQLModel fields (Prompt model) and PipelineIntrospector.get_metadata() output shape (documented in research). These types may need adjustment when tasks 22/24 land.
- Zod 4 peer dep mismatch with @tanstack/zod-adapter accepted in task 30 (monitor only)

## Recommendations for Planning
1. Subtask ordering: (a) TypeScript types, (b) apiClient + DevTools mount, (c) query key factory, (d) runs hooks, (e) steps hooks, (f) events hooks, (g) prompts hooks, (h) pipelines hooks, (i) WebSocket hook + Zustand store. Dependencies flow left-to-right.
2. apiClient as foundation subtask -- all hooks import from it. Base URL from Vite proxy (/api), typed error responses, JSON parsing.
3. TypeScript types in `src/api/types.ts` mirroring: RunSummary, RunDetail, StepSummary, StepDetail, PipelineEvent (from implemented Pydantic models), Prompt (from SQLModel), PipelineMetadata (from PipelineIntrospector.get_metadata() shape). Mark prompts/pipelines types as provisional with TSDoc comments.
4. Query key factory pattern (`queryKeys.runs.list(filters)`, `queryKeys.runs.detail(id)`, etc.) for all resources -- enables targeted invalidation and consistent key structure.
5. Dynamic staleTime implementation: helper function that checks run status. Completed/failed -> `Infinity`. Running/pending -> `5_000` or `refetchInterval: 3_000`. Apply to run detail and nested resource hooks.
6. WebSocket hook is highest-complexity subtask: must handle 3 server modes, integrate with query cache via `queryClient.setQueryData` for events/steps/run status, use thin Zustand store for connection state (status, error, reconnect count). Only reconnect for running runs with network interruption, not for completed runs (server intentionally closes).
7. Mount ReactQuery DevTools in main.tsx early (lazy import, dev-mode only via `import.meta.env.DEV`).
8. Wire Route.useSearch() in index.tsx per task 30 recommendation when implementing useRuns hook.
9. Prompts/pipelines hooks: implement full CRUD-ready query hooks typed against inferred shapes. Add TSDoc noting these will 404 until tasks 22/24 complete. Downstream tasks 39/40 will consume these hooks directly.
