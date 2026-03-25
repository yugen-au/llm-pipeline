# PLANNING

## Summary

Build the Step Creator frontend view: a `/creator` route with a 3-column weighted layout (280px input / 1fr editor / 350px results). Requires a backend addendum to task 48 (extend GET /drafts/{id} response + add draft rename), shared component extraction from StepDetailPanel, a new API layer, Monaco editor integration, draft picker with resume, name collision handling, and the CreatorResultsPanel. Local useState state machine drives the generate -> draft -> testing -> tested -> accepting -> accepted workflow.

## Plugin & Agents

**Plugin:** frontend-mobile-development, ui-design
**Subagents:** [available agents]
**Skills:** [available skills]

## Phases

1. **Backend addendum**: Extend GET /drafts/{id} to return DraftDetail (generated_code + test_results), add PATCH /drafts/{id} for rename, add unique name collision handling on draft name update. Unblocks all frontend steps that depend on generated_code.
2. **Shared components + API layer**: Extract reusable visual patterns from StepDetailPanel into src/components/shared/, add creator query keys, build src/api/creator.ts with all hooks/types.
3. **Route skeleton + Monaco**: Create src/routes/creator.tsx with 3-column layout, add sidebar nav entry, install @monaco-editor/react, configure Vite manualChunks, build CreatorEditor component.
4. **Input column + draft picker**: Build CreatorInputForm (description field + toggles + Generate button), DraftPicker (compact list with status badges, resume on click).
5. **Results panel**: Build CreatorResultsPanel using extracted shared components -- EventStream during generation, TestResultsCard for sandbox results, AcceptResultsCard for integration results.
6. **Name handling + integration**: Editable name field post-generation, collision error surfacing, wire up full workflow state machine in route.

## Architecture Decisions

### DraftDetail Response Model
**Choice:** Extend GET /drafts/{draft_id} to return a new `DraftDetail` Pydantic model that includes `generated_code: dict` and `test_results: dict | None` fields, alongside the existing DraftItem fields.
**Rationale:** Extending the existing endpoint is simpler than a new endpoint. Frontend uses `useDraft(draftId)` after generation completes (via WS stream_complete) and on draft resume. Keeping it a single endpoint avoids a new URL. DraftItem (lightweight) is only used for the list endpoint.
**Alternatives:** Separate `/drafts/{id}/detail` endpoint (unnecessary URL proliferation); return generated_code from generate mutation (insufficient for page refresh/resume).

### Draft Name Handling Strategy
**Choice:** Backend appends `_2`, `_3` suffix on IntegrityError during name update in run_creator background task. Frontend shows the final LLM-generated name as an editable field (Input component) after generation completes. PATCH /drafts/{id} endpoint accepts `{name: str}` for rename.
**Rationale:** CEO decision to address collision now. Suffix approach is invisible to user unless they inspect. Editable name field lets user override before accept. Backend catches IntegrityError and retries with suffix up to 9 times.
**Alternatives:** Only surface error to frontend (requires user action on collision); keep temp name until accept (loses LLM-generated name).

### Shared Component Extraction Scope
**Choice:** Extract exactly these patterns from StepDetailPanel.tsx into `src/components/shared/`: (1) `LabeledPre` - labeled pre block (`text-xs font-medium text-muted-foreground` label + `whitespace-pre-wrap bg-muted p-3` pre), (2) `BadgeSection` - Badge + content block, (3) `TabScrollArea` - `ScrollArea` with `h-[calc(100vh-220px)]` height pattern, (4) `LoadingSkeleton` - reusable pulse skeleton variants, (5) `EmptyState` - `text-sm text-muted-foreground` message.
**Rationale:** These 5 patterns appear in multiple tabs of StepDetailPanel and are needed by CreatorResultsPanel. Creating `src/components/shared/` directory (does not exist yet). StepDetailPanel is refactored to use them (regression check: no behavior change).
**Alternatives:** Duplicate patterns in CreatorResultsPanel (violates DRY, harder to maintain); extract only what CreatorResultsPanel needs (leaves StepDetailPanel inconsistent).

