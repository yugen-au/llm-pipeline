# Architecture Review

## Overall Assessment
**Status:** complete

Solid implementation. All 10 new files + 1 modified file follow consistent patterns, use TanStack Query v5 API correctly, and align well with the PLAN. Types mirror backend Pydantic models accurately. The WebSocket hook handles React 19 Strict Mode, reconnection, and cache integration properly. A handful of medium/low issues found -- none blocking.

## Project Guidelines Compliance
**CLAUDE.md:** `D:\Documents\claude-projects\llm-pipeline\CLAUDE.md`

| Guideline | Status | Notes |
| --- | --- | --- |
| No semicolons | pass | All files use no-semicolon style per .prettierrc |
| Single quotes | pass | Consistent single quotes throughout |
| `import type` for type-only imports | pass | All type imports use `import type` syntax; `ApiError` in client.ts is correctly a value import (class) |
| `verbatimModuleSyntax: true` compliance | pass | No implicit type re-exports; value/type imports properly split |
| No hardcoded values | pass | API base path is `/api` (resolved by Vite proxy), WS URL built from `window.location`; no hardcoded ports |
| Error handling present | pass | apiClient throws typed ApiError; WS hook handles parse failures, close codes, unmount |
| Prettier config (semi:false, singleQuote:true, trailingComma:all, tabWidth:2, printWidth:100) | pass | Code formatting matches config |

## Issues Found

### Critical

None

### High

None

### Medium

#### Unreachable `'replaying'` status in Zustand store
**Step:** 9
**Details:** `WsConnectionStatus` type includes `'replaying'` but the WebSocket hook never calls `setStatus('replaying')`. PLAN Step 9 point 3 specifies `replay_complete` should set `'replaying'` then `'closed'`, but the implementation goes straight to `'closed'`. Any UI component checking `status === 'replaying'` will never trigger. Either remove `'replaying'` from the union type, or add `setStatus('replaying')` before `setStatus('closed')` in the `replay_complete` handler.

#### Duplicated URLSearchParams helper across three files
**Step:** 4, 6, 7
**Details:** `toSearchParams` in `runs.ts`, `buildEventParams` in `events.ts`, and `buildPromptParams` in `prompts.ts` are three implementations of the same logic (filter null/undefined, serialize to query string). Two variants exist: `runs.ts` uses `params.set()` in a loop while the other two use the `URLSearchParams` constructor with pre-filtered entries. This is a DRY violation. Extract a single shared `toSearchParams` utility into `client.ts` or a new `utils.ts` and import everywhere.

#### `WsMessage` discriminated union is not truly discriminated
**Step:** 1
**Details:** `WsMessage = WsHeartbeat | WsStreamComplete | WsReplayComplete | WsError | EventItem`. The first four types have a `type` discriminant field, but `EventItem` uses `event_type` instead and has no `type` field. TypeScript cannot narrow this union via `switch(msg.type)`. The WebSocket hook works around this by checking `raw.type` then falling through to `raw.event_type`, but any consumer trying to use `WsMessage` as a proper discriminated union at the type level will hit issues. Consider adding `type?: undefined` to `EventItem` or creating a separate `WsPipelineEvent` wrapper with `type: 'pipeline_event'`.

### Low

#### Missing `enabled` guard on `useSteps`, `useStep`, `useEvents`
**Step:** 5, 6
**Details:** `useRun` and `useRunContext` have `enabled: Boolean(runId)` to prevent fetching with empty strings, but `useSteps`, `useStep`, and `useEvents` do not. If a consumer passes an empty string `runId`, these hooks will fire a request to `/runs//steps` returning a 404. Not critical since `runId` is typed as `string` (not optional), but inconsistent with the defensive pattern used elsewhere.

#### `useRun` staleTime function casts `data?.status` to `RunStatus | undefined`
**Step:** 4
**Details:** `RunDetail.status` is typed as `string` (matching backend `str`), not `RunStatus`. The cast `as RunStatus | undefined` in the `staleTime` and `refetchInterval` callbacks is safe in practice but bypasses type checking. If the backend ever returns a status value not in the `RunStatus` union, `isTerminalStatus` still returns false (safe fallback), so this is low risk. Consider narrowing `RunDetail.status` to `RunStatus` if the backend guarantees only those values, or add a comment explaining the intentional widening.

