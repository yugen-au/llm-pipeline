# Architecture Review

## Overall Assessment
**Status:** partial
Solid v1 implementation following existing project patterns. Module separation (models/evaluators/runner/yaml_sync/routes) is clean. Frontend hooks and pages follow established reviews.ts patterns well. Several issues need fixing before merge: a critical route ordering bug, a high-severity duplicate run creation bug, an N+1 query problem in list_datasets, and inconsistent session handling across run endpoints.

## Project Guidelines Compliance
**CLAUDE.md:** `c:\Users\SamSG\Documents\claude-projects\llm-pipeline\.claude\CLAUDE.md`
| Guideline | Status | Notes |
| --- | --- | --- |
| Python 3.11+ / uv | pass | Standard deps, pydantic-evals added to pyproject.toml |
| Pydantic v2 / SQLModel | pass | Models use SQLModel correctly with JSON columns |
| Pipeline + Strategy + Step pattern | pass | evaluators field added to StepDefinition dataclass cleanly |
| Convention directory pattern | pass | llm-pipeline-evals/ follows llm-pipeline-prompts/ convention |
| YAML sync pattern | pass | yaml_sync.py mirrors prompts yaml_sync.py (simpler, no versioning per CEO decision) |
| TDD strict | pass | 3 test files covering evaluators, yaml_sync, and runner |
| No hardcoded values | pass | Ports, paths, model names all configurable |
| Error handling present | pass | Runner catches exceptions, marks runs as failed |
| Hatchling build | pass | No build changes needed beyond pyproject.toml dep |

## Issues Found
### Critical
#### Route ordering: GET /evals/schema shadowed by GET /evals/{dataset_id}
**Step:** 5 (backend routes - runs/introspection)
**Details:** `GET /evals/schema` is registered on line 640, AFTER `GET /evals/{dataset_id}` on line 165. FastAPI matches routes in registration order, so a request to `/api/evals/schema` will match the `/{dataset_id}` path with `dataset_id="schema"`, resulting in a 422 (int parse failure) or 404 instead of reaching the schema endpoint. The schema endpoint must be registered BEFORE the `/{dataset_id}` route, or moved to a separate prefix (e.g. `/evals-schema`).

### High
#### Duplicate EvaluationRun creation in trigger_eval_run
**Step:** 5 (backend routes - runs/introspection)
**Details:** `trigger_eval_run()` (evals.py line 613-622) creates a "pending" `EvaluationRun` row and returns its ID. Then in the background, `runner.run_dataset()` (runner.py line 66-74) creates a SECOND "running" `EvaluationRun` row for the same dataset. This produces orphan pending runs that never complete and actual run results stored in a different row than the one returned to the client. Fix: either pass the pre-created run_id into the runner (preferred), or remove the pending row creation from the route.

#### N+1 query in list_datasets: _last_run_pass_rate called per row
**Step:** 4 (backend routes - datasets/cases CRUD)
**Details:** `list_datasets()` calls `_last_run_pass_rate(db, ds.id)` in a loop for each dataset (line 157). Each call executes a separate SQL query. With 50 datasets this means 51 queries per list call. This should be computed as a subquery or window function joined into the main query, similar to how `case_count` is already computed via subquery.

### Medium
#### Inconsistent session handling: run endpoints use manual Session, others use DI
**Step:** 5 (backend routes - runs/introspection)
**Details:** Dataset/case endpoints correctly use `DBSession` and `WritableDBSession` dependency injection. However, `list_eval_runs`, `get_eval_run`, and `trigger_eval_run` create manual `Session(engine)` via `request.app.state.engine`. This breaks consistency with the rest of the file and bypasses any middleware/lifecycle management the DI provides. These should use `DBSession`/`WritableDBSession` like the dataset endpoints.

#### _create_dev_app does not pass evals_dir or demo_mode
**Step:** 6 (wire evals router + startup sync)
**Details:** `_create_dev_app()` in cli.py (line 314-328) reads env vars for db_path, model, and pipeline_modules but does NOT pass `evals_dir` or `demo_mode` to `create_app()`. While `create_app` reads these from env vars as fallback, `_create_dev_app` misses the pattern established for `prompts_dir` (also not passed). This is consistent with the existing gap for prompts_dir, but means `--evals-dir` only works on first launch, not after uvicorn hot-reload. Low urgency since env vars cover it.

#### No cascade delete defined at DB model level
**Step:** 1 (core dep, DB models)
**Details:** FK relationships in models.py have no `ondelete="CASCADE"` in the `sa_column_kwargs`. The manual cascade delete in `delete_dataset` (evals.py lines 312-335) compensates, but this is fragile -- direct DB operations or future endpoints could leave orphaned rows. Adding `sa_column_kwargs={"ondelete": "CASCADE"}` to the FK fields would be more robust. Not blocking for v1 since the manual cascade works.

#### target_type not validated as enum at DB/API level
**Step:** 1 (core dep, DB models) / Step 4 (backend routes)
**Details:** `EvaluationDataset.target_type` is a free-form `str` with max_length=20. `DatasetCreateRequest.target_type` is also unvalidated `str`. Only the schema introspection endpoint validates `target_type` via `Query(..., pattern="^(step|pipeline)$")`. Invalid target_type values like "foo" can be stored, causing runtime errors when the runner tries to resolve them. Add a Literal["step", "pipeline"] or regex validator on `DatasetCreateRequest`.