### Monaco Editor Integration Approach
**Choice:** `React.lazy()` + `Suspense` for component-level lazy loading of `@monaco-editor/react`. Single Editor instance outside TabsContent; tabs only change the `path` prop to switch between artifact files. Add `monaco-editor` manualChunks entry to vite.config.ts. Use `saveViewState: true` so undo/scroll position persists per-tab.
**Rationale:** Validated in research. Monaco is ~2MB -- must be lazy-loaded. The `path` prop pattern avoids unmount/remount on tab switch (loses undo history). autoCodeSplitting already handles route-level splitting; Monaco needs additional chunk.
**Alternatives:** Load Monaco eagerly (unacceptable bundle size impact); remount editor per tab (loses editor state, causes flicker).

### Workflow State Machine Location
**Choice:** Local `useState` in `creator.tsx` route component. WorkflowState type: `'idle' | 'generating' | 'draft' | 'testing' | 'tested' | 'accepting' | 'accepted' | 'error'`. No Zustand store.
**Rationale:** Matches live.tsx pattern -- page-specific state stays local. Zustand stores are for cross-page UI state. The creator workflow is entirely contained within the creator route.
**Alternatives:** Zustand store (over-engineering for single-page state); URL search params (unnecessary complexity for transient workflow state).

### Draft Picker UX in Column 1
**Choice:** Scrollable compact draft list above the form in column 1 (both visible simultaneously, not toggled). Draft list shows: name (truncated), status Badge, relative timestamp. Selecting a draft populates editor + results, switches to 'draft' workflow state. "New" button clears selection back to idle.
**Rationale:** Column 1 is 280px fixed -- enough for a compact list + short form. Having both visible avoids navigation between list and form. Form has only 2 fields (description + toggles) so it's compact enough to share the column.
**Alternatives:** Toggle between list view and form view (extra state/complexity); separate list+detail pattern like prompts.tsx (too much space needed).

## Implementation Steps

### Step 1: Backend DraftDetail endpoint + PATCH rename
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. In `llm_pipeline/ui/routes/creator.py`, add `DraftDetail` Pydantic model with all DraftItem fields plus `generated_code: dict` and `test_results: dict | None`.
2. Replace GET /drafts/{draft_id} response_model from `DraftItem` to `DraftDetail`. Update `get_draft()` to return all fields including generated_code and test_results from the DraftStep row.
3. Add `class RenameRequest(BaseModel): name: str` and PATCH `/drafts/{draft_id}` endpoint `rename_draft()` that updates DraftStep.name and handles IntegrityError with 409 response carrying `{detail: "name_conflict", suggested_name: <suffixed>}`.
4. In `run_creator()` background task, wrap the `draft.name = gen_rec.step_name_generated` assignment in a retry loop: catch `sqlalchemy.exc.IntegrityError`, append `_2` through `_9` suffix, retry commit. Log collision with `logger.warning`.
5. Update `DraftListResponse` to keep `DraftItem` (lightweight, no code) -- list endpoint unchanged.

