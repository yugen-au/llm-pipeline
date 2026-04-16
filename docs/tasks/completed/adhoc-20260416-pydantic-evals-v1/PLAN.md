# PLANNING

## Summary

Integrate pydantic-evals into llm-pipeline as a core dependency. Adds 4 new DB tables, an `evals/` module (YAML sync, runner, auto FieldMatch evaluators), `evaluators=` param on `@step_definition`, backend routes at `/api/evals/`, a full Evals tab in the frontend (dataset list, case editor, run history, run detail), a CLI `eval` subcommand, and a worked sentiment_analysis example in `llm-pipeline-evals/`.

## Plugin & Agents

**Plugin:** llm-application-dev, backend-development, frontend-mobile-development
**Subagents:** llm-application-dev:ai-assistant, backend-development:api-design-principles, frontend-mobile-development:react-state-management
**Skills:** llm-application-dev:llm-evaluation, backend-development:api-design-principles, api-scaffolding:fastapi-templates, python-development:python-testing-patterns

## Phases

1. **Group A - Foundation**: Core dep, DB models, `evaluators=` param on step_definition, `llm_pipeline/evals/` module (evaluators.py, yaml_sync.py, runner.py), CLI subcommand. No UI dependencies - all backend/framework code.
2. **Group B - Backend routes**: `/api/evals/` router with dataset/case/run CRUD + introspection endpoint. Wired into app.py. Depends on Group A.
3. **Group C - Frontend**: Evals tab, API hooks, 3 route pages, Sidebar update. Runs parallel to Group B (frontend mocks data until B lands).
4. **Group D - Worked example**: `llm-pipeline-evals/sentiment_analysis.yaml` + custom evaluators on a demo step. Depends on Group A.

## Architecture Decisions

### evaluators= storage on StepDefinition
**Choice:** Add `evaluators: list[type] = field(default_factory=list)` to `StepDefinition` dataclass in `strategy.py`, and accept `evaluators=` kwarg in `step_definition` decorator in `step.py`. Stored as class attribute on the decorated step class, copied into `StepDefinition` at create_definition() time.
**Rationale:** Mirrors how `review=` is declared on `@step_definition` today. No global registry needed - evaluators travel with the step class. Runner reads them from `StepDefinition.evaluators` at eval time.
**Alternatives:** Global evaluator registry (rejected - CEO decision: declared on step_definition); separate evaluator config file (rejected - unnecessary indirection).

### Auto FieldMatch evaluator
**Choice:** `llm_pipeline/evals/evaluators.py` defines `AutoFieldMatchEvaluator` - a pydantic-evals-compatible callable class. At runner time, if `StepDefinition.evaluators` is empty, runner calls `build_auto_evaluators(instructions_cls)` which iterates `instructions_cls.model_fields` and returns one `FieldMatchEvaluator(field_name)` per field. Each `FieldMatchEvaluator.__call__` returns `{}` if the expected field is None (self-skipping).
**Rationale:** CEO confirmed: auto field-match when no explicit evaluators. Keeps zero-config evals useful out-of-the-box. Matches pydantic-evals `{}` skip contract.
**Alternatives:** Always require explicit evaluators (rejected); use built-in EqualsExpected (rejected - does full equality only, no partial field match).

### DB tables location
**Choice:** 4 new SQLModel tables defined in `llm_pipeline/evals/models.py` (not state.py). Imported into `llm_pipeline/db/__init__.py` alongside existing tables, registered in `init_pipeline_db()` `create_all` call.
**Rationale:** Eval models are a distinct subsystem. state.py already has 7 classes; splitting keeps files manageable. Pattern matches how `PipelineReview` could have been split. db/__init__.py is the single registration point - consistent with existing pattern.
**Alternatives:** Add to state.py (rejected - file already large, evals are separable); new db/evals.py (rejected - unnecessary extra indirection layer).

### YAML sync (evals)
**Choice:** New `llm_pipeline/evals/yaml_sync.py`. On startup: scan `llm-pipeline-evals/` (CWD + package if demo_mode), parse YAML, insert-if-not-exists into DB (by dataset name). On UI save: overwrite YAML file (write-to-temp + rename for atomicity). No version tracking.
**Rationale:** CEO decision: DB is source of truth, no versioning. Much simpler than prompts yaml_sync.py (no compare_versions needed). Write-to-temp+rename mitigates YAML corruption risk identified in VALIDATED_RESEARCH open items.
**Alternatives:** Version-tracked sync like prompts (rejected by CEO); no YAML writeback (rejected - YAML is the developer-facing artifact).

