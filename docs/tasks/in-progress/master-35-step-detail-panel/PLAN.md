# PLANNING

## Summary

Implement Step Detail Panel (task 35) with expanded scope covering 2 backend features and the frontend panel rewrite. Backend adds a `step_name` column to `PipelineEventRecord` for efficient server-side filtering plus a new instruction content endpoint that queries the `Prompt` table. Frontend rewrites the div-based panel as a shadcn/ui Sheet with 7 tabs (Input, Prompts, LLM Response, Instructions, Context Diff, Extractions, Meta), consuming data from the new and existing hooks.

## Plugin & Agents

**Plugin:** backend-development (backend steps), frontend-mobile-development (frontend steps)
**Subagents:** backend-dev, frontend-dev
**Skills:** none

## Phases

1. **Backend - Event Filter**: Add `step_name` column to `PipelineEventRecord`, populate on persist, add filter to events API endpoint
2. **Backend - Instruction Content**: New GET endpoint for step prompt content querying the `Prompt` table via DB session
3. **Frontend - Infrastructure**: Install shadcn Sheet + Tabs, update TypeScript types, create hooks
4. **Frontend - Panel Rewrite**: Rewrite `StepDetailPanel` with Sheet+Tabs+7 tab content components, rewrite tests

## Architecture Decisions

### step_name column vs JSON extraction at query time

**Choice:** Add `step_name` as a dedicated nullable column on `PipelineEventRecord` with a composite index on `(run_id, step_name)`.
**Rationale:** Matches the existing pattern in `PipelineEventRecord` which explicitly documents "Intentionally duplicates run_id/event_type/timestamp as columns for query efficiency." SQLite JSON extraction functions (`json_extract`) are slower than indexed column lookups and the codebase has no prior usage. Column is nullable to accommodate pipeline-level events (PipelineStarted, PipelineCompleted) that have no step scope.
**Alternatives:** JSON extraction at query time - rejected due to no index support and performance; separate step_events table - over-engineering.

### ALTER TABLE migration strategy for existing DBs

**Choice:** Add startup migration in `SQLiteEventHandler.__init__` using raw SQL `ALTER TABLE pipeline_events ADD COLUMN step_name VARCHAR(100)` wrapped in a try/except for `OperationalError` (column already exists). No migration framework.
**Rationale:** SQLite only supports `ADD COLUMN`, not `DROP` or `MODIFY`. `create_all()` does not add columns to existing tables. The project has no migration framework (no Alembic). Existing rows will have NULL step_name which is correct - pipeline-level events have no step. New rows will have step_name set from event attributes. This matches the minimal footprint of the project.
**Alternatives:** Alembic - adds significant dependency; manual one-time SQL script - requires user action; JSON backfill - possible but would make startup non-idempotent and slow.

### Instruction content endpoint URL

**Choice:** `GET /api/pipelines/{name}/steps/{step_name}/prompts` returning `StepPromptsResponse` with system and user prompt variants.
**Rationale:** Logically nested under the existing pipelines router. Consistent with REST hierarchy. The existing `/pipelines/{name}` endpoint uses `Request` for app.state registry access; the new endpoint adds `DBSession` dependency to query Prompt table - these are orthogonal and can coexist in the same router file.
**Alternatives:** `GET /api/pipelines/{name}/steps/{step_name}/instructions` - less precise naming (instructions = schema, prompts = content); extending `GET /pipelines/{name}` to inline prompt content - would bloat the introspection response.

### useStepEvents hook placement

**Choice:** Add `useStepEvents(runId, stepName, runStatus?)` to `src/api/events.ts` as a named export alongside `useEvents`. It calls `useEvents` with `{ step_name: stepName }` filter.
**Rationale:** Keeps all event-fetching hooks co-located. Avoids duplication of staleTime/polling logic by delegating to `useEvents`. query key naturally differs due to filter object inclusion.
**Alternatives:** Inline filtering in StepDetailPanel - would not benefit from server-side pagination and adds client-side noise.

### Multi-call (consensus) display for Prompts/LLM Response tabs

**Choice:** Use `.filter()` on step events to get all `llm_call_starting` and `llm_call_completed` events. Render as a list with call index as separator header (e.g. "Call 1 of 3"). Show all calls, not just the first.
**Rationale:** `LLMCallStarting.call_index` and `LLMCallCompleted.call_index` fields support this. Task description incorrectly uses `.find()` (returns first match); consensus steps emit multiple events. Rendering all calls provides full visibility.
**Alternatives:** Only show last/winning call - loses consensus debugging value; show only first call - same problem.

