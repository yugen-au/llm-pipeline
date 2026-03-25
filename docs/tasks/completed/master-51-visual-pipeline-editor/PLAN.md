# PLANNING

## Summary

Build the Visual Pipeline Editor: a full-stack feature consisting of 7 new backend endpoints (editor.py router) and a 3-panel React frontend at `/editor`. The frontend provides a step palette (left), multi-strategy DnD sortable step lists (center), and step properties panel (right). Auto-compile runs on every structural change with debounce. Users can create new pipelines or fork existing registered ones and persist them as DraftPipelines.

## Plugin & Agents

**Plugin:** backend-development, frontend-mobile-development, ui-design
**Subagents:** [available agents]
**Skills:** [available skills]

## Phases

1. **Backend**: Implement `llm_pipeline/ui/routes/editor.py` with all 7 endpoints and register in app.py
2. **Frontend Shell**: Route file, 3-panel layout, sidebar nav entry, API hooks, query keys
3. **Step Palette**: Left panel - available steps list with search/filter, quick-create link
4. **DnD Strategy Editor**: Center panel - multi-strategy sortable lists with @dnd-kit, add/remove steps
5. **Properties Panel + Auto-Compile**: Right panel step detail, compile-on-change with debounce, error display
6. **Fork Flow**: Load existing registered pipeline, convert to editor state, save as new DraftPipeline

## Architecture Decisions

### DraftPipeline.structure JSON Schema
**Choice:** `{ schema_version: 1, strategies: [{ strategy_name: string, steps: [{ step_ref: string, source: "draft" | "registered", position: number }] }] }`
**Rationale:** Matches the compile request shape directly. `schema_version: 1` enables forward migration. `step_ref` matches backend vocabulary. `source` matches CEO-resolved terminology from VALIDATED_RESEARCH.
**Alternatives:** Flat step list with strategy_name per step (rejected: harder to reconstruct per-strategy lists); coupling to frontend EditorStep type fully (rejected: mixes UI concerns into DB schema).

### Backend-First Build Order
**Choice:** Implement backend (Step A) before frontend (Steps B-F).
**Rationale:** Avoids mock-to-real API migration cost. Frontend hooks can reference real endpoints from day one. Validated in VALIDATED_RESEARCH recommendations.
**Alternatives:** Parallel build with mocks (rejected: two implementations of the same schema, divergence risk).

### State Management: Local React State
**Choice:** Local `useState` in editor.tsx for all editor state (strategies map, selected step, compile status).
**Rationale:** Creator (task 49) uses local state exclusively. Research confirmed Zustand handles only global concerns (sidebar, theme). Multi-strategy state is complex but manageable with a well-typed `Map<strategyName, EditorStep[]>`.
**Alternatives:** Zustand store (available as escalation path if state becomes unwieldy; not starting architecture per CEO+research).

### DnD Architecture: Single DndContext, Multiple SortableContext
**Choice:** One `DndContext` wrapping one `SortableContext` per strategy, each with `verticalListSortingStrategy`. Drag handles on `GripVertical` element only (not full card).
**Rationale:** Prevents cross-strategy dragging (out of scope v1). Correct handle isolation allows clicks on step select/remove buttons. VALIDATED_RESEARCH corrects step-2 pattern of spreading listeners on full wrapper div.
**Alternatives:** One SortableContext for all strategies (rejected: enables cross-strategy drag, unsupported in v1); react-beautiful-dnd (rejected: not in codebase, @dnd-kit already selected).

### Auto-Compile Pattern
**Choice:** 300ms debounce on structural changes (add/remove/reorder). AbortController cancels in-flight compile requests on new structural change. Errors cleared immediately on change, re-displayed after debounced compile resolves.
**Rationale:** CEO confirmed auto-compile on every structural change (Q6). Compile endpoint is structural-only (no LLM), so fast enough for near-real-time feedback. 300ms matches standard debounce for interactive UIs.
**Alternatives:** Manual compile button only (rejected by CEO); 500ms debounce (acceptable but 300ms preferred for responsiveness).

### Quick-Create Escape Hatch UX
**Choice:** "Create step" link in the step palette that navigates to `/creator` in a new tab (or same tab). No inline form or modal.
**Rationale:** The creator route already exists and is purpose-built for step creation. An inline modal would duplicate creator logic. New-tab navigation preserves editor state. VALIDATED_RESEARCH left this open; navigation is the lowest-complexity option.
**Alternatives:** Inline modal with minimal creator form (rejected: duplicates creator logic, increases scope); redirect same-tab (acceptable but loses editor context).

