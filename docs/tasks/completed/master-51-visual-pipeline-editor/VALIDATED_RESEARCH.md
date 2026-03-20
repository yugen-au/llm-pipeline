# Research Summary

## Executive Summary

Validated three research documents for Task 51 (Visual Pipeline Editor). Research identified 5 internal contradictions and 6 architectural questions -- all now resolved via CEO decisions. The task is **full-stack**: 7 backend endpoints (compile + DraftPipeline CRUD + available-steps) plus a 3-panel frontend with multi-strategy DnD editing, step palette, and auto-compile on structural changes. All codebase claims verified against source files. DraftPipeline model exists (task 50 done) but has zero API surface -- backend must be built from scratch. Key resolved contradictions: local React state (not Zustand), 3-panel layout, strategy-grouped data model, 'registered' terminology, drag-handle isolation. Fork-existing-pipeline is in scope and can leverage the existing `GET /api/pipelines/{name}` endpoint for loading registered pipeline structure.

## Domain Findings

### @dnd-kit Library Selection
**Source:** research/step-1-dnd-editor-patterns.md

Stable packages (@dnd-kit/core + @dnd-kit/sortable + @dnd-kit/utilities) are the correct choice. The new @dnd-kit/react v0.3.2 is pre-1.0 and unsuitable.

**Risk identified:** React 19.2 compatibility with @dnd-kit is unverified. The project uses React 19.2.0 which is very recent. Version numbers cited (core v6.3.1, sortable v10.0.0) should be confirmed against npm registry before install.

**Verified pattern:** Drag handle isolation (attributes+listeners on GripVertical only, not entire card) is the correct approach for cards with interactive elements (select, remove buttons). Step 2's SortableStep example incorrectly spreads listeners on the entire wrapper div -- this would prevent click-to-select behavior.

### State Management -- RESOLVED
**Source:** step-1 vs step-2

- Step 1 proposes Zustand store with persist middleware (localStorage) for editor state
- Step 2 recommends local React state in the route file, following the Creator pattern (task 49)
- **Codebase verification:** Creator (creator.tsx) uses `useState` exclusively for all workflow/form/draft state. No Zustand store exists for creator-specific state. The UI Zustand store handles only global concerns (sidebar, theme).
- **Resolution:** Follow the Creator pattern. Local state in editor.tsx. Step 1's Zustand proposal is discarded. However, given the editor's complexity (multi-strategy DnD + auto-compile + palette interactions), if local state becomes unwieldy during implementation, a Zustand store can be introduced then -- but not as the starting architecture.

### Layout -- RESOLVED
**Source:** step-1 vs step-2; CEO decision Q5

- Step 1 proposes 2-panel: DnD step list (center) + properties panel (right)
- Step 2 proposes 3-panel: step palette (left) + DnD list (center) + properties (right)
- **CEO decision: 3-PANEL.** Left palette (available steps) + center DnD list + right properties panel.
- **Codebase verification:** Creator and Live both use 3-column layout. The editor follows the same `lg:grid lg:grid-cols-[280px_1fr_350px]` pattern with tabs mobile fallback.
- Step 1's AddStepDialog.tsx is superseded -- steps are added from the palette panel, not a dialog.

### Step Data Model -- RESOLVED
**Source:** step-1 vs step-3; CEO decisions Q4, Q2

| Aspect | Step 1 (EditorStep) | Step 3 (CompileStepRef) | **Resolution** |
| --- | --- | --- | --- |
| Name field | `stepName` | `step_ref` | Use `step_ref` (matches compile API) |
| Source values | `'pipeline' \| 'draft'` | `'draft' \| 'registered'` | Use `'draft' \| 'registered'` (matches codebase vocab) |
| Position | Implicit (array index) | Explicit `position: number` | Explicit position (needed for multi-strategy compile request) |
| Structure | Flat `EditorStep[]` | Nested `strategies[].steps[]` | **Nested** -- CEO confirmed multiple strategies visible |

**Frontend state model** must be strategy-grouped: `Map<strategyName, EditorStep[]>` or equivalent, where each strategy has its own SortableContext. Step 1's flat model is discarded.

**Step source filtering (CEO Q2):** Non-errored DraftSteps + registered steps. Errored DraftSteps excluded. Additionally, a "quick-create" escape hatch lets users create a real DraftStep from within the editor (redirects to or embeds a minimal creator form that writes to the DraftStep table).

### Strategy-Awareness -- RESOLVED
**Source:** step-1 (absent), step-3 (present), task 51 description; CEO decision Q4