### TypeScript event_data discriminated unions

**Choice:** Define minimum required typed interfaces in `types.ts`: `LLMCallStartingData`, `LLMCallCompletedData`, `ContextUpdatedData`, `ExtractionCompletedData`. Access via type assertion helpers in StepDetailPanel (no runtime schema validation).
**Rationale:** The existing `EventItem.event_data: Record<string, unknown>` is already in types.ts. Adding typed interfaces for the 4 event types needed by tab content is low-cost and sufficient. Full runtime validation (zod) is out of scope for this task.
**Alternatives:** Runtime zod parsing - adds dependency, out of scope; leave as Record<string, unknown> with unsafe casts throughout - harder to maintain.

### Context Diff tab implementation

**Choice:** Show ContextUpdated events before/after for this step as two JSON blocks (previous step's snapshot vs this step's snapshot). Use simple side-by-side or stacked display with highlighted new_keys list. Defer rich visual diff to task 36.
**Rationale:** VALIDATED_RESEARCH.md states "Defer rich diff visualization to task 36; show raw JSON comparison for now." The `new_keys` field on ContextUpdated event tells us exactly what changed - display that as a summary alongside the snapshots.
**Alternatives:** Rich JSON diff library now - deferred to task 36 per CEO decision.

## Implementation Steps

### Step 1: Add step_name column to PipelineEventRecord

**Agent:** backend-development:backend-dev
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Edit `llm_pipeline/events/models.py`: add `step_name: Optional[str] = Field(default=None, max_length=100, description="Step name for step-scoped events, None for pipeline-level events")` to `PipelineEventRecord` after `pipeline_name`.
2. Add `Index("ix_pipeline_events_run_step", "run_id", "step_name")` to `__table_args__`.
3. Edit `llm_pipeline/events/handlers.py` `SQLiteEventHandler.__init__`: after `SQLModel.metadata.create_all(...)`, add try/except `OperationalError` block that runs `ALTER TABLE pipeline_events ADD COLUMN step_name VARCHAR(100)` via `engine.connect()` to handle existing DBs.
4. Edit `SQLiteEventHandler.emit`: extract `step_name = getattr(event, "step_name", None)` and pass to `PipelineEventRecord(...)`.

### Step 2: Add step_name filter to events API

