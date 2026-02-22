# Testing Results

## Summary
**Status:** passed
All 10 new TypeScript files compile, bundle, and pass lint/circular-dependency checks. One lint error found in `src/api/websocket.ts` (react-hooks self-reference violation) was fixed during this testing phase before final verification.

## Automated Testing
### Test Scripts Created
| Script | Purpose | Location |
| --- | --- | --- |
| tsc -b --noEmit | TypeScript strict-mode compilation | llm_pipeline/ui/frontend/ |
| npm run build | Vite production bundle (tsc + vite build) | llm_pipeline/ui/frontend/ |
| npm run lint | ESLint with react-hooks plugin | llm_pipeline/ui/frontend/ |
| npx madge --circular --extensions ts,tsx src/ | Circular dependency scan | llm_pipeline/ui/frontend/ |

### Test Execution
**Pass Rate:** 4/4 checks pass (after fix)

```
TypeScript (tsc -b --noEmit): clean, no output

Vite build:
vite v7.3.1 building client environment for production...
253 modules transformed.
dist/index.html                    0.41 kB | gzip:   0.27 kB
dist/assets/index-CsnzxF6W.css   10.84 kB | gzip:   2.82 kB
dist/assets/index-DWfXAnXC.js     0.24 kB | gzip:   0.19 kB
dist/assets/prompts-DoZ7PVMo.js   0.30 kB | gzip:   0.21 kB
dist/assets/live-BkGWJ67T.js      0.30 kB | gzip:   0.22 kB
dist/assets/pipelines-CNLFP1EI.js 0.30 kB | gzip:   0.22 kB
dist/assets/_runId-CZFOsYMg.js    0.46 kB | gzip:   0.28 kB
dist/assets/index-BK3eSKoh.js   368.96 kB | gzip: 113.43 kB
built in 1.94s

ESLint: no problems

madge circular scan: 22 files processed, No circular dependency found!
```

### Failed Tests
None (after fix applied)

## Build Verification
- [x] TypeScript strict compilation passes (`noUnusedLocals`, `noUnusedParameters`, `verbatimModuleSyntax`, `strict`)
- [x] Vite production build succeeds (253 modules, no bundling errors)
- [x] ESLint passes with zero errors or warnings
- [x] No circular dependencies across all 22 src TypeScript files
- [x] DevTools chunk excluded from main bundle (not present in dist/assets/ in prod build)

## Success Criteria (from PLAN.md)
- [x] `src/api/types.ts` exists with 31 exports (29 interfaces, 2 type aliases, 1 class) covering runs, steps, events, context, prompts (provisional), pipelines (provisional), WebSocket messages, ApiError
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
- [x] TypeScript compilation passes with strict mode
- [x] No semicolons, single quotes throughout (confirmed by tsc/eslint clean pass)
- [x] `useCreateRun` mutation invalidates `queryKeys.runs.all` on success

## Human Validation Required
### DevTools visible in dev mode
**Step:** Step 2 (apiClient and DevTools)
**Instructions:** Run `npm run dev` in `llm_pipeline/ui/frontend/`, open browser at localhost:5173, look for TanStack Query DevTools button in bottom-right corner of the page.
**Expected Result:** A floating DevTools panel toggle button is visible. Clicking it opens the TanStack Query inspector showing query cache entries.

### WebSocket reconnect behavior
**Step:** Step 9 (WebSocket Hook)
**Instructions:** Open a run detail page while the backend is running. Manually stop and restart the backend. Observe the connection status indicator (if wired to UI) or check browser DevTools network tab for WebSocket reconnection attempts.
**Expected Result:** After unexpected disconnect, hook attempts reconnect with exponential backoff (1s, 2s, 4s..., max 30s). No reconnect occurs when close code is 1000 or 4004.

### Prompts/Pipelines hooks return 404
**Step:** Steps 7, 8 (Prompts and Pipelines hooks)
**Instructions:** Import `usePrompts` or `usePipelines` in a test component and render it. Check browser DevTools network tab.
**Expected Result:** Network request to `/api/prompts` or `/api/pipelines` returns 404 (expected until tasks 22/24 land). TanStack Query error state is populated with `ApiError(404, ...)`.