### Available-Steps API: Deduplication by step_name
**Choice:** `GET /editor/available-steps` returns merged list: non-errored DraftSteps (status in draft/tested/accepted) + registered steps from introspection_registry. Deduplicates by `step_ref` (step_name). Each item includes `source` field and `pipeline_names` list for registered steps.
**Rationale:** Step name uniqueness risk noted in VALIDATED_RESEARCH. Including provenance allows frontend to show which pipeline(s) each registered step belongs to. Non-errored filtering matches CEO Q2 answer.
**Alternatives:** No deduplication (risk: duplicate entries confuse users); separate endpoints for draft vs registered (rejected: frontend must merge manually).

## Implementation Steps

### Step 1: Backend Editor Router
**Agent:** [available agents]
**Skills:** [available skills]
**Context7 Docs:** /fastapi/fastapi
**Group:** A

1. Create `llm_pipeline/ui/routes/editor.py` with `router = APIRouter(prefix="/editor", tags=["editor"])`.
2. Define Pydantic request/response models (plain BaseModel, NOT SQLModel):
   - `EditorStep(step_ref: str, source: Literal["draft","registered"], position: int)`
   - `EditorStrategy(strategy_name: str, steps: list[EditorStep])`
   - `CompileRequest(strategies: list[EditorStrategy])`
   - `CompileError(strategy_name: str, step_ref: str, message: str)`
   - `CompileResponse(valid: bool, errors: list[CompileError])`
   - `AvailableStep(step_ref: str, source: Literal["draft","registered"], status: str | None, pipeline_names: list[str])`
   - `AvailableStepsResponse(steps: list[AvailableStep])`
   - `DraftPipelineItem(id: int, name: str, status: str, created_at: datetime, updated_at: datetime)`
   - `DraftPipelineDetail(extends DraftPipelineItem + structure: dict, compilation_errors: dict | None)`
   - `CreateDraftPipelineRequest(name: str, structure: dict)`
   - `UpdateDraftPipelineRequest(name: str | None, structure: dict | None)`
   - `DraftPipelineListResponse(items: list[DraftPipelineItem], total: int)`
3. Implement `POST /editor/compile`:
   - Parse CompileRequest; validate each step_ref exists in introspection_registry or non-errored DraftStep table.
   - Return CompileResponse(valid, errors). No LLM calls.
   - Uses `Session(engine)` for DB reads (read-only but needs explicit session pattern per codebase).
4. Implement `GET /editor/available-steps`:
   - Query DraftStep where status NOT IN ('error'). Map to AvailableStep(source='draft').
   - Read introspection_registry from `request.app.state`. Map each registered step_name to AvailableStep(source='registered', pipeline_names=[...]).
   - Merge and deduplicate by step_ref (registered wins if name clash; include both sources in pipeline_names).
   - Return AvailableStepsResponse.
5. Implement DraftPipeline CRUD (5 endpoints):
   - `POST /editor/drafts`: create DraftPipeline, set updated_at, handle IntegrityError (409).
   - `GET /editor/drafts`: list ordered by created_at desc, return DraftPipelineListResponse.
   - `GET /editor/drafts/{id}`: get by id, 404 if missing, return DraftPipelineDetail.
   - `PATCH /editor/drafts/{id}`: update name/structure, explicitly set `updated_at = utc_now()`, handle name IntegrityError (409 with suggested_name), return DraftPipelineDetail.
   - `DELETE /editor/drafts/{id}`: delete by id, 404 if missing, return 204.
6. All write endpoints use `with Session(engine) as session:` (not DBSession per creator.py pattern).
7. Register router in `llm_pipeline/ui/app.py`: `from llm_pipeline.ui.routes.editor import router as editor_router` then `app.include_router(editor_router, prefix="/api")`.

### Step 2: Frontend API Layer
**Agent:** [available agents]
**Skills:** [available skills]
**Context7 Docs:** /tanstack/query
**Group:** B

1. Add `editor` section to `src/api/query-keys.ts`:
   ```
   editor: {
     all: ['editor'] as const,
     availableSteps: () => ['editor', 'available-steps'] as const,
     drafts: () => ['editor', 'drafts'] as const,
     draft: (id: number) => ['editor', 'drafts', id] as const,
   }
   ```
2. Create `src/api/editor.ts` with TypeScript interfaces matching Step 1 Pydantic models:
   - `EditorStep`, `EditorStrategy`, `CompileRequest`, `CompileResponse`, `CompileError`
   - `AvailableStep`, `AvailableStepsResponse`
   - `DraftPipelineItem`, `DraftPipelineDetail`, `DraftPipelineListResponse`
   - `CreateDraftPipelineRequest`, `UpdateDraftPipelineRequest`