- **CEO decision: MULTIPLE VISIBLE LISTS.** All strategies visible side-by-side as separate sortable step lists.
- Each strategy gets its own `SortableContext` with `verticalListSortingStrategy`.
- All wrapped in a single `DndContext` -- steps are reorderable within their strategy but not draggable between strategies (cross-strategy drag is out of scope for v1; same step can be added to multiple strategies independently).
- Center panel layout: strategies arranged horizontally (or vertically stacked if many). Each strategy section has a header (strategy name) + its sortable step list.
- For forked pipelines, strategies are pre-populated from the registered pipeline's introspection metadata.

### Backend API Surface -- CONFIRMED IN SCOPE
**Source:** research/step-3-backend-api-validation.md; CEO decision Q1

**CEO decision: FULL-STACK.** All 7 endpoints are in scope for task 51.

**Verified claims:**
- [x] No editor.py route file exists (glob confirmed)
- [x] DraftPipeline has no API surface (creator.py imports DraftStep only, not DraftPipeline)
- [x] All routes use plain Pydantic BaseModel for request/response (verified in creator.py, pipelines.py)
- [x] DBSession yields ReadOnlySession; writes need explicit Session(engine) (verified in creator.py)
- [x] introspection_registry lives on request.app.state (verified in app.py:203)
- [x] DraftPipeline.structure is untyped dict -- schema truly undefined (verified in state.py:254)

**Endpoints to build (7 total):**
1. POST /editor/compile -- validate structure (auto-triggered on every structural change with debounce)
2. GET /editor/available-steps -- merged step palette (non-errored DraftSteps + registered steps)
3. POST /editor/drafts -- create DraftPipeline
4. GET /editor/drafts -- list DraftPipelines
5. GET /editor/drafts/{id} -- get DraftPipeline
6. PATCH /editor/drafts/{id} -- update DraftPipeline
7. DELETE /editor/drafts/{id} -- delete DraftPipeline

**Fork-existing-pipeline (CEO Q3):** No new endpoint needed. The existing `GET /api/pipelines/{name}` returns full `PipelineMetadata` with strategies and steps. The frontend can load this, convert to the editor's strategy-grouped state model, and save as a new DraftPipeline via POST /editor/drafts.

**Risk -- step name uniqueness:** The compile endpoint assumes step names are globally unique. But different pipelines could theoretically use the same step class (same derived step_name). The available-steps endpoint should deduplicate by step_name and indicate which pipeline(s) each step belongs to.

**Risk -- auto-compile debounce:** CEO confirmed auto-compile on every structural change (Q6). The compile endpoint must be fast (no LLM calls, structural validation only). Frontend should debounce compile mutations (300-500ms) and cancel in-flight requests when new changes arrive. Use AbortController or TanStack Query mutation cancellation.

### DraftPipeline.structure Schema
**Source:** step-3

Step 3 proposes storing `strategies[{strategy_name, steps[{step_ref, source, position}]}]` in the JSON column. This is reasonable but:
- No versioning field -- if schema evolves, existing records could break
- Couples storage format to CompileRequest API format
- **Recommendation:** Add a `schema_version: 1` field at the top level for forward compatibility

### Task 50 Deviations
**Source:** task 50 SUMMARY.md, verified in state.py

- DraftStep removed redundant `ix_draft_steps_name` index (unique constraint suffices)
- Both models have unique constraint on `name`
- `updated_at` must be explicitly set on UPDATE (no DB trigger, no onupdate hook) -- this is a correctness requirement for any CRUD endpoint
- Both models exist and are exported from top-level package

### Existing Patterns for Consistency
**Source:** step-2, verified in codebase

- Route: `createFileRoute('/editor')({ component: EditorPage })`
- Sidebar: Add to navItems array (type-safe via FileRoutesByTo)
- Page header: `text-2xl font-semibold text-card-foreground`
- Query keys: hierarchical factory in query-keys.ts, needs `editor` section
- API hooks: follow creator.ts pattern (mutations + query invalidation)
- Component organization: `src/components/editor/` directory
- Tests: colocated `.test.tsx` files

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| Q1: Backend scope -- frontend-only or include backend? | FULL-STACK: include all 7 backend endpoints | Task is large (7 endpoints + DnD frontend). Consider subtask breakdown in planning. |
| Q2: Step source for "Add Step" | Non-errored DraftSteps + registered steps. Quick-create escape hatch for new DraftSteps from within editor. | available-steps endpoint filters `status != 'error'`. Quick-create needs minimal creator integration (POST /creator/generate or inline form that creates DraftStep). |
| Q3: Editor purpose -- new or fork existing? | BOTH: create new pipelines and load/fork existing registered pipelines | Fork flow uses existing `GET /api/pipelines/{name}` to load structure, converts to editor state, saves as new DraftPipeline. No new backend endpoint needed for fork. |
| Q4: Strategy handling | MULTIPLE VISIBLE LISTS: all strategies side-by-side | Multiple SortableContext instances within one DndContext. Center panel shows all strategies simultaneously. Cross-strategy drag out of scope for v1. |
| Q5: Layout | 3-PANEL: palette (left) + DnD list (center) + properties (right) | Follows creator/live 3-column pattern. Step 1's AddStepDialog.tsx superseded by palette panel. Mobile falls back to tabs. |
| Q6: Compile trigger | AUTO-COMPILE on every structural change with debounce | Frontend debounces compile mutations (300-500ms). Must handle in-flight cancellation. Errors clear on next structural change, re-appear after debounced compile. |

