# Validated Research — Versioning + Run Snapshots

Implementation-ready consolidation of `research/step-1`, `research/step-2`, `research/step-3-pythonsqlmodel-versioning-research.md`. Supersedes the three research docs for implementation purposes; they remain as historical reference.

All contradictions resolved by CEO answers (see §Q&A Record at the end). Planning agent consumes this doc directly.

---

## Executive Summary

Three schema-level additions: `is_latest` on `Prompt`, `(version, is_active, is_latest, updated_at)` on `EvaluationCase`, and four snapshot JSON columns on `EvaluationRun`. Versioning is enforced by a partial unique index on each (`WHERE is_active AND is_latest`). Writes go through a single generic helper `save_new_version` in `llm_pipeline/db/versioning.py`. Reads add an `is_latest == True` clause at 17 sites across prompts + eval runner + UI. YAML sync for datasets mirrors the prompt pattern (startup read, PUT-side writeback, `compare_versions` wins). `EvaluationRun` is populated with a single `_build_run_snapshot(...)` helper inside the same transaction as run creation.

---

## 1. Locked Decisions (full list)

### 1.1 Original PM-locked decisions (11)

1. **Version comparator.** `compare_versions` semantics stay: dotted numeric, zero-padded. No semver.
2. **Versioning key scope.** Prompt = `(prompt_key, prompt_type, version)`. EvalCase = `(dataset_id, name, version)`.
3. **Soft-delete.** `is_active=False` is the flag. No `deleted_at` column.
4. **Sandbox same schema.** Sandbox DB uses the same migration path.
5. **YAML > DB semantics.** YAML version `>` DB latest → INSERT new version row + flip prior latest. Same/lower → no-op.
6. **DB→YAML writeback.** Fires from CRUD PUT/POST/DELETE handlers after commit.
7. **Run snapshot columns.** `case_versions`, `prompt_versions`, `model_snapshot`, `instructions_schema_snapshot` on `EvaluationRun`.
8. **`EvaluationCaseResult.case_id` preservation.** Result rows point at the exact case row used at run time. FK unchanged.
9. **Reset-on-recreate.** After soft-delete then recreate, new row starts at `version="1.0"`.
10. **Legacy rows.** Compare view treats NULL snapshot as "pre-versioning" — skip mismatch detection.
11. **Hard delete stays hard at the dataset level.** `DELETE /evals/{dataset_id}` nukes runs/results/cases/variants/dataset including all version rows.

### 1.2 CEO answers applied (10)

| # | Question | Answer |
|---|----------|--------|
| A1 | `prompt_versions` shape | Nested `{"<prompt_key>": {"<prompt_type>": "<version>"}}`. Pipeline-target wraps in step_name: `{"<step_name>": {"<prompt_key>": {"<prompt_type>": "<version>"}}}`. No `"target_type"` tag inside JSON — runtime reads `EvaluationRun.*` / `EvaluationDataset.target_type`. |
| A2 | `model_snapshot` type | Dict/JSON. `{"<step_name>": "<model_id>"}`. Step-target = single-entry; pipeline-target = one entry per step. Migration row becomes `TEXT` (JSON-serialised). |
| A3 | Sandbox seed filter | Filter `is_latest=True AND is_active=True`. |
| A4 | Helper location | Single generic `llm_pipeline/db/versioning.py`. No per-entity wrappers. |
| A5 | `compare_versions` location | Move to `llm_pipeline/utils/versioning.py`. Both `llm_pipeline/prompts/yaml_sync.py` and `db/versioning.py` import from utils. |
| A6 | `EvaluationCase.updated_at` | ADD the column. `_MIGRATIONS` row: `("eval_cases", "updated_at", "TIMESTAMP")`. Soft-delete helper writes it. |
| A7 | `ix_prompts_active` | DROP it. Partial unique index supersedes. |
| A8 | YAML no-op logging | `logger.warning("YAML version %s <= DB latest %s for %s; skipping", ...)`. |
| A9 | Pipeline-target snapshot scope | IN SCOPE. `_build_run_snapshot` walks all steps of a pipeline-target. Keying: `prompt_versions` and `model_snapshot` by step_name for pipeline-target; flat (no step_name wrapper) for step-target. |
| A10 | `flip_prior_latest` kwarg | DROP. Helper always flips. |

---

## 2. Consolidated Schema

### 2.1 `Prompt` (`llm_pipeline/db/prompt.py`)

**Column add** (after existing `is_active`):
```python
is_latest: bool = Field(default=True, index=True)
```

**Unchanged:** `version: str = Field(default="1.0", max_length=20)`, `is_active: bool = Field(default=True)`.

**Constraint/Index drops:**
- DROP `UniqueConstraint('prompt_key', 'prompt_type', name='uq_prompts_key_type')` (Step 1 §1, Step 3 §1.1).
- DROP `Index("ix_prompts_active", "is_active")` (A7).

**Final `__table_args__`:**
```python
__table_args__ = (
    Index(
        "uq_prompts_active_latest",
        "prompt_key", "prompt_type",
        unique=True,
        sqlite_where=text("is_active = 1 AND is_latest = 1"),
        postgresql_where=text("is_active = true AND is_latest = true"),
    ),
    Index("ix_prompts_key_type_live",
          "prompt_key", "prompt_type", "is_active", "is_latest"),
    Index("ix_prompts_category_step", "category", "step_name"),
    Index("ix_prompts_key_type_version",
          "prompt_key", "prompt_type", "version"),
)
```

Imports: `from sqlalchemy import Index, text`. Remove `UniqueConstraint` import if no longer used.

### 2.2 `EvaluationCase` (`llm_pipeline/evals/models.py`)

