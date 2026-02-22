# Task Summary

## Work Completed

Implemented the complete frontend API layer for the llm-pipeline UI (Task 31: TanStack Query API Hooks). Built a shared `apiClient` fetch wrapper with typed error handling, a TypeScript type module mirroring all backend Pydantic response models, a hierarchical query key factory, TanStack Query v5 hooks for all 11 API operations across runs/steps/events/context/prompts/pipelines, a WebSocket hook integrating live event streaming with the query cache via `setQueryData`, and a thin Zustand v5 store for WebSocket connection status. ReactQuery DevTools mounted in dev-only lazy import. All files passed strict TypeScript compilation, Vite production build, ESLint, and circular dependency checks. Six review issues were identified and resolved in a fixing-review loop before final approval.

## Files Changed

### Created

| File | Purpose |
| --- | --- |
| `llm_pipeline/ui/frontend/src/api/types.ts` | 31 TypeScript exports: interfaces for runs, steps, events, context, prompts (@provisional), pipelines (@provisional), WebSocket messages (`WsMessage` discriminated union via `WsPipelineEvent` wrapper), `ApiError` class, shared `toSearchParams()` utility |
| `llm_pipeline/ui/frontend/src/api/client.ts` | `apiClient<T>(path, options?)` fetch wrapper -- prepends `/api`, throws typed `ApiError` on non-OK responses, returns parsed JSON |
| `llm_pipeline/ui/frontend/src/api/query-keys.ts` | Hierarchical `queryKeys` factory object (`runs.*`, `prompts.*`, `pipelines.*`) with `as const` tuples; exports `isTerminalStatus()` helper for dynamic staleTime |
| `llm_pipeline/ui/frontend/src/api/runs.ts` | `useRuns`, `useRun`, `useCreateRun`, `useRunContext` -- dynamic staleTime/refetchInterval on active vs terminal runs; mutation invalidates `runs.all` on success |
| `llm_pipeline/ui/frontend/src/api/steps.ts` | `useSteps`, `useStep` -- dynamic staleTime + polling for active runs; `enabled: Boolean(runId)` guard on both hooks |
| `llm_pipeline/ui/frontend/src/api/events.ts` | `useEvents` -- dynamic staleTime + 3s polling for active runs; `enabled` guard; uses shared `toSearchParams` |
| `llm_pipeline/ui/frontend/src/api/prompts.ts` | `usePrompts` -- provisional hook targeting `/api/prompts` (Task 22); `@provisional` TSDoc; will 404 until Task 22 lands |
| `llm_pipeline/ui/frontend/src/api/pipelines.ts` | `usePipelines`, `usePipeline` -- provisional hooks targeting `/api/pipelines` (Task 24); `enabled: Boolean(name)` guard on detail hook; `@provisional` TSDoc |
| `llm_pipeline/ui/frontend/src/api/websocket.ts` | `useWebSocket(runId)` hook -- handles all 3 server behaviors (404/close-4004, replay/close-1000, live-stream); appends pipeline events to event query cache; invalidates run detail on `stream_complete`; React 19 Strict Mode guard; exponential backoff reconnect (1s base, 30s max); `parseWsMessage()` tags raw events with `type: 'pipeline_event'` discriminant |
| `llm_pipeline/ui/frontend/src/stores/websocket.ts` | Zustand v5 `useWsStore` -- `WsConnectionStatus` union (`idle \| connecting \| connected \| replaying \| closed \| error`), `error`, `reconnectCount`; actions: `setStatus`, `setError`, `incrementReconnect`, `reset` |

### Modified

| File | Changes |
| --- | --- |
| `llm_pipeline/ui/frontend/src/main.tsx` | Added lazy `ReactQueryDevtools` import inside `if (import.meta.env.DEV)` conditional block; rendered as last child of `QueryClientProvider` wrapped in `Suspense`; no production bundle impact |

## Commits Made

