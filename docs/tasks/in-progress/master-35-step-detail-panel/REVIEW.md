# Architecture Review

## Overall Assessment
**Status:** complete

Solid implementation across 8 steps. Backend schema migration is idempotent, event filtering is correct, new endpoint follows existing patterns. Frontend Sheet+Tabs rewrite properly eliminates custom a11y code, all 7 tabs render distinct data, hooks are well-guarded. TypeScript event_data interfaces match Python dataclass fields. Test coverage adequate with 10 tests covering Sheet portal behavior.

## Project Guidelines Compliance
**CLAUDE.md:** C:\Users\SamSG\Documents\claude_projects\llm-pipeline\CLAUDE.md

| Guideline | Status | Notes |
| --- | --- | --- |
| Python 3.11+ | pass | `str \| None` union syntax used correctly in handlers.py |
| Pydantic v2 | pass | StepPromptItem/StepPromptsResponse use BaseModel correctly |
| SQLModel/SQLAlchemy 2.0 | pass | PipelineEventRecord uses SQLModel Field+Index patterns, select() API |
| Hatchling build | pass | No build config changes |
| Pipeline+Strategy+Step pattern | pass | New column/endpoint align with existing architecture |
| Tests pass | pass | 10 frontend tests, backend pytest passing (1 pre-existing failure unrelated) |
| No hardcoded values | pass | No secrets, no magic strings beyond event type constants |
| Error handling present | pass | ALTER TABLE try/except, 404 on missing pipeline, loading/error states in all tabs |

## Issues Found
### Critical
None

### High

#### ExtractionCompletedData.execution_time_ms typed as number, Python source is float
**Step:** 4
**Details:** TypeScript interface `ExtractionCompletedData` declares `execution_time_ms: number`. The Python dataclass `ExtractionCompleted` uses `execution_time_ms: float`. In practice, JavaScript `number` covers both int and float, so this is not a runtime bug -- JSON serialization of Python float produces a JS number. However, the explicit `number` type in TS masks the fact that this field can be fractional (e.g., 1234.5ms). This is cosmetically misleading but functionally harmless. Severity downgraded from critical to high because it cannot cause a runtime failure, but the type documentation is inaccurate.

#### Prompt query uses step_name only -- no pipeline_name scoping
**Step:** 3
**Details:** `get_step_prompts` queries `Prompt.where(step_name == step_name)` without filtering by pipeline_name. If two different pipelines define steps with the same step_name (e.g., "extract"), the endpoint returns prompts from both pipelines merged together. The Prompt table has a `step_name` column but no `pipeline_name` column, so there is no way to filter at the DB level currently. The endpoint validates pipeline existence in the introspection registry but this only prevents 404 -- it does not scope the query. This is an architectural gap in the Prompt table design (no pipeline_name FK) that predates this task, but the new endpoint exposes it. **Mitigation for now:** The endpoint is documented as returning prompts "for a step," and in practice step names are typically unique within a deployment. A proper fix would require adding pipeline_name to the Prompt table (out of scope for task 35).

### Medium

#### useStepEvents passes filter object with empty step_name to query key
**Step:** 6
**Details:** When `stepName` is `''` (falsy), `useStepEvents` still passes `{ step_name: '' }` as the filter to `useEvents`. The query is correctly disabled via `effectiveRunId = ''` causing `enabled: Boolean('') = false`, so no HTTP request fires. But the query key `['runs', '', 'events', { step_name: '' }]` is cached. If `stepName` later resolves to a real value, TanStack Query creates a new cache entry with the correct key. The empty-string entry remains in cache until GC. Not a bug but wasted cache entry. Minor improvement: could pass `undefined` as step_name when falsy to avoid polluting cache.

#### ALTER TABLE migration has no index creation for existing DBs
**Step:** 1
**Details:** The ALTER TABLE migration in `SQLiteEventHandler.__init__` only adds the `step_name` column. The composite index `ix_pipeline_events_run_step` on `(run_id, step_name)` is defined in `__table_args__` and created by `create_all()` for new DBs, but `create_all()` does not add indexes to existing tables if the table already exists. For existing DBs, the column gets added via ALTER TABLE but the index does not get created. This means existing deployments that upgrade will have the column but no index, resulting in slower queries when filtering by step_name. **Fix:** Add a second try/except block after the ALTER TABLE that creates the index via raw SQL: `CREATE INDEX IF NOT EXISTS ix_pipeline_events_run_step ON pipeline_events(run_id, step_name)`.