### Step 2: Shared component library (src/components/shared/)
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. Create directory `llm_pipeline/ui/frontend/src/components/shared/`.
2. Create `LabeledPre.tsx`: props `label: string`, `content: string`, optional `className`. Renders `<p className="text-xs font-medium text-muted-foreground">{label}</p>` + `<pre className="whitespace-pre-wrap break-all rounded-md bg-muted p-3 text-xs">{content}</pre>`.
3. Create `BadgeSection.tsx`: props `badge: ReactNode`, `children: ReactNode`. Renders a `div` with `space-y-1` containing badge + children block.
4. Create `TabScrollArea.tsx`: props `children: ReactNode`, optional `className`. Renders `<ScrollArea className={cn("h-[calc(100vh-220px)]", className)}>` wrapping children. Import ScrollArea from `@/components/ui/scroll-area`.
5. Create `LoadingSkeleton.tsx`: exports `SkeletonLine` (`h-4 animate-pulse rounded bg-muted` with optional `width` prop), `SkeletonBlock` (`h-20 animate-pulse rounded bg-muted`).
6. Create `EmptyState.tsx`: props `message: string`. Renders `<p className="text-sm text-muted-foreground">{message}</p>`.
7. Create `index.ts` barrel export for all shared components.
8. Refactor `StepDetailPanel.tsx` to use the new shared components where patterns match. Run existing StepDetailPanel tests to verify no regression (no behavior change expected -- pure extraction).

### Step 3: Creator query keys + API layer
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. In `src/api/query-keys.ts`, add `creator` section after `pipelines`:
   ```typescript
   creator: {
     all: ['creator'] as const,
     drafts: () => ['creator', 'drafts'] as const,
     draft: (id: number) => ['creator', 'drafts', id] as const,
   },
   ```
2. Create `src/api/creator.ts`. Add TypeScript interfaces matching backend models: `GenerateRequest`, `GenerateResponse`, `TestRequest`, `TestResponse`, `AcceptRequest`, `AcceptResponse`, `DraftItem`, `DraftDetail`, `DraftListResponse`, `RenameRequest`.
3. Implement `useGenerateStep()` mutation: POST `/creator/generate`, returns `GenerateResponse`. On success: seed event cache for run_id (same pattern as live.tsx `queryClient.setQueryData`), resolve draftId from response.
4. Implement `useTestDraft(draftId)` mutation: POST `/creator/test/${draftId}`, body `TestRequest`. On success: invalidate `queryKeys.creator.draft(draftId)`.
5. Implement `useAcceptDraft(draftId)` mutation: POST `/creator/accept/${draftId}`, body `AcceptRequest`. On success: invalidate `queryKeys.creator.drafts()` and `queryKeys.creator.draft(draftId)`.
6. Implement `useDrafts()` query: GET `/creator/drafts`, returns `DraftListResponse`. staleTime: 30_000.
7. Implement `useDraft(draftId: number | null)` query: GET `/creator/drafts/${draftId}`, returns `DraftDetail`. Enabled only when draftId != null. staleTime: Infinity once status is 'accepted'; 10_000 for active drafts.
8. Implement `useRenameDraft()` mutation: PATCH `/creator/drafts/${draftId}`, body `RenameRequest`. On success: invalidate `queryKeys.creator.draft(draftId)` and `queryKeys.creator.drafts()`.

### Step 4: Monaco editor installation + Vite config
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /suren-atoyan/monaco-react
**Group:** C

1. In `llm_pipeline/ui/frontend/`, run `npm install @monaco-editor/react`. Verify package added to `package.json` dependencies.
2. In `vite.config.ts`, add Monaco chunk to `manualChunks` function:
   ```typescript
   if (id.includes('node_modules/monaco-editor/')) {
     return 'monaco'
   }
   ```
   Place before the existing react-dom check so Monaco is caught first.
3. Create `src/components/creator/EditorSkeleton.tsx`: renders `<div className="flex h-full flex-col gap-1 rounded-md bg-muted p-4">` with 12 animated skeleton lines of varying widths (`h-4 animate-pulse rounded bg-muted-foreground/10`). Used as Suspense fallback.

### Step 5: CreatorEditor component
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /suren-atoyan/monaco-react
**Group:** D