### Pipeline-level eval runner aggregation
**Choice:** `EvaluationRun.report_data` stores per-step results as `dict[step_name, EvaluationReport serialized]`. Pass/fail counts in `EvaluationRun` are aggregate totals across all steps. For pipeline evals, `task_fn` calls `pipeline.execute(input_data=inputs)` and returns `dict[step_name, step_output]` as the OutputT. Each step's expected_output is matched against its slice of the output dict. All-steps-must-pass for pipeline-level pass/fail (most conservative, simplest to implement).
**Rationale:** VALIDATED_RESEARCH flagged this as open - "different evaluator aggregation" but specifics TBD. All-must-pass is the safest default for v1; can be made configurable later via dataset metadata field.
**Alternatives:** Weighted average (deferred); per-step thresholds (deferred).

### Schema introspection endpoint
**Choice:** New endpoint `GET /api/evals/schema?target_type=step&target_name=sentiment_analysis` returns JSON Schema for the step/pipeline input. For steps: reflects `prepare_calls()` signature or `input_data` type annotation on the step class. For pipelines: uses existing `PipelineIntrospector`. Returns `{"type": "object", "properties": {...}}` compatible with JSON Schema draft-07.
**Rationale:** CEO decision: typed form fields in case editor require backend schema resolution. Reuses existing `PipelineIntrospector` for pipeline case. Step schema resolution via type hints on step's `__call__` or `input_data` param.
**Alternatives:** Client-side inference (rejected - not reliable without backend type info); raw JSON textarea only (rejected by CEO).

### EvaluationRun result storage
**Choice:** `EvaluationRun` has `report_data: dict` (JSON column, full serialized report), plus denormalized `total_cases: int`, `passed: int`, `failed: int`, `errored: int` for fast list queries. `EvaluationCaseResult` has per-case `evaluator_scores: dict` (JSON) and `passed: bool`.
**Rationale:** VALIDATED_RESEARCH recommendation #5: denormalized counts for fast list queries, full JSON blob for flexibility. Avoids re-parsing report_data on every list call.
**Alternatives:** Only report_data JSON (rejected - slow list queries); only denormalized counts (rejected - loses full result detail).

## Implementation Steps

### Step 1: Add pydantic-evals core dependency
**Agent:** backend-development:api-design-principles
**Skills:** python-development:uv-package-manager
**Context7 Docs:** -
**Group:** A

1. In `pyproject.toml` `[project.dependencies]`, add `"pydantic-evals"` (already in uv.lock, just needs declaration).
2. Run `uv sync` to verify no conflicts.
3. Verify `from pydantic_evals import Dataset, Case` imports cleanly in a scratch check.

### Step 2: DB models - EvaluationDataset, EvaluationCase, EvaluationRun, EvaluationCaseResult
**Agent:** backend-development:api-design-principles
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Create `llm_pipeline/evals/__init__.py` (empty, marks package).
2. Create `llm_pipeline/evals/models.py` with 4 SQLModel table classes following state.py patterns:
   - `EvaluationDataset`: id (PK), name (unique, indexed), target_type ("step"|"pipeline"), target_name, description, created_at, updated_at. `__tablename__ = "eval_datasets"`.
   - `EvaluationCase`: id (PK), dataset_id (FK int, indexed), name, inputs (JSON column), expected_output (JSON column, nullable), metadata_ (JSON column, nullable), created_at. `__tablename__ = "eval_cases"`.
   - `EvaluationRun`: id (PK), dataset_id (FK int, indexed), status ("pending"|"running"|"completed"|"failed"), total_cases (int, default 0), passed (int, default 0), failed (int, default 0), errored (int, default 0), report_data (JSON column, nullable), error_message (str, nullable), started_at, completed_at (nullable). `__tablename__ = "eval_runs"`.
   - `EvaluationCaseResult`: id (PK), run_id (FK int, indexed), case_id (FK int, indexed), case_name (str), passed (bool), evaluator_scores (JSON column), output_data (JSON column, nullable), error_message (str, nullable). `__tablename__ = "eval_case_results"`.
