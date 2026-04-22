# Step 2: Backend Comparison Logic Research

## 1. Current State

### Models (llm_pipeline/evals/models.py)

**EvaluationRun** snapshot fields (added in versioning-snapshots branch):
- `case_versions: Optional[dict]` — `{str(case.id): case.version}` e.g. `{"42": "1.0", "43": "1.2"}`
- `prompt_versions: Optional[dict]` — nested `{prompt_key: {prompt_type: version}}`
- `model_snapshot: Optional[dict]` — `{step_name: model_string}`
- `instructions_schema_snapshot: Optional[dict]` — JSON schema of instructions class
- `variant_id`, `delta_snapshot` — variant tracking (pre-existing)

**EvaluationCaseResult** fields:
- `case_id: int` (FK to eval_cases.id)
- `case_name: str` (denormalized, stable across versions)
- `passed: bool`, `evaluator_scores: dict`, `output_data: Optional[dict]`, `error_message: Optional[str]`

**EvaluationCase** versioning fields (added in versioning-snapshots):
- `version: str` (default "1.0"), `is_active: bool`, `is_latest: bool`
- Partial unique index on (dataset_id, name) WHERE is_active=1 AND is_latest=1
- Index on (dataset_id, name, version) for historical lookups

### Runner (llm_pipeline/evals/runner.py)

**`_build_run_snapshot`** (line 612):
- `case_versions` built as `{str(c.id): c.version for c in cases}` — key is case DB id, not case name
- Only active+latest cases included (filtered at query time)
- For step targets: resolves prompt keys via auto-discovery, fetches Prompt rows for versions
- For pipeline targets: walks all steps across all strategies

**`run_dataset`** flow:
- Loads active+latest cases, optional variant
- Calls `_build_run_snapshot` for all snapshot dicts
- Creates EvaluationRun row with snapshots
- Builds pydantic-evals Dataset, runs evaluate_sync
- Links results via `name_to_id = {cr["name"]: cr["id"] for cr in case_rows}`
- CaseResult gets both `case_id` (from name_to_id lookup) and `case_name` (from pydantic-evals result name)

### Routes (llm_pipeline/ui/routes/evals.py)

**RunListItem** (Pydantic response model, line 110-125): Includes all snapshot fields.

**RunDetail** (line 132-133): Extends RunListItem, adds `case_results: List[CaseResultItem]`.

**GET /{dataset_id}/runs/{run_id}** (line 1004): Validates `run.dataset_id == dataset_id`. Returns RunDetail with all case_results ordered by id.

**GET /{dataset_id}/runs** (line 967): Returns RunListItem[] with all snapshot fields.

**No dedicated comparison endpoint exists.** Frontend fetches two RunDetail objects and computes everything client-side.

**Step-target-only endpoints:**
- `GET /{dataset_id}/prod-prompts` — resolved prod prompts for variant editor + compare delta summary
- `GET /{dataset_id}/prod-model` — resolved prod model

### Frontend Comparison (compare.tsx)

**Case matching strategy** (line 1366-1374): Builds `Map<string, CaseResultItem>` keyed by `case_name` from both runs' `case_results`. Unions keys via `new Set([...baseMap.keys(), ...varMap.keys()])`. Pure client-side, no version awareness.

**Current URL structure**: `/evals/$datasetId/compare?baseRunId=X&variantRunId=Y` — scoped to single dataset.

**Labels**: Uses "Baseline" vs "Variant" terminology. Compare page assumes variant run has delta_snapshot.

## 2. Data Model Implications

### case_versions Keying Problem

`case_versions` uses `str(case.id)` as key. When comparing two runs:
- Same case_name may have different case.id values if versioned between runs
- To derive case_name -> version for comparison, must join: `case_versions[str(case_result.case_id)]` via `case_result.case_name`
- This is achievable client-side since RunDetail includes both case_results (with case_id + case_name) and case_versions

**Derivation path**: For each case_result in a run:
```
case_name = case_result.case_name
case_id = case_result.case_id  # note: not currently in CaseResultItem response!
version = run.case_versions[str(case_id)]
```

### CaseResultItem Missing case_id

