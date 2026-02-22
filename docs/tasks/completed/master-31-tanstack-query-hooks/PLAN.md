# PLANNING

## Summary

Build the complete frontend API layer for the llm-pipeline UI: a shared `apiClient` fetch wrapper, TypeScript types mirroring backend Pydantic models, a hierarchical query key factory, TanStack Query hooks for all 11 API operations (runs, steps, events, context, prompts, pipelines), a WebSocket hook integrating with query cache via `setQueryData` plus a thin Zustand store for connection status, and ReactQuery DevTools mounted in `main.tsx`. Prompts and pipelines hooks will be typed against existing DB/introspection models and return 404s until backend tasks 22/24 land. All code goes into new `src/api/` and `src/stores/` directories.

## Plugin & Agents

**Plugin:** frontend-mobile-development
**Subagents:** [available agents]
**Skills:** none

## Phases

1. **Foundation**: Create TypeScript types, apiClient wrapper, query key factory, and DevTools mount - all other steps depend on these
2. **Query Hooks**: Implement all TanStack Query hooks (runs, steps, events, context, prompts, pipelines) using the foundation
3. **WebSocket**: Implement WebSocket hook with query cache integration and Zustand connection status store

## Architecture Decisions

### Query Key Factory

**Choice:** Centralized `queryKeys` object exported from `src/api/query-keys.ts` with nested factory functions per resource (e.g. `queryKeys.runs.list(filters)`, `queryKeys.runs.detail(id)`, `queryKeys.runs.steps(id)`)
**Rationale:** Hierarchical keys enable targeted invalidation (`invalidateQueries({ queryKey: ['runs'] })` clears all run data, `['runs', runId]` clears one run and its children). Centralized factory prevents key string drift across hook files. Standard TanStack Query v5 pattern documented in official docs.
**Alternatives:** Inline string arrays per hook (no invalidation hierarchy, error-prone)

### Dynamic staleTime

**Choice:** Per-hook helper function `isTerminalStatus(status)` returning `true` for `completed` and `failed`. Hooks accepting a run object apply `staleTime: Infinity` when terminal, `staleTime: 5_000` with `refetchInterval: 3_000` when running/pending.
**Rationale:** Completed/failed runs are immutable - their steps, events, and context will never change. Polling immutable data wastes bandwidth and masks query freshness. Active runs need polling to reflect live DB writes from background pipeline execution.
**Alternatives:** Global 30s default for all (wastes requests on completed runs); WebSocket-only refresh (no polling fallback when WS disconnected)

### WebSocket State Split

**Choice:** TanStack Query cache (via `queryClient.setQueryData`) for event data; thin Zustand store (`src/stores/websocket.ts`) for connection status (`'idle' | 'connecting' | 'connected' | 'replaying' | 'closed' | 'error'`), last error, and reconnect count.
**Rationale:** CEO decision. Event data belongs in query cache so downstream hooks (`useEvents`) stay consistent with REST data. Connection status is ephemeral UI state unsuited to query cache (no fetch, no invalidation). Zustand v5 `create` is already installed.
**Alternatives:** Pure Zustand (event data and status both in store, loses cache coherence); standalone hook state (no global connection visibility for devtools/header)

### Shared apiClient

**Choice:** `src/api/client.ts` exports `apiClient<T>(path, options?)` that prepends `/api`, handles non-OK responses by throwing a typed `ApiError`, and returns `T` from parsed JSON.
**Rationale:** All REST hooks import one function. Base URL `/api` is resolved by Vite proxy in dev and by same-origin serving in prod. Typed error object (`status`, `message`, `detail`) enables consistent error UI across all hooks. Avoids repeated try/catch boilerplate in each hook file.
**Alternatives:** Raw `fetch()` per hook (no type safety, repetitive error handling); axios (adds bundle weight, no benefit over native fetch for this use case)

### Prompts and Pipelines Hooks

**Choice:** Implement full hooks typed against existing Pydantic/SQLModel fields (Prompt model, PipelineIntrospector.get_metadata() shape). Add TSDoc comment on each hook noting it will 404 until backend task 22/24 lands.
**Rationale:** CEO confirmed. Downstream tasks 39 (Prompt Browser) and 40 (Pipeline Structure) depend on `usePrompts`, `usePipelines`, `usePipeline`. Creating these hooks now means tasks 39/40 can code against real hook signatures and only need backend endpoints to go live.
**Alternatives:** Skip prompts/pipelines (breaks task 39/40 dependency chain); create empty stubs (incomplete signatures force task 39/40 agents to rewrite)