**Column adds:**
```python
version: str = Field(default="1.0", max_length=20)
is_active: bool = Field(default=True)
is_latest: bool = Field(default=True, index=True)
updated_at: datetime = Field(default_factory=utc_now)   # NEW per A6
```

**Final `__table_args__`:**
```python
__table_args__ = (
    Index(
        "uq_eval_cases_active_latest",
        "dataset_id", "name",
        unique=True,
        sqlite_where=text("is_active = 1 AND is_latest = 1"),
        postgresql_where=text("is_active = true AND is_latest = true"),
    ),
    Index("ix_eval_cases_dataset", "dataset_id"),
    Index("ix_eval_cases_dataset_live",
          "dataset_id", "is_active", "is_latest"),
    Index("ix_eval_cases_dataset_name_version",
          "dataset_id", "name", "version"),
)
```

### 2.3 `EvaluationRun` snapshot columns (`llm_pipeline/evals/models.py`)

All four nullable, default NULL. Placed after the existing `delta_snapshot` column.

```python
case_versions: Optional[dict] = Field(default=None, sa_column=Column(JSON))
prompt_versions: Optional[dict] = Field(default=None, sa_column=Column(JSON))
model_snapshot: Optional[dict] = Field(default=None, sa_column=Column(JSON))   # dict per A2
instructions_schema_snapshot: Optional[dict] = Field(default=None, sa_column=Column(JSON))
```

Shapes (see §5 for details):
- `case_versions`: flat `{str(case.id): version}` in all targets.
- `prompt_versions`:
  - step-target: flat `{"<prompt_key>": {"<prompt_type>": "<version>"}}`
  - pipeline-target: nested `{"<step_name>": {"<prompt_key>": {"<prompt_type>": "<version>"}}}`
- `model_snapshot`: `{"<step_name>": "<model_id>"}` in both cases (single-entry for step-target).
- `instructions_schema_snapshot`:
  - step-target: `model_json_schema()` dict at top level.
  - pipeline-target: `{"<step_name>": <schema_dict>}`.

### 2.4 FK preservation

`EvaluationCaseResult.case_id → eval_cases.id` unchanged. Historical result rows resolve to the exact row used at run time (which may be non-latest post-bump). Append-mostly, no cascade-delete change.

---

## 3. Consolidated Migration

File: `llm_pipeline/db/__init__.py`

### 3.1 `_MIGRATIONS` additions

```python
("prompts", "is_latest", "INTEGER DEFAULT 1"),
("eval_cases", "version", "VARCHAR(20) DEFAULT '1.0'"),
("eval_cases", "is_active", "INTEGER DEFAULT 1"),
("eval_cases", "is_latest", "INTEGER DEFAULT 1"),
("eval_cases", "updated_at", "TIMESTAMP"),          # per A6
("eval_runs", "case_versions", "TEXT"),
("eval_runs", "prompt_versions", "TEXT"),
("eval_runs", "model_snapshot", "TEXT"),            # TEXT (JSON) per A2
("eval_runs", "instructions_schema_snapshot", "TEXT"),
```

`DEFAULT 1` backfills all existing rows — correct since every pre-migration row is the one and only live+latest.

### 3.2 `_migrate_partial_unique_indexes(engine)`

New function invoked from `init_pipeline_db` right after `_migrate_add_columns`. Raw DDL; idempotent via `IF NOT EXISTS`; dialect-aware.

```python
def _migrate_partial_unique_indexes(engine: Engine) -> None:
    """One-off: retire legacy unique, dedupe eval_cases, install partial
    uniques + supporting indexes. Idempotent."""
    is_sqlite = engine.url.drivername.startswith("sqlite")

    drops = [
        "DROP INDEX IF EXISTS uq_prompts_key_type",   # legacy unique
        "DROP INDEX IF EXISTS ix_prompts_active",     # per A7
    ]

    dedupe_sql = [
        # Keep newest by created_at (tiebreak id DESC); mark older duplicates
        # is_latest=0 so partial unique no longer collides. is_active kept as-is.
        """
        UPDATE eval_cases
           SET is_latest = 0
         WHERE id NOT IN (
               SELECT id FROM (
                   SELECT id,
                          ROW_NUMBER() OVER (
                              PARTITION BY dataset_id, name
                              ORDER BY created_at DESC, id DESC
                          ) AS rn
                     FROM eval_cases
               ) t
               WHERE rn = 1
         )
        """,
    ]

    if is_sqlite:
        creates = [
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_prompts_active_latest "
            "ON prompts (prompt_key, prompt_type) "
            "WHERE is_active = 1 AND is_latest = 1",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_cases_active_latest "
            "ON eval_cases (dataset_id, name) "
            "WHERE is_active = 1 AND is_latest = 1",
            "CREATE INDEX IF NOT EXISTS ix_prompts_key_type_live "
            "ON prompts (prompt_key, prompt_type, is_active, is_latest)",
            "CREATE INDEX IF NOT EXISTS ix_prompts_key_type_version "
            "ON prompts (prompt_key, prompt_type, version)",
            "CREATE INDEX IF NOT EXISTS ix_eval_cases_dataset_live "
            "ON eval_cases (dataset_id, is_active, is_latest)",
            "CREATE INDEX IF NOT EXISTS ix_eval_cases_dataset_name_version "
            "ON eval_cases (dataset_id, name, version)",
        ]
    else:
        creates = [
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_prompts_active_latest "
            "ON prompts (prompt_key, prompt_type) "
            "WHERE is_active = true AND is_latest = true",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_cases_active_latest "
            "ON eval_cases (dataset_id, name) "
            "WHERE is_active = true AND is_latest = true",
            "CREATE INDEX IF NOT EXISTS ix_prompts_key_type_live "
            "ON prompts (prompt_key, prompt_type, is_active, is_latest)",
            "CREATE INDEX IF NOT EXISTS ix_prompts_key_type_version "
            "ON prompts (prompt_key, prompt_type, version)",
            "CREATE INDEX IF NOT EXISTS ix_eval_cases_dataset_live "
            "ON eval_cases (dataset_id, is_active, is_latest)",
            "CREATE INDEX IF NOT EXISTS ix_eval_cases_dataset_name_version "
            "ON eval_cases (dataset_id, name, version)",
        ]

    with engine.connect() as conn:
        for stmt in drops:
            try: conn.execute(text(stmt))
            except OperationalError: pass
        for stmt in dedupe_sql:
            try: conn.execute(text(stmt))
            except OperationalError: pass  # eval_cases may not exist on fresh DB
        for stmt in creates:
            try: conn.execute(text(stmt))
            except OperationalError: pass
        conn.commit()
```

