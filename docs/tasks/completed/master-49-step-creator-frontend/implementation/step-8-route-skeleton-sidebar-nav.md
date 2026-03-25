# IMPLEMENTATION - STEP 8: ROUTE SKELETON + SIDEBAR NAV
**Status:** completed

## Summary
Created the `/creator` route with full workflow state machine, WebSocket integration, 3-column desktop layout (280px/1fr/350px), mobile tab fallback, and added Creator entry to sidebar navigation.

## Files
**Created:** `llm_pipeline/ui/frontend/src/routes/creator.tsx`
**Modified:** `llm_pipeline/ui/frontend/src/components/Sidebar.tsx`, `llm_pipeline/ui/frontend/src/routeTree.gen.ts`
**Deleted:** none

## Changes
### File: `src/components/Sidebar.tsx`
Added Wand2 icon import and Creator nav item.
```
# Before
import { List, Play, FileText, Box, PanelLeftClose, PanelLeftOpen, Menu } from 'lucide-react'
...
const navItems: NavItem[] = [
  { to: '/', label: 'Runs', icon: List },
  { to: '/live', label: 'Live', icon: Play },
  { to: '/prompts', label: 'Prompts', icon: FileText },
  { to: '/pipelines', label: 'Pipelines', icon: Box },
]

# After
import { List, Play, FileText, Box, Wand2, PanelLeftClose, PanelLeftOpen, Menu } from 'lucide-react'
...
const navItems: NavItem[] = [
  { to: '/', label: 'Runs', icon: List },
  { to: '/live', label: 'Live', icon: Play },
  { to: '/prompts', label: 'Prompts', icon: FileText },
  { to: '/pipelines', label: 'Pipelines', icon: Box },
  { to: '/creator', label: 'Creator', icon: Wand2 },
]
```

### File: `src/routes/creator.tsx`
New file implementing CreatorPage with:
- WorkflowState machine: idle -> generating -> draft -> testing -> tested -> accepting -> accepted | error
- All local state: description, targetPipeline, includeExtraction, includeTransformation, activeDraftId, activeRunId, generatedCode, activeTab, editableName, testResults, acceptResults, errorMessage, renameError
- useWebSocket(activeRunId) for generation progress streaming
- useWsStore for wsStatus
- useEvents for EventStream data
- stream_complete detection via useEffect watching events array
- handleGenerate: validates, calls generateStep.mutate(), seeds event cache, sets activeRunId, transitions to 'generating'
- handleTest: builds code_overrides from editor state, calls testDraft.mutate(), transitions testing -> tested/error
- handleAccept: calls acceptDraft.mutate(), transitions accepting -> accepted/error
- handleSelectDraft: fetches DraftDetail, populates editor state, sets workflow state based on draft.status
- handleNewDraft: resets all state to idle
- handleRename: calls renameDraft.mutate(), handles 409 conflict with inline error message
- Desktop: div with `lg:grid lg:grid-cols-[280px_1fr_350px] lg:gap-4`
- Mobile: Tabs with Input/Editor/Results tabs following live.tsx pattern
- Editable name Input field above editor with rename-on-blur and Enter key support

### File: `src/routeTree.gen.ts`
Added CreatorRoute import, route config, and all type declarations for `/creator` path.

## Decisions
### CreatorInputColumn wrapper usage
**Choice:** Used the existing `CreatorInputColumn` component (from step 6) that wraps DraftPicker + CreatorInputForm in a Card, rather than inlining both in the route.
**Rationale:** Component already exists and encapsulates the Card layout with proper separator and scroll behavior.

### Draft ID resolution after generate
**Choice:** After generate mutation succeeds, invalidate drafts query then read cache to find newest draft ID.
**Rationale:** GenerateResponse returns run_id and draft_name but not draft ID. Invalidating the list and reading the first item (ordered by created_at desc) is the simplest way to get the ID without a separate endpoint.

### Rename error handling for 409
**Choice:** Parse the error detail JSON for suggested_name and show inline error text below the name input.
**Rationale:** Matches plan spec. ApiError.detail may contain the JSON body with suggested_name from backend PATCH endpoint.

## Verification
[x] TypeScript compilation passes (`npx tsc --noEmit` - clean)
[x] Sidebar.tsx: Wand2 imported, navItem added with correct `to: '/creator'`
[x] routeTree.gen.ts: Creator route registered in all type interfaces
[x] Desktop layout: `lg:grid-cols-[280px_1fr_350px]` with `lg:gap-4`
[x] Mobile layout: 3 tabs (Input, Editor, Results) matching live.tsx pattern
[x] Page header: "Step Creator" title + subtitle
[x] All 7 callbacks implemented: handleGenerate, stream_complete effect, handleTest, handleAccept, handleSelectDraft, handleNewDraft, handleRename
[x] WebSocket wired: useWebSocket(activeRunId), useWsStore for wsStatus, useEvents for events
[x] WorkflowState type imported from CreatorResultsPanel (single source of truth)
