# IMPLEMENTATION - STEP 4: ADD WSRUNCREATED TYPE
**Status:** completed

## Summary
Added `WsRunCreated` interface to frontend types file for global WebSocket run-creation notifications on `/ws/runs`.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/src/api/types.ts
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/api/types.ts`
Added `WsRunCreated` interface after the `WsMessage` union type, in the WebSocket message types section. Standalone -- not added to the `WsMessage` union (which is per-run only).

```
# Before
export type WsMessage =
  | WsHeartbeat
  | WsStreamComplete
  | WsReplayComplete
  | WsError
  | WsPipelineEvent

// ---------------------------------------------------------------------------
// Shared utilities

# After
export type WsMessage =
  | WsHeartbeat
  | WsStreamComplete
  | WsReplayComplete
  | WsError
  | WsPipelineEvent

/**
 * Global run-creation notification received on /ws/runs.
 *
 * Standalone type -- NOT part of WsMessage union which is per-run only.
 * Used by useRunNotifications hook to detect externally-started runs.
 */
export interface WsRunCreated {
  type: 'run_created'
  run_id: string
  pipeline_name: string
  started_at: string
}

// ---------------------------------------------------------------------------
// Shared utilities
```

## Decisions
None -- straightforward type addition following existing naming conventions (`Ws` prefix + PascalCase event name).

## Verification
[x] TypeScript compiles with no errors (`npx tsc --noEmit` clean)
[x] Interface placed in WebSocket message types section
[x] Not added to WsMessage union (per-run only)
[x] Follows existing naming convention (WsHeartbeat, WsStreamComplete, etc.)