| Hash | Message |
| --- | --- |
| `e7f9062` | docs(implementation-A): master-31-tanstack-query-hooks -- client.ts, main.tsx DevTools, step-2/step-3 impl notes |
| `44c19eb` | docs(implementation-A): master-31-tanstack-query-hooks -- query-keys.ts |
| `2e45079` | docs(implementation-A): master-31-tanstack-query-hooks -- step-1 impl notes |
| `e8863b9` | docs(implementation-B): master-31-tanstack-query-hooks -- runs.ts, steps.ts, events.ts, prompts.ts, pipelines.ts, step-5/6/7 impl notes |
| `4957fd4` | docs(implementation-C): master-31-tanstack-query-hooks -- websocket.ts, stores/websocket.ts, step-9 impl notes |
| `977a895` | docs(fixing-review-A): master-31-tanstack-query-hooks -- types.ts (WsPipelineEvent, toSearchParams), runs.ts/events.ts/prompts.ts deduplication |
| `d8ef4e0` | docs(fixing-review-B): master-31-tanstack-query-hooks -- events.ts/runs.ts/steps.ts enabled guards, prompts impl notes |
| `a9fb1f9` | docs(fixing-review-B): master-31-tanstack-query-hooks -- step-6 impl notes |
| `6dba9b1` | docs(fixing-review-C): master-31-tanstack-query-hooks -- websocket.ts (replaying status, reconnect dedup, parseWsMessage) |

Note: task 31 implementation code was committed inside `docs(implementation-*)` commits alongside implementation notes. No dedicated `feat(ui):` commit was created for task 31 (unlike tasks 29/30); code will be covered by the branch merge commit.

## Deviations from Plan

- `WsMessage` initial implementation used raw `EventItem` in the union without a `type` discriminant, then corrected in the fixing-review phase by adding `WsPipelineEvent = { type: 'pipeline_event' } & EventItem` wrapper and `parseWsMessage()` helper. Plan described this as a potential risk but the initial agent did not pre-empt it.
- `'replaying'` status was not set in the initial WebSocket implementation (handler went straight to `'closed'` on `replay_complete`). Fixed in review: `'replaying'` now transitions on the first `pipeline_event` received while `connected`. Semantic side effect: live-streaming runs also briefly show `'replaying'` before `stream_complete` because the WS protocol does not distinguish replay from live events.
- `toSearchParams()` was initially duplicated across `runs.ts` (`toSearchParams`), `events.ts` (`buildEventParams`), and `prompts.ts` (`buildPromptParams`) with two different implementations. Consolidated into a single export in `types.ts` during review fixes.
- `reconnectCount` was tracked in both a local `useRef` and the Zustand store simultaneously. Consolidated to single source of truth (Zustand store only) in review fixes.
- `useSteps`, `useStep`, `useEvents` initially lacked `enabled: Boolean(runId)` guard that `useRun` and `useRunContext` had. Added during review fixes for consistency.
- `useRunListSearch()` convenience hook (PLAN Step 4, item 8) was not implemented. The plan note was documentation-only; Task 33 should use `Route.useSearch()` directly.
- ESLint `react-hooks/immutability` violation in `useWebSocket` found during testing: `connect` useCallback self-referenced for reconnect. Fixed by introducing `connectRef = useRef` and assigning inside effect.

## Issues Encountered

### ESLint react-hooks/immutability: useCallback self-reference
**Resolution:** Introduced `connectRef = useRef<(() => void) | null>(null)`, assigned `connectRef.current = connect` at top of the `useEffect` body (satisfying `react-hooks/refs` rule), and called `connectRef.current?.()` from the `onclose` handler instead of the callback variable directly.

### WsMessage union not discriminated by TypeScript
**Resolution:** Added `WsPipelineEvent = { type: 'pipeline_event' } & EventItem` intersection type to `types.ts`. Updated `WsMessage` union to use `WsPipelineEvent` instead of raw `EventItem`. Added `parseWsMessage()` in `websocket.ts` that tags incoming raw events with the `type: 'pipeline_event'` property, enabling exhaustive `switch(msg.type)` dispatch.

### Duplicated URLSearchParams serialization logic
**Resolution:** Extracted a single `toSearchParams(params: Record<string, string | number | boolean | undefined | null>): string` utility into `types.ts`. Removed three per-file local helpers (`toSearchParams` in runs.ts, `buildEventParams` in events.ts, `buildPromptParams` in prompts.ts). All three files now import the shared function.