### DevTools Mount

**Choice:** Lazy import of `ReactQueryDevtools` from `@tanstack/react-query-devtools` inside a conditional `import.meta.env.DEV` block in `main.tsx`, rendered inside `QueryClientProvider`.
**Rationale:** CEO confirmed. Dev-only lazy import means no production bundle impact. Must be inside `QueryClientProvider` to access the client. Lazy import avoids Vite tree-shaking edge cases with side-effect imports.
**Alternatives:** Always-on DevTools (adds ~50KB to prod bundle); separate `DevTools` component file (unnecessary indirection for a one-liner)

## Implementation Steps

### Step 1: TypeScript Types

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /tanstack/query
**Group:** A

1. Create `src/api/types.ts` with all TypeScript interfaces mirroring backend Pydantic response models
2. Define `RunStatus` as `'running' | 'completed' | 'failed'` string literal union
3. Define `RunListItem`, `RunListResponse`, `RunDetail`, `StepSummary` matching GET /api/runs shapes
4. Define `TriggerRunRequest` (`{ pipeline_name: string }`), `TriggerRunResponse` (`{ run_id: string; status: string }`)
5. Define `ContextSnapshot`, `ContextEvolutionResponse` matching GET /api/runs/{id}/context
6. Define `StepListItem`, `StepListResponse`, `StepDetail` matching GET /api/runs/{id}/steps shapes
7. Define `EventItem`, `EventListResponse` matching GET /api/runs/{id}/events shapes
8. Define `RunListParams` (pipeline_name, status, started_after, started_before, offset, limit) and `EventListParams` (event_type, offset, limit) for query param types
9. Define `Prompt` interface from `llm_pipeline/db/prompt.py` SQLModel fields (id, prompt_key, prompt_name, prompt_type, category, step_name, content, required_variables, description, version, is_active, created_at, updated_at, created_by) - mark with TSDoc `@provisional`
10. Define `PromptListResponse` (items: Prompt[], total, offset, limit) and `PromptListParams` (prompt_type, category, step_name, is_active, offset, limit) - mark `@provisional`
11. Define `PipelineStepMetadata`, `PipelineStrategyMetadata`, `PipelineMetadata` matching `PipelineIntrospector.get_metadata()` return shape (pipeline_name, registry_models, strategies[{name, display_name, class_name, steps[...], error}], execution_order) - mark `@provisional`
12. Define `PipelineListItem` (`{ name: string; strategy_count: number; step_count: number; has_input_schema: boolean }`) per task 24 expected shape - mark `@provisional`
13. Define WebSocket message types: `WsHeartbeat`, `WsStreamComplete`, `WsReplayComplete`, `WsError`, `WsMessage` discriminated union
14. Define `ApiError` class extending `Error` with `status: number`, `detail: string` fields
15. Use `import type` for all type-only imports per `verbatimModuleSyntax: true` tsconfig rule; no semicolons, single quotes per Prettier config

### Step 2: apiClient and DevTools

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /tanstack/query
**Group:** A

1. Create `src/api/client.ts` exporting `apiClient<T>(path: string, options?: RequestInit): Promise<T>`
2. Prepend `/api` to path (all REST calls proxied by Vite; no hardcoded port)
3. Call native `fetch`, check `response.ok`; if false, parse JSON body and throw `new ApiError(response.status, body.detail ?? response.statusText)`
4. On success, return `response.json() as Promise<T>`
5. Import `ApiError` from `./types` using `import type` where applicable
6. Update `src/main.tsx`: add lazy DevTools import inside `if (import.meta.env.DEV)` block, render `<ReactQueryDevtools initialIsOpen={false} />` as last child inside `QueryClientProvider`
7. Use dynamic `import()` pattern for DevTools to avoid production bundle impact: `const { ReactQueryDevtools } = await import('@tanstack/react-query-devtools')` via a wrapper component or direct conditional JSX

### Step 3: Query Key Factory

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /tanstack/query
**Group:** A

