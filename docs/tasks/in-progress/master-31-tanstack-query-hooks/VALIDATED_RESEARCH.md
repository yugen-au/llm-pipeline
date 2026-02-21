# Research Summary

## Executive Summary

Cross-referenced findings from both research agents (API surface + frontend patterns). Both agents independently confirmed the same critical gap: prompts and pipelines API endpoints are empty stubs with zero route handlers. The 8 implemented endpoints (4 runs, 2 steps, 1 events, 1 websocket) are well-documented with consistent type shapes across both reports. The frontend has TanStack Query v5 + Router v1 already configured with no existing API client code. Six questions surfaced requiring CEO decisions before planning can proceed -- two are critical (stub endpoint scope, WebSocket state architecture), two are important (fetch wrapper, missing prompts backend task), and two are minor defaults.

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
| (pending CEO responses - first validation pass) | - | - |

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

## Open Items
- Prompts API response shape: DB model exists but no endpoint or Pydantic response model defined; shape must be guessed or deferred
- Pipelines API response shape: task 24 description provides expected shapes but task 24 is still pending; shapes could change
- TriggerRunRequest only accepts pipeline_name; task 37 expects input_data field (backend change needed, out of scope for task 31)
- Task 33 code example references `data?.runs` but actual API returns `data?.items` (minor downstream fix)
- Zustand v5 installed but no stores created yet; WS connection state may need a store
- ReactQuery DevTools installed but not mounted
- Zod 4 peer dep mismatch with @tanstack/zod-adapter accepted in task 30

## Recommendations for Planning
1. Scope task 31 to ONLY working endpoints (runs, steps, events, websocket) unless CEO decides otherwise on stub hooks
2. Create a shared fetch client as the first subtask -- all hooks depend on it for consistent error handling and type safety
3. WebSocket hook should be the most complex subtask -- needs careful design for 3 server behavioral modes, replay vs live, and cache integration strategy
4. Mount ReactQuery DevTools in main.tsx as a quick early subtask (aids debugging all subsequent work)
5. Define TypeScript types in a dedicated `src/api/types.ts` file, mirroring backend Pydantic models exactly as documented in research
6. Wire Route.useSearch() in index.tsx as recommended by task 30 when implementing useRuns hook
7. Add a task for prompts backend endpoints to unblock the task 39 -> task 31 dependency chain
8. Query key factory pattern (e.g., `queryKeys.runs.list(filters)`) recommended over inline key arrays for maintainability
