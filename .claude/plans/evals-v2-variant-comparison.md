# Evals v2: Variant Comparison System

## Context

v1 evals are merged and working: sandbox pipeline execution, field-match evaluators, UI with dataset/case/run views. The next step is variant-based comparison — the ability to modify a step definition (model, prompts, instructions schema) and compare eval results against the production baseline.

## Architecture

A variant is a **delta** from the production StepDefinition. The delta is a JSON object where null = use production default. At eval time, the runner applies the delta to create a modified StepDefinition, executes via sandbox pipeline, and stores results linked to the variant.

### Data Flow

```
Production StepDefinition
        │
        ├── Baseline variant (delta={}) ──→ Sandbox ──→ Results A
        │
        └── Experiment variant (delta={   ──→ Sandbox ──→ Results B
              model: "anthropic:...",                        │
              system_prompt: "...",                          │
              instructions_delta: {...}                      ▼
            })                                    Comparison View
                                                  (A vs B side-by-side)
                                                       │
                                                  [Accept Changes]
                                                       │
                                                       ▼
                                              Apply delta to prod
```

## Implementation Phases

### Phase 1: Data Model + Delta Application

**New DB table: `EvaluationVariant`**
- `id` (PK auto)
- `dataset_id` (FK to EvaluationDataset, indexed)
- `name` (str, e.g. "baseline", "experiment-1")
- `delta` (JSON column): `{model, system_prompt, user_prompt, instructions_delta}`
- `created_at`, `updated_at`
- Unique constraint: `(dataset_id, name)`

**`instructions_delta` schema:**
```json
{
  "add": [{"name": "emotion", "type": "str", "default": "", "description": "..."}],
  "remove": ["confidence_score"],
  "modify": [{"name": "sentiment", "type": "str", "default": "", "description": "new desc"}]
}
```

**Delta application logic** (`llm_pipeline/evals/variants.py`):
- `apply_variant_delta(step_def, delta, sandbox_engine) -> StepDefinition`
  - Model: override `step_def.model` if `delta.model` is set
  - Prompts: insert/update Prompt rows in sandbox DB with modified content
  - Instructions: use `pydantic.create_model()` starting from production model's fields, apply add/remove/modify

**Modified instructions via create_model():**
```python
from pydantic import create_model

base_fields = {name: (info.annotation, info.default) for name, info in ProductionInstructions.model_fields.items()}

# Apply delta
for field in delta.get("remove", []):
    base_fields.pop(field, None)
for field in delta.get("add", []):
    base_fields[field["name"]] = (resolve_type(field["type"]), field.get("default", ""))
for field in delta.get("modify", []):
    existing = base_fields.get(field["name"])
    if existing:
        base_fields[field["name"]] = (resolve_type(field.get("type", existing[0])), field.get("default", existing[1]))

ModifiedInstructions = create_model("ModifiedInstructions", **base_fields)
```

**Register table in init_pipeline_db()** — add to db/__init__.py create_all list.

**Files:**
- `llm_pipeline/evals/models.py` — add EvaluationVariant
- `llm_pipeline/evals/variants.py` — new, delta application logic
- `llm_pipeline/db/__init__.py` — register table

### Phase 2: Runner Integration

**Update EvalRunner to support variants:**
- `run_dataset()` accepts optional `variant_id` param
- If variant_id provided: load variant, apply delta to step_def before building sandbox pipeline
- `EvaluationRun` gets new `variant_id` (FK, nullable) column — links run to which variant was used
- Baseline runs have `variant_id=NULL` (production step_def, no delta)

**Update sandbox pipeline creation:**
- After `create_sandbox_engine()`, apply prompt overrides to sandbox DB
- Pass modified instructions class to `StepDefinition` copy
- Pass model override

**Files:**
- `llm_pipeline/evals/runner.py` — variant-aware execution
- `llm_pipeline/evals/models.py` — variant_id on EvaluationRun

### Phase 3: Backend Routes

**New endpoints on `/api/evals` router:**
- `GET /evals/{dataset_id}/variants` — list variants for dataset
- `POST /evals/{dataset_id}/variants` — create variant (name + delta JSON)
- `PUT /evals/{dataset_id}/variants/{variant_id}` — update delta
- `DELETE /evals/{dataset_id}/variants/{variant_id}` — delete variant
- `GET /evals/{dataset_id}/variants/{variant_id}/diff` — returns structured diff (production fields vs delta-applied fields, for UI rendering)

