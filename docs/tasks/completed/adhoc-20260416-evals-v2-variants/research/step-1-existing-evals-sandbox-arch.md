# Research: Existing Evals & Sandbox Architecture

## 1. Current Data Model

### EvaluationDataset (`eval_datasets`)
- `id`, `name` (unique), `target_type` ("step"|"pipeline"), `target_name`, `description`, timestamps
- Variant is scoped per-dataset — `EvaluationVariant.dataset_id` FK aligns naturally

### EvaluationCase (`eval_cases`)
- `id`, `dataset_id` (FK), `name`, `inputs` (JSON), `expected_output` (JSON), `metadata_` (JSON)
- No changes needed for v2

### EvaluationRun (`eval_runs`)
- `id`, `dataset_id` (FK), `status`, `total_cases`, `passed`, `failed`, `errored`, `report_data` (JSON), `error_message`, timestamps
- **GAP**: No `variant_id` column. Needs nullable FK to `EvaluationVariant`. Baseline runs = `variant_id=NULL`.

### EvaluationCaseResult (`eval_case_results`)
- `id`, `run_id` (FK), `case_id` (FK), `case_name`, `passed`, `evaluator_scores` (JSON), `output_data` (JSON), `error_message`
- No changes needed — `output_data` JSON already stores full step output for comparison

### Missing Table: EvaluationVariant
- Not in codebase. Must be created per plan spec.

## 2. Runner Modification Points

### `EvalRunner.__init__()` (runner.py:34)
- Takes `engine`, `pipeline_registry`, `introspection_registry`
- No changes needed to constructor

### `EvalRunner.run_dataset()` (runner.py:44)
- **Signature change**: Add `variant_id: int | None = None` param
- Currently accepts `dataset_id` and `model`
- Creates `EvaluationRun` row at line 66 — must set `variant_id` here
- Calls `_resolve_task()` at line 93 — variant delta must be applied BEFORE or WITHIN this call

### `EvalRunner._find_step_def()` (runner.py:302)
- Returns `(step_def, input_data_cls, default_model)` from production introspection registry
- Returns the PRODUCTION step_def — variant delta applied AFTER this returns
- No modifications needed to this method itself

### `EvalRunner._resolve_step_task()` (runner.py:271)
- Calls `_find_step_def()`, then `_build_step_task_fn()`
- **Insertion point**: Between finding prod step_def and building task_fn, apply variant delta
- Pass variant-modified step_def to `_build_step_task_fn()`

### `EvalRunner._build_step_task_fn()` (runner.py:349)
- Creates closure calling `create_single_step_pipeline(step_def, input_data_cls, prod_engine, model)`
- **Key**: step_def and model params here are the variant-modified versions
- Sandbox engine created inside task_fn via `create_single_step_pipeline` — prompt overrides must happen AFTER engine creation but BEFORE execution
- Current flow: `create_single_step_pipeline` -> `create_sandbox_engine` (seeds from prod) -> execute
- **Needed**: After sandbox engine seeded, update Prompt rows for variant prompt overrides

### `EvalRunner._build_pipeline_task_fn()` (runner.py:384)
- Uses `create_sandbox_from_factory()` — pipeline-level variants not in v2 scope but same pattern applies

### `EvalRunner._resolve_evaluators()` (runner.py:327)
- Calls `build_auto_evaluators(step_def.instructions)` — if instructions class changes (fields added/removed), evaluators auto-adapt
- No explicit changes needed — just pass variant-modified instructions class

## 3. Sandbox Extension Points

### `create_sandbox_engine()` (sandbox.py:41)
- Creates in-memory SQLite, calls `init_pipeline_db()`, copies all Prompt + StepModelConfig rows from prod
- **Extension for variants**: Return engine, then caller applies prompt overrides by updating Prompt rows in sandbox DB
- Current API returns Engine — no need to change, variant logic is caller-side

### `create_single_step_pipeline()` (sandbox.py:104)
- Accepts `step_def`, `input_data_cls`, `engine`/`prod_engine`, `model`, `run_id`, `event_emitter`
- If `engine=None` and `prod_engine` provided, calls `create_sandbox_engine(prod_engine)`
- **Extension approach**: For variants, create sandbox engine externally, apply prompt overrides, then pass pre-built `engine` param
- Alternative: Add a `prompt_overrides` param that applies after seeding

### `SandboxSingleStepStrategy` (sandbox.py:87)
- Wraps a single StepDefinition — variant-modified step_def passed here via `create_single_step_pipeline`
- No changes needed

### `create_sandbox_from_factory()` (sandbox.py:148)
- For pipeline-level — creates sandbox engine, calls factory with it
- Not in v2 scope but same pattern for future pipeline variants

## 4. Prompt Override Mechanism

### How prompts are resolved at runtime
- `StepDefinition.create_step()` (strategy.py:51) looks up prompts by `prompt_key` + `prompt_type` in the pipeline's DB session
- Keys come from `step_def.system_instruction_key` and `step_def.user_prompt_key`
- Auto-discovery fallback: `{step_name}.{strategy_name}` then `{step_name}`

