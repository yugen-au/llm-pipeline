# Research Summary

## Executive Summary

Two research agents produced comprehensive analysis of frontend architecture and UI component design for task 49 (Step Creator Frontend). Cross-referencing with actual codebase revealed one critical API mismatch (GenerateRequest lacks step_name -- resolved: match backend, no step_name input), one blocker (no endpoint returns generated_code -- resolved: extend GET /drafts/{id}), and confirmed StepDetailPanel reuse requires extracting shared visual patterns into new shared components. All six CEO decisions are incorporated below. Research findings are otherwise accurate and actionable.

## Domain Findings

### Frontend Architecture (Codebase Patterns)
**Source:** step-1-frontend-architecture-research.md, verified against actual code

- Tech stack versions confirmed: React 19.2, TanStack Router 1.161.3, TanStack Query 5.90, Zustand 5.0, Zod 4.3, Vite 7.3, Tailwind 4.2
- File-based routing with autoCodeSplitting confirmed in vite.config.ts
- apiClient wrapper confirmed: prepends `/api`, throws typed ApiError
- Query key factory confirmed: hierarchical keys, no creator keys exist yet
- Zustand stores: useUIStore, useFiltersStore, useWsStore -- page-specific state uses local useState (live.tsx pattern)
- Monaco NOT installed (confirmed no @monaco-editor/react in package.json)
- Sidebar navItems uses `keyof FileRoutesByTo` for type-safe routing

### API Contract -- RESOLVED
**Source:** cross-reference of step-1 section 4 vs actual llm_pipeline/ui/routes/creator.py

Both research files assumed a "Step Name" input. The actual `GenerateRequest` model has:
- `description: str` (required)
- `target_pipeline: str | None` (optional)
- `include_extraction: bool = True`
- `include_transformation: bool = False`

Step name is LLM-generated, not user-provided. Backend creates temp name `draft_{run_id[:8]}`, updates from `GenerationRecord.step_name_generated` after pipeline completion.

**CEO Decision:** Match backend contract. Form has description field only (plus target_pipeline and toggle options). No step_name input.

**Impact on research:** Research step-2 section 3 "Input Form Design" snake_case validation is unnecessary. Research step-2 section 2 Monaco `path` prop cannot use stepName until AFTER generation completes (must use draft_name or artifact keys directly from the DraftDetail response).

### Generated Code Data Flow -- RESOLVED
**Source:** cross-reference of step-1 Q3, step-2 section 11 vs actual creator.py

The frontend cannot populate Monaco editor after generation because:
1. POST /generate returns 202 with `{run_id, draft_name, status}` -- no generated_code
2. Background task writes generated_code to DraftStep asynchronously
3. GET /drafts/{id} returns DraftItem which OMITS generated_code and test_results

**CEO Decision:** Extend GET /drafts/{id} to include generated_code + test_results. This is a task 48 addendum (backend change).

**Impact on planning:** Need to implement backend change before frontend can fully function. The `useDraft(draftId)` hook will return full DraftDetail including code. Frontend flow: detect generation completion via WS stream_complete event, then fetch DraftDetail to populate editor.

### Results Panel -- RESOLVED
**Source:** step-1 section 7, step-2 section 6, verified against StepDetailPanel.tsx (546 lines)

StepContent (inner component) is tightly coupled to pipeline run data:
- Props: (runId, stepNumber, runStatus)
- Uses 5 hooks: useStep, useStepEvents, useStepInstructions, usePipeline, useRunContext (research said 4, actually 5)
- 7 tabs all bound to StepDetail/EventItem/ContextSnapshot types
- Tab content components are private functions within StepDetailPanel.tsx

Creator test results (SandboxResult: import_ok, security_issues, output, errors, modules_found) have zero overlap with StepDetail shape.

**CEO Decision:** Extract shared visual patterns from StepDetailPanel into shared components, build new CreatorResultsPanel using those extracted patterns.

**Impact on planning:** This creates an extraction subtask BEFORE building CreatorResultsPanel. Candidates for extraction from StepDetailPanel.tsx:
- `ScrollArea` + `h-[calc(100vh-XXXpx)]` content wrapper pattern (used by every tab)
- Labeled `pre` block pattern (`text-xs font-medium text-muted-foreground` label + `whitespace-pre-wrap bg-muted p-3` pre) -- used in PromptsTab, ResponseTab
- Badge-labeled section pattern (Badge + content block) -- used in PromptsTab, InstructionsTab, MetaTab
- Loading skeleton patterns (pulse skeletons of varying sizes) -- used in PromptsTab, InputTab
- Empty state message pattern (`text-sm text-muted-foreground`) -- used in every tab
- Note: No `src/components/shared/` directory exists yet -- must create it
- JsonViewer is already a standalone shared component (`src/components/JsonViewer.tsx`)

