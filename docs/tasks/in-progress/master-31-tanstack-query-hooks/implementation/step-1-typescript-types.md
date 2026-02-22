# IMPLEMENTATION - STEP 1: TYPESCRIPT TYPES
**Status:** completed

## Summary
Created `src/api/types.ts` with 31 TypeScript exports (29 interfaces, 2 type aliases, 1 class) mirroring all backend Pydantic response models for the llm-pipeline UI. Covers runs, steps, events, context, prompts (provisional), pipelines (provisional), WebSocket messages, and ApiError.

## Files
**Created:** `llm_pipeline/ui/frontend/src/api/types.ts`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/api/types.ts`
New file. All interfaces derived from backend sources:
- `RunStatus`, `RunListItem`, `RunListResponse`, `StepSummary`, `RunDetail`, `TriggerRunRequest`, `TriggerRunResponse` from `llm_pipeline/ui/routes/runs.py`
- `RunListParams`, `EventListParams` from runs.py and events.py query param models
- `ContextSnapshot`, `ContextEvolutionResponse` from runs.py context endpoint
- `StepListItem`, `StepListResponse`, `StepDetail` from `llm_pipeline/ui/routes/steps.py`
- `EventItem`, `EventListResponse` from `llm_pipeline/ui/routes/events.py`
- `Prompt`, `PromptListResponse`, `PromptListParams` (@provisional) from `llm_pipeline/db/prompt.py`
- `ExtractionMetadata`, `TransformationMetadata`, `PipelineStepMetadata`, `PipelineStrategyMetadata`, `PipelineMetadata`, `PipelineListItem` (@provisional) from research on `PipelineIntrospector.get_metadata()`
- `WsHeartbeat`, `WsStreamComplete`, `WsReplayComplete`, `WsError`, `WsMessage` from `llm_pipeline/ui/routes/websocket.py`
- `ApiError` class extending `Error`

## Decisions
### Nullable fields use `| null` not `?` for response types
**Choice:** Used `field: type | null` for nullable response fields (e.g. `completed_at: string | null`)
**Rationale:** Backend returns explicit `null` in JSON for these fields (Pydantic serialization of `Optional` with default `None`). Using `?` would imply the field might be absent from the response, which is not the case.

### ExtractionMetadata and TransformationMetadata as separate interfaces
**Choice:** Extracted these as standalone interfaces rather than inline types within PipelineStepMetadata
**Rationale:** They're complex enough to warrant reuse and readability. Downstream task 40 (Pipeline Structure) will likely reference them individually.

### WsMessage discriminated union includes EventItem
**Choice:** Raw pipeline events in the WS stream are typed as `EventItem` (same shape as REST events)
**Rationale:** Backend sends `event_data` dicts over WS with the same fields as PipelineEventRecord. Using EventItem avoids duplicating the shape. Discrimination works via the `type` field on control messages vs `event_type` field on data events.

## Verification
[x] TypeScript compilation passes (`npx tsc --noEmit --project tsconfig.app.json`)
[x] Prettier formatting passes (`npx prettier --check src/api/types.ts`)
[x] No semicolons, single quotes throughout
[x] 31 exports exceed the 14+ interface target
[x] All `@provisional` TSDoc markers on prompts and pipelines types
[x] `import type` not needed (no type-only imports in this file)
[x] `verbatimModuleSyntax` compatible (no imports at all)

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] WsMessage discriminated union not truly discriminated -- added WsPipelineEvent wrapper type with `type: 'pipeline_event'` discriminant, replaced raw EventItem in WsMessage union
[x] Duplicated URLSearchParams helper across runs.ts, events.ts, prompts.ts -- added shared `toSearchParams()` utility to types.ts, removed local helpers from all three hook files

### Changes Made
#### File: `llm_pipeline/ui/frontend/src/api/types.ts`
Added `WsPipelineEvent` wrapper type: `{ type: 'pipeline_event' } & EventItem`. Updated `WsMessage` union to use `WsPipelineEvent` instead of raw `EventItem`. Added `toSearchParams()` utility function that filters null/undefined values and serializes to `?key=value&...` query string.

```
# Before (WsMessage)
export type WsMessage = WsHeartbeat | WsStreamComplete | WsReplayComplete | WsError | EventItem

# After (WsMessage)
export type WsPipelineEvent = { type: 'pipeline_event' } & EventItem
export type WsMessage = WsHeartbeat | WsStreamComplete | WsReplayComplete | WsError | WsPipelineEvent

# Before (no shared utility)
# (three local helpers in runs.ts, events.ts, prompts.ts)

# After (shared utility in types.ts)
export function toSearchParams(
  params: Record<string, string | number | boolean | undefined | null>,
): string
```

#### File: `llm_pipeline/ui/frontend/src/api/runs.ts`
Removed local `toSearchParams` function. Added `import { toSearchParams } from './types'`.

#### File: `llm_pipeline/ui/frontend/src/api/events.ts`
Removed local `buildEventParams` function. Added `import { toSearchParams } from './types'`. Updated call site.

#### File: `llm_pipeline/ui/frontend/src/api/prompts.ts`
Removed local `buildPromptParams` function. Added `import { toSearchParams } from './types'`. Updated call site.

### Verification
[x] TypeScript compilation passes (`npx tsc --noEmit --project tsconfig.app.json`)
[x] Prettier formatting passes on all 5 changed files
[x] WsMessage is now a proper discriminated union on `type` field
[x] All three hook files use shared `toSearchParams` -- no local duplicates remain