### Prompt table structure (db/prompt.py)
- Unique constraint: `(prompt_key, prompt_type)`
- Content in `content` field (text)
- `is_active` flag

### Variant prompt override flow
1. `create_sandbox_engine()` seeds all Prompt rows from prod
2. Variant delta has `system_prompt` and/or `user_prompt` content strings
3. After sandbox engine created, UPDATE the matching Prompt rows:
   - `UPDATE prompts SET content = ? WHERE prompt_key = ? AND prompt_type = 'system'`
   - `UPDATE prompts SET content = ? WHERE prompt_key = ? AND prompt_type = 'user'`
4. Step execution reads from sandbox DB session — gets variant content

### Identifying which prompt rows to update
- `step_def.system_instruction_key` = prompt_key for system prompt
- `step_def.user_prompt_key` = prompt_key for user prompt
- If keys are `None`, auto-discovery in `create_step()` — but for eval, step_def comes from introspection where keys may be explicitly set. Need to handle None case.

## 5. Model Override Mechanism

### Production model resolution (pipeline.py:1225)
Priority: DB StepModelConfig > step_def.model > pipeline._model

### Sandbox model resolution
- Sandbox copies StepModelConfig from prod — so DB overrides carry over
- `create_single_step_pipeline()` accepts `model` param, sets `pipeline._model`
- For variants, two approaches:
  1. **Override step_def.model** field — but `_resolve_step_model` checks DB config first
  2. **Upsert StepModelConfig in sandbox DB** — cleanest, matches production resolution path
  3. **Pass model to create_single_step_pipeline** — sets pipeline default, but DB config still wins

### Recommended approach
- If variant has model override: upsert StepModelConfig row in sandbox DB for the target step
- This respects the existing priority chain and matches how the UI configures models

## 6. Instructions Override (create_model)

### How instructions class is used
- `StepDefinition.instructions` = Pydantic model Type (e.g. `ShipmentInstructions`)
- Passed to step constructor: `step.py:41` `instructions: Type[BaseModel]`
- Used as pydantic-ai Agent `output_type` at execution time
- `build_auto_evaluators()` reads `model_fields` from the class

### Dynamic model via create_model()
- `pydantic.create_model()` returns a new Pydantic model class
- Fields from production class + delta (add/remove/modify)
- Dynamic class has `model_fields`, `model_json_schema()` — evaluators and schema endpoints work

### Risk: pydantic-ai Agent output_type
- pydantic-ai Agent uses output_type for structured output parsing
- Dynamic models created via `create_model()` should work — they're valid Pydantic models
- But: no __module__ path for import, serialization edge cases possible
- **Mitigation**: Test with a simple create_model class as Agent output_type before building full variant system

## 7. DB Registration

### init_pipeline_db() (db/__init__.py:145)
- Explicit table list at line 199-217
- Must add `EvaluationVariant.__table__` to `create_all` tables list
- Migration: add `variant_id` column to `eval_runs` table in `_MIGRATIONS` list

## 8. Route Integration Points

### Existing eval routes (ui/routes/evals.py)
- Router: `APIRouter(prefix="/evals")`
- Deps: `DBSession` (read-only), `WritableDBSession` (mutations)
- Pattern: Pydantic request/response models, manual query building

### trigger_eval_run() (evals.py:632)
- `TriggerRunRequest` has `model: Optional[str]` — add `variant_id: Optional[int]`
- Creates `EvalRunner` from `request.app.state`
- Calls `runner.run_dataset(dataset_id, model=eval_model)` — add variant_id param

### RunListItem / RunDetail response models
- Need `variant_id: Optional[int]` and `variant_name: Optional[str]` fields
- Run list query needs LEFT JOIN to EvaluationVariant for name

### New variant CRUD endpoints
- Follow existing dataset CRUD pattern (create/read/update/delete)
- Nested under `/{dataset_id}/variants/`

## 9. Cascade Deletion

### Current cascade (evals.py:399)
- Manual cascade: case_results -> runs -> cases -> dataset
- Must add: delete variants when deleting dataset
- Must also handle: what if variant is deleted but runs reference it? Nullable FK handles this (run keeps variant_id but variant row gone)

## 10. Summary of Changes Needed

### New files
- `llm_pipeline/evals/variants.py` — EvaluationVariant delta application logic

### Modified files
- `llm_pipeline/evals/models.py` — EvaluationVariant table, variant_id on EvaluationRun
- `llm_pipeline/evals/runner.py` — variant_id param, delta application before sandbox execution
- `llm_pipeline/sandbox.py` — possibly add prompt override helper (or keep in variants.py)
- `llm_pipeline/db/__init__.py` — register EvaluationVariant table, add variant_id migration
- `llm_pipeline/ui/routes/evals.py` — variant CRUD, updated run trigger/list/detail
