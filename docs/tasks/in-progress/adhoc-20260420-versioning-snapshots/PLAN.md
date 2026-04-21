# PLANNING

## Summary

Add `is_latest` to `Prompt`, add `(version, is_active, is_latest, updated_at)` to `EvaluationCase`, add four run-snapshot JSON columns to `EvaluationRun`, and enforce versioning via partial unique indexes. A single generic helper (`db/versioning.py`) mediates all version writes. YAML sync for datasets mirrors the prompt pattern. Snapshot columns are populated atomically at run creation via `_build_run_snapshot`. Compare-view API surfaces snapshots directly; frontend badge rendering is deferred.

## Plugin & Agents

**Plugin:** database-design, backend-development, python-development
**Subagents:** database-design:database-architect, backend-development:backend-architect, python-development:python-pro
**Skills:** database-design:postgresql, backend-development:api-design-principles, python-development:python-testing-patterns

## Phases

1. **Implementation** — all code changes in groups A, B, C (detailed below)
2. **Testing** — consolidated `uv run pytest` across full suite; sandbox regression; manual UI smoke tests
3. **Review** — architect review of schema + runtime + YAML sync surface (high risk level)

## Architecture Decisions

### Single Generic Versioning Helper
**Choice:** One `llm_pipeline/db/versioning.py` with `save_new_version`, `get_latest`, `soft_delete_latest`. No per-entity wrappers.
**Rationale:** CEO answer A4. Avoids duplication across prompt and eval-case domains. `compare_versions` moved to `llm_pipeline/utils/versioning.py` (A5) so `db/versioning.py` has no cross-module dependency on `prompts/` or `evals/`.
**Alternatives:** Per-entity wrappers (`prompts/versioning.py`, `evals/versioning.py`) — rejected for DRY violation.

### Partial Unique Index Enforcement
**Choice:** `WHERE is_active = 1 AND is_latest = 1` partial unique on `(prompt_key, prompt_type)` for Prompt, `(dataset_id, name)` for EvaluationCase.
**Rationale:** Allows historical version rows with same business key without triggering constraint. SQLite >= 3.8.0 (Python 3.11 ships 3.37+); PostgreSQL natively supported.
**Alternatives:** Application-level uniqueness guard only — rejected; DB-level constraint provides safety net against helper bypass.

### Flush-Before-Insert Transaction Discipline
**Choice:** `session.flush()` after `prior.is_latest = False`, before new row INSERT, inside the same transaction; caller commits.
**Rationale:** SQLite checks partial unique indexes at statement boundaries; without the flush, the old active-latest row still occupies the slot when the new row is inserted.
**Alternatives:** Commit between flip and insert — rejected; splits atomicity.

