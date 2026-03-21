# PLANNING

## Summary
Enhance the existing POST /api/editor/compile endpoint with 4 additional structural validations (duplicate steps, empty strategies, position gaps/duplicates, prompt key existence), make compile stateful via optional `draft_id` field that writes compilation_errors to DraftPipeline records, and add comprehensive pytest tests for all 7 editor endpoints. No new endpoints; no build_pipeline_class(). DraftPipeline.compilation_errors field already exists in state.py.

## Plugin & Agents
**Plugin:** backend-development
**Subagents:** backend-development:tdd-orchestrator, backend-development:test-automator
**Skills:** none

## Phases
1. Enhance compile endpoint: add 4 structural validations + stateful draft_id write path
2. Write pytest test suite: all 7 editor endpoints, valid + invalid + edge cases

## Architecture Decisions

### Compile Statefulness via Optional draft_id
**Choice:** Add `draft_id: int | None = None` to CompileRequest. When present, look up the DraftPipeline record and write compilation_errors + update status ("draft" if valid, "error" if errors). When absent, remain stateless.
**Rationale:** Frontend auto-compile fires before save (no draft_id yet). Explicit "compile & save" flow can pass draft_id for persistence. Backward compatible -- no frontend changes needed for current behavior.
**Alternatives:** Always require draft_id (breaking); separate PATCH endpoint for errors only (extra round-trip).

### CompileError Model Enhancement
**Choice:** Add optional `field: str | None = None` and `severity: Literal["error", "warning"] = "error"` to CompileError. Step-ref errors are "error"; prompt key issues are "warning".
**Rationale:** VALIDATED_RESEARCH.md Finding 7 notes CompileResponse errors already have per-step StepError with severity in Graphiti memory. Frontend CompileErrorList component shows severity. Consistent with existing frontend expectations.
**Alternatives:** Keep flat CompileError model (loses warning/info distinction).

### Validation Scope
**Choice:** 5 validation checks in order: (1) step-ref existence (existing), (2) duplicate step_ref within a strategy, (3) empty strategies (zero steps), (4) position sequence gaps/duplicates within a strategy, (5) prompt key existence for registered steps via Prompt table query.
**Rationale:** All 4 new checks are CEO-approved per Q&A in VALIDATED_RESEARCH.md. All are achievable without build_pipeline_class(). Prompt key check is "warning" severity (step may have no prompts; missing key is advisory, not blocking). Position check catches drag-and-drop ordering bugs.
**Alternatives:** Extraction order validation for all-registered-step pipelines (stretch goal, deferred -- requires more introspection work).

### compilation_errors Storage Format
**Choice:** Store as `{"errors": [{"strategy_name": ..., "step_ref": ..., "field": ..., "message": ..., "severity": ...}]}` in DraftPipeline.compilation_errors JSON column.
**Rationale:** DraftPipeline.compilation_errors is already `Optional[dict]` in state.py (L258-260). A wrapper dict with "errors" key provides extensibility (can add "compiled_at", "valid" flags later). CompileResponse.errors list serialized directly into this wrapper.
**Alternatives:** Store as raw list (less extensible); store CompileResponse directly (tight coupling between API model and DB shape).

### Test Architecture
**Choice:** Single `tests/ui/test_editor.py` file, one `_make_seeded_editor_app()` factory, two fixtures (`editor_client` and `editor_app_and_client`), test classes per endpoint group.
**Rationale:** Matches test_creator.py pattern exactly (StaticPool in-memory SQLite, TestClient, seeded rows). No mocking needed for editor endpoints (no LLM calls, no external deps). introspection_registry set to `{}` for compile tests to isolate from real pipeline classes.
**Alternatives:** Separate fixture files (overkill for 7 endpoints).

## Implementation Steps

### Step 1: Enhance CompileRequest and CompileError models
**Agent:** backend-development:backend-architect
**Skills:** none
**Context7 Docs:** /fastapi/fastapi, /websites/sqlmodel_tiangolo
**Group:** A

