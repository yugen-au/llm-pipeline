# IMPLEMENTATION - STEP 9: WEBSOCKET HOOK
**Status:** completed

## Summary
Created Zustand v5 connection status store and WebSocket hook with TanStack Query cache integration. Hook handles all 3 server behaviors (not-found/4004, replay, live streaming), appends pipeline events to event query cache via setQueryData, invalidates steps on step-scoped events, and invalidates run detail on stream_complete. Includes React 19 Strict Mode guard, exponential backoff reconnection, and proper cleanup.

## Files
**Created:** llm_pipeline/ui/frontend/src/stores/websocket.ts, llm_pipeline/ui/frontend/src/api/websocket.ts
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/stores/websocket.ts`
New Zustand v5 store with WsConnectionStatus type union ('idle' | 'connecting' | 'connected' | 'replaying' | 'closed' | 'error') and WsState interface. Actions: setStatus, setError, incrementReconnect, reset. Uses create<WsState>()() double-call pattern per Zustand v5 TypeScript convention. No devtools middleware.

### File: `llm_pipeline/ui/frontend/src/api/websocket.ts`
New useWebSocket(runId: string | null) hook. Key implementation details:
- Returns early when runId is null, resets store to idle
- Builds ws/wss URL from window.location (Vite proxy handles upgrade in dev)
- React 19 Strict Mode guard: checks wsRef.current readyState before creating new WebSocket
- Parses messages as Record<string, unknown>, branches on `type` field for control messages vs `event_type` for pipeline events (avoids TypeScript discriminated union issue since EventItem lacks `type` field)
- heartbeat: no-op
- replay_complete: set status closed
- stream_complete: set status closed, invalidate run detail
- error: set status error with detail message
- Pipeline events: append to event cache via setQueryData, invalidate steps if step-scoped
- Close code 4004: set error "Run not found", no reconnect
- Close code 1000: normal closure, no reconnect
- Unexpected close: exponential backoff reconnect (1s base, 30s max)
- Cleanup: null all handlers, close ws, clear reconnect timer, reset store

## Decisions
### Discriminated union bypass
**Choice:** Parse WS messages as Record<string, unknown> and branch on `type` field presence instead of using WsMessage discriminated union with switch statement
**Rationale:** EventItem (part of WsMessage union) has `event_type` not `type`, so TypeScript cannot discriminate on `msg.type` across the union. Runtime check on `raw.type` and `raw.event_type` achieves the same dispatch without type errors.

### WebSocket URL construction
**Choice:** Build full ws/wss URL from window.location instead of relative `/ws/runs/{id}` path
**Rationale:** The WebSocket constructor requires an absolute URL. Using window.location.protocol and host ensures correct behavior in both dev (Vite proxy on localhost:5173) and prod (same-origin). Vite proxy config already maps `/ws` to the backend.

### mountedRef pattern
**Choice:** Track component mount state via useRef to guard all async callbacks
**Rationale:** WebSocket callbacks (onopen, onmessage, onclose) fire asynchronously and may execute after the effect cleanup runs (especially in Strict Mode). The mountedRef guard prevents state updates on unmounted components and avoids reconnection attempts after cleanup.

## Verification
[x] TypeScript compilation passes (tsc -b --noEmit)
[x] Prettier formatting passes (no semicolons, single quotes)
[x] Zustand store exports WsConnectionStatus type and useWsStore hook
[x] useWebSocket handles heartbeat, replay_complete, stream_complete, error message types
[x] Pipeline events appended to query cache via setQueryData
[x] Step-scoped events invalidate steps query
[x] stream_complete invalidates run detail query
[x] React 19 Strict Mode guard on wsRef.current readyState
[x] Close code 4004 sets "Run not found" error, no reconnect
[x] Close code 1000 treated as normal closure, no reconnect
[x] Unexpected disconnect triggers exponential backoff reconnect
[x] Effect cleanup closes ws, clears timer, resets store
[x] No unused imports (WsMessage removed since not directly used)