3. Add SQLAlchemy `Index` for `(dataset_id,)` on EvaluationCase and EvaluationRun.

### Step 3: Register eval tables in init_pipeline_db()
**Agent:** backend-development:api-design-principles
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. In `llm_pipeline/db/__init__.py`, import the 4 new models from `llm_pipeline.evals.models`.
2. Add all 4 `.__table__` entries to the `SQLModel.metadata.create_all(engine, tables=[...])` call in `init_pipeline_db()`.
3. No migration needed (new tables; existing DBs get them on next startup via create_all).

### Step 4: evaluators= param on step_definition decorator + StepDefinition field
**Agent:** backend-development:api-design-principles
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. In `llm_pipeline/strategy.py`, add `evaluators: list[type] = field(default_factory=list)` to `StepDefinition` dataclass.
2. In `llm_pipeline/step.py`, add `evaluators: Optional[List[Type]] = None` kwarg to `step_definition()` signature.
3. In `step_definition` decorator body: store `evaluators` list on the decorated class as `cls._step_evaluators = evaluators or []`.
4. In `StepDefinition.create_definition()` (or wherever StepDefinition is instantiated from the decorated class): pass `evaluators=cls._step_evaluators` to StepDefinition constructor.
5. Add unit test in `tests/` verifying that `@step_definition(instructions=..., evaluators=[MyEvaluator])` stores the evaluator class on the resulting StepDefinition.

### Step 5: Auto FieldMatch evaluator + evaluators module
**Agent:** llm-application-dev:ai-assistant
**Skills:** llm-application-dev:llm-evaluation
**Context7 Docs:** -
**Group:** A

1. Create `llm_pipeline/evals/evaluators.py`:
   - `FieldMatchEvaluator(field_name: str)` - callable class. `__call__(self, output, expected)`: if `expected` is None or field not in expected, return `{}` (skip). Else return `bool(getattr(output, field_name, None) == expected[field_name])`.
   - `build_auto_evaluators(instructions_cls: type) -> list` - iterates `instructions_cls.model_fields.keys()`, returns `[FieldMatchEvaluator(f) for f in fields]`.
2. Add unit tests covering: skip when expected=None, skip when field missing from expected, True when match, False when mismatch.

### Step 6: YAML dataset sync service
**Agent:** backend-development:api-design-principles
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Create `llm_pipeline/evals/yaml_sync.py`:
   - `sync_evals_yaml_to_db(engine, scan_dirs: list[Path]) -> None`: for each `*.yaml` in scan_dirs, parse YAML (fields: name, target_type, target_name, description, cases[]). Insert EvaluationDataset if not exists (by name). For each case in YAML, insert EvaluationCase if not exists (by dataset_id + name).
   - `write_dataset_to_yaml(engine, dataset_id: int, target_dir: Path) -> None`: load dataset + cases from DB, serialize to YAML. Write to `target_dir/{dataset_name}.yaml` via write-to-temp + `Path.replace()` for atomicity.
2. YAML case format: `{name, inputs: {...}, expected_output: {...} | null, metadata: {...} | null}`.
3. Add unit tests with tmp_path fixture: verify insert-if-missing, verify no duplicate on re-sync, verify writeback produces parseable YAML.

### Step 7: Eval runner
**Agent:** llm-application-dev:ai-assistant
**Skills:** llm-application-dev:llm-evaluation
**Context7 Docs:** -
**Group:** A

1. Create `llm_pipeline/evals/runner.py`:
   - `EvalRunner(engine, pipeline_registry, introspection_registry)`.
   - `run_dataset(dataset_id: int, model: str | None) -> int` (returns run_id): creates EvaluationRun row (status=running), loads cases, builds pydantic-evals `Dataset`, calls `dataset.evaluate(task_fn)`, writes results to EvaluationCaseResult rows, updates EvaluationRun with aggregate counts + full report_data JSON, sets status=completed (or failed on exception).
   - `_build_step_task_fn(step_def, model)`: returns async function `(input_data) -> instructions_output`. Instantiates step via `build_step_agent()`, calls with `input_data`, returns structured output.
   - `_build_pipeline_task_fn(pipeline_factory, model)`: returns async function `(input_data) -> dict[step_name, output]`. Calls `pipeline.execute(input_data=input_data)`, collects per-step outputs.
   - Evaluator resolution: if `step_def.evaluators` non-empty, use those; else call `build_auto_evaluators(step_def.instructions)`.