1. In `llm_pipeline/ui/routes/editor.py`, update `CompileError` model: add `field: str | None = None` and `severity: Literal["error", "warning"] = "error"`.
2. Update `CompileRequest` model: add `draft_id: int | None = None`.
3. Update `CompileResponse` model: no structural changes needed; errors list already present.

### Step 2: Add structural validation logic to compile_pipeline
**Agent:** backend-development:backend-architect
**Skills:** none
**Context7 Docs:** /fastapi/fastapi, /websites/sqlmodel_tiangolo
**Group:** B

1. In `compile_pipeline()` in `llm_pipeline/ui/routes/editor.py`, after the existing step-ref existence check, add validation pass 2: detect duplicate `step_ref` values within each strategy (same step_ref appearing more than once in same strategy.steps list). Emit `CompileError` with `field="step_ref"`, `severity="error"`.
2. Add validation pass 3: detect strategies with zero steps (`len(strategy.steps) == 0`). Emit `CompileError` with `step_ref=""`, `field="steps"`, `message="Strategy '{name}' has no steps"`, `severity="error"`.
3. Add validation pass 4: detect position gaps or duplicates within each strategy. Collect `[s.position for s in strategy.steps]`, check for duplicates and gaps from 0..N-1. Emit `CompileError` with `field="position"`, `severity="error"`.
4. Add validation pass 5: for steps with `source="registered"`, query the Prompt table for `prompt_key` values associated with the step. Use `PipelineIntrospector` metadata (`system_key`, `user_key`) to get expected keys; query `select(Prompt).where(Prompt.prompt_key.in_(expected_keys))` to check existence. Emit missing keys as `CompileError` with `severity="warning"`. Import `Prompt` from `llm_pipeline.db.prompt`.

### Step 3: Add stateful compile write path
**Agent:** backend-development:backend-architect
**Skills:** none
**Context7 Docs:** /fastapi/fastapi, /websites/sqlmodel_tiangolo
**Group:** C

1. In `compile_pipeline()`, after all validation passes complete and `errors` list is built, check if `body.draft_id` is not None.
2. If `body.draft_id` is set: open `Session(engine)`, fetch `DraftPipeline` by id. If not found, raise `HTTPException(status_code=404, detail="Draft pipeline not found")`.
3. Set `draft.compilation_errors = {"errors": [e.model_dump() for e in errors]}`.
4. Set `draft.status = "error" if errors else "draft"`.
5. Set `draft.updated_at = utc_now()`.
6. Commit session, then return `CompileResponse`.

### Step 4: Write pytest test suite for all 7 editor endpoints
**Agent:** backend-development:test-automator
**Skills:** none
**Context7 Docs:** /fastapi/fastapi, /websites/sqlmodel_tiangolo
**Group:** D

1. Create `tests/ui/test_editor.py`. Import pattern from `test_creator.py`: `create_engine`, `StaticPool`, `Session`, `TestClient`, `init_pipeline_db`.
2. Write `_make_seeded_editor_app()` factory: in-memory SQLite, `init_pipeline_db(engine)`, mount `editor_router` at `/api`, seed 2 DraftStep rows (`alpha_step` status=draft, `beta_step` status=error), seed 2 DraftPipeline rows, set `app.state.introspection_registry = {}`.
3. Write `editor_client` and `editor_app_and_client` pytest fixtures.
4. Write `TestCompileEndpoint` class with tests:
   - `test_compile_valid_returns_valid_true`: strategies with known step refs, expect `valid=True, errors=[]`
   - `test_compile_unknown_step_returns_error`: unknown step_ref, expect `valid=False`, error in list
   - `test_compile_duplicate_steps_in_strategy`: same step_ref twice, expect error with `field="step_ref"`
   - `test_compile_empty_strategy`: strategy with no steps, expect error with `field="steps"`
   - `test_compile_position_gap`: positions [0, 2] (gap), expect error with `field="position"`
   - `test_compile_position_duplicate`: positions [0, 0], expect error with `field="position"`
   - `test_compile_stateful_writes_errors`: pass `draft_id`, check DB row has `compilation_errors` set
   - `test_compile_stateful_valid_clears_errors`: valid compile with draft_id, check `compilation_errors={"errors":[]}` and status="draft"
   - `test_compile_stateful_draft_not_found`: draft_id=9999, expect 404
   - `test_compile_excludes_errored_draft_steps`: errored DraftStep not in known set