3. Implement TanStack Query hooks in `src/api/editor.ts`:
   - `useAvailableSteps()`: GET /editor/available-steps, staleTime 30s.
   - `useDraftPipelines()`: GET /editor/drafts, staleTime 30s.
   - `useDraftPipeline(id)`: GET /editor/drafts/{id}, enabled when id != null.
   - `useCompilePipeline()`: `useMutation` POST /editor/compile. Does NOT invalidate cache (compile is ephemeral).
   - `useCreateDraftPipeline()`: `useMutation` POST /editor/drafts, onSuccess invalidates drafts list.
   - `useUpdateDraftPipeline()`: `useMutation` PATCH /editor/drafts/{id}, onSuccess invalidates draft detail + list.
   - `useDeleteDraftPipeline()`: `useMutation` DELETE /editor/drafts/{id}, onSuccess invalidates drafts list.
4. Export all from `src/api/editor.ts`.

### Step 3: Route File + 3-Panel Shell
**Agent:** [available agents]
**Skills:** [available skills]
**Context7 Docs:** /tanstack/router
**Group:** B

1. Create `src/routes/editor.tsx`:
   - `export const Route = createFileRoute('/editor')({ component: EditorPage })`
   - `EditorPage` renders page header (`text-2xl font-semibold text-card-foreground` pattern from creator.tsx).
   - Desktop: `lg:grid lg:grid-cols-[280px_1fr_350px] lg:gap-4` (matches creator.tsx cols pattern).
   - Mobile: `Tabs` with "Palette" / "Editor" / "Properties" tabs (3 tabs, follows creator.tsx mobile pattern).
   - Columns: `<EditorPalettePanel>`, `<EditorStrategyCanvas>`, `<EditorPropertiesPanel>` (placeholder components initially).
2. Define TypeScript types local to editor.tsx:
   - `EditorStepItem`: `{ id: string; step_ref: string; source: "draft" | "registered" }`  (id is a uuid for DnD key, distinct from step_ref)
   - `EditorStrategyState`: `{ strategy_name: string; steps: EditorStepItem[] }`
   - Editor state: `strategies: EditorStrategyState[]`, `selectedStepId: string | null`, `activeDraftPipelineId: number | null`, `compileResult: CompileResponse | null`, `compileStatus: "idle" | "pending" | "error"`
3. Add editor route to sidebar in `src/components/Sidebar.tsx`:
   - Import `GitBranch` (or `Network`, or `LayoutGrid`) from lucide-react.
   - Add `{ to: '/editor', label: 'Editor', icon: GitBranch }` to navItems array.
   - TanStack Router's type system enforces `to` is `keyof FileRoutesByTo`; route must be created first for type safety (or use type assertion temporarily).

### Step 4: Step Palette Panel
**Agent:** [available agents]
**Skills:** [available skills]
**Context7 Docs:** /clauderic/dnd-kit
**Group:** C

1. Create `src/components/editor/EditorPalettePanel.tsx`:
   - Props: `onAddStepToStrategy(strategyName: string, step: AvailableStep): void`
   - Uses `useAvailableSteps()` hook; shows loading skeleton on pending.
   - Search input (shadcn `Input`) filters steps by step_ref substring.
   - Renders two sections: "Registered Steps" and "Draft Steps" (or combined sorted list with source badge).
   - Each step item: step_ref name + source badge (Badge component) + "Add" button per strategy (or select strategy then add).
   - "Create new step" link at bottom navigates to `/creator` (opens new tab: `window.open('/creator', '_blank')`). Uses shadcn Button variant="outline".
   - Each step is `draggable` from palette to strategy list via @dnd-kit `useDraggable` -- data payload `{ type: "palette-step", step }`. This enables drag-from-palette as alternative to Add button.
   - On empty state: use `src/components/shared/EmptyState.tsx` pattern.
2. Export `EditorPalettePanel` from `src/components/editor/index.ts`.

### Step 5: Multi-Strategy DnD Canvas
**Agent:** [available agents]
**Skills:** [available skills]
**Context7 Docs:** /clauderic/dnd-kit
**Group:** C

1. Install @dnd-kit packages in `llm_pipeline/ui/frontend/`:
   - `npm install @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities`
   - Verify React 19.2 compatibility against npm registry before committing package-lock changes.
