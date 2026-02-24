# IMPLEMENTATION - STEP 5: USERUNNOTIFICATIONS HOOK
**Status:** completed

## Summary
Created `useRunNotifications` hook that connects to the global `/ws/runs` WebSocket endpoint to receive `run_created` notifications. Enables auto-detection of Python-initiated or externally-started pipeline runs.

## Files
**Created:** `llm_pipeline/ui/frontend/src/api/useRunNotifications.ts`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/api/useRunNotifications.ts`
New hook following the same reconnect-with-exponential-backoff pattern as `useWebSocket` in `src/api/websocket.ts`. Key differences from `useWebSocket`:
- No `runId` parameter -- connects unconditionally on mount to `/ws/runs`
- No TanStack Query cache integration -- simpler, only manages `latestRun` via `useState<WsRunCreated | null>`
- No Zustand store dependency -- reconnect count tracked via local ref
- Only processes `run_created` messages; ignores heartbeats and all other types
- `buildGlobalWsUrl()` helper constructs `ws(s)://host/ws/runs` (no run_id segment)

```
# Before
(file did not exist)

# After
- buildGlobalWsUrl() -> ws(s)://host/ws/runs
- useRunNotifications() hook:
  - useState<WsRunCreated | null> for latestRun
  - Refs: wsRef, reconnectTimerRef, hadConnectionRef, mountedRef, reconnectCountRef, connectRef
  - connect(): creates WebSocket, sets onopen/onmessage/onerror/onclose
  - onmessage: JSON.parse -> if type === 'run_created' -> setLatestRun
  - onclose: exponential backoff reconnect (BASE_RECONNECT_DELAY * 2^(count-1), capped at MAX_RECONNECT_DELAY)
  - Cleanup: clear timer, null-out handlers, close ws
  - Returns { latestRun }
```

## Decisions
### No Zustand store for connection state
**Choice:** Use local refs for reconnect count instead of a shared Zustand store
**Rationale:** This hook's connection state (connecting/connected/error) is not consumed by any UI component. Only `latestRun` matters to consumers. Adding a second Zustand store or extending the existing `useWsStore` (which is per-run scoped) would add unnecessary complexity.

### Reconnect on any non-1000 close code
**Choice:** Only skip reconnect on code 1000 (normal closure), reconnect on everything else
**Rationale:** Unlike per-run `useWebSocket` which also skips 4004 (run not found), the global endpoint has no equivalent "not found" terminal state. Any non-normal close is unexpected and should trigger reconnect.

## Verification
[x] TypeScript compilation passes (`tsc --noEmit` -- zero errors)
[x] ESLint passes (zero warnings/errors)
[x] Hook follows existing `useWebSocket` reconnect pattern (exponential backoff, hadConnection guard, mountedRef guard, connectRef for stale closure avoidance)
[x] `WsRunCreated` type imported from `src/api/types.ts` (added in Step 4)
[x] Cleanup nulls out all WebSocket handlers before closing (prevents post-unmount state updates)