2. Add integration test: mock step that returns fixed output, verify EvaluationRun created with correct pass/fail counts.

### Step 8: CLI eval subcommand
**Agent:** backend-development:api-design-principles
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. In `llm_pipeline/ui/cli.py`, add `eval` subparser to `argparse`: `sub.add_parser("eval")` with args `dataset_name` (positional), `--db`, `--model`, `--pipelines`.
2. Dispatch in `main()`: if `args.command == "eval"`: init DB engine, load pipeline modules if provided, instantiate `EvalRunner`, call `run_dataset_by_name(dataset_name)`, print summary (pass/fail/error counts).
3. Add `run_dataset_by_name(name: str)` to runner.py that looks up dataset by name then delegates to `run_dataset(id)`.

### Step 9: Backend evals router - datasets + cases CRUD
**Agent:** backend-development:api-design-principles
**Skills:** api-scaffolding:fastapi-templates
**Context7 Docs:** -
**Group:** B

1. Create `llm_pipeline/ui/routes/evals.py` with `router = APIRouter(prefix="/evals", tags=["evals"])`.
2. Pydantic request/response models: `DatasetListItem`, `DatasetListResponse`, `DatasetDetail`, `DatasetCreateRequest`, `DatasetUpdateRequest`, `CaseItem`, `CaseCreateRequest`, `CaseUpdateRequest`.
3. Endpoints:
   - `GET /evals` - list datasets with total case count (subquery), last run pass rate (join EvaluationRun).
   - `GET /evals/{dataset_id}` - dataset detail + cases list.
   - `POST /evals` - create dataset, optionally trigger evals-dir writeback.
   - `PUT /evals/{dataset_id}` - update dataset name/description.
   - `DELETE /evals/{dataset_id}` - delete dataset + cascade cases + runs.
   - `POST /evals/{dataset_id}/cases` - add case.
   - `PUT /evals/{dataset_id}/cases/{case_id}` - update case inputs/expected_output.
   - `DELETE /evals/{dataset_id}/cases/{case_id}` - delete case.

### Step 10: Backend evals router - runs + introspection
**Agent:** backend-development:api-design-principles
**Skills:** api-scaffolding:fastapi-templates
**Context7 Docs:** -
**Group:** B

1. In `llm_pipeline/ui/routes/evals.py`, add run endpoints:
   - `GET /evals/{dataset_id}/runs` - list runs for dataset (id, status, total/passed/failed/errored, started_at, completed_at).
   - `GET /evals/{dataset_id}/runs/{run_id}` - run detail with per-case results (EvaluationCaseResult rows).
   - `POST /evals/{dataset_id}/runs` - trigger eval run via BackgroundTasks; instantiates EvalRunner, calls run_dataset(). Returns run_id immediately.
2. Add introspection endpoint:
   - `GET /evals/schema?target_type=step|pipeline&target_name=<name>` - returns JSON Schema for the input type. For pipeline: reuses `PipelineIntrospector`. For step: reflects `input_data` type annotation from step class (via `inspect.get_annotations` or `typing.get_type_hints`), calls `.model_json_schema()` on Pydantic model.
3. Add `RunListItem`, `RunListResponse`, `RunDetail`, `CaseResultItem`, `SchemaResponse` Pydantic models.

### Step 11: Wire evals router into app.py + startup sync
**Agent:** backend-development:api-design-principles
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. In `llm_pipeline/ui/app.py`:
   - Import `from llm_pipeline.ui.routes.evals import router as evals_router`.
   - `app.include_router(evals_router, prefix="/api")`.
   - After existing prompt sync block, add evals YAML sync: scan `llm-pipeline-evals/` (CWD + package if demo_mode) via `sync_evals_yaml_to_db(engine, scan_dirs)`.
   - Store `app.state.evals_dir = project_evals_dir` (parallel to `app.state.prompts_dir`).