### Draft Resumption -- RESOLVED
**Source:** step-1 Q2

**CEO Decision:** Full draft picker feature. Show list of existing drafts with ability to resume.

**Impact on planning:**
- Need draft list UI in column 1 (above or alongside form)
- `useDrafts()` query hook needed (GET /drafts already exists)
- `useDraft(draftId)` must return generated_code to populate editor on resume (covered by Q2 resolution)
- Selecting a draft loads its generated_code into Monaco, test_results into results panel, and enters "draft" workflow state
- UI pattern: follow prompts.tsx 2-column list+detail pattern, but adapted for column 1 of 3-column layout (compact draft list above form, or scrollable draft list replacing form when browsing)

### Unique Name Collision -- RESOLVED
**Source:** discovered during codebase cross-reference (state.py DraftStep unique constraint on name)

DraftStep has `UniqueConstraint("name")`. Generate creates `draft_{run_id[:8]}` (unique), then renames to LLM-generated `step_name_generated`. If two runs produce same name, second rename crashes.

**CEO Decision:** Address now -- add unique constraint handling with suffix or user rename.

**Impact on planning:**
- Backend: catch IntegrityError on name update, append numeric suffix (e.g., `_2`, `_3`) or surface error to frontend
- Frontend: after generation completes, show the LLM-generated name as editable (rename capability). If collision detected, prompt user to rename before accepting
- Requires backend endpoint or field for renaming a draft (PATCH /drafts/{id} with new name, or include name in accept request)
- This is both a backend addendum (task 48) and a frontend feature (task 49)

### Layout -- RESOLVED
**Source:** step-2 sections 1, 7

**CEO Decision:** Weighted columns: `grid-cols-[280px_1fr_350px]`. Editor gets most space.

**Impact on planning:** Deviates from live.tsx `grid-cols-3` but is appropriate for IDE-like interface. Mobile tab fallback pattern remains the same.

### Monaco Editor Strategy -- VALIDATED
**Source:** step-1 section 9, step-2 section 2