#### Reconnect timer uses local ref + Zustand store in parallel
**Step:** 9
**Details:** `reconnectCountRef` (local ref) and `useWsStore.reconnectCount` (Zustand) track the same value independently. The ref is used for backoff delay calculation, the store for external visibility. They stay in sync because `incrementReconnect` is called alongside `reconnectCountRef.current += 1`, but this dual-tracking is fragile. Consider using only the store value (read via `useWsStore.getState().reconnectCount`) for delay calculation.

## Review Checklist
[x] Architecture patterns followed -- clean separation: types, client, query keys, hooks per resource, WebSocket, Zustand store
[x] Code quality and maintainability -- well-documented with TSDoc, consistent file structure, clear naming
[x] Error handling present -- apiClient throws typed errors, WS hook handles all close codes and parse failures
[x] No hardcoded values -- base URLs resolved via Vite proxy, constants extracted (MAX_RECONNECT_DELAY, etc.)
[x] Project conventions followed -- no semicolons, single quotes, `import type`, trailingComma: all
[x] Security considerations -- no XSS risk from setQueryData (only updates typed cache, no innerHTML); WS messages parsed safely with try/catch
[x] Properly scoped (DRY, YAGNI, no over-engineering) -- minor DRY issue with URLSearchParams helpers; no over-engineering detected

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| `src/api/types.ts` | pass | 14+ interfaces, all match backend Pydantic models; provisional types marked; WsMessage union not truly discriminated (medium) |
| `src/api/client.ts` | pass | Clean fetch wrapper, typed ApiError, correct `import` (not `import type`) for ApiError class |
| `src/api/query-keys.ts` | pass | Hierarchical keys with `as const`, isTerminalStatus helper correct |
| `src/api/runs.ts` | pass | 4 hooks, dynamic staleTime via function callback (v5 API), mutation invalidation correct |
| `src/api/steps.ts` | pass | 2 hooks, dynamic staleTime, missing `enabled` guard (low) |
| `src/api/events.ts` | pass | 1 hook, dynamic staleTime + polling, missing `enabled` guard (low) |
| `src/api/prompts.ts` | pass | Provisional hook, correct @provisional TSDoc |
| `src/api/pipelines.ts` | pass | 2 provisional hooks, enabled guard present on usePipeline |
| `src/api/websocket.ts` | pass | Strict Mode guard, reconnect with capped exponential backoff, cache integration correct; `'replaying'` status never set (medium) |
| `src/stores/websocket.ts` | pass | Clean Zustand v5 store; `'replaying'` in type but unused (medium) |
| `src/main.tsx` | pass | Lazy DevTools import, Suspense boundary, dev-only conditional |

## New Issues Introduced
- None detected -- no regressions to existing code; main.tsx modification is additive (DevTools mount)

## Recommendation
**Decision:** APPROVE

All success criteria from PLAN.md are met. TypeScript compiles clean, types match backend models, TanStack Query v5 API is used correctly (staleTime/refetchInterval as functions, object-form hooks, proper invalidation). WebSocket hook properly handles React 19 Strict Mode via readyState guard and mountedRef. The three medium issues (unreachable `'replaying'` status, duplicated URL params helper, non-discriminated WsMessage union) are all non-blocking and can be addressed in a follow-up cleanup.

---

# Architecture Re-Review (Post-Fix)

## Overall Assessment
**Status:** complete

All 6 issues from the initial review have been addressed. Fixes are clean, correct, and introduce no regressions. One new low-severity observation about the `'replaying'` status semantics in live-streaming mode.

## Project Guidelines Compliance
**CLAUDE.md:** `D:\Documents\claude-projects\llm-pipeline\CLAUDE.md`