## Assumptions Validated

- [x] DraftPipeline and DraftStep SQLModel tables exist in state.py with correct fields (verified)
- [x] No editor backend routes exist -- must be created from scratch (glob confirmed)
- [x] Creator uses local React state, not Zustand, for page-scoped state (verified in creator.tsx)
- [x] introspection_registry on app.state provides PipelineConfig class references (verified in app.py)
- [x] DraftPipeline.structure JSON column has no defined schema (verified in state.py)
- [x] All route files use plain Pydantic BaseModel for request/response (verified in creator.py, pipelines.py)
- [x] DBSession provides ReadOnlySession; writes use explicit Session(engine) (verified in creator.py)
- [x] updated_at requires explicit set on UPDATE -- no DB trigger (per task 50 SUMMARY)
- [x] TanStack Router file-based routing auto-generates routeTree.gen.ts (verified)
- [x] Sidebar navItems use FileRoutesByTo type constraint for route safety (verified in Sidebar.tsx)

## Open Items

- @dnd-kit compatibility with React 19.2 needs npm registry verification before planning commits to package versions
- DraftPipeline.structure schema needs explicit definition during planning -- it is the contract between frontend, backend, and DB
- Step name global uniqueness across pipelines is assumed but unverified at scale -- the available-steps endpoint should include pipeline provenance
- Quick-create escape hatch UX undefined: does it open the creator in a new tab, a modal, or an inline form? Needs design during planning
- Cross-strategy step dragging explicitly out of scope for v1 -- document this in PLAN.md as future work
- Auto-compile error UX: how are per-step errors shown across multiple visible strategy lists? Needs wireframe during planning

## Recommendations for Planning

1. **Define DraftPipeline.structure schema first** -- it is the contract between frontend, backend, and DB. Add `schema_version: 1` field at top level for forward compatibility. Shape: `{ schema_version: 1, strategies: [{ strategy_name, steps: [{ step_ref, source, position }] }] }`
2. **Build backend before frontend** -- the 7 endpoints (editor.py) should be implemented and tested first, then frontend built against real API. This avoids mock-to-real migration cost.
3. **Split into subtasks** -- task is large. Suggested breakdown: (a) backend CRUD + compile endpoints, (b) frontend 3-panel shell + palette, (c) DnD multi-strategy editing, (d) auto-compile integration + error display, (e) fork-existing-pipeline flow, (f) quick-create escape hatch
4. **Follow creator pattern for state management** -- local React state in editor.tsx. Escalate to Zustand only if multi-strategy state becomes unwieldy during implementation.
5. **Use 'registered' terminology** (not 'pipeline') for steps from introspection_registry -- matches codebase vocabulary
6. **Drag handle isolation** -- listeners on GripVertical element only, not entire card. Step 2's SortableStep example (full-element listeners) must be corrected.
7. **Auto-compile debounce pattern** -- 300-500ms debounce on structural changes. Use AbortController to cancel in-flight compile requests. Clear errors immediately on change, re-display after debounced compile resolves.
8. **Verify @dnd-kit + React 19 compatibility** before `npm install` -- check changelogs and issue trackers for known React 19 issues
9. **available-steps endpoint filtering** -- non-errored DraftSteps (status in draft/tested/accepted) + registered steps from introspection. Deduplicate by step_name, include pipeline provenance for registered steps.
10. **Fork flow leverages existing API** -- `GET /api/pipelines/{name}` returns full PipelineMetadata with strategies[].steps[]. Frontend converts this to editor state model and saves as new DraftPipeline. No new backend endpoint needed.
11. **Multi-strategy DnD architecture** -- single DndContext wrapping multiple SortableContext instances (one per strategy). Each SortableContext uses verticalListSortingStrategy. Strategy sections arranged in the center panel with headers.