Confirmed correct:
- React.lazy + Suspense for component-level lazy loading
- @monaco-editor/react loads Monaco core from CDN (no bundler config needed)
- `path` prop pattern preserves editor state (undo, scroll) across tab switches
- All 4 artifacts are Python files (not YAML as task 49 spec suggested for Prompts tab)
- manualChunks in vite.config.ts needs Monaco chunk added
- `saveViewState: true` + `automaticLayout: true` are essential options
- `path` prop must use artifact keys from DraftDetail response (not stepName, since stepName isn't known until after generation)

### Workflow State Machine -- VALIDATED WITH REFINEMENT
**Source:** step-2 section 5

Proposed states: idle -> generating -> draft -> testing -> tested -> accepting -> accepted (+ error)

Refinements needed:
- Add "resuming" transition: selecting an existing draft from picker jumps to "draft" state
- "generating" phase detects completion via WS `stream_complete` event, then fetches DraftDetail
- "draft" state tracks: draftId, draftName (LLM-generated), generatedCode dict, editable name field
- After "accepted": option to start fresh (return to idle) or view accepted draft in read-only mode

### WebSocket Integration -- VALIDATED
**Source:** step-1 section 14

Generate creates PipelineRun for "step_creator" pipeline and broadcasts `run_created`. Existing `useWebSocket(runId)` tracks progress. Flow:
1. POST /generate -> 202 with {run_id, draft_name}
2. Connect useWebSocket(run_id)
3. Stream events (step_started, llm_call_starting, llm_call_completed, etc.)
4. On stream_complete -> fetch DraftDetail to populate editor

### Testing Patterns -- VALIDATED
**Source:** step-1 section 12

- Vitest + RTL + jsdom confirmed
- Colocated test files (Component.test.tsx next to Component.tsx)
- Hook mocking via vi.mock pattern confirmed
- No router wrapper needed for non-route components

### Sidebar Navigation -- VALIDATED
**Source:** step-2 section 10

Add `{ to: '/creator', label: 'Creator', icon: Wand2 }` to navItems array. Type-safe via `keyof FileRoutesByTo`.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| 1. GenerateRequest has no step_name. Match backend or add step_name (backend change)? | Match backend. Form has description only. | Removes step_name input field, snake_case validation. Simplifies form to description + toggles. |
| 2. DraftDetail endpoint needed for generated_code? | Extend GET /drafts/{id} to include generated_code + test_results. Task 48 addendum. | Adds backend dependency. Frontend fetches DraftDetail after generation completes via WS. |
| 3. StepDetailPanel reuse approach? | Extract shared visual patterns into shared components, build new CreatorResultsPanel using them. | Creates extraction subtask. Need new src/components/shared/ directory. |
| 4. Draft resumption? | Full feature -- draft picker with resume capability. | Adds draft list UI, useDrafts() hook, draft selection logic. Significant scope increase. |
| 5. Unique name collision? | Address now with suffix or user rename. | Backend + frontend work. Backend: collision handling. Frontend: editable name field post-generation. |
| 6. Column proportions? | Weighted: grid-cols-[280px_1fr_350px]. | Deviation from live.tsx grid-cols-3 is intentional for IDE-like layout. |

## Assumptions Validated
- [x] Monaco not installed -- must add @monaco-editor/react
- [x] All generated artifacts are Python files (not YAML) -- confirmed via GeneratedStep.from_draft()
- [x] 3-column layout follows live.tsx pattern with mobile tab fallback (weighted columns per CEO)
- [x] Sidebar uses type-safe routing via keyof FileRoutesByTo
- [x] apiClient prepends /api, throws ApiError on non-OK
- [x] Generate endpoint is 202+background, creates PipelineRun and broadcasts WS run_created
- [x] Test endpoint persists code_overrides before running sandbox ("test and save" semantics)
- [x] WebSocket hook (useWebSocket) can track generation progress via run_id
- [x] EventStream component is standalone and reusable for generation progress display
- [x] Query key factory exists, needs creator keys added
- [x] Vite manualChunks exists but needs Monaco chunk
- [x] Form fields match backend: description (required), target_pipeline (optional), include_extraction, include_transformation
- [x] No step_name input -- LLM generates name
- [x] DraftDetail endpoint will be extended (task 48 addendum)
- [x] Shared visual patterns extracted from StepDetailPanel before building CreatorResultsPanel
- [x] Draft picker with resume is in scope
- [x] Name collision handling is in scope
- [x] Weighted columns (280px / 1fr / 350px) for layout

## Open Items
- Task 48 addendum: extend GET /drafts/{id} response + add draft rename capability (backend dependency, must be done before frontend can fully function)
- Shared component extraction: identify exact components to extract from StepDetailPanel.tsx (candidates listed in Results Panel finding above)
- Draft picker UX: exact placement in column 1 (above form, collapsible list, or toggle between list/form view) -- can be decided during planning

## Recommendations for Planning
1. **Start with task 48 addendum** -- extend GET /drafts/{id} to return generated_code + test_results, add PATCH /drafts/{id} for rename. This unblocks editor population and draft resume.
2. **Extract shared visual patterns** from StepDetailPanel.tsx into `src/components/shared/` as first frontend subtask. Candidates: labeled pre blocks, badge-labeled sections, loading skeletons, empty state messages, scrollable content wrappers. Refactor StepDetailPanel to use the new shared components (verify no regression).
3. **Build API layer** (src/api/creator.ts) with all hooks: useGenerateStep, useTestDraft, useAcceptDraft, useDrafts, useDraft. Add creator query keys to query-keys.ts.
4. **Build route skeleton** (src/routes/creator.tsx) with 3-column weighted layout, mobile tab fallback, sidebar nav entry.
5. **Monaco integration** as separate subtask: install @monaco-editor/react, add Vite manualChunks, implement lazy loading with EditorSkeleton, tab switching with path prop.
6. **Draft picker + form** in column 1: compact draft list (status badges, timestamps), selection loads DraftDetail into editor. Form below list for new generation.
7. **CreatorResultsPanel** in column 3 using extracted shared components: EventStream during generation, TestResultsCard for sandbox results, AcceptResultsCard for integration results.
8. **Name collision handling**: editable name field shown post-generation, backend suffix logic on collision, validation on rename.
9. **Use local useState for page state** (not Zustand) -- matches live.tsx pattern.
10. **Testing**: colocated test files, vi.mock for hooks, test workflow state transitions, test draft resume flow.