1. Create `src/api/query-keys.ts` exporting a `queryKeys` const object with factory functions
2. `queryKeys.runs.all` -> `['runs'] as const`
3. `queryKeys.runs.list(filters: Partial<RunListParams>)` -> `['runs', filters] as const`
4. `queryKeys.runs.detail(runId: string)` -> `['runs', runId] as const`
5. `queryKeys.runs.context(runId: string)` -> `['runs', runId, 'context'] as const`
6. `queryKeys.runs.steps(runId: string)` -> `['runs', runId, 'steps'] as const`
7. `queryKeys.runs.step(runId: string, stepNumber: number)` -> `['runs', runId, 'steps', stepNumber] as const`
8. `queryKeys.runs.events(runId: string, filters: Partial<EventListParams>)` -> `['runs', runId, 'events', filters] as const`
9. `queryKeys.prompts.all` -> `['prompts'] as const`
10. `queryKeys.prompts.list(filters: Partial<PromptListParams>)` -> `['prompts', filters] as const`
11. `queryKeys.pipelines.all` -> `['pipelines'] as const`
12. `queryKeys.pipelines.detail(name: string)` -> `['pipelines', name] as const`
13. Export `isTerminalStatus(status: RunStatus | string): boolean` helper returning `status === 'completed' || status === 'failed'` for dynamic staleTime use in hook files

### Step 4: Runs Hooks

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /tanstack/query
**Group:** B

