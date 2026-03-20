# IMPLEMENTATION - STEP 9: WIRE DRAFTPICKER INTEGRATION
**Status:** completed

## Summary
All 6 step 9 requirements were already implemented in step 8's creator.tsx. The only change needed was fixing handleSelectDraft to use apiClient instead of raw fetch() for consistency and proper error handling.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/src/routes/creator.tsx
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/routes/creator.tsx`
Added `apiClient` import and replaced raw `fetch()` in handleSelectDraft with `apiClient<DraftDetail>()` for consistent error handling via ApiError.

```
# Before
import { ... } from '@/api/creator'
...
queryFn: () =>
  fetch(`/api/creator/drafts/${draft.id}`).then((r) => r.json()) as Promise<DraftDetail>,

# After
import { ... } from '@/api/creator'
import { apiClient } from '@/api/client'
...
queryFn: () =>
  apiClient<DraftDetail>(`/creator/drafts/${draft.id}`),
```

## Verification of Step 9 Requirements

### 1. useDrafts() at route level
Already wired: line 70 calls `useDrafts()`, passes `draftsData?.items ?? []` and `draftsLoading` via CreatorInputColumn to DraftPicker.

### 2. onSelect -> draft resume handler
Already wired: `handleSelectDraft` (lines 252-292) fetches DraftDetail via queryClient.fetchQuery, populates generatedCode + editableName + testResults via `populateFromDraft()`, sets activeDraftId, maps status to workflowState (draft/error -> 'draft', tested -> 'tested', accepted -> 'accepted').

### 3. onNew -> reset to idle
Already wired: `handleNewDraft` (lines 296-311) clears activeDraftId, generatedCode, editableName, testResults, acceptResults, activeRunId, description, workflowState -> 'idle'.

### 4. Generate mutation invalidates drafts
Already wired: `useGenerateStep` hook (api/creator.ts) invalidates `queryKeys.creator.drafts()` onSuccess. Additionally, `handleGenerate` in creator.tsx explicitly invalidates and refetches drafts to resolve the new draft ID.

### 5. Accept mutation invalidates drafts
Already wired: `useAcceptDraft` hook (api/creator.ts) invalidates both `queryKeys.creator.drafts()` and `queryKeys.creator.draft(draftId)` onSuccess.

### 6. Selected draft visually highlighted
Already wired: `selectedDraftId={activeDraftId}` passed to DraftPicker. DraftPicker applies `bg-accent ring-1 ring-ring/20` when `selectedDraftId === draft.id`.

## Decisions
### Use apiClient instead of raw fetch
**Choice:** Replaced `fetch('/api/creator/drafts/...')` with `apiClient<DraftDetail>('/creator/drafts/...')` in handleSelectDraft
**Rationale:** apiClient prepends `/api`, handles non-OK responses with typed ApiError, and is used by all other API calls. Raw fetch bypassed error normalization.

## Verification
[x] useDrafts() called at route level, data passed to DraftPicker
[x] onSelect wired to handleSelectDraft with status-to-workflowState mapping
[x] onNew wired to handleNewDraft with full state reset
[x] Generate mutation invalidates queryKeys.creator.drafts()
[x] Accept mutation invalidates queryKeys.creator.drafts()
[x] Selected draft highlighted via activeDraftId -> selectedDraftId comparison
[x] apiClient used consistently (fixed raw fetch)