**Update run trigger:**
- `POST /evals/{dataset_id}/runs` body gets optional `variant_id`
- Response includes `variant_id` and `variant_name`

**Update run list/detail:**
- `RunListItem` / `RunDetail` include `variant_id`, `variant_name`
- Run detail includes the delta that was used (snapshot, not live reference)

**Schema endpoint update:**
- `GET /evals/schema` gets optional `variant_id` query param
- If provided, returns the delta-applied schema (so case editor can preview modified fields)

**Files:**
- `llm_pipeline/ui/routes/evals.py` — variant CRUD + updated run endpoints

### Phase 4: Frontend — Variant Management

**Dataset detail page updates:**
- New "Variants" tab alongside Cases and Run History
- Variant list: name, delta summary (what's changed), created date
- "New Variant" button → variant editor

**Variant editor page** (`evals.$datasetId.variants.$variantId.tsx`):
- Split view: left = production (read-only), right = variant (editable)
- **Model selector:** dropdown with available models
- **Prompt editors:** reuse existing prompt template component (textarea with variable highlighting). Shows production text, editable copy for variant.
- **Instructions field editor:** table of fields (name, type, description, default). Add/remove/modify rows. Reuse FieldDefinition pattern from step creator.
- Save → PUT variant delta
- "Run with this variant" button → trigger eval run with variant_id

**Files:**
- `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.variants.$variantId.tsx` — variant editor
- `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.index.tsx` — variants tab
- `llm_pipeline/ui/frontend/src/api/evals.ts` — variant hooks

### Phase 5: Frontend — Comparison View

**Run history updates:**
- Filter runs by variant
- Run rows show variant name badge
- "Compare" button: select two runs (different variants) → comparison view

**Comparison page** (`evals.$datasetId.compare.tsx`):
- Header: Variant A name vs Variant B name
- Delta diff panel: what changed between A and B (model, prompts, fields)
- Results grid: per-case, side-by-side pass/fail for each variant
- Aggregate: pass rate A vs B, per-evaluator breakdown
- "Accept Variant B" button (if B outperforms)

**Files:**
- `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.compare.tsx` — comparison view
- Updated run history with variant filtering + compare selection

### Phase 6: Accept Changes Workflow

**"Accept Changes" applies a variant's delta to production:**

**Model override:**
- Upsert `StepModelConfig` row in prod DB for the target step

**Prompt changes:**
- Update `Prompt.content` in prod DB for the target prompt keys
- Trigger YAML writeback to `llm-pipeline-prompts/` directory

**Instructions field changes:**
- Read production instructions .py file
- Apply AST transforms: add/remove/modify class fields
- Write back (reuse `creator/integrator.py` AST modification patterns)
- This is the hardest part — modifying Python source files safely

**Backend endpoint:**
- `POST /evals/{dataset_id}/variants/{variant_id}/accept`
- Returns summary of what was applied
- Requires confirmation (UI shows preview of changes before applying)

**Files:**
- `llm_pipeline/evals/accept.py` — new, accept workflow logic
- `llm_pipeline/ui/routes/evals.py` — accept endpoint
- Frontend confirmation dialog

## Dependencies Between Phases

```
Phase 1 (data model)
    └── Phase 2 (runner) ──→ Phase 3 (routes) ──→ Phase 4 (variant UI)
                                                        └── Phase 5 (comparison)
                                                              └── Phase 6 (accept)
```

Phases 1-3 are backend-only, can be tested via API. Phase 4-5 are frontend. Phase 6 is the "close the loop" feature.

## Risks

- **create_model() limitations**: dynamically created models can't be imported by name, may cause issues with pydantic-ai agent output_type validation. Needs testing.
- **AST modification for accept**: modifying Python source is fragile. The creator's integrator does this but for new files, not existing ones. Modifying existing class fields is harder.
- **Prompt versioning**: accepting prompt changes overwrites production. No built-in rollback beyond git. Could add a "previous version" snapshot.
- **Instructions schema compatibility**: if a variant removes a field that `process_instructions()` references, the step will crash. Need validation before accept.

## Out of Scope (v3+)

- Step logic changes (prepare_calls, process_instructions method overrides)
- Multi-step context seeding for isolated step evals
- Auto-generated variants (LLM suggests prompt improvements based on failing cases)
- A/B rollout (run variant in production on % of traffic)
- Eval scheduling (run nightly against latest prompt versions)