### 3.3 Call order in `init_pipeline_db`

```python
SQLModel.metadata.create_all(engine, tables=[...])   # existing
_migrate_add_columns(engine)                         # columns exist after this
_migrate_partial_unique_indexes(engine)              # NEW
add_missing_indexes(engine)                          # existing
```

Column creation must precede partial-unique-index creation (predicate columns must exist). Fresh DBs get declared indexes via `create_all`; upgrade path gets them via raw DDL — belt-and-braces, both idempotent.

---

## 4. Helper API

Module: **`llm_pipeline/db/versioning.py`** (NEW — single generic file, no per-entity wrappers).

Imports `compare_versions` from `llm_pipeline/utils/versioning.py` (moved there per A5). No cross-module dependency on `prompts/` or `evals/`.

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypeVar

from sqlmodel import Session, select

from llm_pipeline.utils.versioning import compare_versions

T = TypeVar("T")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _bump_minor(version: str) -> str:
    """'1.0' -> '1.1', '1.9' -> '1.10', '1' -> '1.1', '1.2.3' -> '1.2.4'.
    ValueError on non-numeric parts."""
    parts = version.split(".")
    if not parts or not all(p.isdigit() for p in parts):
        raise ValueError(f"Non-numeric version: {version!r}")
    if len(parts) == 1:
        return f"{parts[0]}.1"
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)


def save_new_version(
    session: Session,
    model_cls: type[T],
    key_filters: dict[str, Any],
    new_fields: dict[str, Any],
    version: str | None = None,
) -> T:
    """Insert new version row, always flipping any prior active-latest.

    1. Find active-latest row matching key_filters.
    2. If found: flip is_latest=False (updated_at=now); session.flush();
       auto-bump minor unless `version` is supplied; INSERT new row.
    3. If not found: INSERT fresh row at version="1.0" (or `version` if supplied).

    Helper flushes; caller commits. Forbids managed cols in new_fields
    (version, is_active, is_latest, created_at, updated_at).
    """
    forbidden = {"version", "is_active", "is_latest", "created_at", "updated_at"}
    if forbidden & new_fields.keys():
        raise ValueError(
            f"new_fields must not include versioning-managed columns: "
            f"{sorted(forbidden & new_fields.keys())}"
        )

    stmt = select(model_cls).where(
        model_cls.is_active == True,  # noqa: E712
        model_cls.is_latest == True,  # noqa: E712
    )
    for col, val in key_filters.items():
        stmt = stmt.where(getattr(model_cls, col) == val)
    prior = session.exec(stmt).first()

    now = _utc_now()
    if prior is None:
        new_version = version or "1.0"
    else:
        new_version = version or _bump_minor(prior.version)
        if compare_versions(new_version, prior.version) <= 0:
            raise ValueError(
                f"new version {new_version!r} is not greater than prior "
                f"{prior.version!r} for {model_cls.__name__} {key_filters}"
            )
        prior.is_latest = False
        prior.updated_at = now
        session.add(prior)
        session.flush()  # release the partial-unique slot before INSERT

    row_kwargs = {
        **key_filters,
        **new_fields,
        "version": new_version,
        "is_active": True,
        "is_latest": True,
        "created_at": now,
        "updated_at": now,
    }
    new_row = model_cls(**row_kwargs)
    session.add(new_row)
    session.flush()
    return new_row


def get_latest(
    session: Session,
    model_cls: type[T],
    **filters: Any,
) -> T | None:
    """Return active-latest row matching filters, or None."""
    stmt = select(model_cls).where(
        model_cls.is_active == True,  # noqa: E712
        model_cls.is_latest == True,  # noqa: E712
    )
    for col, val in filters.items():
        stmt = stmt.where(getattr(model_cls, col) == val)
    return session.exec(stmt).first()


def soft_delete_latest(
    session: Session,
    model_cls: type[T],
    **key_filters: Any,
) -> T | None:
    """Set is_active=False on current active-latest row; keep is_latest=True
    (so historical 'most recent' queries still resolve). Writes updated_at.
    Flushes. Returns the soft-deleted row, or None if no match.
    """
    row = get_latest(session, model_cls, **key_filters)
    if row is None:
        return None
    row.is_active = False
    row.updated_at = _utc_now()
    session.add(row)
    session.flush()
    return row