5. Write `TestAvailableStepsEndpoint` class with tests:
   - `test_available_steps_returns_non_errored_drafts`: alpha_step (draft) present, beta_step (error) absent
   - `test_available_steps_deduplicates_registered_wins`: registered step same name as draft, source="registered"
   - `test_available_steps_empty_registry_returns_drafts_only`: no introspection_registry, only draft steps
6. Write `TestDraftPipelineCRUD` class with tests:
   - `test_create_draft_pipeline_returns_201`: POST /drafts with name+structure, check id/status/structure
   - `test_create_draft_pipeline_name_conflict_returns_409`: duplicate name returns 409 with detail="name_conflict"
   - `test_list_draft_pipelines_returns_seeded`: GET /drafts, check total=2
   - `test_get_draft_pipeline_returns_detail`: GET /drafts/{id}, check structure+compilation_errors fields
   - `test_get_draft_pipeline_not_found_returns_404`: id=9999 returns 404
   - `test_update_draft_pipeline_name`: PATCH with new name, check updated_at advanced
   - `test_update_draft_pipeline_name_conflict_returns_409_with_suggested`: duplicate name returns 409 with suggested_name
   - `test_update_draft_pipeline_not_found_returns_404`: id=9999 returns 404
   - `test_delete_draft_pipeline_returns_204`: DELETE returns 204, subsequent GET returns 404
   - `test_delete_draft_pipeline_not_found_returns_404`: id=9999 returns 404

## Risks & Mitigations
| Risk | Impact | Mitigation |
| --- | --- | --- |
| Prompt table query in compile adds DB overhead for auto-compile (300ms debounce) | Low | Prompt check is only for registered steps; scope is bounded. Warning severity means frontend can ignore. |
| PipelineIntrospector raises on edge-case pipeline classes | Medium | Step 2 wraps introspection in try/except matching existing _collect_registered_steps pattern (L107-110 in editor.py). Skip prompt check for steps where introspection fails. |
| Position validation logic incorrect for sparse position values | Medium | Define "valid" as: sorted positions form range(0, len(steps)). Test with [0,2] gap and [0,0] duplicate. |
| SQLite JSON column stores dict but Pydantic model_dump() may include non-serializable types | Low | CompileError fields are all str/None/Literal -- safe for JSON. model_dump() produces plain dicts. |
| test_creator.py seeded DraftStep has `run_id` field; state.py DraftStep may require it | Low | Read DraftStep model fields before seeding in test factory. If run_id required, generate uuid4(). |

## Success Criteria
- [ ] CompileError has `field` and `severity` fields
- [ ] CompileRequest has optional `draft_id: int | None = None`
- [ ] compile_pipeline() runs 5 validation passes (step-ref, duplicate, empty, position, prompt key)
- [ ] compile_pipeline() writes compilation_errors to DraftPipeline when draft_id provided
- [ ] compile_pipeline() sets status="error" on error, status="draft" on clean compile
- [ ] compile_pipeline() returns 404 when draft_id provided but DraftPipeline not found
- [ ] tests/ui/test_editor.py exists with test classes for all 7 endpoints
- [ ] All compile validation paths have dedicated test cases
- [ ] CRUD 409/404 paths covered by tests
- [ ] pytest passes with no warnings on new test file

## Phase Recommendation
**Risk Level:** low
**Reasoning:** All changes are enhancements to existing endpoints with no schema migrations needed (compilation_errors column already exists). No new tables, no breaking API changes, no LLM calls. Test patterns are established and directly replicable from test_creator.py.
**Suggested Exclusions:** testing, review
