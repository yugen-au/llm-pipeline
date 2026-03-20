# Research Summary

## Executive Summary

Task 52's spec is largely obsolete. Task 51 already implemented all 7 editor endpoints (compile, available-steps, DraftPipeline CRUD) in `llm_pipeline/ui/routes/editor.py`, plus a full frontend with TanStack Query hooks. The spec's core differentiator -- `build_pipeline_class()` for deep PipelineConfig-level validation -- does not exist in the codebase and is infeasible for draft-step pipelines (no Python classes to instantiate). The spec also uses incorrect API patterns (`async def`, `provider=None`) that don't match the project's conventions.

Three possible scopes remain: (a) mark task as done/cancelled, (b) redefine as "enhance compile validations + add pytest tests", (c) build full dynamic class construction. CEO decision required.

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

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Pending: see Questions below | -- | -- |

## Assumptions Validated
- [x] All 7 editor endpoints exist and function (confirmed via editor.py source review, lines 128-361)
- [x] `build_pipeline_class()` does not exist anywhere in codebase (grep returns only research docs + tasks.json)
- [x] No editor pytest tests exist (glob for `tests/ui/test_editor*` returns nothing)
- [x] FK validation requires live SQLAlchemy `__table__` metadata (confirmed in `_validate_foreign_key_dependencies` at pipeline.py L368-385)
- [x] PipelineConfig.__init__ requires `model: str` not `provider=None` (confirmed at pipeline.py L209-211)
- [x] Compile endpoint is stateless -- no DraftPipeline writes (confirmed, only reads DraftStep for existence check)
- [x] Project uses sync `def` handlers exclusively (confirmed across all route files)
- [x] Upstream task 50 (done): DraftStep + DraftPipeline models exist in state.py with proper table registration
- [x] Upstream task 24 (done): Pipelines API + PipelineIntrospector exist and are used by editor's `_collect_registered_steps()`

## Open Items
- Task 52 scope needs CEO redefinition given task 51 overlap
- Whether compile should gain side-effects (write compilation_errors to DraftPipeline) or stay stateless
- Whether to add structural validations (duplicates, empty strategies, position checks) to compile
- Whether pytest tests for editor endpoints belong in task 52 or separate work
- Whether forked pipelines (all registered steps) should unlock deeper validation

## Recommendations for Planning
1. **Redefine task 52 scope** before planning. The spec is obsolete. Recommend option (b): enhance compile with structural validations + add pytest tests. This provides clear deliverables without the risk/complexity of dynamic class construction.
2. **Keep compile stateless.** Current separation (compile = validation, CRUD = POST/PATCH) is cleaner than the spec's coupled approach. The frontend already auto-compiles on structure changes and saves via separate mutations.
3. **Add structural validations to compile:** duplicate step detection, empty strategy check, position sequencing. These are safe, fast, and catch real user errors in the visual editor.
4. **Add prompt key validation** for registered steps only. Query the Prompt table to verify system/user keys exist. Draft steps skip this check (their prompts are generated alongside the code).
5. **Write pytest tests** for all 7 editor endpoints using the established pattern (StaticPool in-memory SQLite, TestClient, seeded data). Task 51 explicitly recommended this.
6. **Do NOT build `build_pipeline_class()`.** Dynamic PipelineConfig subclass creation is complex, has security implications (arbitrary code execution path), and provides no value for draft-step pipelines. Metadata-based validation via PipelineIntrospector is safer and sufficient.
7. **Consider extraction order validation** for all-registered-step pipelines as a stretch goal. Use PipelineIntrospector metadata to check model extraction ordering without instantiation.