## Issues Found
### ESLint react-hooks/immutability: self-reference in useCallback
**Severity:** high
**Step:** Step 9 (WebSocket Hook)
**Details:** `connect` useCallback referenced itself for reconnect via `setTimeout(() => connect(), delay)`. ESLint `react-hooks/immutability` rule blocks accessing a `useCallback` variable before its declaration completes. Fixed by introducing `connectRef = useRef<(() => void) | null>(null)`, assigning `connectRef.current = connect` inside `useEffect` (after declaration, inside effect to satisfy `react-hooks/refs` rule), and calling `connectRef.current?.()` from the `onclose` handler instead.

### ESLint react-hooks/refs: ref mutation during render
**Severity:** high
**Step:** Step 9 (WebSocket Hook)
**Details:** Initial fix placed `connectRef.current = connect` in the render body between hooks. ESLint `react-hooks/refs` rule blocks ref mutations outside effects/handlers. Fixed by moving the assignment to the top of the existing `useEffect` body.

## Recommendations
1. No further fixes needed. Both issues were found and resolved in this testing phase.
2. `useRunListSearch()` convenience hook noted in step-4 implementation file is not present in `src/api/runs.ts` - it was listed in PLAN.md Step 4 item 8 as a documentation note only ("document that index.tsx should import this when wiring the filter UI"). Task 33 agent should use `Route.useSearch()` directly from the runs index route; no hook stub is missing.
3. Prompts/pipelines hooks will 404 at runtime until tasks 22/24 land - this is expected and documented in TSDoc.
4. Production bundle size is clean: 368 kB main chunk (React + TanStack Router + Query + Zustand), DevTools excluded.

---

# Re-verification Results (post review-fix phase)

## Summary
**Status:** passed
Re-ran all 4 checks after review-phase changes to types.ts, runs.ts, steps.ts, events.ts, prompts.ts, and websocket.ts. All pass with zero errors.

## Changes Verified
- `src/api/types.ts` - added `WsPipelineEvent` discriminated union wrapper (`type: 'pipeline_event' & EventItem`), added `toSearchParams()` shared utility, `WsConnectionStatus` now includes `'replaying'` state
- `src/api/runs.ts` - switched from local `buildRunParams` to shared `toSearchParams` import
- `src/api/steps.ts` - added `enabled: Boolean(runId)` guard to both `useSteps` and `useStep`
- `src/api/events.ts` - added `enabled: Boolean(runId)` guard, switched to `toSearchParams`
- `src/api/prompts.ts` - switched to `toSearchParams`
- `src/api/websocket.ts` - `parseWsMessage()` helper added, tags raw pipeline events with `type: 'pipeline_event'`, `switch(msg.type)` exhaustive dispatch, `replaying` status set on first pipeline_event while `connected`, reconnect count now reads from `useWsStore.getState().reconnectCount` instead of local ref

## Automated Testing
### Test Execution
**Pass Rate:** 4/4

```
tsc -b --noEmit: clean (no output)

npm run build:
vite v7.3.1 building client environment for production...
253 modules transformed.
dist/index.html                      0.41 kB | gzip:   0.27 kB
dist/assets/index-DqoSpvZ3.css      9.63 kB | gzip:   2.62 kB
dist/assets/index-CUYJWBEp.js       0.24 kB | gzip:   0.19 kB
dist/assets/prompts-u5OqvGiN.js     0.30 kB | gzip:   0.21 kB
dist/assets/live-DjK8vLyA.js        0.30 kB | gzip:   0.22 kB
dist/assets/pipelines-Dvb70C9k.js   0.30 kB | gzip:   0.22 kB
dist/assets/_runId-Ff3MmHHx.js      0.46 kB | gzip:   0.28 kB
dist/assets/index-DwWfAv0n.js     368.96 kB | gzip: 113.43 kB
built in 2.87s

npm run lint: no problems

madge --circular: 22 files processed, No circular dependency found!
```

### Failed Tests
None

## Build Verification
- [x] TypeScript strict compilation passes (tsc -b --noEmit, zero output)
- [x] Vite production build succeeds (253 modules, 2.87s)
- [x] ESLint passes with zero errors or warnings
- [x] No circular dependencies (22 files scanned)

## Issues Found
None