1. Create `src/api/runs.ts`
2. Import `useQuery`, `useMutation`, `useQueryClient` from `@tanstack/react-query`
3. Import `apiClient` from `./client`, `queryKeys`, `isTerminalStatus` from `./query-keys`, types from `./types`
4. `useRuns(filters: Partial<RunListParams>)`: `useQuery({ queryKey: queryKeys.runs.list(filters), queryFn: () => apiClient<RunListResponse>('/runs?' + new URLSearchParams(...)) })` - uses global 30s staleTime; no per-hook override needed for lists (they're always fresh)
5. `useRun(runId: string)`: `useQuery({ queryKey: queryKeys.runs.detail(runId), queryFn: () => apiClient<RunDetail>('/runs/' + runId), staleTime: data ? (isTerminalStatus(data.status) ? Infinity : 5_000) : 30_000, refetchInterval: data && !isTerminalStatus(data.status) ? 3_000 : false })`
6. `useCreateRun()`: `useMutation({ mutationFn: (req: TriggerRunRequest) => apiClient<TriggerRunResponse>('/runs', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(req) }), onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.runs.all }) })`
7. `useRunContext(runId: string, status?: RunStatus)`: `useQuery({ queryKey: queryKeys.runs.context(runId), queryFn: () => apiClient<ContextEvolutionResponse>('/runs/' + runId + '/context'), staleTime: status && isTerminalStatus(status) ? Infinity : 30_000 })`
8. Wire `Route.useSearch()` usage: export a `useRunListSearch()` convenience hook that calls `Route.useSearch()` from the index route for page+status params; document that index.tsx should import this when wiring the filter UI (task 33)
9. Note in file TSDoc: `data?.items` (not `data?.runs`) is the correct field per task 33 known deviation

### Step 5: Steps Hooks

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /tanstack/query
**Group:** B

1. Create `src/api/steps.ts`
2. Import `useQuery` from `@tanstack/react-query`, `apiClient`, `queryKeys`, `isTerminalStatus` from their modules, types from `./types`
3. `useSteps(runId: string, runStatus?: RunStatus)`: `useQuery({ queryKey: queryKeys.runs.steps(runId), queryFn: () => apiClient<StepListResponse>('/runs/' + runId + '/steps'), staleTime: runStatus && isTerminalStatus(runStatus) ? Infinity : 5_000, refetchInterval: runStatus && !isTerminalStatus(runStatus) ? 3_000 : false })`
4. `useStep(runId: string, stepNumber: number, runStatus?: RunStatus)`: `useQuery({ queryKey: queryKeys.runs.step(runId, stepNumber), queryFn: () => apiClient<StepDetail>('/runs/' + runId + '/steps/' + stepNumber), staleTime: runStatus && isTerminalStatus(runStatus) ? Infinity : 30_000 })`
5. Both hooks accept optional `runStatus` param to enable dynamic staleTime without requiring consumers to fetch run separately

### Step 6: Events Hooks

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /tanstack/query
**Group:** B

1. Create `src/api/events.ts`
2. Import `useQuery` from `@tanstack/react-query`, `apiClient`, `queryKeys`, `isTerminalStatus`, types
3. `useEvents(runId: string, filters: Partial<EventListParams>, runStatus?: RunStatus)`: `useQuery({ queryKey: queryKeys.runs.events(runId, filters), queryFn: () => apiClient<EventListResponse>('/runs/' + runId + '/events?' + new URLSearchParams(...)), staleTime: runStatus && isTerminalStatus(runStatus) ? Infinity : 5_000, refetchInterval: runStatus && !isTerminalStatus(runStatus) ? 3_000 : false })`
4. Build URLSearchParams from `filters` by omitting undefined/null values before serializing

### Step 7: Prompts Hooks

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /tanstack/query
**Group:** B

1. Create `src/api/prompts.ts`
2. Add file-level TSDoc: `@remarks These hooks target /api/prompts endpoints implemented by Task 22. They will return 404 until that task is complete.`
3. Import `useQuery` from `@tanstack/react-query`, `apiClient`, `queryKeys`, types
4. `usePrompts(filters: Partial<PromptListParams>)`: `useQuery({ queryKey: queryKeys.prompts.list(filters), queryFn: () => apiClient<PromptListResponse>('/prompts?' + new URLSearchParams(...)) })`
5. Prompts are static reference data - use default 30s staleTime from QueryClient global config (no override needed)
6. Export hook so tasks 39 (Prompt Browser) can import directly from `@/api/prompts`

### Step 8: Pipelines Hooks

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /tanstack/query
**Group:** B

1. Create `src/api/pipelines.ts`
2. Add file-level TSDoc: `@remarks These hooks target /api/pipelines endpoints implemented by Task 24. They will return 404 until that task is complete.`
3. Import `useQuery` from `@tanstack/react-query`, `apiClient`, `queryKeys`, types
4. `usePipelines()`: `useQuery({ queryKey: queryKeys.pipelines.all, queryFn: () => apiClient<{ pipelines: PipelineListItem[] }>('/pipelines') })` - static config data, use default staleTime
5. `usePipeline(name: string)`: `useQuery({ queryKey: queryKeys.pipelines.detail(name), queryFn: () => apiClient<PipelineMetadata>('/pipelines/' + name), enabled: Boolean(name) })`
6. Export both hooks so tasks 37 (Live Execution) and 40 (Pipeline Structure) can import from `@/api/pipelines`

### Step 9: WebSocket Hook and Zustand Store

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /tanstack/query, /pmndrs/zustand
**Group:** C

1. Create `src/stores/websocket.ts`:
   - Define `WsConnectionStatus` type: `'idle' | 'connecting' | 'connected' | 'replaying' | 'closed' | 'error'`
   - Export `useWsStore` via Zustand v5 `create<WsState>()(() => ({ status: 'idle', error: null, reconnectCount: 0, setStatus: ..., setError: ..., incrementReconnect: ..., reset: ... }))`
   - No `devtools` middleware needed (keep it thin)

2. Create `src/api/websocket.ts`:
   - Import `useEffect`, `useRef`, `useCallback` from `react`
   - Import `useQueryClient` from `@tanstack/react-query`
   - Import `useWsStore` from `../stores/websocket`
   - Import `queryKeys` from `./query-keys`, types from `./types`

3. Export `useWebSocket(runId: string | null)` hook:
   - Return early (no-op) when `runId` is null; set status to `'idle'`
   - Use `wsRef = useRef<WebSocket | null>(null)` and `queryClient = useQueryClient()`
   - In `useEffect` keyed on `runId`: construct `ws = new WebSocket('/ws/runs/' + runId)` (Vite proxy handles upgrade)
   - `ws.onopen`: call `setStatus('connecting')` then `setStatus('connected')`
   - `ws.onmessage`: parse `JSON.parse(event.data)` as `WsMessage`; branch on `msg.type`:
     - `'heartbeat'`: no-op (keep-alive only)
     - `'replay_complete'`: call `setStatus('replaying')` then `setStatus('closed')`; no cache update (REST endpoint already has this data)
     - `'stream_complete'`: call `setStatus('closed')`; invalidate `queryKeys.runs.detail(runId)` to trigger REST refetch for final status
     - `'error'`: call `setStatus('error')`, `setError(msg.detail)`
     - default (raw pipeline event with `event_type`): treat as `EventItem`; call `queryClient.setQueryData(queryKeys.runs.events(runId, {}), (old) => old ? { ...old, items: [...old.items, msg], total: old.total + 1 } : undefined)`; if event_type is step-scoped, also invalidate `queryKeys.runs.steps(runId)` to trigger steps list refresh
   - `ws.onerror`: call `setStatus('error')`
   - `ws.onclose`: if `event.code === 4004` set `setStatus('error')` with "Run not found"; if `event.code === 1000` leave status as `'closed'`; never reconnect for code 1000 (replay complete) or 4004 (bad runId)
   - Cleanup: `ws.close()` in effect cleanup; `wsStore.reset()` on unmount
   - Return `{ status: wsStore.status, error: wsStore.error }` for consumers

4. Reconnect strategy: only reconnect if `status === 'connected'` was achieved and close code is not 1000/4004 (unexpected disconnect during live run). Implement with `reconnectCount` increment and `setTimeout` in `ws.onclose`.

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Prompts/pipelines types drift when tasks 22/24 land with different shapes | Medium | Mark all provisional types with `@provisional` TSDoc. Tasks 22/24 agents must update `src/api/types.ts` as first step. Note in VALIDATED_RESEARCH open items. |
| Task 33 uses `data?.runs` (wrong field) instead of `data?.items` | Low | Add TSDoc note to `useRuns` hook JSDoc. The VALIDATED_RESEARCH already flags this deviation for task 33 agent. |
| WebSocket `setQueryData` optimistic update causes stale event count if REST events query later fetches | Medium | `staleTime: 5_000` + `refetchInterval: 3_000` on `useEvents` for active runs ensures REST reconciles cache within 3s of any WS-driven update. |
| TriggerRunRequest lacks `input_data` field task 37 expects | Low | `TriggerRunRequest` type is defined accurately against current backend. Task 37 or a prerequisite must extend both backend and this type. Note in types.ts TSDoc. |
| Zod v4 peer dep mismatch with `@tanstack/zod-adapter` | Low | Already accepted in task 30. No new exposure from task 31 (no zod imports in API layer). Monitor only. |
| React 19 Strict Mode double-invoking effects may open two WebSocket connections | Medium | Use `wsRef.current` guard: skip `new WebSocket()` if ref already set. Check `wsRef.current?.readyState` before creating new instance in effect body. |
| URLSearchParams serialization of undefined/null filter values sends empty strings | Low | Filter out undefined/null values before constructing URLSearchParams: `Object.entries(filters).filter(([, v]) => v != null)` |

## Success Criteria

- [ ] `src/api/types.ts` exists with all 14+ interfaces covering runs, steps, events, context, prompts (provisional), pipelines (provisional), WebSocket messages, and ApiError class
- [ ] `src/api/client.ts` exports `apiClient<T>()` that throws typed `ApiError` on non-OK responses
- [ ] `src/api/query-keys.ts` exports `queryKeys` factory and `isTerminalStatus` helper
- [ ] `src/api/runs.ts` exports `useRuns`, `useRun`, `useCreateRun`, `useRunContext` with dynamic staleTime on `useRun`/`useRunContext`
- [ ] `src/api/steps.ts` exports `useSteps`, `useStep` with dynamic staleTime
- [ ] `src/api/events.ts` exports `useEvents` with dynamic staleTime and polling for active runs
- [ ] `src/api/prompts.ts` exports `usePrompts` with `@provisional` TSDoc
- [ ] `src/api/pipelines.ts` exports `usePipelines`, `usePipeline` with `@provisional` TSDoc
- [ ] `src/stores/websocket.ts` exports Zustand `useWsStore` with `WsConnectionStatus` type
- [ ] `src/api/websocket.ts` exports `useWebSocket(runId)` that handles all 3 server behaviors (not-found/replay/live), updates event query cache via `setQueryData`, and invalidates run detail on `stream_complete`
- [ ] `src/main.tsx` mounts `ReactQueryDevtools` in dev mode only via lazy import
- [ ] TypeScript compilation passes with strict mode (`noUnusedLocals`, `noUnusedParameters`, `verbatimModuleSyntax`)
- [ ] No semicolons, single quotes throughout (Prettier config compliance)
- [ ] `useCreateRun` mutation invalidates `queryKeys.runs.all` on success

## Phase Recommendation

**Risk Level:** medium
**Reasoning:** Core REST hooks (runs, steps, events) are low risk - endpoints exist and types are verified. The WebSocket hook is genuinely complex (3 server behaviors, cache integration, reconnect logic, React 19 Strict Mode double-effect risk). Prompts/pipelines hooks introduce type drift risk but are isolated. Overall implementation risk is medium due to WebSocket complexity and provisional typing.
**Suggested Exclusions:** review