**Agent:** backend-development:backend-dev
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Edit `llm_pipeline/ui/routes/events.py` `EventListParams`: add `step_name: Optional[str] = None`.
2. Edit `list_events` count query: add `if params.step_name is not None: count_stmt = count_stmt.where(PipelineEventRecord.step_name == params.step_name)`.
3. Edit `list_events` data query: same conditional WHERE clause.
4. No change needed to `EventItem` response model (step_name not needed in response body - it's a filter param).

### Step 3: Add instruction content endpoint

**Agent:** backend-development:backend-dev
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. Add Pydantic response models to `llm_pipeline/ui/routes/pipelines.py`: `StepPromptItem` (prompt_key, prompt_type, content, required_variables, version) and `StepPromptsResponse` (pipeline_name, step_name, prompts: list[StepPromptItem]).
2. Add endpoint `GET /{name}/steps/{step_name}/prompts` to pipelines router. Accepts `name: str`, `step_name: str`, `request: Request`, `db: DBSession`. Validates pipeline exists in introspection registry (404 if not). Queries `Prompt` table: `select(Prompt).where(Prompt.step_name == step_name)`. Returns `StepPromptsResponse`.
3. Add import for `Prompt` from `llm_pipeline.db.prompt` and `DBSession` from `llm_pipeline.ui.deps`.

### Step 4: Update TypeScript types and add event_data interfaces

**Agent:** frontend-mobile-development:frontend-dev
**Skills:** none
**Context7 Docs:** /shadcn-ui/ui
**Group:** C

1. Edit `src/api/types.ts` `EventListParams`: add `step_name?: string`.
2. Add typed event_data interfaces after the Events section: `LLMCallStartingData { call_index: number; rendered_system_prompt: string; rendered_user_prompt: string }`, `LLMCallCompletedData { call_index: number; raw_response: string | null; parsed_result: Record<string, unknown> | null; model_name: string | null; attempt_count: number; validation_errors: string[] }`, `ContextUpdatedData { new_keys: string[]; context_snapshot: Record<string, unknown> }`, `ExtractionCompletedData { extraction_class: string; model_class: string; instance_count: number; execution_time_ms: number }`.
3. Add `StepPromptsResponse { pipeline_name: string; step_name: string; prompts: StepPromptItem[] }` and `StepPromptItem { prompt_key: string; prompt_type: string; content: string; required_variables: string[] | null; version: string }` types.
4. Add `stepPrompts` key to `queryKeys.pipelines` in `src/api/query-keys.ts`: `stepPrompts: (name: string, stepName: string) => ['pipelines', name, 'steps', stepName, 'prompts'] as const`.

### Step 5: Install shadcn Sheet and Tabs components

**Agent:** frontend-mobile-development:frontend-dev
**Skills:** none
**Context7 Docs:** /shadcn-ui/ui
**Group:** C

1. Run `npx shadcn@latest add sheet` in `llm_pipeline/ui/frontend/`.
2. Run `npx shadcn@latest add tabs` in `llm_pipeline/ui/frontend/`.
3. Verify generated files at `src/components/ui/sheet.tsx` and `src/components/ui/tabs.tsx` exist.

### Step 6: Create useStepEvents and useStepInstructions hooks

**Agent:** frontend-mobile-development:frontend-dev
**Skills:** none
**Context7 Docs:** -
**Group:** D

1. Edit `src/api/events.ts`: add `useStepEvents(runId: string, stepName: string, runStatus?: RunStatus | string)` that calls `useEvents(runId, { step_name: stepName }, runStatus)`.
2. Create `src/api/pipelines.ts`: add `useStepInstructions(pipelineName: string, stepName: string)` that fetches `GET /pipelines/{pipelineName}/steps/{stepName}/prompts` with `staleTime: Infinity` (static pipeline definition data). Import `StepPromptsResponse` from types, use `queryKeys.pipelines.stepPrompts(pipelineName, stepName)`.

### Step 7: Rewrite StepDetailPanel with Sheet and 7-tab layout

**Agent:** frontend-mobile-development:frontend-dev
**Skills:** none
**Context7 Docs:** /shadcn-ui/ui
**Group:** E

1. Fully rewrite `src/components/runs/StepDetailPanel.tsx`. Replace div-based panel + custom a11y (focus trap, Escape, backdrop, ~50 lines) with `Sheet` + `SheetContent className="w-[600px]"`. Use `Sheet open={open} onOpenChange={(o) => !o && onClose()}`.
2. Keep `StepDetailPanelProps` interface identical: `{ runId, stepNumber: number | null, open, onClose, runStatus? }`. Keep `StepContent` child component pattern (mounts only when open && stepNumber != null).
3. Inside `StepContent`, fetch: `useStep(runId, stepNumber, runStatus)`, `useStepEvents(runId, step?.step_name, runStatus)` (enabled after step resolves for step_name), `useStepInstructions(run.pipeline_name, step?.step_name)` (enabled after step resolves).
4. Add `Tabs defaultValue="meta"` with `TabsList` and 7 `TabsTrigger` values: input, prompts, response, instructions, context, extractions, meta.
5. Build tab content components as private functions within the file:
   - `InputTab`: filters step events for `context_updated` typed as `ContextUpdatedData`, finds previous step's snapshot by looking for event where step order < current step (use step_number to identify). Display previous snapshot as formatted JSON in `ScrollArea`. Show "No prior context (first step)" when step_number === 1.
   - `PromptsTab`: filters events for `llm_call_starting` typed as `LLMCallStartingData[]`. For each call, render call index header + system prompt block + user prompt block in `ScrollArea`.
   - `ResponseTab`: filters events for `llm_call_completed` typed as `LLMCallCompletedData[]`. Two-column grid per call: raw_response in `<pre>` block, parsed_result as formatted JSON.
   - `InstructionsTab`: displays data from `useStepInstructions` - list of `StepPromptItem` with prompt_type badge, prompt_key, content in `ScrollArea`. Loading/error states.
   - `ContextDiffTab`: same ContextUpdated events as Input tab but shows before snapshot (previous step) vs after snapshot (this step) side-by-side + `new_keys` badge list.
   - `ExtractionsTab`: filters events for `extraction_completed` typed as `ExtractionCompletedData[]`. Show extraction_class, model_class, instance_count per extraction. Show `extraction_error` events if any.
   - `MetaTab`: uses `useStep` data (model, execution_time_ms, created_at, prompt_system_key, prompt_user_key). Also reads `llm_call_completed` events for validation_errors list, attempt_count. Reads `cache_hit`/`cache_miss` event for cache status. Reads `step_selected` event for strategy_name.

### Step 8: Rewrite StepDetailPanel tests

**Agent:** frontend-mobile-development:frontend-dev
**Skills:** none
**Context7 Docs:** /shadcn-ui/ui
**Group:** E

1. Rewrite `src/components/runs/StepDetailPanel.test.tsx`. All 8 existing tests must be updated for Sheet's Radix portal DOM structure.
2. Sheet uses `data-state="open"/"closed"` rather than CSS translate classes - update assertions accordingly.
3. Mock `useEvents` from `@/api/events` (in addition to existing `useStep` mock). Mock `useStepInstructions` from `@/api/pipelines`.
4. Re-test: closed state (data-state=closed), open state with step data (tabs visible), loading state (skeleton), error state, close button, Escape key (Sheet handles via Radix - test via `data-state` change), backdrop click.
5. Add new test: tab switching renders correct content (click tab trigger, verify content visible).

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| ALTER TABLE fails on read-only or locked SQLite DB | High | Catch `OperationalError` specifically; log warning; app still starts. Column being absent means step_name filter returns no results, not a crash. |
| `step_name` attribute missing on pipeline-level events at persist time | Medium | `getattr(event, "step_name", None)` safely returns None for events without the attribute (PipelineStarted, PipelineCompleted, PipelineError with no step). |
| Prompt table has no rows for a step (prompts not registered) | Low | Return empty `StepPromptsResponse` with `prompts: []`; Instructions tab shows "No instructions registered" placeholder. |
| Input tab: ContextUpdated event for previous step not available via step_name filter | Medium | The Input tab needs the PREVIOUS step's ContextUpdated event. Current step_name filter returns current step's events. Strategy: fetch ContextUpdated events for all steps (no step_name filter), sort by timestamp, find the one immediately before current step's first event. Or use existing `useContextEvolution` data if available in parent. Mitigate by passing context snapshots via prop from RunDetailPage which already fetches them. |
| useStepEvents enabled guard: step_name unknown until useStep resolves | Low | Gate `useStepEvents` with `enabled: Boolean(runId && step?.step_name)` to avoid early empty requests. |
| shadcn Sheet install modifies tailwind config or globals | Low | Review generated files before committing; shadcn adds to existing config, does not replace. |
| Radix portal in tests: Sheet renders outside component container | Medium | Use `screen.getByRole` queries which search full document; avoid `container.querySelector`. Check `data-state` attribute instead of CSS classes for open/closed assertions. |
| Pipeline not in introspection registry when instructions endpoint called | Low | Endpoint validates registry membership, returns 404. Frontend `useStepInstructions` shows loading/error states. |

## Success Criteria

- [ ] `PipelineEventRecord` has nullable `step_name` column with `(run_id, step_name)` index
- [ ] `SQLiteEventHandler.emit` populates `step_name` from event for step-scoped events
- [ ] Existing DBs receive column via ALTER TABLE migration on startup without error
- [ ] `GET /api/runs/{run_id}/events?step_name=x` returns only events for that step
- [ ] `GET /api/pipelines/{name}/steps/{step_name}/prompts` returns prompt content from DB
- [ ] `EventListParams` TS interface has `step_name?: string`
- [ ] `useStepEvents` hook exists and passes step_name filter to backend
- [ ] `useStepInstructions` hook exists with `staleTime: Infinity`
- [ ] shadcn Sheet and Tabs components present at `src/components/ui/sheet.tsx` and `src/components/ui/tabs.tsx`
- [ ] `StepDetailPanel` uses Sheet (no manual focus-trap or Escape handler code)
- [ ] Panel width is `w-[600px]` per spec
- [ ] All 7 tabs (Input, Prompts, LLM Response, Instructions, Context Diff, Extractions, Meta) render without error
- [ ] Prompts tab shows all LLM calls (consensus = multiple), not just first
- [ ] All existing 8 tests pass (rewritten for Sheet/portal)
- [ ] At least 1 new test for tab switching

## Phase Recommendation

**Risk Level:** medium
**Reasoning:** Backend schema change (ALTER TABLE migration) and new endpoint are moderate risk items. Frontend Sheet rewrite eliminates all custom a11y code and introduces Radix portal which affects test patterns. The Input tab's dependency on previous step ContextUpdated events has a data-access complexity that requires care. No high-severity unknowns remain after research validation.
**Suggested Exclusions:** Exclude review phase; include testing phase.