**Critical gap**: `CaseResultItem` Pydantic response model (line 101-107) does NOT expose `case_id`. The DB model `EvaluationCaseResult` has it, but the route serialization drops it. Without `case_id` in the response, client cannot look up the version from `case_versions`.

**Fix needed**: Add `case_id: int` to `CaseResultItem` response model.

### Frontend TS Types Stale

`RunListItem` in `evals.ts` (line 44-57) is missing: `case_versions`, `prompt_versions`, `model_snapshot`, `instructions_schema_snapshot`. Only has `delta_snapshot`. The backend Pydantic model includes all of these. Frontend types need sync.

### Legacy Runs (case_versions=null)

Runs created before versioning-snapshots have `case_versions=null`. Strategy: treat all cases as "version unknown" — matchable by case_name but version comparison yields "unknown" bucket instead of matched/drifted.

## 3. Case Matching Strategy for Version Buckets

Given two runs A and B with their case_results and case_versions:

1. Build `case_name -> version` map for each run:
   - For each `case_result` in run: `name_to_version[case_result.case_name] = run.case_versions[str(case_result.case_id)]`
   - Requires case_id in CaseResultItem (see gap above)

2. Bucket classification:
   - **matched**: case_name in both runs AND versions equal (or both null/missing)
   - **drifted**: case_name in both runs AND versions differ
   - **unmatched**: case_name in only one run (added/removed between runs)
   - **unknown**: case_name in both runs BUT one or both runs have null case_versions (legacy)

3. Scoped aggregates: pass rate / score averages computed per bucket.

### Alternative: Add case_name-keyed version dict

Instead of fixing client-side derivation, runner could store a parallel `case_name_versions: {case_name: version}` dict alongside `case_versions`. Simpler for comparison but adds redundancy. Lower priority — fixing CaseResultItem to include case_id is cleaner.

## 4. Endpoint Design Options

### Option A: Keep Client-Side (Recommended for v1)

- Add `case_id` to CaseResultItem response
- Sync frontend TS types with new snapshot fields
- Client builds version maps and buckets from two RunDetail fetches
- Pros: No new endpoints, minimal backend change, all logic in existing compare page
- Cons: Repeated computation on each page load, can't aggregate across many runs server-side

### Option B: Backend Comparison Endpoint

```
GET /evals/compare?run_a={id}&run_b={id}
```

- Accepts two run IDs (no dataset_id scoping — enables cross-dataset)
- Returns pre-computed: matched/drifted/unmatched case pairs, per-bucket aggregates, version diffs
- Pros: Single fetch, server-computed buckets, enables cross-dataset
- Cons: New endpoint + response model, more backend code, duplicates logic that frontend already handles

### Option C: Hybrid — Enhance RunDetail, Client Computes

- Add `case_name_versions: dict` to RunDetail (redundant but convenient)
- Client computes buckets from two RunDetail fetches using case_name_versions directly
- No derivation through case_id needed
- Pros: Simple client logic, backward compatible
- Cons: Redundant data in run response

## 5. Cross-Dataset Comparison

**Current constraint**: All run endpoints scoped by dataset_id. `GET /{dataset_id}/runs/{run_id}` validates `run.dataset_id == dataset_id`.

**For cross-dataset support**:
- Need unscoped run fetch: `GET /evals/runs/{run_id}` (no dataset_id in path)
- Case matching would be by case_name only — same logical case may exist in different datasets
- prod-prompts/prod-model endpoints would need per-run resolution (each run's dataset may target different steps)
- Significant route + UI changes

**Recommendation**: Defer cross-dataset to a future iteration. Focus on same-dataset any-two-runs comparison first.

## 6. Summary of Required Changes (Backend)

### Minimal (Option A):
1. Add `case_id: int` to `CaseResultItem` Pydantic response model in routes/evals.py
2. Sync frontend TS types: add missing snapshot fields to RunListItem/RunDetail

### Recommended additions:
3. Add `case_name_versions: Optional[dict]` field to EvaluationRun model (runner stores `{case_name: version}`)
4. Populate in `_build_run_snapshot` alongside existing `case_versions`
5. Expose in RunListItem/RunDetail Pydantic models

### Deferred:
- Backend comparison endpoint (Option B) — only if client-side performance becomes an issue
- Cross-dataset comparison — significant scope expansion
- Unscoped run fetch endpoint