```

**Notes**:
- No `flip_prior_latest` kwarg (A10).
- Transaction rule: helper flushes, caller commits. Matches `sync_yaml_to_db` pattern.
- `session.flush()` between flip and INSERT is REQUIRED to release the partial-unique slot before the new row claims it (SQLite checks indexes at statement boundaries).
- Soft-delete writes `updated_at` (needs A6 column on EvaluationCase).

Re-create after soft-delete: caller calls `soft_delete_latest(...)` then `save_new_version(...)`; helper's "prior is None" path triggers fresh `version="1.0"` (decision #9). No branching in callers.

---

## 5. Runtime Call-Site Changes (consolidated)

Numbering follows Step 2 inventories.

### 5.1 Prompt read sites — add `is_latest == True`

17 sites. All listed below route through the new filter except the three intentional-history exceptions.

| Tag | File:Line | Change |
|---|---|---|
| #1 | `llm_pipeline/prompts/resolver.py:53-58` | add `is_latest==True` |
| #2 | `llm_pipeline/prompts/service.py:24-37` | add `is_latest==True` |
| #3 | `llm_pipeline/prompts/service.py:80-84` (`prompt_exists`) | add `is_latest==True` |
| #4 | `llm_pipeline/pipeline.py:1281` | add `is_active==True AND is_latest==True` |
| #5 | `llm_pipeline/pipeline.py:1368` | add `is_active==True AND is_latest==True` |
| #6 | `llm_pipeline/introspection.py:310-313` | add `is_latest==True` |
| #7 | `llm_pipeline/ui/routes/editor.py:267-270` | add `is_latest==True` |
| #8 | `llm_pipeline/ui/routes/evals.py:545-551` | add `is_active==True AND is_latest==True` |
| #9 | `llm_pipeline/ui/routes/pipelines.py:228` | add `is_active==True AND is_latest==True` |
| #10 | `llm_pipeline/ui/routes/prompts.py:169-177` (admin list) | default `is_latest==True`, overridable via query param |
| #11 | `llm_pipeline/ui/routes/prompts.py:196-200` (detail) | intentional history — no filter change; future `/versions` endpoint for cleaner slice |
| #12 | `llm_pipeline/ui/routes/prompts.py:267-271` (PUT lookup) | add `is_latest==True` |
| #13 | `llm_pipeline/ui/routes/prompts.py:335-339` (DELETE lookup) | add `is_latest==True` |
| #14 | `llm_pipeline/ui/routes/prompts.py:355-359` (variable-schema lookup) | add `is_latest==True` |
| #15 | `llm_pipeline/prompts/yaml_sync.py:171-176` | replaced by `get_latest(session, Prompt, ...)` helper |
| #16 | `llm_pipeline/sandbox.py:53` (seed) | FILTER `is_latest==True AND is_active==True` per A3 |
| #17 | `llm_pipeline/ui/app.py:180-181` (`_sync_variable_definitions`) | add `is_latest==True` |
| #18 | `llm_pipeline/evals/runner.py:626-632, 654-660` | add `is_latest==True` (defence-in-depth; sandbox only has live post-A3) |
| #19 | `llm_pipeline/creator/prompts.py:357-362` | switch to `get_latest(...)` |
| #20 | `llm_pipeline/creator/integrator.py:205-209` | switch to `get_latest(...)` |

### 5.2 Prompt write sites

| Tag | File:Line | Change |
|---|---|---|
| W1 | `llm_pipeline/ui/routes/prompts.py:231-247` (`create_prompt`) | route through `save_new_version(session, Prompt, key_filters, new_fields)` — helper handles first-row vs flip |
| W2 | `llm_pipeline/ui/routes/prompts.py:275-305` (`update_prompt`) | replace in-place mutation + `_increment_version` with `save_new_version(...)`. Auto-bump (or accept explicit `version`). DB→YAML writeback follows in same request. |
| W3 | `llm_pipeline/ui/routes/prompts.py:328-346` (`delete_prompt`) | call `soft_delete_latest(session, Prompt, prompt_key=..., prompt_type=...)`. `is_latest` stays True. |
| W4 | `llm_pipeline/prompts/yaml_sync.py:169-204` (`sync_yaml_to_db`) | YAML version `>` DB latest → `save_new_version(..., version=yaml_version)`; same/lower → `logger.warning("YAML version %s <= DB latest %s for %s; skipping", ...)` (A8). First-time → `save_new_version(..., version=yaml_version)` (helper handles no-prior path). |
| W5 | `llm_pipeline/creator/prompts.py:363-369` (`_seed_prompts`) | content-hash delta → `save_new_version(...)`; else no-op (matches existing `_content_hash` gating) |
| W6 | `llm_pipeline/creator/integrator.py:211` (`_insert_prompts`) | `save_new_version(...)` with first-time `"1.0"` fallback |
| W7 | `llm_pipeline/sandbox.py:54-68` (sandbox seed) | copy-through of `is_latest`; READ filter per A3 (see #16 above); no versioning logic |
| W9 | `llm_pipeline/evals/runner.py:716-727` (`_merge_variant_defs_into_prompt`) | no change — sandbox is in-memory, in-place mutation stays |

### 5.3 EvaluationCase read sites

| Tag | File:Line | Change |
|---|---|---|
| C1 | `llm_pipeline/evals/runner.py:98-102` | add `is_active==True AND is_latest==True` |
| C2 | `llm_pipeline/evals/yaml_sync.py:111-116` | replaced by `get_latest(session, EvaluationCase, dataset_id=..., name=...)` helper |
| C3 | `llm_pipeline/evals/yaml_sync.py:154-158` (writeback) | add `is_active==True AND is_latest==True` |
| C4 | `llm_pipeline/ui/routes/evals.py:343-349` (case-count subquery) | add `is_active==True AND is_latest==True` before group-by |
| C5 | `llm_pipeline/ui/routes/evals.py:455-459` (get_dataset cases) | add both filters |
| C6 | `llm_pipeline/ui/routes/evals.py:696-700` (update_dataset reload) | add both filters |
| C7 | `llm_pipeline/ui/routes/evals.py:751-753` (delete_dataset cascade) | no filter — cascade hits every version row per decision #11 |
| C8 | `llm_pipeline/ui/routes/evals.py:817-821` (update_case lookup) | by id — N/A |
| C9 | `llm_pipeline/ui/routes/evals.py:859-863` (delete_case lookup) | by id — N/A |

### 5.4 EvaluationCase write sites

| Tag | File:Line | Change |
|---|---|---|
| CW1 | `llm_pipeline/ui/routes/evals.py:786-798` (`create_case`) | `save_new_version(session, EvaluationCase, {"dataset_id":..., "name":...}, {inputs, expected_output, metadata_})` |
| CW2 | `llm_pipeline/ui/routes/evals.py:809-841` (`update_case`) | replace in-place mutation with `save_new_version(...)`. Triggers DB→YAML writeback for the parent dataset in the same request. |
| CW3 | `llm_pipeline/ui/routes/evals.py:852-875` (`delete_case`) | switch HARD delete to `soft_delete_latest(session, EvaluationCase, dataset_id=..., name=...)`. Triggers DB→YAML writeback. |
| CW4 | `llm_pipeline/ui/routes/evals.py:725-765` (`delete_dataset` cascade) | no change — hard delete nukes everything per decision #11 |
| CW5 | `llm_pipeline/evals/yaml_sync.py:118-127` (case insert) | YAML version `>` DB latest → `save_new_version(..., version=yaml_version)`; same/lower → same WARNING log as prompts (A8); first-time → `save_new_version(..., version=yaml_version)` |

### 5.5 YAML no-op WARNING log (A8)

Both prompt yaml_sync (W4) and case yaml_sync (CW5) emit the same shape when YAML version ≤ DB latest:

```python
logger.warning(
    "YAML version %s <= DB latest %s for %s; skipping",
    yaml_version, db_latest.version, identity_str,
)
```

`identity_str` is `"{prompt_key}/{prompt_type}"` for prompts, `"{dataset.name}/{case_name}"` for cases.

---

## 6. YAML Sync for Datasets

Mirrors the prompt pattern one-for-one.

### 6.1 File layout — one YAML per dataset

```
llm-pipeline-evals/
  <dataset_name>.yaml