1. Create `src/components/creator/CreatorEditor.tsx`.
2. Define props: `generatedCode: Record<string, string>`, `draftName: string | null`, `activeTab: string`, `onTabChange: (tab: string) => void`, `onCodeChange: (filename: string, value: string) => void`, `onTest: () => void`, `onAccept: () => void`, `workflowState: WorkflowState`, `hasExtraction: boolean`.
3. Lazy-load Editor: `const MonacoEditor = lazy(() => import('@monaco-editor/react'))`.
4. Implement tab bar using shadcn Tabs: tabs for 'step', 'instructions', 'prompts', and optionally 'extractions' (disabled when `!hasExtraction`). Tab triggers control `activeTab` prop.
5. Render Monaco editor outside TabsContent: `path` prop = `${draftName ?? 'draft'}_${activeTab}.py` (maps tab to artifact filename). `defaultLanguage="python"`, `saveViewState={true}`. Options: `automaticLayout: true`, `scrollBeyondLastLine: false`, `minimap: { enabled: false }`, `fontSize: 13`, `tabSize: 4`, `wordWrap: 'on'`. Value comes from `generatedCode[currentPath] ?? ''`. onChange calls `onCodeChange(currentPath, value ?? '')`.
6. Pre-generation state: show `<EmptyState message="Generate a step to start editing" />` (imported from shared) instead of editor when generatedCode is empty.
7. Action button bar below editor (or tabs): Test button (FlaskConical icon, disabled unless workflowState in ['draft', 'tested', 'error']), Accept button (Check icon, disabled unless workflowState === 'tested'). Loader2 spinner when testing/accepting. Button states match the workflow state table from research.
8. Wrap Monaco in `<Suspense fallback={<EditorSkeleton />}>`.

### Step 6: CreatorInputForm + DraftPicker
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** D

1. Create `src/components/creator/DraftPicker.tsx`. Props: `drafts: DraftItem[]`, `isLoading: boolean`, `selectedDraftId: number | null`, `onSelect: (draft: DraftItem) => void`, `onNew: () => void`.
2. DraftPicker renders a compact scrollable list. Each item shows: truncated name (font-mono text-xs), status Badge (variant by status: 'secondary' for draft/tested, 'default' for accepted, 'destructive' for error), relative timestamp. Selected item highlighted. "New" button at top clears selection.
3. Create `src/components/creator/CreatorInputForm.tsx`. Props: `description: string`, `onDescriptionChange: (v: string) => void`, `targetPipeline: string | null`, `onTargetPipelineChange: (v: string | null) => void`, `includeExtraction: boolean`, `onIncludeExtractionChange: (v: boolean) => void`, `includeTransformation: boolean`, `onIncludeTransformationChange: (v: boolean) => void`, `onGenerate: () => void`, `isGenerating: boolean`, `disabled: boolean`.
4. Form fields: Description Textarea (required, min 10 chars inline validation, `aria-invalid` on error), target_pipeline Input (optional, labeled "Target Pipeline"), include_extraction Checkbox (default checked), include_transformation Checkbox (default unchecked).
5. Generate button: full-width, `disabled={!description.trim() || description.length < 10 || isGenerating || disabled}`. Shows Loader2 + "Generating..." when isGenerating; Wand2 + "Generate" otherwise.
6. Wrap both in a Card. DraftPicker at top (with `ScrollArea` wrapping list, max-h ~40% of column), CreatorInputForm below in `CardContent`.

### Step 7: CreatorResultsPanel + sub-components
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** D