### Soft-Delete Semantics
**Choice:** `is_active=False`, keep `is_latest=True`. No `deleted_at` column (locked decision #3).
**Rationale:** `is_latest=True` on the soft-deleted row means "most recent historical row for this key"; partial unique index uses `is_active AND is_latest` so soft-deleted row vacates the live slot.
**Alternatives:** `deleted_at` column — rejected by CEO in locked decisions.

### Run Snapshot via `_build_run_snapshot` Pre-Pass
**Choice:** Resolve all prompts, models, and instruction schemas in a single pre-pass before `EvaluationRun` construction; commit atomically with the run row.
**Rationale:** Snapshots must be deterministic at run creation time, not lazily resolved per case. Mirrors existing `_find_step_def` + resolution pattern.
**Alternatives:** Populate snapshots post-run — rejected; race condition if prompt is versioned between case executions.

### Prompt YAML Atomic Writer Upgrade
**Choice:** Port `write_prompt_to_yaml` to temp-file + `Path.replace` pattern (already used by `write_dataset_to_yaml`).
**Rationale:** Once multiple version rows share a file, partial-write corruption becomes a real risk. Low-cost, in-scope per VALIDATED_RESEARCH §6.5.
**Alternatives:** Leave non-atomic — rejected given versioning semantics depend on YAML integrity.

---

## Implementation Steps

### Step 1: Move `compare_versions` to utils
**Agent:** python-development:python-pro
**Skills:** none
**Context7 Docs:** /pydantic/pydantic
**Group:** A

1. Create `llm_pipeline/utils/versioning.py`; move `compare_versions` function from `llm_pipeline/prompts/yaml_sync.py` into it.
2. Update `llm_pipeline/prompts/yaml_sync.py` to import `compare_versions` from `llm_pipeline.utils.versioning`.
3. Verify no other modules currently import `compare_versions` directly from `yaml_sync` (grep check).
4. Tests: add `test_compare_versions_*` unit tests in `tests/test_versioning_helpers.py` — bump minor edge cases from §9.1 #7 (these cover the moved function too).

### Step 2: Create `llm_pipeline/db/versioning.py` helper module
**Agent:** python-development:python-pro
**Skills:** python-development:python-testing-patterns
**Context7 Docs:** /websites/sqlmodel_tiangolo, /websites/sqlalchemy_en_20_orm
**Group:** A

1. Create `llm_pipeline/db/versioning.py` with `_utc_now`, `_bump_minor`, `save_new_version`, `get_latest`, `soft_delete_latest` exactly as specified in VALIDATED_RESEARCH §4.
2. Import `compare_versions` from `llm_pipeline.utils.versioning` (Step 1 prerequisite — same group, Step 1 must land first within group A commits).
3. Tests: write `tests/test_versioning_helpers.py` tests #1–#8 from §9.1 — covers `save_new_version` bump+flip, partial unique guard, soft-delete+recreate, `get_latest` inactive exclusion, managed-col guard, explicit-version validation, `_bump_minor` edge cases, `updated_at` population.

**Dependency note:** Step 2 imports from Step 1. Within Group A, commit Step 1 before Step 2 runs.

### Step 3: Schema — `Prompt` model updates
**Agent:** database-design:database-architect
**Skills:** database-design:postgresql
**Context7 Docs:** /websites/sqlmodel_tiangolo, /websites/sqlalchemy_en_20_core
**Group:** A

1. In `llm_pipeline/db/prompt.py`: add `is_latest: bool = Field(default=True, index=True)` after `is_active`.
2. Drop `UniqueConstraint('prompt_key', 'prompt_type', name='uq_prompts_key_type')` from `__table_args__`.
3. Drop `Index("ix_prompts_active", "is_active")` from `__table_args__` (per A7).
4. Add partial unique index `uq_prompts_active_latest` and supporting indexes `ix_prompts_key_type_live`, `ix_prompts_category_step`, `ix_prompts_key_type_version` to `__table_args__` exactly as specified in VALIDATED_RESEARCH §2.1.
5. Add `from sqlalchemy import Index, text`; remove `UniqueConstraint` import if no longer used.
6. No tests for model shape — covered by migration idempotency tests in Step 4.

### Step 4: Schema — `EvaluationCase` + `EvaluationRun` model updates
**Agent:** database-design:database-architect
**Skills:** database-design:postgresql
**Context7 Docs:** /websites/sqlmodel_tiangolo, /websites/sqlalchemy_en_20_orm
**Group:** A

1. In `llm_pipeline/evals/models.py`: add `version`, `is_active`, `is_latest`, `updated_at` columns to `EvaluationCase` as specified in VALIDATED_RESEARCH §2.2; update `__table_args__` with partial unique `uq_eval_cases_active_latest` and supporting indexes.
2. Add `from sqlalchemy import Index, text` import; ensure `datetime` and `utc_now` imports present.
3. Add four snapshot JSON columns to `EvaluationRun` — `case_versions`, `prompt_versions`, `model_snapshot`, `instructions_schema_snapshot` — all `Optional[dict]`, default `None`, `sa_column=Column(JSON)`, placed after `delta_snapshot` per §2.3.
4. Ensure `JSON`, `Column`, `Optional` are imported.
5. No standalone tests — migration and runner tests cover this.

### Step 5: Migration — `_MIGRATIONS` + `_migrate_partial_unique_indexes`
**Agent:** database-design:database-architect
**Skills:** database-design:postgresql, database-migrations:sql-migrations
**Context7 Docs:** /websites/sqlalchemy_en_20_core
**Group:** A

1. In `llm_pipeline/db/__init__.py`: extend `_MIGRATIONS` list with the 9 new entries from VALIDATED_RESEARCH §3.1 (prompts.is_latest, eval_cases.version/is_active/is_latest/updated_at, eval_runs.case_versions/prompt_versions/model_snapshot/instructions_schema_snapshot).
2. Add `_migrate_partial_unique_indexes(engine)` function exactly as specified in §3.2 — drops legacy indexes, dedupes eval_cases, creates partial unique indexes and supporting indexes; idempotent via `IF NOT EXISTS`.
3. Wire `_migrate_partial_unique_indexes(engine)` into `init_pipeline_db` after `_migrate_add_columns` and before `add_missing_indexes` per §3.3.
4. Tests: write `tests/test_migrations.py` tests #19, #20, #21 from §9.6 — dedupe of duplicate `(dataset_id, name)` rows, legacy index drops, idempotency.

**Dependency note:** Step 5 depends on Steps 3 and 4 (columns must be declared in models before migration runs against them). All are Group A; commit order within group: 3 → 4 → 5.

---

### Step 6: Prompt read-site call-site updates
**Agent:** backend-development:backend-architect
**Skills:** none
**Context7 Docs:** /websites/sqlmodel_tiangolo
**Group:** B

Update 17 prompt read sites to add `is_latest==True` (and `is_active==True` where noted). Files and line references from VALIDATED_RESEARCH §5.1:

1. `llm_pipeline/prompts/resolver.py` tag #1: add `is_latest==True`.
2. `llm_pipeline/prompts/service.py` tags #2, #3: add `is_latest==True` to `get_prompt` and `prompt_exists`.
3. `llm_pipeline/pipeline.py` tags #4, #5: add `is_active==True AND is_latest==True`.
4. `llm_pipeline/introspection.py` tag #6: add `is_latest==True`.
5. `llm_pipeline/ui/routes/editor.py` tag #7: add `is_latest==True`.
6. `llm_pipeline/ui/routes/evals.py` tag #8: add `is_active==True AND is_latest==True`.
7. `llm_pipeline/ui/routes/pipelines.py` tag #9: add both filters.
8. `llm_pipeline/ui/routes/prompts.py` tags #10, #12, #13, #14: admin list default `is_latest==True`, PUT lookup, DELETE lookup, variable-schema lookup.
9. `llm_pipeline/ui/app.py` tag #17: add `is_latest==True` in `_sync_variable_definitions`.
10. `llm_pipeline/prompts/yaml_sync.py` tag #15: replace manual query with `get_latest(session, Prompt, ...)` from helper.
11. `llm_pipeline/sandbox.py` tag #16: filter seed query by `is_latest==True AND is_active==True` per A3.
12. `llm_pipeline/evals/runner.py` tags #18: add `is_latest==True` defence-in-depth.
13. `llm_pipeline/creator/prompts.py` tag #19: switch to `get_latest(...)`.
14. `llm_pipeline/creator/integrator.py` tag #20: switch to `get_latest(...)`.
15. Post-implementation: run `grep -rn "select(Prompt)" llm_pipeline/` and `grep -rn "session.exec.*Prompt" llm_pipeline/` to audit for any missed call sites.
16. Tests: add `test_sandbox_seed_filters_is_latest_is_active` (#11) to `tests/test_versioning_helpers.py` per §9.3.

**Dependency note:** Requires Group A (versioning helper must exist for `get_latest` calls).

### Step 7: Prompt write-site + YAML sync rewrites
**Agent:** backend-development:backend-architect
**Skills:** backend-development:api-design-principles
**Context7 Docs:** /websites/sqlmodel_tiangolo, /pydantic/pydantic
**Group:** B

1. `llm_pipeline/ui/routes/prompts.py` W1 (`create_prompt`): route through `save_new_version(session, Prompt, key_filters, new_fields)`.
2. `llm_pipeline/ui/routes/prompts.py` W2 (`update_prompt`): replace in-place mutation + `_increment_version` with `save_new_version(...)`; auto-bump; DB→YAML writeback follows in same request.
3. `llm_pipeline/ui/routes/prompts.py` W3 (`delete_prompt`): call `soft_delete_latest(session, Prompt, prompt_key=..., prompt_type=...)`.
4. `llm_pipeline/prompts/yaml_sync.py` W4 (`sync_yaml_to_db`): YAML version `>` DB latest → `save_new_version(..., version=yaml_version)`; same/lower → WARNING log per A8; first-time → `save_new_version(...)` (no-prior path). Also port `write_prompt_to_yaml` to temp-file + `Path.replace` atomic pattern (§6.5).
5. `llm_pipeline/creator/prompts.py` W5 (`_seed_prompts`): content-hash delta → `save_new_version(...)`; else no-op.
6. `llm_pipeline/creator/integrator.py` W6 (`_insert_prompts`): `save_new_version(...)` with first-time `"1.0"` fallback.
7. `llm_pipeline/sandbox.py` W7 (sandbox seed): copy-through of `is_latest` on seeded rows; no versioning logic.
8. Tests: add `tests/prompts/test_yaml_sync.py` tests #13, #14 from §9.5 — YAML newer inserts version+flips, older/equal logs WARNING+noop (verify via `caplog`).

**Dependency note:** Requires Group A; no file overlap with Step 6.

### Step 8: EvaluationCase read/write call-site updates
**Agent:** backend-development:backend-architect
**Skills:** none
**Context7 Docs:** /websites/sqlmodel_tiangolo
**Group:** B

1. `llm_pipeline/evals/runner.py` C1: add `is_active==True AND is_latest==True` to case query.
2. `llm_pipeline/evals/yaml_sync.py` C2: replace manual query with `get_latest(session, EvaluationCase, dataset_id=..., name=...)`.
3. `llm_pipeline/evals/yaml_sync.py` C3 (writeback): add `is_active==True AND is_latest==True`.
4. `llm_pipeline/ui/routes/evals.py` C4 (case-count subquery): add both filters before group-by.
5. `llm_pipeline/ui/routes/evals.py` C5 (get_dataset cases): add both filters.
6. `llm_pipeline/ui/routes/evals.py` C6 (update_dataset reload): add both filters.
7. `llm_pipeline/ui/routes/evals.py` CW1 (`create_case`): route through `save_new_version(session, EvaluationCase, {"dataset_id":..., "name":...}, {...})`.
8. `llm_pipeline/ui/routes/evals.py` CW2 (`update_case`): replace in-place mutation with `save_new_version(...)`; trigger DB→YAML writeback.
9. `llm_pipeline/ui/routes/evals.py` CW3 (`delete_case`): switch hard delete to `soft_delete_latest(session, EvaluationCase, ...)`; trigger DB→YAML writeback.
10. `llm_pipeline/evals/yaml_sync.py` CW5 (case insert): YAML version `>` DB latest → `save_new_version(..., version=yaml_version)`; same/lower → WARNING log; first-time → `save_new_version(...)`.
11. Post-implementation: grep `select(EvaluationCase)` and `session.exec.*EvaluationCase` to audit missed read sites.
12. Tests: add `tests/evals/test_yaml_sync.py` tests #15, #16, #17, #18 from §9.5; add `tests/ui/test_evals_routes.py` test #12 from §9.4.

**Dependency note:** Requires Group A; no file overlap with Steps 6 or 7 (different files in `evals/` vs `prompts/`).

### Step 9: `_build_run_snapshot` + runner snapshot population
**Agent:** backend-development:backend-architect
**Skills:** backend-development:workflow-orchestration-patterns
**Context7 Docs:** /websites/pydantic_dev_validation
**Group:** B

1. In `llm_pipeline/evals/runner.py`: implement `_build_run_snapshot(session, dataset, cases, variant_delta, model_kwarg)` as specified in VALIDATED_RESEARCH §7.2–§7.4.
   - Step-target: flat `prompt_versions`, single-entry `model_snapshot`, flat `instructions_schema_snapshot`.
   - Pipeline-target (A9 in scope): walk all registered steps; `prompt_versions` and `model_snapshot` keyed by `step_name`.
2. Call `_build_run_snapshot(...)` in `EvalRunner.run_dataset` right before `EvaluationRun(...)` construction (line 108); pass returned tuple into the run constructor's four snapshot fields.
3. Ensure `EvaluationCaseResult.case_id` continues to point at the exact row used (no FK change, append-only).
4. Tests: add `tests/test_eval_runner.py` tests #9, #10 from §9.2 — step-target and pipeline-target snapshot shapes.

**Dependency note:** Requires Group A (snapshot columns on `EvaluationRun`); no file overlap with Steps 6, 7, 8.

---

### Step 10: Dataset YAML sync — bidirectional
**Agent:** backend-development:backend-architect
**Skills:** none
**Context7 Docs:** /websites/sqlmodel_tiangolo
**Group:** C

1. Rewrite `sync_evals_yaml_to_db` case loop in `llm_pipeline/evals/yaml_sync.py` to use `get_latest` + `save_new_version` + WARNING no-op log per VALIDATED_RESEARCH §6.3.
2. Extended per-case YAML format: read `version` field from YAML (default `"1.0"` if absent) per §6.2.
3. Wire DB→YAML writeback triggers: `write_dataset_to_yaml(engine, dataset_id, evals_dir)` called after commit in `POST /evals/{dataset_id}/cases` (CW1), `PUT /evals/{dataset_id}/cases/{case_id}` (CW2), `DELETE /evals/{dataset_id}/cases/{case_id}` (CW3), and `PUT /evals/{dataset_id}` per §6.4. Use `app.state.evals_dir` as writeback target.
4. `write_dataset_to_yaml` writer already atomic (temp-file + `Path.replace`) — no changes to the writer itself.
5. Tests: tests #15–#18 already assigned to Step 8; no new tests here.

**Dependency note:** Requires Group B (Steps 8 must have landed; CW1/CW2/CW3 routes already updated).

### Step 11: Sandbox seed filter update
**Agent:** python-development:python-pro
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. `llm_pipeline/sandbox.py`: update seed query filter to `is_latest==True AND is_active==True` per A3.
2. Ensure seeded rows carry `is_latest` in the copy-through (Step 6 already handles the read filter; this step locks in the write side).
3. Tests: `test_sandbox_seed_filters_is_latest_is_active` (#11) already assigned to Step 6; confirm no duplicate.

**Dependency note:** Depends on Group A schema (is_latest column on Prompt) and Group B Step 6 (read filter). No file overlap with Step 10.

### Step 12: API response shape — run detail snapshot columns
**Agent:** backend-development:backend-architect
**Skills:** backend-development:api-design-principles
**Context7 Docs:** /pydantic/pydantic
**Group:** C

1. In `llm_pipeline/ui/routes/evals.py`: add four snapshot fields to `RunListItem` and `RunDetail` Pydantic models (lines 109–128) — all `Optional[dict] = None` per §8.1.
2. Thread fields through `GET /evals/{dataset_id}/runs` (list, lines 883–913) and `GET /evals/{dataset_id}/runs/{run_id}` (detail, lines 916–961).
3. No server-side mismatch computation — surface raw JSON; frontend badge rendering is deferred.
4. Tests: add `tests/ui/test_evals_routes.py` test #12 — null snapshot tolerability (legacy compat, §9.4). Already assigned in Step 8; confirm no duplicate.

**Dependency note:** Depends on Group A (snapshot columns on EvaluationRun) and Group B Step 9 (snapshot population in runner).

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Existing `eval_cases` duplicate `(dataset_id, name)` rows block partial unique index creation | High | `_migrate_partial_unique_indexes` runs `UPDATE eval_cases SET is_latest=0 WHERE id NOT IN (newest per partition)` BEFORE index CREATE. Migration test #19 explicitly seeds duplicates and verifies dedupe. |
| Missed prompt or eval-case read call site returns non-latest rows silently | High | Post-implementation grep audit mandated in Steps 6 and 8. Full suite regression in testing phase catches query-level regressions. |
| `session.flush()` missing between flip and INSERT causes partial-unique collision on SQLite | High | Helper API enforces flush internally — callers cannot bypass. Migration test #21 (idempotency) and helper test #2 (partial unique guard) cover this at DB level. |
| Sandbox regressions from seed filter change | Medium | Sandbox seed filter test #11 covers live+latest only, explicitly seeding non-latest and inactive rows. Run `tests/test_eval_runner.py` full suite in testing phase. |
| `EvaluationCaseResult.case_id` pointing to wrong version row | Medium | Runner snapshot pre-pass uses the same `cases` list already loaded for the run; `case_id` FK is unchanged, append-only. Runner tests #9, #10 assert `case_versions` keys match loaded case IDs. |
| YAML no-op WARNING log noise in dev | Low | Log level is `WARNING` per A8 — not emitted at `INFO` level in normal operation. Confirm logger config does not promote `WARNING` to stdout by default. |
| Partial unique index support in target SQLite version | Low | Safe — SQLite partial indexes since 3.8.0 (2013); Python 3.11 ships SQLite 3.37+. Migration test #21 runs against SQLite and confirms index creation. |
| Prompt YAML non-atomic write causes corruption on concurrent PUT | Low | `write_prompt_to_yaml` upgraded to temp-file + `Path.replace` in Step 7 (§6.5). |
| Creator module calls `save_new_version` on every startup even when content unchanged | Low | Existing `_content_hash` gating preserved in W5 — `save_new_version` only called on hash delta. Verify at implementation time per open item in §12. |

## Success Criteria

- [ ] `uv run pytest tests/test_versioning_helpers.py` passes — all 8 helper unit tests + sandbox test green
- [ ] `uv run pytest tests/test_migrations.py` passes — dedupe, legacy-index drop, idempotency
- [ ] `uv run pytest tests/prompts/test_yaml_sync.py tests/evals/test_yaml_sync.py` passes — YAML newer/older logic, writeback on PUT/DELETE
- [ ] `uv run pytest tests/test_eval_runner.py` passes — step-target and pipeline-target snapshot shapes
- [ ] `uv run pytest tests/ui/test_evals_routes.py` passes — null-snapshot legacy compat
- [ ] `uv run pytest` (full suite) exits 0 with no new failures
- [ ] Manual: start `uv run llm-pipeline ui --dev`, edit a prompt via UI → new version row in DB with correct `is_latest=True`; YAML file updated
- [ ] Manual: run eval with a prompt override variant → `EvaluationRun.prompt_versions` populated with correct snapshot in DB
- [ ] Manual: soft-delete a prompt via DELETE endpoint → `is_active=False, is_latest=True` in DB; recreate via POST → new row at `version="1.0"`
- [ ] Grep audit post-implementation finds no `select(Prompt)` or `select(EvaluationCase)` call sites missing `is_latest` filter (excluding intentional history exceptions tagged in §5.1)
- [ ] No regression in existing tests for pipeline execution, prompt resolution, or eval runner

## Phase Recommendation

**Risk Level:** high
**Reasoning:** Schema migration touches three tables on existing databases; partial unique index requires deduplication pre-pass; 20+ read call sites across prompt and eval domains risk silent non-latest-row bugs if any are missed; bidirectional YAML sync adds new failure surface; run snapshot pre-pass is a non-trivial rewrite of `EvalRunner.run_dataset` that could regress all existing eval tests.
**Suggested Exclusions:** none
