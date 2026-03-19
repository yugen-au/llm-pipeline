# Research Summary

## Executive Summary

Two research agents produced comprehensive analysis of frontend architecture and UI component design for task 49 (Step Creator Frontend). Cross-referencing with actual codebase revealed one **critical API mismatch** (GenerateRequest lacks step_name), one **blocker** (no endpoint returns generated_code), and confirmed StepDetailPanel reuse is impractical. Most other findings (tech stack, patterns, Monaco strategy) are accurate and actionable. Six questions require CEO input before planning can proceed.

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

### API Contract Mismatch (CRITICAL)
**Source:** cross-reference of step-1 section 4 vs actual llm_pipeline/ui/routes/creator.py

Both research files assume the frontend form includes a "Step Name" input field and that `GenerateRequest` accepts a `step_name` parameter. **This is wrong.** The actual `GenerateRequest` model (creator.py lines 30-35) has:
- `description: str` (required)
- `target_pipeline: str | None` (optional)
- `include_extraction: bool = True`
- `include_transformation: bool = False`

The step name is LLM-generated, not user-provided. The backend creates a temporary name `draft_{run_id[:8]}`, then updates it from `GenerationRecord.step_name_generated` after pipeline completion. This invalidates:
- Research step-2 section 3 "Input Form Design" proposing Step Name field with snake_case validation
- Research step-1 section 4 proposing GenerateRequest type with step_name
- Research step-2 section 2 using `stepName` to construct file paths (not available until after generation)
- Task 49 spec code sample referencing `step_name: request.step_name`

### Generated Code Data Flow (BLOCKER)
**Source:** cross-reference of step-1 Q3, step-2 section 11 vs actual creator.py

The frontend cannot populate the Monaco editor after generation because:
1. POST /generate returns 202 with `{run_id, draft_name, status}` -- no generated_code
2. Background task writes generated_code to DraftStep asynchronously
3. GET /drafts/{id} returns DraftItem which OMITS generated_code and test_results (confirmed: creator.py lines 69-81, 391-407)

A DraftDetail endpoint (or extending GET /drafts/{id}) that returns generated_code and test_results is **required**, not optional. This is a backend change (task 48 addendum).

### StepDetailPanel Incompatibility
**Source:** step-1 section 7, step-2 section 6, verified against StepDetailPanel.tsx (546 lines)

StepContent (inner component) is tightly coupled to pipeline run data:
- Props: (runId, stepNumber, runStatus)
- Uses 5 hooks: useStep, useStepEvents, useStepInstructions, usePipeline, useRunContext (research said 4, actually 5)
- 7 tabs all bound to StepDetail/EventItem/ContextSnapshot types

Creator test results (SandboxResult: import_ok, security_issues, output, errors, modules_found) have zero overlap with StepDetail shape. Extracting StepContent is unnecessary because:
- During generation: EventStream component (already standalone) can show WS events directly
- After testing: TestResponse needs its own card, not StepContent tabs
- After acceptance: AcceptResponse also has unique shape (files_written, prompts_registered, etc.)

### Monaco Editor Strategy
**Source:** step-1 section 9, step-2 section 2

Confirmed correct:
- React.lazy + Suspense for component-level lazy loading
- @monaco-editor/react loads Monaco core from CDN (no bundler config needed)
- `path` prop pattern preserves editor state (undo, scroll) across tab switches
- All 4 artifacts are Python files (not YAML as task 49 spec suggested for Prompts tab)
- manualChunks in vite.config.ts needs Monaco chunk added (line 38-48 in vite.config.ts)
- `saveViewState: true` + `automaticLayout: true` are essential options

### Layout and Responsive Pattern
**Source:** step-2 sections 1, 7, verified against live.tsx

- 3-column desktop grid with mobile tab fallback confirmed in live.tsx (lines 298-328)
- Content extracted into const variables for reuse in both layouts -- correct pattern
- Page header outside grid -- correct
- Weighted columns (grid-cols-[280px_1fr_350px]) deviate from live.tsx (grid-cols-3) but are more appropriate for IDE-like editor panel

### Workflow State Machine
**Source:** step-2 section 5

Proposed states: idle -> generating -> draft -> testing -> tested -> accepting -> accepted (+ error).
This is reasonable but needs refinement given API findings:
- "generating" phase needs to handle async completion via WS events
- Transition from "generating" to "draft" requires fetching DraftDetail (which doesn't exist yet)
- "draft" state should track both draftId AND the generated step name (which comes from backend)

### DraftStep Unique Constraint Risk
**Source:** discovered during codebase cross-reference (state.py line 236)

DraftStep has `UniqueConstraint("name")`. The generate endpoint creates initial draft with `draft_{run_id[:8]}` (unique), then renames to `GenerationRecord.step_name_generated` (LLM output). If two generation runs produce the same step name, the second rename will crash with a unique constraint violation. No conflict handling exists in the backend.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| (pending -- first validation loop, no CEO answers yet) | | |

## Assumptions Validated
- [x] Monaco not installed -- confirmed, must add @monaco-editor/react
- [x] All generated artifacts are Python files (not YAML) -- confirmed via GeneratedStep.from_draft()
- [x] 3-column layout follows live.tsx pattern with mobile tab fallback
- [x] Sidebar uses type-safe routing via keyof FileRoutesByTo
- [x] apiClient prepends /api, throws ApiError on non-OK
- [x] Generate endpoint is 202+background, creates PipelineRun and broadcasts WS run_created
- [x] Test endpoint persists code_overrides before running sandbox ("test and save" semantics)
- [x] WebSocket hook (useWebSocket) can track generation progress via run_id
- [x] EventStream component is standalone and reusable for generation progress display
- [x] Query key factory exists, needs creator keys added
- [x] Vite manualChunks exists but needs Monaco chunk

## Open Items
- GenerateRequest API mismatch: form fields must match actual backend contract (no step_name)
- DraftDetail endpoint required: backend must expose generated_code and test_results
- StepDetailPanel reuse decision: recommend building new CreatorResultsPanel
- Draft resumption support: determines whether draft picker UI is needed
- DraftStep name collision handling: LLM-generated names may conflict
- Column proportions: weighted vs equal grid deviation from live.tsx

## Recommendations for Planning
1. **Resolve API contract first** -- form fields must match GenerateRequest (description, target_pipeline, include_extraction, include_transformation). If CEO wants user-provided step_name, that's a backend change.
2. **Add DraftDetail endpoint to task 48** (or create sub-task) -- extend GET /drafts/{id} with optional `?include=code` query param or create separate endpoint. This is a blocker for editor population.
3. **Build CreatorResultsPanel from scratch** -- reuse visual primitives (Card, Badge, ScrollArea) but not StepContent. Three modes: EventStream during generation, TestResultsCard after test, AcceptResultsCard after accept.
4. **Use local useState for page state** (not Zustand) -- matches live.tsx pattern for page-specific state.
5. **Plan Monaco integration as separate subtask** -- lazy loading, Vite chunk config, editor skeleton, tab switching with path prop pattern.
6. **Address DraftStep name collision** before frontend can safely resume drafts -- either add backend conflict resolution or defer draft resumption.