2. Create `src/components/editor/EditorStrategyCanvas.tsx`:
   - Props: `strategies: EditorStrategyState[]`, `onStrategiesChange(strategies: EditorStrategyState[]): void`, `selectedStepId: string | null`, `onSelectStep(id: string | null): void`, `compileErrors: CompileError[]`
   - Renders single `DndContext` with `collisionDetection={closestCenter}` and `onDragEnd` handler.
   - Inside: one `StrategyList` component per strategy, arranged horizontally via flexbox (overflow-x-auto if many strategies).
3. Create `src/components/editor/StrategyList.tsx`:
   - Props: `strategy: EditorStrategyState`, `onStepsChange(steps: EditorStepItem[]): void`, `selectedStepId`, `onSelectStep`, `onRemoveStep(stepId: string): void`, `errors: CompileError[]`
   - Renders strategy name header + `SortableContext` with `verticalListSortingStrategy`.
   - `items` prop to SortableContext uses step `id` (UUID).
   - `useDroppable` on strategy container to accept drops from palette panel.
4. Create `src/components/editor/SortableStepCard.tsx`:
   - Uses `useSortable({ id: step.id })`.
   - `GripVertical` element gets `{...attributes} {...listeners}` (drag handle isolation -- NOT on wrapper).
   - Wrapper div gets `transform: CSS.Transform.toString(transform)`, `transition`.
   - Card content: step_ref name, source badge, error indicator (red border if compile error for this step_ref in this strategy).
   - Click on card body (not grip) calls `onSelectStep(step.id)`.
   - Remove button (X icon) calls `onRemoveStep(step.id)`.
5. `onDragEnd` logic in EditorStrategyCanvas:
   - If `active.data.current.type === 'palette-step'`: add step to target strategy (find strategy by droppable id), assign new UUID as id.
   - If `active.data.current.type === 'sortable-step'`: reorder within same strategy using `arrayMove` from @dnd-kit/sortable.
   - Cross-strategy drag: no-op (step does not move if over !== source strategy; document as v1 limitation).
6. Export from `src/components/editor/index.ts`.

### Step 6: Properties Panel + Auto-Compile
**Agent:** [available agents]
**Skills:** [available skills]
**Context7 Docs:** /tanstack/query
**Group:** D

1. Create `src/components/editor/EditorPropertiesPanel.tsx`:
   - Props: `selectedStep: EditorStepItem | null`, `availableSteps: AvailableStep[]`, `compileResult: CompileResponse | null`, `compileStatus: "idle" | "pending" | "error"`, `draftPipelineId: number | null`, `draftPipelineName: string`, `onNameChange(name: string): void`, `onSave(): void`, `isSaving: boolean`
   - When no step selected: shows pipeline-level info (name input, save button, compile status badge).
   - When step selected: shows step_ref, source, and any compile errors for that step.
   - Compile status display: "Validating..." spinner when pending, green checkmark when valid, error list when invalid.
   - Uses `Card` from shadcn, `ScrollArea` for error list.
2. Wire auto-compile in `editor.tsx`:
   - `useRef<AbortController | null>(null)` to track in-flight compile request.
   - `useEffect` watching `strategies` state:
     ```
     // On structural change: cancel in-flight, clear errors, schedule compile
     abortRef.current?.abort()
     setCompileStatus("idle")  // clear errors immediately
     const timer = setTimeout(async () => {
       const ac = new AbortController()
       abortRef.current = ac
       setCompileStatus("pending")
       try {
         const result = await compileMutation.mutateAsync(buildCompileRequest(strategies), { signal: ac.signal })
         setCompileResult(result)
         setCompileStatus(result.valid ? "idle" : "error")
       } catch (e) {
         if (!ac.signal.aborted) setCompileStatus("error")
       }
     }, 300)
     return () => { clearTimeout(timer); abortRef.current?.abort() }
     ```
   - `buildCompileRequest(strategies)`: converts `EditorStrategyState[]` to `CompileRequest` with explicit position numbering.
3. Wire save in `editor.tsx`:
   - `handleSave`: calls `useCreateDraftPipeline` (if no activeDraftPipelineId) or `useUpdateDraftPipeline` (if exists).
   - Structure serialized as `{ schema_version: 1, strategies: strategies.map((s, si) => ({ strategy_name: s.strategy_name, steps: s.steps.map((step, i) => ({ step_ref: step.step_ref, source: step.source, position: i })) })) }`.
4. Add "New Pipeline" and "Load Draft" UI to EditorPropertiesPanel or a toolbar:
   - "New Pipeline": resets editor state to empty.
   - "Load Draft": dropdown/select showing draft pipeline list (uses `useDraftPipelines()`), on select fetches detail and populates strategies state.

