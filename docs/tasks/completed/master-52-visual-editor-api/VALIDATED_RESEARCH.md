# Research Summary

## Executive Summary

Task 52's spec is largely obsolete. Task 51 already implemented all 7 editor endpoints (compile, available-steps, DraftPipeline CRUD) in `llm_pipeline/ui/routes/editor.py`, plus a full frontend with TanStack Query hooks. The spec's core differentiator -- `build_pipeline_class()` for deep PipelineConfig-level validation -- does not exist in the codebase and is infeasible for draft-step pipelines (no Python classes to instantiate). The spec also uses incorrect API patterns (`async def`, `provider=None`) that don't match the project's conventions.

**Redefined scope (CEO-approved):** Enhance compile with structural validations, make compile stateful (write compilation_errors to DraftPipeline), and add comprehensive pytest tests for all 7 editor endpoints. No `build_pipeline_class()` -- infeasible for JSON drafts.

## Domain Findings

### Finding 1: Complete Endpoint Overlap with Task 51
**Source:** step-1-existing-api-patterns.md, editor.py (codebase)

Task 51 shipped all endpoints task 52 specifies plus more:

| Endpoint | Task 52 Spec | Task 51 Shipped |
|----------|-------------|-----------------|
| POST /api/editor/compile | YES | YES (L128-161) |
| GET /api/editor/available-steps | not mentioned | YES (L164-210) |
| POST /api/editor/drafts | implied | YES (L218-248) |
| GET /api/editor/drafts | YES | YES (L251-270) |
| GET /api/editor/drafts/{id} | implied | YES (L273-289) |
| PATCH /api/editor/drafts/{id} | implied | YES (L292-349) |
| DELETE /api/editor/drafts/{id} | implied | YES (L352-361) |

Frontend hooks also complete: 7 TanStack Query hooks in `api/editor.ts`.

### Finding 2: Spec's Validation Approach Is Infeasible for Draft Steps
**Source:** step-3-pipeline-validation-logic.md, pipeline.py (codebase)

Task 52 spec calls for `build_pipeline_class(request.pipeline_structure)` to instantiate PipelineConfig and trigger `_validate_foreign_key_dependencies()`, `_validate_registry_order()`, `_build_execution_order()`. This requires:
- Live SQLModel classes with `__table__` metadata (FK validation)
- Real extraction class references with `.MODEL` attributes (registry order)
- Actual step classes with `create_definition()` (execution order)

Draft steps stored as JSON in `DraftStep.generated_code` have none of these. `build_pipeline_class()` does not exist anywhere in the codebase (confirmed via grep -- only appears in research docs and tasks.json).

**Exception:** Forked pipelines composed entirely of registered steps DO have Python classes available via `introspection_registry`. Deeper validation is theoretically possible for this subset.

### Finding 3: Spec Has Multiple Incorrect API Patterns
**Source:** step-2-pythonfastapi-patterns.md, editor.py (codebase)

| Spec Pattern | Actual Codebase Pattern |
|-------------|------------------------|
| `async def compile_pipeline` | `def compile_pipeline` (sync, all routes) |
| `pipeline_class(provider=None)` | `PipelineConfig.__init__(model: str, ...)` (no `provider` param) |
| compile saves DraftPipeline | compile is stateless; CRUD handled separately |
| `@router.post('/api/editor/compile')` | `@router.post("/compile")` (prefix set on APIRouter) |

### Finding 4: Practical Validations Available Without Dynamic Construction
**Source:** step-3-pipeline-validation-logic.md

Validations achievable with current architecture (no `build_pipeline_class` needed):

| Validation | Feasible | Applies To |
|-----------|----------|-----------|
| Step-ref existence | YES (already done) | all steps |
| Duplicate steps within strategy | YES | all steps |
| Empty strategies | YES | structural |
| Position sequence gaps | YES | structural |
| Prompt key existence (query Prompt table) | YES | registered steps |
| Extraction order (via introspection metadata) | PARTIAL | registered steps only |
| FK dependency ordering | NO | requires live SQLModel classes |
| Schema compatibility | NO | requires JSON schema comparison |

### Finding 5: No Pytest Tests Exist for Editor Endpoints
**Source:** step-2-pythonfastapi-patterns.md, task 51 SUMMARY, filesystem check

`tests/ui/test_editor.py` does not exist. Task 51 SUMMARY explicitly recommends: "Add pytest tests in `tests/ui/test_editor.py` for the 7 new endpoints." Test patterns established in step-2 research (in-memory SQLite with StaticPool, TestClient, app factory with seeded data).

### Finding 6: PipelineConfig Instantiation Has Side Effects
**Source:** step-3-pipeline-validation-logic.md, pipeline.py L279-291

Even if dynamic class construction were built, `PipelineConfig.__init__` creates an auto-SQLite DB file when no engine/session provided. Validation-only instantiation would need a throwaway in-memory engine to avoid filesystem side effects. The `model: str` parameter is also required (non-optional), needing a dummy value like `"test:dummy"`.

### Finding 7: Compile Statefulness Requires Request Model Change
**Source:** editor.py CompileRequest (L35-36), DraftPipeline model (state.py)