#### SheetContent renders even when stepNumber is null (with empty body)
**Step:** 7
**Details:** When `open=true` and `stepNumber=null`, `visible` is `false` so `Sheet open={false}` prevents rendering. But if for any reason the Sheet primitive leaks a brief render, `SheetContent` is always in the JSX tree (with `{visible ? <StepContent /> : null}` inside). The test for this case (stepNumber=null, open=true) correctly verifies no tabs/content render, which confirms the current behavior is fine. This is just a note -- the Sheet component's `open={false}` correctly prevents portal mount.

### Low

#### React key on PromptsTab/ResponseTab/ExtractionsTab uses array index
**Step:** 7
**Details:** `calls.map(({ data }, i) => <div key={i}>...)` uses array index as React key. Since events are immutable once fetched (terminal run data never changes, active run data is append-only), this is acceptable. However, if the events array ever gets reordered (unlikely with server-side timestamp ordering), React reconciliation would be incorrect. A more robust key would use `event.timestamp + call_index`.

#### No loading state for useStepEvents when step resolves but events still loading
**Step:** 7
**Details:** The eventsLoading check wraps all TabsContent with a skeleton. This means when switching tabs, if events are still loading, all tabs show the same skeleton. This is a reasonable UX choice for simplicity but slightly imprecise -- the Meta tab could show step metadata (from useStep which already loaded) even while events are still loading. Minor UX refinement opportunity.

## Review Checklist
[x] Architecture patterns followed -- Column duplication for query efficiency matches existing pattern. Sheet/Tabs from shadcn replaces custom a11y. Hook composition via delegation.
[x] Code quality and maintainability -- Clean separation of tab components, typed event_data interfaces, helper functions for filtering/formatting.
[x] Error handling present -- ALTER TABLE try/except, 404 on missing pipeline, loading/error states in all tab components.
[x] No hardcoded values -- Panel width matches spec (w-[600px]), no secrets or environment-specific values.
[x] Project conventions followed -- commit style, file placement, Pydantic response models, FastAPI route patterns.
[x] Security considerations -- ReadOnlySession used for DB access, no write operations exposed, no SQL injection (uses SQLModel select() with parameterized queries).
[x] Properly scoped (DRY, YAGNI, no over-engineering) -- No unused props, no premature abstractions, tab components are private to file, no task-49 forward-compat cruft.

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| llm_pipeline/events/models.py | pass | step_name column + composite index correctly placed |
| llm_pipeline/events/handlers.py | pass | ALTER TABLE migration idempotent, step_name extraction via getattr defensive |
| llm_pipeline/ui/routes/events.py | pass | step_name filter on both count and data queries |
| llm_pipeline/ui/routes/pipelines.py | pass | New endpoint follows existing patterns, uses ReadOnlySession |
| llm_pipeline/ui/frontend/src/api/types.ts | pass | Event_data interfaces match Python dataclasses |
| llm_pipeline/ui/frontend/src/api/query-keys.ts | pass | stepPrompts factory follows existing key hierarchy |
| llm_pipeline/ui/frontend/src/api/events.ts | pass | useStepEvents delegates correctly with enabled guard |
| llm_pipeline/ui/frontend/src/api/pipelines.ts | pass | staleTime: Infinity appropriate for static pipeline data |
| llm_pipeline/ui/frontend/src/components/ui/sheet.tsx | pass | Generated by shadcn CLI, standard Radix Dialog wrapper |
| llm_pipeline/ui/frontend/src/components/ui/tabs.tsx | pass | Generated by shadcn CLI, standard Radix Tabs wrapper |
| llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.tsx | pass | Full rewrite, 7 tabs, proper data flow, consensus multi-call display |
| llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.test.tsx | pass | 10 tests, Radix portal assertions, tab switching test |

## New Issues Introduced
- Missing index creation on existing DB upgrades (ALTER TABLE adds column but not index) -- MEDIUM severity, see Issues section
- Prompt query cross-pipeline leakage when step names collide -- HIGH severity, pre-existing gap in Prompt table design exposed by new endpoint

## Recommendation
**Decision:** CONDITIONAL

Two items warrant attention before merge:

1. **Index migration (MEDIUM):** Add `CREATE INDEX IF NOT EXISTS ix_pipeline_events_run_step ON pipeline_events(run_id, step_name)` after the ALTER TABLE in `SQLiteEventHandler.__init__`. Without this, existing deployments get the column but not the index, degrading step_name filter performance. Simple fix, low risk.

2. **Prompt cross-pipeline awareness (HIGH):** Document the known limitation that the instruction endpoint returns all prompts matching step_name regardless of pipeline. If step name collisions across pipelines are possible in the deployment, this needs a TODO or follow-up task. If step names are guaranteed unique, document that assumption.

Everything else is production-ready. The Sheet+Tabs rewrite is clean, the backend changes follow established patterns, and test coverage is adequate.