| Guideline | Status | Notes |
| --- | --- | --- |
| No semicolons | pass | Verified across all changed files |
| Single quotes | pass | No double-quote regressions |
| `import type` for type-only imports | pass | `toSearchParams` correctly uses value import (it's a function); type imports unchanged |
| `verbatimModuleSyntax: true` compliance | pass | New `import { toSearchParams }` in runs.ts, events.ts, prompts.ts are value imports (function), correct |
| No hardcoded values | pass | No changes to URLs or constants |
| Error handling present | pass | No regressions |
| Prettier config compliance | pass | No style violations detected |

## Fix Verification

### Fix 1: WsMessage discriminated union (MEDIUM - Step 1)
**Verdict:** RESOLVED
`WsPipelineEvent` wrapper type added to `types.ts` with `type: 'pipeline_event'` discriminant. `WsMessage` union now uses `WsPipelineEvent` instead of raw `EventItem`. `parseWsMessage()` in `websocket.ts` tags incoming events with `type: 'pipeline_event'`. `switch(msg.type)` in the handler now has a proper `case 'pipeline_event'` branch. Union is fully discriminated and narrowable.

### Fix 2: URLSearchParams deduplication (MEDIUM - Steps 4, 6, 7)
**Verdict:** RESOLVED
Single `toSearchParams()` function in `types.ts` (line 365-371). Imported by `runs.ts`, `events.ts`, `prompts.ts`. Old per-file helpers (`buildEventParams`, `buildPromptParams`, local `toSearchParams` in runs.ts) removed. Implementation correctly filters null/undefined, returns empty string or `?key=value&...`.

### Fix 3: Unreachable 'replaying' status (MEDIUM - Step 9)
**Verdict:** RESOLVED (with observation)
WebSocket hook now transitions to `'replaying'` on the first `pipeline_event` when `currentStatus === 'connected'` (websocket.ts lines 173-177). Uses `useWsStore.getState().status` for synchronous read -- correct pattern. See low issue below re: live-stream semantics.

### Fix 4: Missing `enabled` guards (LOW - Steps 5, 6)
**Verdict:** RESOLVED
`enabled: Boolean(runId)` added to `useSteps` (line 22), `useStep` (line 53), `useEvents` (line 28). Now consistent with `useRun` and `useRunContext`.

### Fix 5: Status type cast (LOW - Step 4)
**Verdict:** RESOLVED
`as RunStatus | undefined` cast removed from `useRun` staleTime/refetchInterval callbacks. `isTerminalStatus` already accepts `RunStatus | string` (query-keys.ts line 41), so `query.state.data?.status` (typed as `string | undefined`) is accepted without casting.

### Fix 6: Dual reconnect tracking (LOW - Step 9)
**Verdict:** RESOLVED
Local `reconnectCountRef` removed. Reconnect delay now calculated from `useWsStore.getState().reconnectCount` (websocket.ts line 217) after `incrementReconnect()` call. Single source of truth.

## Issues Found

### Critical
None

### High
None

### Medium
None

### Low

#### `'replaying'` status triggers for both replay and live-stream modes
**Step:** 9
**Details:** The fix transitions to `'replaying'` on the first `pipeline_event` when status is `'connected'`. This works correctly for replay mode (completed/failed runs). However, for live-streaming runs (actively executing), the first real-time event also triggers `'replaying'`, which is semantically misleading -- the UI would show "replaying" during a live stream. The WebSocket protocol does not distinguish replay events from live events at the message level, so the hook cannot differentiate the two modes. Not functionally harmful (status transitions to `'closed'` on `stream_complete`/`replay_complete` regardless), but downstream UI components should be aware that `'replaying'` means "receiving events" rather than strictly "replaying historical data." Consider renaming to `'streaming'` in a follow-up if this distinction matters.

## Review Checklist
[x] Architecture patterns followed
[x] Code quality and maintainability
[x] Error handling present
[x] No hardcoded values
[x] Project conventions followed
[x] Security considerations
[x] Properly scoped (DRY, YAGNI, no over-engineering)

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| `src/api/types.ts` | pass | `WsPipelineEvent` wrapper added, `toSearchParams` centralized, union properly discriminated |
| `src/api/runs.ts` | pass | Uses shared `toSearchParams`, status cast removed, no regressions |
| `src/api/steps.ts` | pass | `enabled: Boolean(runId)` added to both hooks |
| `src/api/events.ts` | pass | Uses shared `toSearchParams`, `enabled` guard added |
| `src/api/prompts.ts` | pass | Uses shared `toSearchParams`, no other changes |
| `src/api/websocket.ts` | pass | `'replaying'` status set, dual ref removed, `WsPipelineEvent` case added |
| `src/stores/websocket.ts` | pass | No changes needed; `'replaying'` now reachable |

## New Issues Introduced
- None detected -- all fixes are additive/corrective with no regressions

## Recommendation
**Decision:** APPROVE

All 6 original issues resolved correctly. One new low observation (replaying/streaming semantic ambiguity) is non-blocking and purely a naming concern for future UI work. Code is clean, consistent, and ready to merge.