Current `CompileRequest` has only `strategies: list[EditorStrategy]` -- no `draft_id`. To write `compilation_errors` to a DraftPipeline record, compile needs to know which draft to update. Two options:
- Add optional `draft_id: int | None = None` to CompileRequest (write errors only when draft_id provided, stay stateless for ad-hoc validation)
- Always require draft_id (breaking change for frontend auto-compile which fires before save)

The optional approach is safer: frontend auto-compile can omit draft_id (stateless), and explicit "compile & save" flow can include it.

### Finding 8: Prompt Key Validation Is Feasible via Introspection Metadata
**Source:** introspection.py L138-139, db/prompt.py

PipelineIntrospector metadata includes `system_key` and `user_key` per step. The `Prompt` table has `prompt_key` + `prompt_type` columns with a unique constraint on `(prompt_key, prompt_type)`. Compile can query the Prompt table to verify that referenced prompt keys exist for registered steps. Draft steps skip this check (their prompts are generated alongside the code, not yet in the Prompt table).

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Task 51 shipped all 7 endpoints. Mark done/cancelled, redefine as enhance+test, or build dynamic class? | Enhance + test: structural validations, stateful compile, pytest tests. No build_pipeline_class. | Scope redefined. No new endpoints needed. Focus on compile enhancement + tests. |
| Should compile stay stateless or gain side-effects writing compilation_errors to DraftPipeline? | Stateful per spec -- write compilation_errors for cross-session persistence. | CompileRequest needs optional `draft_id` field. Compile endpoint gains DB write path. |
| Add structural validations (duplicates, empty strategies, position gaps, prompt key checks)? | Yes -- all four validation types approved. | Compile grows from 1 check (step-ref existence) to 5 checks. |
| Should pytest tests for editor endpoints be part of task 52? | Yes -- comprehensive tests for all 7 endpoints. | New test file `tests/ui/test_editor.py` needed. Follow test_creator.py pattern. |

## Assumptions Validated
- [x] All 7 editor endpoints exist and function (confirmed via editor.py source review, lines 128-361)
- [x] `build_pipeline_class()` does not exist anywhere in codebase (grep returns only research docs + tasks.json)
- [x] No editor pytest tests exist (glob for `tests/ui/test_editor*` returns nothing; 11 other test files in tests/ui/)
- [x] FK validation requires live SQLAlchemy `__table__` metadata (confirmed in `_validate_foreign_key_dependencies` at pipeline.py L368-385)
- [x] PipelineConfig.__init__ requires `model: str` not `provider=None` (confirmed at pipeline.py L209-211)
- [x] Compile endpoint is stateless -- no DraftPipeline writes (confirmed, only reads DraftStep for existence check)
- [x] Project uses sync `def` handlers exclusively (confirmed across all route files)
- [x] Upstream task 50 (done): DraftStep + DraftPipeline models exist in state.py with proper table registration
- [x] Upstream task 24 (done): Pipelines API + PipelineIntrospector exist and are used by editor's `_collect_registered_steps()`
- [x] Prompt table exists at `llm_pipeline/db/prompt.py` with `prompt_key` + `prompt_type` columns (UniqueConstraint on both)
- [x] PipelineIntrospector metadata includes `system_key` and `user_key` per step (introspection.py L138-139)
- [x] CompileRequest currently has no `draft_id` field -- only `strategies` (editor.py L35-36)
- [x] Test pattern established: in-memory SQLite with StaticPool, TestClient, app factory with seeded data (test_creator.py L25-78)

## Open Items
- Whether forked pipelines (all registered steps) should unlock deeper extraction-order validation as a stretch goal
- Exact CompileRequest schema: recommend optional `draft_id: int | None = None` so stateless auto-compile (no draft_id) and stateful explicit compile (with draft_id) coexist
- Whether CompileError model needs a `level` field (error vs warning) for prompt key warnings vs hard step-ref errors

## Recommendations for Planning
1. **Enhance compile with 5 validation checks:** (1) step-ref existence (already done), (2) duplicate steps within strategy, (3) empty strategies, (4) position sequence gaps/duplicates, (5) prompt key existence for registered steps via Prompt table query.
2. **Make compile stateful via optional `draft_id`.** Add `draft_id: int | None = None` to CompileRequest. When provided, write `compilation_errors` to the DraftPipeline record and update its status to "error" or "draft". When omitted, behave as current (stateless). This preserves backward compat with frontend auto-compile.
3. **Do NOT build `build_pipeline_class()`.** CEO confirmed infeasible for JSON drafts. Metadata-based validation via PipelineIntrospector is sufficient.
4. **Write pytest tests** for all 7 editor endpoints in `tests/ui/test_editor.py`. Follow `test_creator.py` pattern (StaticPool in-memory SQLite, TestClient, seeded data). Cover: compile valid/invalid/stateful, available-steps merge/dedup, DraftPipeline CRUD with 409 cases.
5. **Consider extraction order validation** for all-registered-step pipelines as a stretch goal. Use PipelineIntrospector metadata to check model extraction ordering without instantiation.
6. **Frontend impact:** CompileRequest schema change (optional `draft_id`) is backward compatible. Frontend auto-compile continues working without changes. Explicit "compile & save" flow can pass `draft_id` to persist errors. Response model (`CompileResponse`) may gain `draft_id` echo field.