```

Already the convention enforced by `write_dataset_to_yaml` (`evals/yaml_sync.py:182`: `target_dir / f"{dataset.name}.yaml"`).

### 6.2 Extended per-case format (adds `version`)

```yaml
name: step_a_cases
target_type: step
target_name: step_a
description: ...
cases:
  - name: happy_path
    version: "1.2"            # NEW
    inputs: {...}
    expected_output: {...}
    metadata: {...}
```

No top-level dataset `version` in this scope (decision #2 scopes versioning to case level).

### 6.3 Read path — startup ingestion

Existing dual-dir assembly in `llm_pipeline/ui/app.py:406-424` stays. `sync_evals_yaml_to_db(engine, eval_scan_dirs)` body rewrites to:

```python
for case in yaml_cases:
    latest = get_latest(session, EvaluationCase,
                        dataset_id=dataset_id, name=case["name"])
    yaml_version = str(case.get("version", "1.0"))
    if latest is None:
        save_new_version(
            session, EvaluationCase,
            {"dataset_id": dataset_id, "name": case["name"]},
            {
                "inputs": case["inputs"],
                "expected_output": case.get("expected_output"),
                "metadata_": case.get("metadata"),
            },
            version=yaml_version,
        )
    elif compare_versions(yaml_version, latest.version) > 0:
        save_new_version(
            session, EvaluationCase,
            {"dataset_id": dataset_id, "name": case["name"]},
            {
                "inputs": case["inputs"],
                "expected_output": case.get("expected_output"),
                "metadata_": case.get("metadata"),
            },
            version=yaml_version,
        )
    else:
        logger.warning(
            "YAML version %s <= DB latest %s for %s/%s; skipping",
            yaml_version, latest.version, dataset.name, case["name"],
        )
```

### 6.4 DB→YAML writeback trigger

Three CRUD endpoints fire `write_dataset_to_yaml(engine, dataset_id, evals_dir)` after DB commit:
- `POST /evals/{dataset_id}/cases` (CW1)
- `PUT /evals/{dataset_id}/cases/{case_id}` (CW2)
- `DELETE /evals/{dataset_id}/cases/{case_id}` (CW3)

Plus `PUT /evals/{dataset_id}` for dataset-header changes (`name`, `description`).

Writer already atomic (temp-file + `Path.replace`) and already serialises latest-only content. No changes to writer itself; only the callers are new.

`app.state.evals_dir` is already set to `project_evals` at `app.py:424` — the writeback target.

### 6.5 Prompt writeback atomicity upgrade (risk R3)

`write_prompt_to_yaml` at `yaml_sync.py:225-275` is currently non-atomic (`open(...)` + `yaml.dump(...)` overwrite). Port the atomic temp-file + `Path.replace` pattern used by `write_dataset_to_yaml`. Low-cost, in-scope for this task.

---

## 7. Snapshot Population — `_build_run_snapshot`

### 7.1 Call site

`llm_pipeline/evals/runner.py` — `EvalRunner.run_dataset`, right before `EvaluationRun(...)` construction (line 108). Populated inside the same transaction.

### 7.2 Signature

```python
def _build_run_snapshot(
    session: Session,
    dataset: EvaluationDataset,
    cases: list[EvaluationCase],
    variant_delta: dict | None,
    model_kwarg: str | None,
) -> tuple[dict, dict, dict, dict]:
    """Return (case_versions, prompt_versions, model_snapshot,
    instructions_schema_snapshot) for a run about to be created.

    Walks step_def(s) based on dataset.target_type. Resolves models and
    instructions classes eagerly so snapshots are deterministic and committed
    atomically with the EvaluationRun row.
    """
```

Mirrors `_find_step_def` + `resolve_with_auto_discovery` + `resolve_model_with_fallbacks` + `apply_instruction_delta` — moves the resolution from the lazy `_resolve_task` path (runner.py:137-142, 362-397) to a pre-pass that feeds the run row and is threaded into `_resolve_task` as pre-resolved inputs.

### 7.3 Step-target snapshot shapes

```python
case_versions = {str(c.id): c.version for c in cases}

