# Step 2 — Runtime Paths & YAML Sync Research

Map of every runtime code path touching `Prompt` and `EvaluationCase`, the
`EvaluationRun` snapshot-population site, and the bidirectional YAML sync
patterns (prompt template + dataset extension).

All line numbers below are absolute against the current `dev`-derived
branch tree.

---

## 1. Prompt read-site inventory

| # | File:Line | Call shape | Needs `is_latest` filter? | Reason |
|---|-----------|-----------|---------------------------|--------|
| 1 | `llm_pipeline/prompts/resolver.py:53-58` (`_lookup_prompt_key`) | `select(Prompt).where(prompt_key==, prompt_type==, is_active==True).first()` | **YES** | Runtime tier-3 auto-discovery. Must return the one active latest row. Add `is_latest==True`. |
| 2 | `llm_pipeline/prompts/service.py:24-37` (`PromptService.get_prompt`) | `select(...).where(prompt_key==, prompt_type==, is_active==True).first()` | **YES** | Primary runtime prompt fetch. Add `is_latest==True`. |
| 3 | `llm_pipeline/prompts/service.py:80-84` (`prompt_exists`) | existence check, `is_active==True` | **YES** | Consumer uses result to decide availability — must check the live row. |
| 4 | `llm_pipeline/pipeline.py:1281` (`_find_cached_state`) | `select(Prompt).where(prompt_key==).first()` → `.version` used in cache key | **YES** | Must read latest version to cache-key against the actual prompt in use. Add `is_active==True AND is_latest==True`. |
| 5 | `llm_pipeline/pipeline.py:1368` (`_save_step_state`) | `select(Prompt).where(prompt_key==).first()` → `.version` stored in `PipelineStepState` | **YES** | Same reason — persisted version must be the live one. |
| 6 | `llm_pipeline/introspection.py:310-313` (`enrich_with_prompt_readiness`) | `select(key, type).where(key.in_(...), is_active==True)` | **YES** | Readiness flag must reflect live-row existence. |
| 7 | `llm_pipeline/ui/routes/editor.py:267-270` (compile Pass 5) | `select(key).where(key.in_(...), is_active.is_(True))` | **YES** | Compile-time presence check mirrors runtime. Add `is_latest==True`. |
| 8 | `llm_pipeline/ui/routes/evals.py:545-551` (`get_dataset_prod_prompts._fetch`) | `select(Prompt).where(prompt_key==, prompt_type==).first()` | **YES** | Surfaces prod prompt to variant editor. Needs live row — add `is_active==True AND is_latest==True`. |
| 9 | `llm_pipeline/ui/routes/pipelines.py:228` (`get_step_prompts`) | `select(Prompt).where(prompt_key.in_(...))` | **YES** | Lists step prompts for UI. Add both filters. |
| 10 | `llm_pipeline/ui/routes/prompts.py:169-177` (list endpoint) | filtered `select(Prompt)` with optional `is_active` param | **NO (partial)** | Admin browsing. Must stay able to view history. Default filter becomes `is_latest==True` but query param can override. |
| 11 | `llm_pipeline/ui/routes/prompts.py:196-200` (detail endpoint) | `select(Prompt).where(prompt_key==).order_by(prompt_type)` | **NO** | Grouped detail shows all variants; extension: returns history grouped by `(prompt_key, prompt_type)`. New param `version` selects a specific row. |
| 12 | `llm_pipeline/ui/routes/prompts.py:267-271` (PUT lookup) | `select(Prompt).where(prompt_key==, prompt_type==).first()` | **YES (read-side)** | Update path must read the latest row before branching to insert new version (see write-sites #W2). |
| 13 | `llm_pipeline/ui/routes/prompts.py:335-339` (DELETE lookup) | same shape | **YES** | Must deactivate only the latest row; history stays as-is. |
| 14 | `llm_pipeline/ui/routes/prompts.py:355-359` (variable-schema lookup) | same shape | **YES** | Returns merged code+DB schema to the UI. |
| 15 | `llm_pipeline/prompts/yaml_sync.py:171-176` (`sync_yaml_to_db` existing check) | `select(Prompt).where(prompt_key==, prompt_type==).first()` | **Replaced** | Rewrites to "fetch latest by key+type" helper (§9). Becomes ordered-by-version query. |
| 16 | `llm_pipeline/sandbox.py:53` (seed) | `src.exec(select(Prompt)).all()` | **NO (conditional)** | Sandbox seeding. Copies **only** `is_latest==True AND is_active==True` rows to keep sandbox minimal. History is not reproduced. |
| 17 | `llm_pipeline/ui/app.py:180-181` (`_sync_variable_definitions`) | `select(Prompt).where(variable_definitions.isnot(None))` | **YES** | Registry rebuild must only consume live rows — otherwise older `variable_definitions` would clobber the live one. |
| 18 | `llm_pipeline/evals/runner.py:626-632, 654-660` (`_apply_variant_to_sandbox`) | `select(Prompt).where(prompt_key==, prompt_type==).first()` on sandbox engine | **YES** | Sandbox was seeded with latest-only (#16), so the filter is naturally satisfied; still add explicit `is_latest==True` for defence-in-depth. |
| 19 | `llm_pipeline/creator/prompts.py:357-362` (`_seed_prompts`) | `select(...).first()` | **YES** | Upsert path for creator-generated prompts. Becomes "fetch latest" + version-aware insert. |
| 20 | `llm_pipeline/creator/integrator.py:205-209` (`_insert_prompts`) | `select(...).first()` | **YES** | Idempotent insert; should skip if any version exists, or become proper versioned insert. |

**Summary:** 20 read-sites. 17 become `is_active==True AND is_latest==True`.
3 intentionally read history (list/detail admin endpoints, sandbox seed
selective copy).

---

## 2. Prompt write-site inventory

| # | File:Line | Write shape | Becomes "new version + flip"? |
|---|-----------|-------------|-------------------------------|
| W1 | `llm_pipeline/ui/routes/prompts.py:231-247` (`create_prompt`) | `session.add(Prompt(**body))` → commit | **New-path**: INSERT as `(version=body.version, is_latest=True)`. First row for key+type so no flip needed. Partial unique index enforces uniqueness. |
| W2 | `llm_pipeline/ui/routes/prompts.py:275-305` (`update_prompt`) | Mutates in place; auto-increments `version` via `_increment_version` | **YES — core site.** Replace in-place mutation with version-write helper: INSERT new row with incremented version + `is_latest=True`, flip prior latest's `is_latest=False`. Single transaction. `variable_definitions` sync and `rebuild_from_db` run against new row. Also triggers DB→YAML writeback (lines 311-323). |
| W3 | `llm_pipeline/ui/routes/prompts.py:328-346` (`delete_prompt`) | `prompt.is_active = False` on the fetched row | **Modified**: sets `is_active=False` on the latest row. `is_latest` stays True (soft-delete preserves identity — runtime filter `is_active AND is_latest` correctly excludes it). Alternative considered + rejected: flip `is_latest` off. Keeping both flags independent means undelete is trivial. |
| W4 | `llm_pipeline/prompts/yaml_sync.py:169-204` (`sync_yaml_to_db`) | INSERT when missing; UPDATE in place when `compare_versions(yaml, db) > 0` | **YES — core site.** New semantics per locked decision #5: YAML version > latest DB → INSERT new version row + flip (same helper as W2). Same/lower → no-op. No more in-place update. |
| W5 | `llm_pipeline/creator/prompts.py:363-369` (`_seed_prompts`) | INSERT when missing; in-place field assignment when content differs | **YES**: becomes INSERT-new-version + flip when content differs. Version must be provided by the seed data or computed via `_increment_version`. |
| W6 | `llm_pipeline/creator/integrator.py:211` (`_insert_prompts`) | `session.add(Prompt(**data))` | **New-path**: inherits version-write helper. Still idempotent: if a row exists, it must skip (integrator runs once per generation). |
| W7 | `llm_pipeline/sandbox.py:54-68` (sandbox seed) | `dst.add(Prompt(...))` copy with original `is_active`, `version` | **NO — copy-only.** No versioning; sandbox is in-memory ephemeral. Include `is_latest` column (copy through) so downstream `_apply_variant_to_sandbox` queries work without change. |
| W8 | `llm_pipeline/evals/runner.py:688-696` (`_apply_variant_to_sandbox` / StepModelConfig upsert — not Prompt, noted for completeness) | Not a Prompt write | — |
| W9 | `llm_pipeline/evals/runner.py:716-727` (`_merge_variant_defs_into_prompt`) | In-place mutation of a sandbox Prompt row | **NO — sandbox only.** Sandbox is in-memory, never versioned. Mutation stays in place. |

**Single helper (see §9):** W1, W2, W4, W5 all route through
`insert_new_prompt_version(session, row_data)`. Delete (W3) stays as
simple `is_active=False` on the latest row.

---

## 3. EvaluationCase read-site inventory

| # | File:Line | Call shape | Needs `is_latest` filter? | Reason |
|---|-----------|-----------|---------------------------|--------|
| C1 | `llm_pipeline/evals/runner.py:98-102` (run cases for execution) | `select(EvaluationCase).where(dataset_id==).order_by(id)` | **YES** | Runtime execution must only see live-latest cases. Add `is_active==True AND is_latest==True`. |
| C2 | `llm_pipeline/evals/yaml_sync.py:111-116` (sync existence check) | `select(...).where(dataset_id==, name==).first()` | **Replaced** | Rewrites to fetch latest by `(dataset_id, name)`; decide INSERT-new-version vs no-op. |
| C3 | `llm_pipeline/evals/yaml_sync.py:154-158` (writeback read) | `select(...).where(dataset_id==).order_by(id)` | **YES** | YAML writeback must export latest state only. Add both filters. |
| C4 | `llm_pipeline/ui/routes/evals.py:343-349` (case-count subquery in list) | `count(id).group_by(dataset_id)` | **YES** | Count should reflect live cases. Filter before group-by. |
| C5 | `llm_pipeline/ui/routes/evals.py:455-459` (get_dataset cases) | `select(EvaluationCase).where(dataset_id==).order_by(id)` | **YES** | Detail view — live cases only. History endpoint (new) serves retro viewing. |
| C6 | `llm_pipeline/ui/routes/evals.py:696-700` (update_dataset cases reload) | same shape | **YES** | Same. |
| C7 | `llm_pipeline/ui/routes/evals.py:751-753` (delete_dataset cascade) | `select(EvaluationCase).where(dataset_id==).all()` | **NO** | Delete cascade must hit every version row. Leave unfiltered. |
| C8 | `llm_pipeline/ui/routes/evals.py:817-821` (update_case lookup) | `select(...).where(id==, dataset_id==).first()` | **N/A (by id)** | Lookup-by-id always points at one row. Write path (§4) decides whether to version. |
| C9 | `llm_pipeline/ui/routes/evals.py:859-863` (delete_case lookup) | same | **N/A** | Soft-delete the specific row; if it's the latest, `is_active=False` logic applies. |

---

## 4. EvaluationCase write-site inventory

| # | File:Line | Write shape | Becomes "new version + flip"? |
|---|-----------|-------------|-------------------------------|
| CW1 | `llm_pipeline/ui/routes/evals.py:786-798` (`create_case`) | `session.add(EvaluationCase(**body))` | **New-path**: INSERT as `(version="1.0", is_latest=True, is_active=True)`. Partial unique index on `(dataset_id, name)` WHERE `is_latest` enforces single live head. |
| CW2 | `llm_pipeline/ui/routes/evals.py:809-841` (`update_case`) | In-place mutation of `name`, `inputs`, `expected_output` | **YES — core site.** Replace with version-write helper: INSERT new case row with bumped version + `is_latest=True`, flip prior latest `is_latest=False`. Triggers DB→YAML writeback for the parent dataset (new behaviour per locked decision #6). `metadata_` stays on the new row unchanged. |
| CW3 | `llm_pipeline/ui/routes/evals.py:852-875` (`delete_case`) | `db.delete(case)` — **hard** delete | **Modified**: becomes soft-delete. Set `is_active=False` on latest row (keeps history + compare-view audit intact). Triggers DB→YAML writeback. |
| CW4 | `llm_pipeline/ui/routes/evals.py:725-765` (`delete_dataset` cascade) | Hard delete runs/results/cases/variants/dataset | **NO** — dataset-level nuke remains hard delete. All versions of all cases go. |
| CW5 | `llm_pipeline/evals/yaml_sync.py:118-127` (`sync_evals_yaml_to_db` case insert) | INSERT when not-exists; no update path today | **YES — extended.** New semantics per decision #5 mirroring prompts: if YAML version > latest DB version → INSERT new version row + flip. Same/lower → no-op. Today's code skips when any row exists (no version tracking). |

**Single helper (see §9):** CW1, CW2, CW5 route through
`insert_new_case_version(session, row_data)`.

---

## 5. Prompt YAML sync walkthrough (template for datasets)

### Startup order (from `llm_pipeline/ui/app.py:382-404`)

1. `resolved_base` resolved from CLI flag → env var → `None` and applied
   via `set_auto_generate_base_path`.
2. Scan dirs assembled:
   - `pkg_prompts = llm_pipeline/llm-pipeline-prompts/` (only if
     `demo_mode=True`).
   - `project_prompts = <cwd>/llm-pipeline-prompts/` (or
     `LLM_PIPELINE_PROMPTS_DIR` env override). Appended only if distinct
     from `pkg_prompts`.
3. `sync_yaml_to_db(engine, prompt_scan_dirs)` called when at least one
   dir is a directory.
4. `app.state.prompts_dir = project_prompts` — this is the **writeback
   target** used by the PUT route (single-dir policy; pkg-level YAML is
   never overwritten).
5. `_sync_variable_definitions(engine)` rebuilds the runtime `PromptVariables`
   classes from live DB rows.

### File layout convention

```
llm-pipeline-prompts/
  <prompt_key>.yaml              # one file per prompt_key, up to 2 variants inside
```

Inside each file:

```yaml
prompt_key: step_a
prompt_name: Step A
category: analysis
step_name: step_a
system:
  content: |
    ...
  description: ...
  version: "1.3"
  variable_definitions: {...}
user:
  content: |
    ...
  version: "1.2"
  variable_definitions: {...}
```

Shared top-level fields (`prompt_key`, `prompt_name`, `category`,
`step_name`) + per-variant sections (`system`, `user`). Parser at
`yaml_sync.py:68-122` emits **one dict per variant** (flattened) for the
DB layer.

### `compare_versions` usage

Defined at `yaml_sync.py:39-58`. Dotted numeric comparison, zero-padded
to the longer side. Called exactly at `yaml_sync.py:186` today:

```python
cmp = compare_versions(v["version"], existing.version)
if cmp > 0:  # YAML newer — update in place
    ...
```

**Post-decision-5 change:** the `cmp > 0` branch becomes INSERT-new-row
(via the §9 helper) instead of in-place mutation. Same/lower stays no-op.
`compare_versions` itself is unchanged (locked decision #1).

### DB→YAML writeback trigger

`llm_pipeline/ui/routes/prompts.py:311-323`. Fires inside PUT after DB
commit+refresh. Reads `request.app.state.prompts_dir`; no-op if unset.
Calls `write_prompt_to_yaml(prompts_dir, key, type, {...fields})`.

`write_prompt_to_yaml` (`yaml_sync.py:225-275`):
- `mkdir(parents=True, exist_ok=True)`.
- Opens `<key>.yaml` if present, seeds `{prompt_key: key}` otherwise.
- Overlays shared top-level fields (guards on truthiness for
  `prompt_name`).
- Loads or creates the `<prompt_type>` section, overlays its per-variant
  fields (including `_to_literal` wrapping for multi-line `content`).
- `yaml.dump(...)` direct write — **not atomic** (no temp-file + rename).

### Known gap

`write_prompt_to_yaml` is non-atomic (simple overwrite). Dataset
writeback (`evals/yaml_sync.py:184-202`) already uses the atomic
temp-file + `Path.replace` pattern. Prompts should adopt the same
pattern when version rows start flowing through — partial writes during
concurrent edits would be worse now that multiple version rows share a
file.

---

## 6. Dataset YAML sync design

Dataset YAML sync exists today (`llm_pipeline/evals/yaml_sync.py`) but
has:
- No version tracking (insert-if-not-exists only).
- No DB→YAML writeback trigger from UI CRUD.

Per locked decisions #5 and #6, we replicate the prompt pattern.

### File layout — one YAML per dataset (decided)

```
llm-pipeline-evals/
  <dataset_name>.yaml
```

Already the convention enforced by `write_dataset_to_yaml`
(`evals/yaml_sync.py:182`: `target_dir / f"{dataset.name}.yaml"`).

Per-case files were considered and rejected:
- Dataset metadata (`target_type`, `target_name`, `description`) has no
  natural home in per-case files.
- Directory enumeration cost grows with case count (thousands of cases
  → thousands of filesystem entries per dataset). One-file-per-dataset
  keeps filesystem fanout proportional to dataset count.
- Writeback atomicity is simpler: one temp-file + rename per dataset.

### Inside a dataset YAML (extended from current format)

```yaml
name: step_a_cases
target_type: step
target_name: step_a
description: ...
cases:
  - name: happy_path
    version: "1.2"          # NEW — per-case version
    inputs: {...}
    expected_output: {...}
    metadata: {...}          # metadata is versioned alongside content
```

Top-level `version` for the dataset is **not** introduced in this scope.
Locked decision #2 scopes versioning to `(dataset_id, name, version)`
at the case level. A future dataset-level version would compose but is
not needed now.

### Startup ingestion flow (replicates prompts)

1. `llm_pipeline/ui/app.py:406-424` — identical dual-dir assembly for
   `pkg_evals` + `project_evals`. Already in place.
2. `sync_evals_yaml_to_db(engine, eval_scan_dirs)` — existing entry
   point. Rewritten internally:

   ```python
   for case in yaml_cases:
       latest = fetch_latest_case(session, dataset_id, case["name"])
       yaml_version = str(case.get("version", "1.0"))
       if latest is None:
           # INSERT first version
           session.add(EvaluationCase(
               dataset_id=dataset_id, name=case["name"],
               version=yaml_version, is_latest=True, is_active=True,
               ...
           ))
       elif compare_versions(yaml_version, latest.version) > 0:
           insert_new_case_version(session, dataset_id, case["name"], yaml_version, {...})
       # same/lower → no-op
   ```

3. `app.state.evals_dir = project_evals` — already set
   (`app.py:424`). Becomes the writeback target.

### DB→YAML writeback trigger (new)

Added to three CRUD endpoints:
- `POST /evals/{dataset_id}/cases` (CW1)
- `PUT /evals/{dataset_id}/cases/{case_id}` (CW2)
- `DELETE /evals/{dataset_id}/cases/{case_id}` (CW3)

Plus the dataset-level mutations (`PUT /evals/{dataset_id}`) when name/
description change — so the YAML header stays in sync.

Writeback calls `write_dataset_to_yaml(engine, dataset_id, evals_dir)`
(existing function, atomic already). No changes to the writer itself;
the **caller** now exists. The writer already serialises **latest-only**
content (per §4 C3), so no query changes needed there.

### `compare_versions` reuse

Shared from `llm_pipeline/prompts/yaml_sync.py`. No duplication. Either
import directly or move to `llm_pipeline/utils/versioning.py` if the
prompt module-boundary feels awkward. Recommendation: move it. It's
pure, reusable, and neither `prompts` nor `evals` owns semver-lite
ordering.

---

## 7. EvaluationRun creation site

**Exact location:** `llm_pipeline/evals/runner.py:108-117`, inside
`EvalRunner.run_dataset` (method starts at line 53). First DB session
scope loads `EvaluationDataset`, `EvaluationVariant`, `EvaluationCase`
rows, then constructs and commits the run row:

```python
run = EvaluationRun(
    dataset_id=dataset_id,
    status="running",
    total_cases=len(cases),
    variant_id=variant_id,
    delta_snapshot=variant_snapshot,
)
session.add(run)
session.commit()
session.refresh(run)
run_id = run.id
```

All four snapshot fields are populated **here**, within the same
transaction, so there is no window where a run exists without its
snapshot.

### Per-field population plan

| Field | (a) Data in scope? | (b) New lookups needed? | (c) When to populate |
|-------|-------------------|-------------------------|----------------------|
| `case_versions: dict[str, str]` (case_id→version per decision #7; using case name is locked to "name" per decision #2 but case_id is the FK in CaseResult — use **case_id** as key) | **YES** — `cases` list already loaded at line 98-102 | None | Inline dict comp against `cases`: `{str(c.id): c.version for c in cases}`. Populated before `EvaluationRun(...)` call. |
| `prompt_versions: dict` (structure per step-1; suggested shape: `{"system": {"key": "...", "version": "..."}, "user": {...}}` for step-targets; pipeline-targets get a list keyed by step_name) | **PARTIAL** — step_def is resolved lazily inside `_resolve_task` at line 137-142. Needs ordering change: must resolve step_def and its prompt keys BEFORE creating run row. | **YES**: walk registered pipelines for the step (same path as `_find_step_def` lines 416-443) + call `resolve_with_auto_discovery(step_def, session, strategy_name)` + fetch `Prompt.version` for each non-None key. | Populated before `EvaluationRun(...)`. Requires a pre-pass that mirrors `_find_step_def` but also returns prompt rows. For pipeline-target, iterate every step in registered factory. |
| `model_snapshot: str` (the resolved model string) | **NO** — currently resolved inside `_resolve_step_task` (line 377-397) AFTER run row is created. | **YES**: `resolve_model_with_fallbacks` must move into the pre-commit pre-pass. `variant_delta["model"]` and `model` kwarg layer on top — exact same precedence chain as today. | Populated before `EvaluationRun(...)`. For pipeline-target, snapshot is the outer-request model (kwarg or pipeline default) — step-level overrides are captured per-step in the pipeline snapshot shape. |
| `instructions_schema_snapshot: dict` | **NO** — step_def lookup happens lazily same as above; `step_def.instructions` + `apply_instruction_delta` produce the class. | **YES**: pre-pass resolves step_def, applies `instructions_delta` if present (mirrors runner line 362-371), then `modified_cls.model_json_schema()`. | Populated before `EvaluationRun(...)`. For pipeline-target, emit `{step_name: schema}` dict. |

### Refactor shape

Extract a **`_build_run_snapshot(...)`** helper that returns
`(case_versions, prompt_versions, model_snapshot, instructions_schema_snapshot)`
given `(dataset, cases, variant_delta, model_kwarg)`. Called from
`run_dataset` right before the `EvaluationRun(...)` construction (line
108). Moves the current lazy resolution earlier but doesn't change
precedence or behaviour.

The existing `_resolve_task` path at line 137 still runs — it now
reads the already-resolved artefacts (either by re-lookup or by
threading them through). Cleanest: `_build_run_snapshot` returns the
resolved `step_def` too, and `_resolve_task` accepts it as an optional
pre-resolved input to skip its own lookup.

### Handling legacy rows (decision #10)

Old `EvaluationRun` rows where `case_versions IS NULL`: compare view
skips mismatch check. No backfill. New code paths always populate.

---

## 8. Compare view mismatch detection

### Data flow

**Backend (already wired):** `GET /evals/{dataset_id}/runs/{run_id}`
(`llm_pipeline/ui/routes/evals.py:916-961`) returns `RunDetail`
including `delta_snapshot`. The snapshot fields from §7 need to be
added to the `RunListItem`/`RunDetail` pydantic models (lines 109-128)
and threaded through:

```python
# RunListItem additions
case_versions: Optional[dict] = None
prompt_versions: Optional[dict] = None
model_snapshot: Optional[str] = None
instructions_schema_snapshot: Optional[dict] = None
```

Both the list endpoint (lines 883-913) and the detail endpoint (lines
916-961) already enumerate every `EvaluationRun` field they surface;
add the four fields to each response model construction site.

**Frontend fetch:** `useEvalRun(datasetId, runId)` hook
(`llm_pipeline/ui/frontend/src/api/evals.ts`) consumed at
`evals.$datasetId.compare.tsx:1325-1334` provides both `baseRun` and
`variantRun` (both are `RunDetail`). The two snapshots are already in
scope.

### Mismatch detection

Simple per-case compare between `baseRun.case_versions` and
`variantRun.case_versions`:

```typescript
// pseudocode in compare.tsx
const mismatchedCases = new Set<string>()
if (baseRun.case_versions && variantRun.case_versions) {
  const baseMap = baseRun.case_versions    // {case_id: version}
  const varMap  = variantRun.case_versions
  for (const [cid, v] of Object.entries(baseMap)) {
    if (varMap[cid] && varMap[cid] !== v) mismatchedCases.add(cid)
  }
}
```

Either `case_versions` being null (legacy run) → skip entirely per
decision #10.

### Badge render location

`llm_pipeline/ui/frontend/src/routes/evals.$datasetId.compare.tsx`
already renders per-case rows via the `CaseRow` component
(lines 1255-1314). The `caseByName` map (line 1357-1361) keys by
case name; to cross-reference to `case_id` we use
`datasetQ.data.cases[i].id`. Add a new column (or a marker on the
delta column) that renders a `Badge variant="outline"` reading
"version mismatch" when `mismatchedCases.has(String(caseDef.id))`.

Separate **run-level** badges on the Delta summary card (line
1735-1764) surface when:
- `baseRun.model_snapshot !== variantRun.model_snapshot`
- `baseRun.prompt_versions` differs from `variantRun.prompt_versions`
  (JSON-equal compare, shallow)
- `baseRun.instructions_schema_snapshot !== variantRun.instructions_schema_snapshot`
  (JSON-equal compare)

These are passive surface indicators — they don't block compare; they
just warn the reviewer.

Frontend finalises the exact DOM shape.

---

## 9. Helper function signatures (proposal)

### Version-write helper (prompt)

```python
# llm_pipeline/prompts/versioning.py  (new file)
def insert_new_prompt_version(
    session: Session,
    prompt_key: str,
    prompt_type: str,
    version: str,
    payload: dict,                    # fields going onto the new row
    *,
    flip_prior_latest: bool = True,
) -> Prompt:
    """Insert a new Prompt version row and flip prior latest.

    Caller is responsible for transaction boundary. Does not commit.
    Partial unique index guarantees at-most-one (prompt_key, prompt_type,
    is_latest=True) row at commit time.
    """
```

### Latest-read helper (prompt)

```python
def fetch_latest_prompt(
    session: Session,
    prompt_key: str,
    prompt_type: str,
    *,
    include_inactive: bool = False,
) -> Optional[Prompt]:
    """Return the latest Prompt row for (key, type) or None.

    Default filters: is_latest=True AND is_active=True. Callers that need
    the latest soft-deleted row (e.g. undelete UI) pass
    include_inactive=True.
    """
```

### Version-write helper (case)

```python
# llm_pipeline/evals/versioning.py  (new file)
def insert_new_case_version(
    session: Session,
    dataset_id: int,
    name: str,
    version: str,
    payload: dict,                    # inputs, expected_output, metadata_
    *,
    flip_prior_latest: bool = True,
) -> EvaluationCase:
    """Symmetric to insert_new_prompt_version. Scope key is
    (dataset_id, name). Partial unique index enforces single is_latest."""
```

### Latest-read helper (case)

```python
def fetch_latest_case(
    session: Session,
    dataset_id: int,
    name: str,
    *,
    include_inactive: bool = False,
) -> Optional[EvaluationCase]:
    """Return the latest EvaluationCase for (dataset_id, name) or None."""
```

### Shared version comparator

```python
# llm_pipeline/utils/versioning.py  (move from prompts/yaml_sync.py)
def compare_versions(a: str, b: str) -> int:
    """Dot-separated numeric comparator. -1/0/+1."""
```

Step 3 finalises these signatures.

---

## 10. Risks / open patterns

### R1. `EvaluationCaseResult.case_id` uniqueness under versioning

Currently `case_id` on a result row points at the case row used at run
time (decision #8 makes that explicit). If a case row is later soft-
deleted **and** hard-deleted via dataset cascade (CW4), historical
result rows will have dangling `case_id` FKs. SQLite does not enforce
FKs without `PRAGMA foreign_keys=ON`. Either:
- Enforce via pragma at init and add `ON DELETE CASCADE`, or
- Accept dangling IDs as a consequence of full dataset deletion (hard
  nuke == lose all history).

Step 3 must decide. Recommendation: dangling is acceptable because
dataset cascade already destroys runs too.

### R2. `compare_versions` on non-numeric version strings

`int(x)` in `compare_versions` throws on non-numeric segments (e.g.
`"1.0-rc1"`). Today the writer enforces numeric via `_increment_version`,
but YAML can carry anything. Either:
- Validate at YAML-parse time (reject non-numeric), or
- Upgrade to semver-aware comparator.

Recommendation: keep numeric-only per decision #1; add validation at
YAML ingest.

### R3. `write_prompt_to_yaml` non-atomic

Prompt writeback uses plain `open(...)` + `yaml.dump(...)`. Under
concurrent editors this can corrupt the file. Dataset writeback
already uses atomic temp-file + rename. Port the same pattern to
prompts when this task touches `yaml_sync.py`. Low cost, clear win.

### R4. `_sync_variable_definitions` iteration order (app.py:180-184)

If `rebuild_from_db` is called multiple times for the same
`(prompt_key, prompt_type)` with different `variable_definitions`, the
last write wins. Once history rows exist, we must filter to
`is_latest=True` — otherwise iteration order determines which
definition wins. Listed above as read-site #17.

### R5. Sandbox seed copies only latest (W7/#16)

`create_sandbox_engine` currently copies **every** Prompt row. Under
versioning, history rows bloat the sandbox DB and the existence/lookup
assumptions in `_apply_variant_to_sandbox` break (multiple rows per
key+type). Fix: filter `is_latest=True AND is_active=True` in the
copy query. Ripple effect: zero — sandbox only needs live config.

### R6. `get_prompt` detail endpoint (`prompts.py:196-207`) all-history

Already intended to show every variant. Under versioning it returns the
cross-product of version rows × variant types. Frontend must render
grouped by `(prompt_type, version)`. Add a new `GET /prompts/{key}/{type}/versions`
for a cleaner history slice, keep the existing endpoint as-is for back-
compat with the current PromptViewer component.

### R7. Creator-module writes (W5, W6)

`llm_pipeline/creator/` generates prompts via LLM and persists them.
Under versioning, re-running a creator generation needs a policy:
- Bump version each time? Noisy.
- Skip if content hash matches latest? Aligns with today's
  `_content_hash` branch in `_seed_prompts`.
- Bump only when content actually changes.

Recommendation: the creator path computes content-hash delta and only
calls `insert_new_prompt_version` when it changes. Otherwise no-op.

### R8. PUT-prompt auto-version-bump collides with YAML version wins

Today `update_prompt` at `prompts.py:301-302` calls `_increment_version`
when the caller doesn't pass a version. Then on next startup,
`sync_yaml_to_db` sees DB version > YAML version and… does nothing (no
DB→YAML path on startup). The PUT-side writeback at `prompts.py:311-323`
handles it. But this implicit coupling needs an invariant: **DB→YAML
writeback must run in the same request as the DB write**, otherwise a
crash between them causes drift that the next startup sync will silently
ignore (YAML version < DB version → no-op). Already the case today via
the sequential PUT handler; document it in step 3.

### R9. Pipeline-target prompt_versions structure

Decision #7 says "structure per step-1 recommendation". Step 1's recommendation
for pipeline-target snapshots was `{step_name: {"system": {"key","version"},
"user": {...}}}`. For step-target, a flat `{"system": {...}, "user": {...}}`.
Helper shape must surface which case it is — suggest a `target_type` tag
on the top-level snapshot dict: `{"target_type": "step", "prompts": {...}}`
vs `{"target_type": "pipeline", "prompts": {step_name: {...}}}`. Mirrors
existing `EvaluationDataset.target_type`. Step 3 finalises.

---