2. Pass `app.state.evals_dir` into evals router via `request.app.state.evals_dir` for writeback on save.

### Step 12: Frontend API hooks for evals
**Agent:** frontend-mobile-development:react-state-management
**Skills:** none
**Context7 Docs:** /tanstack/router
**Group:** C

1. Create `llm_pipeline/ui/frontend/src/api/evals.ts`:
   - Interfaces: `DatasetListItem`, `DatasetListResponse`, `DatasetDetail`, `CaseItem`, `RunListItem`, `RunListResponse`, `RunDetail`, `CaseResultItem`, `SchemaResponse`.
   - Hooks: `useDatasets()`, `useDataset(id)`, `useCreateDataset()`, `useUpdateDataset()`, `useDeleteDataset()`, `useCreateCase()`, `useUpdateCase()`, `useDeleteCase()`, `useEvalRuns(datasetId)`, `useEvalRun(datasetId, runId)`, `useTriggerEvalRun(datasetId)`, `useInputSchema(targetType, targetName)`.
   - Follow reviews.ts pattern: `useQuery` for reads, `useMutation` + `toast` for writes, `queryClient.invalidateQueries` on success.
2. Add evals keys to `query-keys.ts`: `evals: { all, list, detail(id), runs(id), run(id, runId), schema(type, name) }`.

### Step 13: Frontend route - Evals dataset list
**Agent:** frontend-mobile-development:react-state-management
**Skills:** none
**Context7 Docs:** /tanstack/router
**Group:** C

1. Create `llm_pipeline/ui/frontend/src/routes/evals.tsx`:
   - `createFileRoute('/evals')` with `EvalDatasetsPage` component.
   - Table columns: Name, Target (type + name), Cases, Last Run (pass rate badge), Actions (Run button).
   - "New Dataset" button opens inline form (name, target_type select, target_name input).
   - Clicking row navigates to `/evals/$datasetId`.
   - Uses `useDatasets()`, `useCreateDataset()`.

### Step 14: Frontend route - Dataset detail with case editor + run history
**Agent:** frontend-mobile-development:react-state-management
**Skills:** none
**Context7 Docs:** /tanstack/router
**Group:** C

1. Create `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.tsx`:
   - `createFileRoute('/evals/$datasetId')`.
   - Tabbed layout (Tabs component): "Cases" tab + "Run History" tab.
   - Cases tab: editable table. Each row = one case. Columns driven by input schema fields (from `useInputSchema()`). Add/delete case rows. Per-field input rendering: string -> Input, number -> Input[type=number], boolean -> Checkbox, object/array -> Textarea (JSON). Expected output column = JSON Textarea.
   - "Run Evals" button triggers `useTriggerEvalRun()`, shows toast + navigates to run detail on completion.
   - Run History tab: table of runs (id, status, pass/fail counts, date). Clicking row navigates to `/evals/$datasetId/runs/$runId`.

### Step 15: Frontend route - Run detail
**Agent:** frontend-mobile-development:react-state-management
**Skills:** none
**Context7 Docs:** /tanstack/router
**Group:** C

1. Create `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.runs.$runId.tsx`:
   - `createFileRoute('/evals/$datasetId/runs/$runId')`.
   - Header: dataset name, run status badge, aggregate pass/fail/errored counts.
   - Results grid: rows = cases, columns = case name + one column per evaluator + overall pass/fail. Cells show green check / red x / grey dash (skip).
   - Expandable row (accordion or collapsible) showing raw `output_data` and `error_message` if present.
   - Uses `useEvalRun(datasetId, runId)`.

### Step 16: Add Evals to Sidebar navigation
**Agent:** frontend-mobile-development:react-state-management
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. In `llm_pipeline/ui/frontend/src/components/Sidebar.tsx`:
   - Import `FlaskConical` (or `TestTube2`) icon from `lucide-react`.
   - Add `{ to: '/evals', label: 'Evals', icon: FlaskConical }` to `navItems` array (after Reviews).
2. Ensure TanStack Router `routeTree.gen.ts` regenerates to include new `/evals`, `/evals/$datasetId`, `/evals/$datasetId/runs/$runId` routes (auto-generated by Vite plugin on dev start).