# For the single step resolved via dataset.target_name:
prompt_versions = {
    prompt_key: {prompt_type: prompt.version, ...},
    ...
}
# Flat (no step_name wrapper).

model_snapshot = {dataset.target_name: resolved_model_id}
# Single-entry dict.

instructions_schema_snapshot = modified_cls.model_json_schema()
# Dict at top level (not wrapped).
```

### 7.4 Pipeline-target snapshot shapes (A9 — IN SCOPE)

Walk every step registered in the pipeline factory, resolve each step's prompts + model + instructions class, emit:

```python
case_versions = {str(c.id): c.version for c in cases}   # unchanged

prompt_versions = {
    step_name: {
        prompt_key: {prompt_type: version, ...},
        ...
    },
    ...
}

model_snapshot = {
    step_name: resolved_model_id,
    ...   # one entry per step
}

instructions_schema_snapshot = {
    step_name: <model_json_schema dict>,
    ...
}
```

No `target_type` tag inside any JSON column (A1). Runtime distinguishes by `EvaluationRun.dataset_id → EvaluationDataset.target_type` which is already stored.

### 7.5 Legacy rows

Pre-migration `EvaluationRun` rows have all four snapshot columns NULL. Compare view treats NULL as "pre-versioning — skip mismatch" (decision #10). No backfill.

---

## 8. Compare View API

### 8.1 Backend response shape

Add the four snapshot columns to both `RunListItem` and `RunDetail` pydantic models (`llm_pipeline/ui/routes/evals.py:109-128`):

```python
case_versions: Optional[dict] = None
prompt_versions: Optional[dict] = None
model_snapshot: Optional[dict] = None
instructions_schema_snapshot: Optional[dict] = None
```

Thread through both endpoints:
- `GET /evals/{dataset_id}/runs` (list, lines 883-913)
- `GET /evals/{dataset_id}/runs/{run_id}` (detail, lines 916-961)

Snapshots surfaced directly as JSON on run detail — no derived fields, no server-side mismatch computation.

### 8.2 Frontend scope

Frontend mismatch detection (per-case version mismatch badges + run-level model/prompt/instructions mismatch badges in `evals.$datasetId.compare.tsx`) is **out of scope for this doc** — flag to PM as a follow-on UI task. Data is available on both `baseRun` and `variantRun` via the existing `useEvalRun` hook; rendering is a separate PR.

---

## 9. Test Catalog

Tests live in `tests/test_versioning_helpers.py` (new) and extensions to `tests/test_eval_runner.py`, `tests/ui/test_evals_routes.py`, `tests/prompts/test_yaml_sync.py`, `tests/evals/test_yaml_sync.py`.

Fixture pattern: `create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)` + `init_pipeline_db(e)`. Match `tests/test_eval_runner.py` and `tests/prompts/test_yaml_sync.py` precedent. Do NOT touch `tests/conftest.py`.

### 9.1 Helper unit tests (`tests/test_versioning_helpers.py`)

1. `test_save_new_version_bumps_and_flips_prior` — v1 = "1.0", v2 = "1.1"; old v1 ends up `is_latest=False, is_active=True`.
2. `test_partial_unique_index_prevents_two_latest_active` — two rows same key both `is_active=True, is_latest=True` → `IntegrityError` on commit. Guards bypass of the helper.
3. `test_soft_delete_then_recreate_resets_version` — after 3 versions + soft-delete, `get_latest` is None; next `save_new_version` returns `"1.0"`; 4 total historical rows.
4. `test_get_latest_ignores_inactive_and_non_latest` — latest among history picked; inactive excluded.
5. `test_save_new_version_forbids_managed_cols` — ValueError on `is_latest`/`version`/etc in `new_fields`.
6. `test_explicit_version_must_be_greater` — ValueError when caller passes `version="1.0"` with prior `"1.1"`.
7. `test_bump_minor_edge_cases` — `"1.9" -> "1.10"`, `"1" -> "1.1"`, `"1.2.3" -> "1.2.4"`; non-numeric → ValueError.
8. `test_soft_delete_writes_updated_at` — confirms A6 column populated.

### 9.2 Integration — runner snapshot (`tests/test_eval_runner.py`)

9. `test_run_populates_snapshots_step_target` — step-target run. Assert:
   - `run.case_versions` is `{str, str}` dict; keys are strings, values contain `.`
   - `run.prompt_versions` is flat `{prompt_key: {prompt_type: version}}`
   - `run.model_snapshot` is `{step_name: model_id}` single-entry
   - `run.instructions_schema_snapshot` is the flat schema dict
10. `test_run_populates_snapshots_pipeline_target` — pipeline-target run (per A9). Assert:
    - `run.prompt_versions` is `{step_name: {prompt_key: {prompt_type: version}}}`
    - `run.model_snapshot` has one entry per step
    - `run.instructions_schema_snapshot` is `{step_name: schema_dict}`

### 9.3 Sandbox (`tests/test_versioning_helpers.py` or new `tests/test_sandbox.py`)

11. `test_sandbox_seed_filters_is_latest_is_active` — seed DB with 3 versions of same prompt (1 live+latest, 1 live+non-latest history, 1 inactive+latest); assert sandbox engine has only the live+latest row (per A3).

### 9.4 Legacy compat (`tests/ui/test_evals_routes.py`)

12. `test_run_detail_endpoint_tolerates_null_snapshots` — seed EvaluationRun with all four snapshot cols NULL; GET run detail returns 200, fields null, no error.

### 9.5 YAML sync (`tests/prompts/test_yaml_sync.py`, `tests/evals/test_yaml_sync.py`)

13. `test_prompt_yaml_newer_inserts_version_and_flips` — YAML `"1.5"` vs DB `"1.3"`: new row at `"1.5"`, old flipped.
14. `test_prompt_yaml_older_or_equal_logs_warning_and_noop` (A8) — YAML `"1.0"` vs DB `"1.3"`: DB unchanged, WARNING log captured via `caplog`.
15. `test_dataset_yaml_newer_inserts_case_version` — dataset YAML bumps case version → new case row inserted, old flipped.
16. `test_dataset_yaml_older_or_equal_logs_warning_and_noop` — same pattern as #14.
17. `test_dataset_writeback_fires_on_put_case` — PUT `/evals/.../cases/{id}` → YAML file on disk reflects new case version.
18. `test_dataset_writeback_fires_on_delete_case` — DELETE → YAML file excludes the (soft-deleted) case.

### 9.6 Migration (`tests/test_migrations.py` or equivalent)

19. `test_migration_dedupes_eval_cases` — seed pre-migration DB with duplicate `(dataset_id, name)` rows; run migration; assert exactly one row with `is_latest=True` per group (newest by `created_at` / tiebreak `id DESC`), others `is_latest=False`.
20. `test_migration_drops_legacy_unique_and_ix_prompts_active` — verify `uq_prompts_key_type` and `ix_prompts_active` no longer exist (A7).
21. `test_migration_is_idempotent` — run twice on the same DB, no errors, schema identical.

---

## 10. Q&A Record

### 10.1 Contradictions flagged and resolutions

| # | Contradiction surfaced | CEO answer applied |
|---|------------------------|--------------------|
| 1 | Step 2 suggested `prompt_versions` flat (`"key:type"` join) + optional `target_type` tag; Step 1 proposed nested-by-key; no single agreed shape for pipeline-target. | A1: nested `{key: {type: version}}` for step-target; wrapped in `{step_name: ...}` for pipeline-target; no tag inside JSON. |
| 2 | Step 1 declared `model_snapshot` as plain `VARCHAR(100)`; Step 3 emitted it as JSON dict column; pipeline-target needs per-step entries. | A2: Dict/JSON with `{step_name: model_id}` in all cases. Migration type = `TEXT`. |
| 3 | Step 2 #16 said sandbox seeds only `is_latest==True AND is_active==True`; Step 3 §3 said sandbox "copies every row verbatim". | A3: filter `is_latest=True AND is_active=True`. |
| 4 | Step 2 §9 proposed per-entity helper files (`prompts/versioning.py`, `evals/versioning.py`) with wrapper helpers; Step 3 §2 proposed a single `db/versioning.py` generic helper. | A4: single generic `llm_pipeline/db/versioning.py`. No wrappers. |
| 5 | `compare_versions` lived in `prompts/yaml_sync.py`; Step 2 §6 recommended moving to `utils/versioning.py`; Step 3 imported from `prompts.yaml_sync`. Cross-module coupling if `db/versioning.py` depends on `prompts/`. | A5: move to `llm_pipeline/utils/versioning.py`. Both `prompts/yaml_sync.py` and `db/versioning.py` import from utils. |
| 6 | Step 3 §1.2 declared `EvaluationCase.updated_at`; Step 1 §2 did not include it; migration list inconsistent. | A6: ADD the column. `_MIGRATIONS` row: `("eval_cases", "updated_at", "TIMESTAMP")`. |
| 7 | Step 1 §1 retained `ix_prompts_active`; partial unique index `uq_prompts_active_latest` already indexes `(is_active, is_latest)` as part of key hot path — `ix_prompts_active` is redundant. | A7: DROP `ix_prompts_active`. |
| 8 | Step 2 referenced locked decision #5 (YAML newer → INSERT new version; same/lower → no-op) but did not specify log level for no-op; Step 3 silent. | A8: WARNING log with specified format. |
| 9 | Step 2 §7 marked pipeline-target snapshots as implicit/ambiguous; Step 1 §3 recommended step-level dict keyed by `step_name` but "step 3 finalises"; scope unclear. | A9: IN SCOPE. Walk all steps; keying per A1/A2. |
| 10 | Step 3 §2 included `flip_prior_latest: bool = True` kwarg with no caller justified; no use case in inventory. | A10: DROP the kwarg. Helper always flips. |

### 10.2 Minimum Q&A Loop compliance

Revisions: 1 (CEO answered the 10 questions in one round). Contract minimum met.

---

## 11. Assumptions Validated

- [x] Partial unique indexes are supported on SQLite >= 3.8.0 and on Postgres.
- [x] SQLite boolean storage is INTEGER; `WHERE is_active = 1 AND is_latest = 1` matches SQLModel writes.
- [x] `EvaluationCaseResult.case_id` FK needs no cascade change; append-mostly model.
- [x] `SQLModel.metadata.create_all` is a no-op on existing tables for indexes; raw DDL required on upgrade path.
- [x] `session.flush()` between flip and INSERT is required to release the partial-unique slot.
- [x] JSON columns round-trip int keys as strings; runner stringifies `case.id` at write time.
- [x] YAML atomic writer already in place for datasets; prompts writer needs the same upgrade.
- [x] `compare_versions` numeric-only is acceptable; non-numeric segments rejected at YAML parse.
- [x] Pre-migration rows all satisfy `is_active=True AND is_latest=True` — `DEFAULT 1` backfill correct.
- [x] `delete_dataset` cascade stays hard (decision #11) — dangling FK on `EvaluationCaseResult.case_id` acceptable because runs are also destroyed in same cascade.

---

## 12. Open Items for PM (non-blocking)

- **Frontend compare-view badges.** Mismatch rendering (per-case + run-level) in `evals.$datasetId.compare.tsx` is a follow-on UI task. Backend data is surfaced via the expanded `RunDetail`/`RunListItem` models (§8).
- **History listing endpoint.** Step 2 R6 recommends a new `GET /prompts/{key}/{type}/versions` for a cleaner history slice. Low priority; existing detail endpoint continues to work.
- **Creator-module versioning policy.** Step 2 R7: creator path should only call `save_new_version` when content hash differs vs latest. Already gated today via `_content_hash` branch; verify at implementation time.
- **`compare_versions` non-numeric input hardening.** Validate at YAML-parse time (reject non-numeric segments with a clear error) rather than letting it surface deep in the helper. Low risk; in-scope if time permits.
- **SQLite FK pragma.** Whether to enable `PRAGMA foreign_keys=ON` at init is out of scope for this task. Current behaviour (no FK enforcement on SQLite) tolerated per decision #11.
- **Dataset-level version.** Not in scope; future composition with case-level versions possible if ever needed.

---

## 13. Files to Create / Modify

| File | Change |
|---|---|
| `llm_pipeline/utils/versioning.py` | NEW — `compare_versions` (moved from `prompts/yaml_sync.py`) |
| `llm_pipeline/db/versioning.py` | NEW — `save_new_version`, `get_latest`, `soft_delete_latest`, `_bump_minor` |
| `llm_pipeline/db/prompt.py` | ADD `is_latest`; DROP `uq_prompts_key_type` + `ix_prompts_active`; ADD partial unique + supporting indexes in `__table_args__` |
| `llm_pipeline/evals/models.py` | ADD `version`, `is_active`, `is_latest`, `updated_at` to `EvaluationCase`; ADD 4 snapshot JSON cols to `EvaluationRun`; update `__table_args__` |
| `llm_pipeline/db/__init__.py` | EXTEND `_MIGRATIONS`; ADD `_migrate_partial_unique_indexes`; wire into `init_pipeline_db` |
| `llm_pipeline/prompts/yaml_sync.py` | Import `compare_versions` from `utils/versioning`; rewrite `sync_yaml_to_db` to use `save_new_version` + WARNING log; port atomic writer pattern |
| `llm_pipeline/prompts/service.py` | `get_prompt` + `prompt_exists`: add `is_latest==True` |
| `llm_pipeline/prompts/resolver.py` | `_lookup_prompt_key`: add `is_latest==True` |
| `llm_pipeline/pipeline.py` | `_find_cached_state` + `_save_step_state`: add `is_active AND is_latest` |
| `llm_pipeline/introspection.py` | `enrich_with_prompt_readiness`: add `is_latest==True` |
| `llm_pipeline/ui/app.py` | `_sync_variable_definitions`: add `is_latest==True` |
| `llm_pipeline/ui/routes/editor.py` | compile Pass 5: add `is_latest==True` |
| `llm_pipeline/ui/routes/pipelines.py` | `get_step_prompts`: add both filters |
| `llm_pipeline/ui/routes/prompts.py` | CRUD routes through `save_new_version` / `soft_delete_latest`; history-aware detail + admin list; PUT writeback upgrades |
| `llm_pipeline/ui/routes/evals.py` | Case CRUD through `save_new_version` / `soft_delete_latest`; trigger dataset writeback on POST/PUT/DELETE; read filters on list/detail; ADD 4 snapshot cols to `RunListItem`/`RunDetail` and thread through |
| `llm_pipeline/evals/yaml_sync.py` | Rewrite `sync_evals_yaml_to_db` case loop to use `save_new_version` + WARNING log (A8) |
| `llm_pipeline/evals/runner.py` | ADD `_build_run_snapshot` pre-pass; populate 4 snapshot cols on `EvaluationRun`; add read filters for case + prompt queries |
| `llm_pipeline/sandbox.py` | Filter seed query by `is_latest==True AND is_active==True` (A3); copy-through `is_latest` |
| `llm_pipeline/creator/prompts.py` | `_seed_prompts`: fetch-latest + `save_new_version` on content-hash delta |
| `llm_pipeline/creator/integrator.py` | `_insert_prompts`: `save_new_version` on first-time insert |
| `tests/test_versioning_helpers.py` | NEW — unit tests 9.1 #1–#8, #11 |
| `tests/test_eval_runner.py` | ADD integration tests 9.2 #9, #10 |
| `tests/ui/test_evals_routes.py` | ADD legacy-compat test 9.4 #12 |
| `tests/prompts/test_yaml_sync.py` | ADD YAML sync tests 9.5 #13, #14 |
| `tests/evals/test_yaml_sync.py` | ADD YAML sync tests 9.5 #15, #16, #17, #18 |
| `tests/test_migrations.py` (new or existing) | ADD migration tests 9.6 #19, #20, #21 |

---

## 14. Recommendations for Planning

1. **Implementation ordering:** (a) move `compare_versions` to `utils/versioning.py`; (b) create `db/versioning.py`; (c) schema adds + `__table_args__` updates; (d) migration function; (e) read-site refactors in one PR per layer (db → services → UI); (f) write-site refactors route through helper; (g) runner snapshot pre-pass + column writes; (h) dataset YAML writeback wiring; (i) tests in parallel to each layer.
2. **Transaction discipline:** every call to `save_new_version` / `soft_delete_latest` must be within a `with Session(engine) as session:` block with a single trailing `session.commit()`. Helper flushes, never commits.
3. **YAML atomicity upgrade:** `write_prompt_to_yaml` gets the temp-file + `Path.replace` pattern in the same PR as the sync rewrite — avoids partial-write corruption once multiple version rows share a file.
4. **Belt-and-braces index creation:** keep `__table_args__` declarations AND the raw DDL in `_migrate_partial_unique_indexes`. Fresh DBs get indexes via `create_all`; upgrading DBs get them via the migration. Both idempotent.
5. **Defer frontend mismatch badges.** Backend data is surfaced; rendering is a separate UI task to avoid scope creep.