### Unreachable 'replaying' status in Zustand store
**Resolution:** Added `setStatus('replaying')` call inside the `case 'pipeline_event'` handler in `websocket.ts`, conditional on `currentStatus === 'connected'`. Status now transitions: `idle -> connecting -> connected -> replaying -> closed`. Note: both replay and live-streaming modes trigger `'replaying'` because the WebSocket protocol does not distinguish them at the message level.

### Dual reconnect tracking (useRef + Zustand store)
**Resolution:** Removed `reconnectCountRef`. Reconnect delay calculation now reads `useWsStore.getState().reconnectCount` after calling `incrementReconnect()`, making the Zustand store the single source of truth.

## Success Criteria

- [x] `src/api/types.ts` exists with 31 exports (29 interfaces, 2 type aliases, 1 class) covering all resource shapes -- verified by tsc
- [x] `src/api/client.ts` exports `apiClient<T>()` that throws typed `ApiError` on non-OK responses
- [x] `src/api/query-keys.ts` exports `queryKeys` factory and `isTerminalStatus` helper
- [x] `src/api/runs.ts` exports `useRuns`, `useRun`, `useCreateRun`, `useRunContext` with dynamic staleTime on `useRun`/`useRunContext`
- [x] `src/api/steps.ts` exports `useSteps`, `useStep` with dynamic staleTime
- [x] `src/api/events.ts` exports `useEvents` with dynamic staleTime and polling for active runs
- [x] `src/api/prompts.ts` exports `usePrompts` with `@provisional` TSDoc
- [x] `src/api/pipelines.ts` exports `usePipelines`, `usePipeline` with `@provisional` TSDoc
- [x] `src/stores/websocket.ts` exports Zustand `useWsStore` with `WsConnectionStatus` type
- [x] `src/api/websocket.ts` exports `useWebSocket(runId)` handling all 3 server behaviors, updates event query cache via `setQueryData`, invalidates run detail on `stream_complete`
- [x] `src/main.tsx` mounts `ReactQueryDevtools` in dev mode only via lazy import
- [x] TypeScript compilation passes with strict mode (`noUnusedLocals`, `noUnusedParameters`, `verbatimModuleSyntax`, `strict`) -- tsc -b --noEmit: zero output
- [x] No semicolons, single quotes throughout -- confirmed by tsc/ESLint clean pass
- [x] `useCreateRun` mutation invalidates `queryKeys.runs.all` on success
- [x] Vite production build succeeds (253 modules, 368 kB main chunk, DevTools excluded)
- [x] ESLint passes with zero errors or warnings
- [x] No circular dependencies (22 files scanned by madge)

## Recommendations for Follow-up

1. Rename `'replaying'` status to `'streaming'` in `WsConnectionStatus` -- the current name is semantically misleading for live-streaming runs (first pipeline_event while connected triggers `'replaying'` regardless of whether the run is replaying historical data or streaming live). Change in `src/stores/websocket.ts` and all consumers.
2. Task 22 (Prompts API backend) must update `src/api/types.ts` `Prompt`, `PromptListResponse`, `PromptListParams` interfaces marked `@provisional` before going live, to ensure the shapes match the actual endpoint response.
3. Task 24 (Pipelines API backend) must update `PipelineStepMetadata`, `PipelineStrategyMetadata`, `PipelineMetadata`, `PipelineListItem` interfaces marked `@provisional` in `src/api/types.ts` before going live.
4. Task 37 (Live Execution) will need to extend `TriggerRunRequest` with an `input_data` field if the backend accepts pipeline input -- both backend and this type need updating together.
5. Task 33 (Runs List page) should use `data?.items` (not `data?.runs`) when consuming `useRuns()` response -- noted in `useRuns` TSDoc but worth flagging explicitly in task 33 briefing.
6. Human validation still pending for two scenarios: (a) ReactQuery DevTools visible in browser dev mode, (b) WebSocket reconnect behavior after unexpected backend disconnect. Both require a running backend.
7. Consider adding a `useRunListSearch()` convenience hook wrapping `Route.useSearch()` once Task 33 wires the filter UI, to centralize search param extraction and avoid coupling route structure knowledge into multiple components.