### Step 17: Worked example - sentiment analysis eval dataset
**Agent:** llm-application-dev:ai-assistant
**Skills:** llm-application-dev:llm-evaluation
**Context7 Docs:** -
**Group:** D

1. Create `llm-pipeline-evals/sentiment_analysis.yaml`:
   - `name: sentiment_analysis`, `target_type: step`, `target_name: sentiment_analysis`.
   - 5+ cases with `inputs` matching SentimentAnalysisStep's input schema, `expected_output` with field values to match.
   - Mix of positive/negative/neutral examples plus an edge case (neutral review with weak signals).
2. In the demo step file (wherever `SentimentAnalysisStep` is defined), add `evaluators=[SentimentScoreEvaluator, SentimentLabelEvaluator]` to `@step_definition`.
3. Define `SentimentScoreEvaluator` and `SentimentLabelEvaluator` in the same file or a co-located `evaluators.py`:
   - `SentimentLabelEvaluator`: checks `output.sentiment_label == expected.get("sentiment_label")`, returns `{}` if expected field absent.
   - `SentimentScoreEvaluator`: checks `abs(output.sentiment_score - expected.get("sentiment_score", output.sentiment_score)) < 0.2`, returns `{}` if absent.
4. Add a `README` comment block in the YAML file showing how to run: `uv run llm-pipeline eval sentiment_analysis`.

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| pydantic-evals API surface changes between uv.lock version and latest | Medium | Pin version in pyproject.toml; validate against locked version in step 1 |
| step input schema introspection fails for steps with complex type annotations | Medium | Fallback to raw JSON textarea if schema endpoint returns 422; document limitation |
| Pipeline-level task_fn is slow (runs full pipeline per case) | Medium | Add timeout param to EvalRunner.run_dataset(); document that pipeline evals are slow by design |
| EvaluationReport JSON serialization loses ConfusionMatrix/SpanTree data | Low | Store report_data as-is from pydantic model_dump(mode='json'); accept lossy serialization for complex types in v1 |
| YAML writeback race condition if two UI saves fire simultaneously | Low | Write-to-temp + Path.replace() is atomic on all supported platforms; acceptable for v1 |
| Frontend case editor schema rendering fails for deeply nested input schemas | Low | Render nested objects as JSON textarea; only flat fields get typed inputs |
| routeTree.gen.ts not regenerated in production build | Low | Add note in step 16: run `vite build` to regenerate before shipping |

## Success Criteria

- [ ] `pydantic-evals` listed in `pyproject.toml` core deps and importable without guards
- [ ] `uv run pytest` passes with new tests for evaluators, yaml_sync, runner, step_definition evaluators param
- [ ] `EvaluationDataset`, `EvaluationCase`, `EvaluationRun`, `EvaluationCaseResult` tables created in fresh SQLite DB on startup
- [ ] `@step_definition(instructions=..., evaluators=[MyEval])` stores evaluators on resulting StepDefinition
- [ ] `build_auto_evaluators(InstructionsCls)` returns one FieldMatchEvaluator per model field
- [ ] `GET /api/evals` returns 200 with dataset list
- [ ] `POST /api/evals/{id}/runs` creates EvaluationRun and returns run_id within 200ms
- [ ] `GET /api/evals/schema?target_type=step&target_name=...` returns valid JSON Schema
- [ ] Frontend `/evals` route renders dataset list without console errors
- [ ] Frontend case editor renders typed fields from introspection schema
- [ ] Frontend run detail shows per-evaluator pass/fail grid
- [ ] `uv run llm-pipeline eval sentiment_analysis` runs and prints pass/fail summary
- [ ] `llm-pipeline-evals/sentiment_analysis.yaml` seeds DB on startup and is visible in UI

## Phase Recommendation

**Risk Level:** medium
**Reasoning:** The feature spans 6 distinct subsystems (dep, DB, framework, backend, frontend, CLI) with real interdependencies. pydantic-evals API surface is unfamiliar and introspection endpoint has open design questions. Pipeline-level eval runner wraps existing code but adds new async/background complexity. Frontend case editor's dynamic schema rendering is the highest-uncertainty UI piece.
**Suggested Exclusions:** review (automated testing sufficient for this feature; no security or data-loss risk requiring human review)