### Low
#### Frontend useEvalRuns expects array but backend returns { items: [] }
**Step:** 7 (frontend API hooks)
**Details:** `useEvalRuns` (evals.ts line 143) declares return type `RunListItem[]` but the backend `list_eval_runs` returns `RunListResponse` which has an `items` field. The frontend `RunHistoryTab` component (evals.$datasetId.tsx line 511-513) has a workaround: `Array.isArray(runs) ? runs : (runs as unknown)?.items ?? []`. This works but is fragile. Either change the backend to return a bare array or fix the frontend type to expect `RunListResponse`.

#### No pagination on run list or case result list
**Step:** 5 (backend routes - runs/introspection)
**Details:** `list_eval_runs` returns ALL runs for a dataset with no limit/offset. `get_eval_run` loads ALL case results. For large datasets with many runs or cases, this could return very large payloads. Not a v1 blocker but should be addressed as usage grows.

#### FieldMatchEvaluator uses strict equality only
**Step:** 2 (evaluators param, auto FieldMatch)
**Details:** `FieldMatchEvaluator.__call__` uses `==` comparison. For float fields (e.g. sentiment_score), this requires exact match which is fragile with LLM outputs. The worked example addresses this with `SentimentLabelEvaluator` (string field only), but users defining numeric expected_outputs will hit false failures. Consider documenting this limitation or adding an optional tolerance parameter.

#### useCaseEditor uses useMemo with side effect (setRows)
**Step:** 8 (frontend dataset list/detail)
**Details:** In `evals.$datasetId.tsx` line 189-206, `useMemo` is used to sync server state into local state via `setRows()`. This is a side effect inside a memo, which React docs warn against (can fire multiple times in strict mode). Should use `useEffect` for the state sync instead.

## Review Checklist
[x] Architecture patterns followed
[x] Code quality and maintainability
[x] Error handling present
[x] No hardcoded values
[x] Project conventions followed
[x] Security considerations
[x] Properly scoped (DRY, YAGNI, no over-engineering)

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| llm_pipeline/evals/__init__.py | pass | Empty package marker |
| llm_pipeline/evals/models.py | pass | Clean SQLModel tables, proper indexes. Missing ondelete cascade (medium). |
| llm_pipeline/evals/evaluators.py | pass | Simple, correct. Good self-skipping pattern. |
| llm_pipeline/evals/yaml_sync.py | pass | Follows prompts yaml_sync pattern. Atomic write with tempfile. yaml.safe_load used (secure). |
| llm_pipeline/evals/runner.py | pass | Solid error handling. Snapshots data before leaving session. |
| llm_pipeline/ui/routes/evals.py | fail | Route ordering bug (critical), duplicate run creation (high), N+1 query (high), inconsistent session DI (medium). |
| llm_pipeline/ui/app.py | pass | Evals wired correctly. Mirrors prompts sync pattern. |
| llm_pipeline/ui/cli.py | pass | eval subcommand clean. _create_dev_app gap is pre-existing pattern. |
| llm_pipeline/strategy.py | pass | evaluators field added cleanly with default_factory=list. |
| llm_pipeline/step.py | pass | evaluators= param follows review= pattern exactly. |
| llm_pipeline/db/__init__.py | pass | 4 tables registered in create_all correctly. |
| llm_pipeline/ui/frontend/src/api/evals.ts | pass | Follows reviews.ts pattern. Type mismatch on useEvalRuns (low). |
| llm_pipeline/ui/frontend/src/api/query-keys.ts | pass | Hierarchical keys correct. |
| llm_pipeline/ui/frontend/src/routes/evals.tsx | pass | Clean dataset list with dialog. |
| llm_pipeline/ui/frontend/src/routes/evals.$datasetId.tsx | pass | Schema-driven form fields, JSON fallback. useMemo side effect (low). |
| llm_pipeline/ui/frontend/src/routes/evals.$datasetId.runs.$runId.tsx | pass | Expandable result grid, dynamic evaluator columns. |
| llm_pipeline/ui/frontend/src/components/Sidebar.tsx | pass | FlaskConical icon, correct position after Reviews. |
| llm-pipeline-evals/sentiment_analysis.yaml | pass | 5 cases, good variety including edge cases. |
| llm_pipelines/steps/sentiment_analysis.py | pass | SentimentLabelEvaluator extends FieldMatchEvaluator cleanly. |
| tests/test_evaluators.py | pass | Good coverage of skip/match/mismatch + step_definition integration. |
| tests/test_eval_yaml_sync.py | pass | Insert, resync, roundtrip, edge cases covered. |
| tests/test_eval_runner.py | pass | Mocked task_fn, pass/fail counts, error state. |

## New Issues Introduced
- Route ordering conflict: GET /evals/schema vs GET /evals/{dataset_id} (critical)
- Duplicate EvaluationRun rows from trigger_eval_run + runner.run_dataset (high)
- N+1 queries in list_datasets endpoint (high)
- Inconsistent session management across evals routes (medium)
- No DB-level cascade deletes on FK relationships (medium)
- target_type not validated on create (medium)
- Frontend type mismatch on useEvalRuns response (low)
- useMemo with side effect in case editor (low)

## Recommendation
**Decision:** CONDITIONAL
Fix the critical route ordering bug and the high-severity duplicate run creation bug before merge. The N+1 query fix is strongly recommended but could ship as a fast-follow if needed. The remaining medium/low issues are acceptable for v1 with tracked follow-up.