1. Create `src/components/creator/TestResultsCard.tsx`. Props: `results: TestResponse`. Renders Card with: import status badge (Pass/Fail), security_issues list (if any, in destructive styling), output LabeledPre, errors list (if any), modules_found badge row. Import LabeledPre, BadgeSection, EmptyState from shared.
2. Create `src/components/creator/AcceptResultsCard.tsx`. Props: `results: AcceptResponse`. Renders Card with: files_written list (pre-formatted, LabeledPre), prompts_registered count, pipeline_file_updated Badge, target_dir text.
3. Create `src/components/creator/CreatorResultsPanel.tsx`. Props: `workflowState: WorkflowState`, `activeRunId: string | null`, `testResults: TestResponse | null`, `acceptResults: AcceptResponse | null`, `wsStatus: WsConnectionStatus`, `events: EventItem[]`.
4. Render content based on workflowState:
   - `idle`: `<EmptyState message="Generate a step to see results" />`
   - `generating`: EventStream component (imported from `@/components/live/EventStream`) with `events`, `wsStatus`, `runId={activeRunId}`. Wrap in Card.
   - `draft`: generation complete summary -- show Badge with "Ready to test" + draft status info
   - `testing`: `<SkeletonBlock />` loading indicator (from shared)
   - `tested`: `<TestResultsCard results={testResults} />`
   - `accepting`: `<SkeletonBlock />` loading indicator
   - `accepted`: `<AcceptResultsCard results={acceptResults} />`
   - `error`: error details with retry guidance using LabeledPre
5. Wrap in Card with `flex h-full flex-col overflow-hidden`.

### Step 8: Route skeleton + sidebar nav
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** E

1. In `src/components/Sidebar.tsx`, add `import { Wand2 } from 'lucide-react'` to existing imports. Add `{ to: '/creator', label: 'Creator', icon: Wand2 }` to `navItems` array. TypeScript will validate the route key once creator.tsx route exists.
2. Create `src/routes/creator.tsx`. Export `Route = createFileRoute('/creator')({ component: CreatorPage })`.
3. Implement `CreatorPage` component with all local state: `workflowState`, `description`, `targetPipeline`, `includeExtraction`, `includeTransformation`, `activeDraftId`, `activeRunId`, `generatedCode`, `activeTab`, `editableName`, `testResults`, `acceptResults`.
4. Wire up `useWebSocket(activeRunId)` for generation progress. Use `useWsStore` for wsStatus. Use existing `useEvents` hook with activeRunId for EventStream data.
5. Desktop layout: `<div className="hidden min-h-0 flex-1 lg:grid lg:grid-cols-[280px_1fr_350px] lg:gap-4">` with inputColumn, editorColumn, resultsColumn. Mobile: Tabs with 3 tabs (Input, Editor, Results) following live.tsx pattern exactly.
6. Page header: title "Step Creator", subtitle "Generate pipeline steps from natural language descriptions".
7. `handleGenerate` callback: validate form, call `generateStep.mutate()`, seed event cache, set activeRunId, transition to 'generating'.
8. WS stream_complete detection: `useEffect` watching events for `stream_complete` event type -- on detect, call `useDraft(activeDraftId)` refetch, transition to 'draft', populate generatedCode + editableName from DraftDetail response.
9. `handleTest` callback: build code_overrides from current editor state (codeOverrides dict), call `testDraft.mutate()`, transition to 'testing'. On success: set testResults, transition to 'tested'. On error: transition to 'error'.
10. `handleAccept` callback: call `acceptDraft.mutate()`, transition to 'accepting'. On success: set acceptResults, transition to 'accepted'.
11. Draft resume (from DraftPicker onSelect): call `useDraft(draft.id)` fetch, populate generatedCode + editableName + testResults from DraftDetail. Set activeDraftId. If draft.status in ['draft', 'error'] -> 'draft' state. If draft.status === 'tested' -> 'tested' state. If draft.status === 'accepted' -> 'accepted' state.
12. `handleRename` callback (on editableName blur or rename button): call `renameDraft.mutate({name: editableName})`. Handle 409 conflict: show inline error with suggested_name, allow user to accept suggestion or type new name.

### Step 9: Wire useDrafts + DraftPicker into layout
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** F