### Step 7: Fork Existing Pipeline Flow
**Agent:** [available agents]
**Skills:** [available skills]
**Context7 Docs:** /tanstack/query
**Group:** D

1. Add pipeline selector to EditorPropertiesPanel (or toolbar area):
   - `usePipelines()` hook (already exists in `src/api/pipelines.ts`) to list registered pipelines.
   - "Fork pipeline" select/combobox shows registered pipeline names.
   - On select: call `usePipeline(name)` to fetch `PipelineMetadata`, then convert to editor state:
     ```typescript
     function pipelineMetadataToEditorState(meta: PipelineMetadata): EditorStrategyState[] {
       return meta.strategies.map(s => ({
         strategy_name: s.name,
         steps: s.steps.map((step, i) => ({
           id: crypto.randomUUID(),
           step_ref: step.step_name,
           source: 'registered' as const,
         }))
       }))
     }
     ```
   - After conversion: set strategies state, set pipeline name to `forked_from_{meta.pipeline_name}`, set activeDraftPipelineId to null (fork = new draft).
   - User must save to persist as new DraftPipeline.
2. Reuse existing `usePipelines` and `usePipeline` from `src/api/pipelines.ts` -- no new API endpoints needed.

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| @dnd-kit incompatibility with React 19.2 | High | Verify npm registry changelog before install; check GitHub issues for React 19 reports; have fallback plan to pin React 18 compat shim or use pointer-events approach |
| DraftPipeline.structure schema evolution | Medium | `schema_version: 1` field in all writes; backend compile endpoint validates structure shape before trusting it |
| Auto-compile performance under rapid changes | Medium | AbortController cancels stale requests; 300ms debounce prevents request flood; compile endpoint is read-only (no LLM) |
| Step name uniqueness across pipelines | Low | available-steps deduplicates by step_ref; pipeline_names list shows provenance; user can see which pipelines share a step |
| `updated_at` not auto-set on DraftPipeline UPDATE | Medium | All PATCH handlers explicitly call `updated_at = utc_now()` (per task 50 SUMMARY finding -- no DB trigger) |
| Cross-strategy drag (v1 out of scope) | Low | Code comment + no-op handler; document as future work in code; single DndContext still needed for palette drops |
| Sidebar type safety for /editor route | Low | Route file must be created before adding to navItems; TanStack Router regenerates routeTree.gen.ts on file creation |

## Success Criteria

- [ ] `GET /api/editor/available-steps` returns merged non-errored DraftSteps + registered steps with source labels
- [ ] `POST /api/editor/compile` returns `{ valid: true, errors: [] }` for a valid strategy structure
- [ ] `POST /api/editor/compile` returns `{ valid: false, errors: [...] }` when step_ref is unknown
- [ ] DraftPipeline CRUD (POST/GET/PATCH/DELETE /api/editor/drafts) all return correct status codes
- [ ] PATCH /api/editor/drafts/{id} returns 409 on name collision
- [ ] `/editor` route renders 3-panel layout on desktop (lg+) and tabs on mobile
- [ ] "Editor" appears in sidebar navigation and routes correctly
- [ ] Step palette loads available steps and filters by search input
- [ ] Steps can be reordered within a strategy via drag-and-drop (GripVertical handle)
- [ ] Steps can be added to a strategy from the palette (Add button or drag from palette)
- [ ] Steps can be removed from a strategy (X button on card)
- [ ] Multiple strategies are visible simultaneously in the center panel
- [ ] Structural changes trigger auto-compile after 300ms debounce
- [ ] Compile errors display per-step in the center panel (red indicator on errored step card)
- [ ] Pipeline can be saved as DraftPipeline (persists name + structure)
- [ ] Existing registered pipeline can be forked into editor state
- [ ] Draft pipeline can be loaded back into editor state
- [ ] "Create new step" link opens `/creator` in a new tab
- [ ] @dnd-kit packages install without React 19.2 compatibility errors

## Phase Recommendation

**Risk Level:** high
**Reasoning:** Full-stack feature with new backend router (7 endpoints), new third-party DnD library (@dnd-kit with unverified React 19.2 compat), complex multi-strategy state management, auto-compile with debounce/abort pattern, and fork flow. Multiple integration surfaces (introspection_registry, DraftStep DB, DraftPipeline DB, existing pipelines API). @dnd-kit + React 19.2 compatibility is the highest unknown risk; if incompatible, the DnD approach must change.
**Suggested Exclusions:** none
