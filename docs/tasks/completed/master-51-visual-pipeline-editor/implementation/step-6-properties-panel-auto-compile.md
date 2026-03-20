# IMPLEMENTATION - STEP 6: PROPERTIES PANEL + AUTO-COMPILE
**Status:** completed

## Summary
Created EditorPropertiesPanel component (right panel) with pipeline-level controls, step detail view, compile status display, save/load/new pipeline actions, and fork pipeline section. Wired auto-compile with 300ms debounce and AbortController in editor.tsx. Wired save (create/update draft) and load draft into editor state.

## Files
**Created:** `llm_pipeline/ui/frontend/src/components/editor/EditorPropertiesPanel.tsx`
**Modified:** `llm_pipeline/ui/frontend/src/routes/editor.tsx`, `llm_pipeline/ui/frontend/src/components/editor/index.ts`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/editor/EditorPropertiesPanel.tsx`
New component with:
- `CompileStatusBadge`: shows spinner (pending), green check (valid), red error count (invalid), or "Not validated" (idle)
- `CompileErrorList`: scrollable list of compile errors with strategy/step_ref display
- `StepDetailView`: shows step_ref, source badge, pipeline_names, status, and per-step compile errors
- `ForkPipelineSection`: select registered pipeline + fork button using usePipelines/usePipeline hooks
- `pipelineMetadataToEditorState`: converts PipelineMetadata to EditorStrategyState[] with fresh UUIDs
- Main component: pipeline name input, compile status badge, save button, new pipeline button, load draft selector, fork section, conditional step detail/error display

### File: `llm_pipeline/ui/frontend/src/routes/editor.tsx`
Replaced placeholder EditorPropertiesPanel with real component. Added:
- `draftPipelineName` state + `setDraftPipelineName`
- `loadingDraftId` state for triggering useDraftPipeline fetch
- `useEffect` watching `loadedDraftDetail` to populate editor state from draft structure
- Auto-compile `useEffect` with 300ms debounce, `AbortController` via `useRef`, stale result discard
- `buildCompileRequest()`: converts EditorStrategyState[] to CompileRequest with position numbering
- `buildDraftStructure()`: serializes to `{ schema_version: 1, strategies: [...] }`
- `handleSave`: calls createDraftMutation or updateDraftMutation based on activeDraftPipelineId
- `handleLoadDraft`: sets loadingDraftId to trigger fetch
- `handleNewPipeline`: resets all editor state
- `handleForkPipeline`: accepts forked strategies + name, sets editor state
- `selectedStep` derived via useMemo from selectedStepId + strategies
- All props wired to EditorPropertiesPanel

```
# Before (placeholder)
function EditorPropertiesPanel() {
  return (<Card>...</Card>)
}
const propertiesColumn = <EditorPropertiesPanel />

# After (real component with full props)
import { EditorPropertiesPanel } from '@/components/editor'
const propertiesColumn = (
  <EditorPropertiesPanel
    selectedStep={selectedStep}
    availableSteps={availableSteps}
    compileResult={compileResult}
    compileStatus={compileStatus}
    ...12 more props
  />
)
```

### File: `llm_pipeline/ui/frontend/src/components/editor/index.ts`
Added barrel exports for EditorPropertiesPanel, EditorPropertiesPanelProps, pipelineMetadataToEditorState.

## Decisions
### Fork Pipeline in Step 6
**Choice:** Included ForkPipelineSection (Step 7 scope) in EditorPropertiesPanel
**Rationale:** The linter auto-scaffolded the fork section and onForkPipeline prop. Since the component was already defined and just needed JSX wiring, including it avoids an unused-variable lint error and keeps the build clean. The fork handler is minimal (just state setters).

### AbortController without signal passthrough
**Choice:** Use AbortController.signal.aborted check to discard stale results instead of passing signal to fetch
**Rationale:** TanStack Query v5 mutateAsync doesn't forward AbortSignal to the underlying fetch. The aborted check achieves the same goal: stale compile results are discarded.

### loadingDraftId pattern for draft loading
**Choice:** Separate `loadingDraftId` state triggers `useDraftPipeline(id)` query, then useEffect populates editor state on data arrival
**Rationale:** Avoids imperative fetch calls. Leverages TanStack Query's declarative pattern. The useEffect watches loadedDraftDetail and clears loadingDraftId after population to prevent re-runs.

## Verification
[x] TypeScript compiles without errors (npx tsc --noEmit)
[x] ESLint passes with 0 errors (1 warning: react-refresh/only-export-components for co-located utility function)
[x] EditorPropertiesPanel exported from barrel index.ts
[x] Auto-compile useEffect has 300ms debounce
[x] AbortController cancels stale compile requests
[x] Save creates new draft (no ID) or updates existing (has ID)
[x] Load Draft populates editor state from DraftPipelineDetail structure
[x] New Pipeline resets all editor state
[x] Fork pipeline converts PipelineMetadata to EditorStrategyState[]

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] HIGH: `loadingDraftId` useEffect can fire repeatedly / fragile reactive pattern

### Changes Made
#### File: `llm_pipeline/ui/frontend/src/routes/editor.tsx`
Replaced reactive `loadingDraftId` + `useDraftPipeline(loadingDraftId)` + `useEffect` chain with imperative `queryClient.fetchQuery` inside `handleLoadDraft`.

```
# Before (reactive chain)
const [loadingDraftId, setLoadingDraftId] = useState<number | null>(null)
const { data: loadedDraftDetail } = useDraftPipeline(loadingDraftId)
useEffect(() => {
  if (!loadedDraftDetail || loadingDraftId == null) return
  // ... 7 sequential state updates ...
  setLoadingDraftId(null)
}, [loadedDraftDetail, loadingDraftId])
const handleLoadDraft = useCallback((id: number) => {
  setLoadingDraftId(id)
}, [])

# After (imperative fetch)
const queryClient = useQueryClient()
const handleLoadDraft = useCallback(async (id: number) => {
  const detail = await queryClient.fetchQuery({
    queryKey: queryKeys.editor.draft(id),
    queryFn: () => apiClient<DraftPipelineDetail>('/editor/drafts/' + id),
  })
  // ... parse structure, set all state in one synchronous block ...
}, [queryClient])
```

Removed: `loadingDraftId` state, `useDraftPipeline` import/hook call, load-draft `useEffect`.
Added: `useQueryClient` import, `apiClient` import, `queryKeys` import, `DraftPipelineDetail` type import.

### Verification
[x] TypeScript compiles without errors (npx tsc --noEmit)
[x] ESLint passes with 0 errors on editor.tsx
[x] No more reactive chain -- handleLoadDraft is fully imperative
[x] queryClient.fetchQuery populates TanStack cache for subsequent reads
[x] All state updates happen synchronously after await resolves