1. In `creator.tsx`, call `useDrafts()` at route level. Pass `data?.items ?? []` and `isLoading` to DraftPicker.
2. Connect `onSelect` to resume handler (Step 8 point 11). Connect `onNew` to reset all state back to idle.
3. On successful generate mutation: invalidate `queryKeys.creator.drafts()` so DraftPicker refreshes.
4. On successful accept: invalidate `queryKeys.creator.drafts()` so status shows 'accepted' in list.
5. Ensure selected draft is visually highlighted in DraftPicker (compare activeDraftId).

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Backend addendum (step 1) blocks frontend editor population | High | Step 1 is Group A (first), all editor-dependent steps are Group D/E/F. Plan explicitly sequences backend before frontend. |
| Monaco CDN load fails in dev/offline | Medium | @monaco-editor/react falls back gracefully; Suspense shows skeleton. Document that CDN is required in dev. No extra mitigation needed for MVP. |
| DraftStep.name unique constraint collision (timing) | Medium | Backend retry loop (step 1) handles concurrent generation. Frontend editable name + PATCH endpoint handles post-hoc rename. |
| useWebSocket stream_complete detection in creator vs live.tsx interference | Medium | useWebSocket is per-runId -- each call creates an isolated WS connection. No interference between live.tsx and creator.tsx. |
| Shared component extraction breaks StepDetailPanel visual regression | Low | Extraction is pure structural refactor (no logic change). StepDetailPanel tests remain and verify behavior. |
| `routeTree.gen.ts` not regenerated until dev server restart | Low | Adding creator.tsx route requires TanStack Router plugin to regenerate. Known limitation -- dev server must restart. Sidebar NavItem type check fails until then. |
| Monaco `path` prop file keys -- draftName not known until post-generation | Low | Use `draft_${draftId}` as path prefix when draftName is null; update path props once draftName is resolved from DraftDetail. |

## Success Criteria

- [ ] GET /drafts/{draft_id} returns generated_code and test_results fields in response
- [ ] PATCH /drafts/{draft_id} renames draft and returns 409 with suggested_name on collision
- [ ] Backend collision handling: duplicate LLM-generated name gets `_2` suffix automatically
- [ ] `src/components/shared/` exists with LabeledPre, BadgeSection, TabScrollArea, LoadingSkeleton, EmptyState
- [ ] StepDetailPanel refactored to use shared components with no visual regression
- [ ] `src/api/creator.ts` has all 5 hooks + TypeScript types matching backend models
- [ ] `query-keys.ts` has creator section with all, drafts, draft keys
- [ ] `@monaco-editor/react` installed in package.json
- [ ] `vite.config.ts` manualChunks includes monaco-editor chunk
- [ ] `/creator` route renders 3-column layout (`grid-cols-[280px_1fr_350px]`) on desktop
- [ ] Mobile tab fallback with Input/Editor/Results tabs renders correctly below lg breakpoint
- [ ] Sidebar shows "Creator" nav item with Wand2 icon linking to /creator
- [ ] Monaco editor lazy-loads with EditorSkeleton fallback
- [ ] Switching editor tabs (Step/Instructions/Prompts/Extractions) preserves undo history via `path` prop
- [ ] Generate workflow: description form -> POST /generate -> WS progress in results panel -> DraftDetail fetch populates editor
- [ ] Draft picker shows existing drafts with status badges; selecting a draft resumes workflow
- [ ] Test workflow: Test button -> POST /test -> TestResultsCard displayed in results panel
- [ ] Accept workflow: Accept button -> POST /accept -> AcceptResultsCard displayed in results panel
- [ ] Editable name field shown post-generation; rename triggers PATCH /drafts/{id}
- [ ] WorkflowState machine: all transitions work correctly (idle -> generating -> draft -> testing -> tested -> accepting -> accepted)
- [ ] Form validation: description required + min 10 chars enforced client-side

## Phase Recommendation

**Risk Level:** medium
**Reasoning:** Backend addendum (extend DraftDetail, add PATCH, collision handling) must land before frontend can fully function. This is a cross-layer dependency with a completed task (48). The shared component extraction adds refactoring risk to an existing component. Monaco installation is new-to-codebase but well-validated. Overall: medium risk from backend dependency sequencing and extraction refactor.
**Suggested Exclusions:** review
