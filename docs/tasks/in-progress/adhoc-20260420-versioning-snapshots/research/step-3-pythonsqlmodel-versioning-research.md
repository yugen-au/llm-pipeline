# Step 3 — Python/SQLModel Idioms: Row Versioning + Snapshot Columns

Prescriptive. Matches project conventions in `llm_pipeline/db/prompt.py`, `llm_pipeline/evals/models.py`, `llm_pipeline/prompts/yaml_sync.py`, `llm_pipeline/db/__init__.py`.

**Python target:** 3.11+ (per `pyproject.toml` `requires-python = ">=3.11"`).
**Typing rule:** SQLModel `Field(...)` declarations use `Optional[X]` (match existing `db/prompt.py`, `evals/models.py`, `state.py`). Helper function signatures use `X | None` (match `llm_pipeline/evals/runner.py`).
**Transaction rule:** helpers flush; callers commit. Matches `yaml_sync.sync_yaml_to_db` pattern (builds up changes in a `with Session(...)` block, single `session.commit()` at end).

---

## 1. SQLModel field declarations

### 1.1 `Prompt` (`llm_pipeline/db/prompt.py`) — add `is_latest`

Insert after `is_active`:

```python
is_active: bool = Field(default=True)
is_latest: bool = Field(default=True, index=True)
```

`index=True` is cheap and covers the non-partial read path. The real uniqueness guarantee is the partial unique index (step 1 schema). Drop the legacy `UniqueConstraint('prompt_key', 'prompt_type', name='uq_prompts_key_type')` — replaced by the partial unique index over `(prompt_key, prompt_type)` filtered on `is_active=1 AND is_latest=1` (per step 1). Also drop `Index("ix_prompts_active", "is_active")` — superseded by `uq_prompts_active_latest`.

The `version: str = Field(default="1.0", max_length=20)` field already exists on `Prompt` — no change needed for versioning itself; it becomes part of a live row vs historical row set.

### 1.2 `EvaluationCase` (`llm_pipeline/evals/models.py`) — add `version`, `is_active`, `is_latest`

```python
class EvaluationCase(SQLModel, table=True):
    __tablename__ = "eval_cases"

    id: Optional[int] = Field(default=None, primary_key=True)
    dataset_id: int = Field(foreign_key="eval_datasets.id", index=True)
    name: str = Field(max_length=200)
    inputs: dict = Field(sa_column=Column(JSON))
    expected_output: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    metadata_: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    version: str = Field(default="1.0", max_length=20)
    is_active: bool = Field(default=True)
    is_latest: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    __table_args__ = (
        Index("ix_eval_cases_dataset", "dataset_id"),
    )
```

`updated_at` is added because soft-delete needs a deletion timestamp and there is no `deleted_at` column (locked decision; step 1 `updated_at` captures it).

### 1.3 `EvaluationRun` snapshot columns (`llm_pipeline/evals/models.py`)

Add inside `EvaluationRun`:

```python
case_versions: Optional[dict] = Field(default=None, sa_column=Column(JSON))
prompt_versions: Optional[dict] = Field(default=None, sa_column=Column(JSON))
model_snapshot: Optional[dict] = Field(default=None, sa_column=Column(JSON))
instructions_schema_snapshot: Optional[dict] = Field(default=None, sa_column=Column(JSON))
```

Place after the existing `delta_snapshot` column to keep all JSON snapshots grouped. Defaults to NULL — legacy rows from runs before this migration satisfy decision #9 (compare view skips mismatch when NULL).

### 1.4 Int-keyed dict round-trip through JSON

JSON has no integer keys — `json.dumps({1: "a"})` emits `{"1": "a"}` and round-trips back as `{"1": "a"}` (string keys). SQLAlchemy's `JSON` column uses `json.dumps`/`json.loads` by default, so any dict written with int keys comes back with string keys.

**Decision for `case_versions`:** runner writes keys as strings. Schema:

```python
# runner: case_id is an int in DB, stringify when building the snapshot
case_versions: dict[str, str] = {
    str(case.id): case.version for case in cases_used
}
run.case_versions = case_versions
```

Frontend and compare-view read code treats keys as strings throughout — never `int(key)` at the boundary. Documented in the EvaluationRun docstring.

`prompt_versions` is keyed by `"{prompt_key}:{prompt_type}"` (already strings) → no coercion concern:

```python
prompt_versions: dict[str, str] = {
    f"{p.prompt_key}:{p.prompt_type}": p.version for p in prompts_used
}
```

`model_snapshot` and `instructions_schema_snapshot` are flat dicts with string keys by construction.

---

## 2. The versioning helper

Location: new module `llm_pipeline/db/versioning.py` (framework-level, next to `db/__init__.py` and `db/prompt.py`).

```python
"""Helpers for string-versioned rows with is_latest invariant.

Used by any table that adopts the (version: str, is_active: bool, is_latest: bool)
versioning pattern with a partial unique index on key cols WHERE is_active
AND is_latest.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypeVar

from sqlmodel import Session, select
from sqlalchemy import desc

from llm_pipeline.prompts.yaml_sync import compare_versions

T = TypeVar("T")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _bump_minor(version: str) -> str:
    """Bump the minor component of a dotted version. '1.0' -> '1.1', '1.9' -> '1.10'.

    Only the last two components are considered. If version has 1 part,
    treat as MAJOR and bump to f"{MAJOR}.1". If more than 2 parts, increment
    the last part. Empty / malformed -> ValueError.
    """
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
    """Write a new version of a versioned row.

    Atomically (within the caller's transaction):
      1. Find the current active-latest row matching ``key_filters``.
      2. If found: flip its ``is_latest`` to False; compute next version by
         minor bump unless ``version`` was explicitly supplied; INSERT new row
         with ``key_filters | new_fields | {version, is_active=True,
         is_latest=True, created_at, updated_at}``.
      3. If not found (no prior live row — fresh entity, or post soft-delete):
         INSERT a fresh row at ``version="1.0"`` (or ``version`` if supplied).

    The helper flushes (so the new row gets its ``id`` and the flip is visible
    inside the transaction) but does NOT commit. Caller commits.

    Args:
        session: open SQLModel session.
        model_cls: SQLModel class with version, is_active, is_latest fields.
        key_filters: identity columns, e.g. {"prompt_key": "foo",
            "prompt_type": "system"} or {"dataset_id": 5, "name": "case_a"}.
        new_fields: the mutable payload. Must NOT include version, is_active,
            is_latest, created_at, updated_at — the helper owns those.
        version: explicit version override. When None, auto-bumps minor from
            prior row (or "1.0" if no prior row).

    Returns:
        The newly inserted row (after flush, so .id is populated).
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
                f"{prior.version!r} for {model_cls.__name__} "
                f"{key_filters}"
            )
        prior.is_latest = False
        prior.updated_at = now
        session.add(prior)
        session.flush()  # releases the partial-unique slot before INSERT

    row_kwargs = {
        **key_filters,
        **new_fields,
        "version": new_version,
        "is_active": True,
        "is_latest": True,
        "created_at": now,
        "updated_at": now,
    }
    # Models without created_at/updated_at (e.g. Prompt currently has them;
    # EvaluationCase must have them added per §1.2) will ValueError at
    # SQLModel init — intentional: callers must add those columns.
    new_row = model_cls(**row_kwargs)
    session.add(new_row)
    session.flush()
    return new_row
```

**Decisions justified:**

- **Auto-bump = minor.** Every write is "I changed the content"; major bumps are semantic events that callers opt into via explicit `version=`. Matches prompt-YAML convention in `yaml_sync.sync_yaml_to_db` (authors bump minor when editing).
- **Commit-in-caller, not helper.** Caller usually does additional work in the same transaction (e.g. EvaluationCaseResult rows referencing the new case_id). Committing inside the helper would force multiple transactions. The single `session.flush()` between the flip and the INSERT is required: it releases the partial unique slot (is_active=1 AND is_latest=1 on key cols) before the new row claims it, avoiding a constraint violation on SQLite which checks indexes at statement boundaries.
- **Fresh-insert fallback = 1.0.** Same as current SQLModel defaults for `version` on `Prompt`/`EvaluationCase`. Single codepath for "fresh entity" and "recreate after soft-delete" — the helper detects via the same `is_active=True AND is_latest=True` lookup.
- **Minor-bump on dotted string.** `_bump_minor` operates on `str.split(".")` parts of digits only. Uses `compare_versions` (already in `yaml_sync.py`) for the sanity check. `"1.9" -> "1.10"` works correctly because `compare_versions` is numeric per component, not lexical.

---

## 3. The read helper

```python
def get_latest(
    session: Session,
    model_cls: type[T],
    **filters: Any,
) -> T | None:
    """Return the active-latest row matching filters, or None.

    Usage:
        prompt = get_latest(session, Prompt, prompt_key="foo", prompt_type="system")
        case = get_latest(session, EvaluationCase, dataset_id=5, name="case_a")
    """
    stmt = select(model_cls).where(
        model_cls.is_active == True,  # noqa: E712
        model_cls.is_latest == True,  # noqa: E712
    )
    for col, val in filters.items():
        stmt = stmt.where(getattr(model_cls, col) == val)
    return session.exec(stmt).first()
```

`PromptService.get_prompt` (`llm_pipeline/prompts/service.py`) gets an `AND Prompt.is_latest == True` clause added — that's the one legacy read site. Sandbox seeding (`sandbox.py`) already copies every row verbatim, no change needed there beyond copying the two new columns.

---

## 4. Soft-delete helper

```python
def soft_delete_latest(
    session: Session,
    model_cls: type[T],
    **key_filters: Any,
) -> T | None:
    """Mark the current active-latest row as is_active=False.

    Leaves is_latest=True so the row still represents "what was most recent"
    for historical queries. Critically: because is_active flips to False,
    the (is_active=1 AND is_latest=1) partial unique index no longer matches
    ANY row for these key_filters — the slot is vacated and a subsequent
    save_new_version(...) with the same key_filters inserts a fresh "1.0"
    row without constraint violation.

    Returns the row that was soft-deleted, or None if no active-latest
    row matched.
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

**Note on the invariant:** the partial unique index is `UNIQUE(...) WHERE is_active AND is_latest`. Setting `is_active=False` removes the row from the index's match set entirely. This is why we do NOT also flip `is_latest=False` — we want "most recent historical state" still queryable via `is_latest=True, is_active=False`.

---

## 5. Re-create-after-soft-delete flow

Covered by `save_new_version` with no branching in callers:

1. Caller: `soft_delete_latest(session, EvaluationCase, dataset_id=5, name="case_a")`.
   → row `id=42, version="1.3"` becomes `is_active=False, is_latest=True`.
2. Caller: `save_new_version(session, EvaluationCase, {"dataset_id": 5, "name": "case_a"}, {"inputs": ..., "expected_output": ...})`.
   → lookup for (dataset_id=5, name="case_a", is_active=True, is_latest=True) finds nothing → fresh INSERT at `version="1.0"`.
3. Historical row 42 remains with `is_active=False, is_latest=True, version="1.3"` — unaffected. Any `EvaluationCaseResult.case_id=42` continues to resolve correctly.

**No explicit caller branch needed.** The helper's "prior is None" path is the recreate path. Rationale: the caller's mental model is "write new case_a"; whether the slot was empty-from-start or empty-from-soft-delete is an implementation detail.

---

## 6. Atomicity

Pattern mirrors `llm_pipeline/prompts/yaml_sync.py:sync_yaml_to_db` (lines 169–204): single `with Session(engine) as session:` block, mutations via `session.add`, trailing `session.commit()`.

Inside `save_new_version`:
- `session.flush()` after flipping prior: required — the partial unique index is checked at statement execution, so the flip must hit the DB before the INSERT.
- `session.flush()` after INSERT: required — so the caller receives a populated `.id` (matches the `session.flush()` pattern in `tests/test_eval_runner.py:41` fixture to get `ds.id` before adding cases).
- No `session.commit()` inside helper.

Caller pattern:

```python
with Session(engine) as session:
    new_case = save_new_version(
        session, EvaluationCase,
        key_filters={"dataset_id": ds_id, "name": "case_a"},
        new_fields={"inputs": {...}, "expected_output": {...}},
    )
    # … other work in same txn …
    session.commit()
```

If the caller raises between `save_new_version` and `commit`, SQLAlchemy rolls back both the flip and the INSERT — atomic end-to-end.

Multi-row batch (e.g. YAML sync of N cases): call `save_new_version` N times in the same session, commit once at the end. No performance concern — `flush()` is per-row but SQLite handles it in the ambient transaction.

---

## 7. Sandbox compatibility

`create_sandbox_engine` (`llm_pipeline/sandbox.py`) creates an in-memory SQLite engine, calls `init_pipeline_db(sandbox_engine)`, then copies rows. Partial unique indexes **work in SQLite in-memory** (partial indexes have been supported since SQLite 3.8.0, 2013). `init_pipeline_db` creates them via `SQLModel.metadata.create_all` and/or the raw-DDL migration step (step 1's recommendation; same raw-DDL approach as `add_missing_indexes`).

Two concrete verifications that belong in the test suite (§8):

1. **Sandbox seed copies new columns.** The existing seeding loop in `create_sandbox_engine` (lines 52–68) rebuilds `Prompt(...)` rows field-by-field. Must be updated to include `is_latest`:
   ```python
   dst.add(Prompt(
       ...,
       version=prompt.version,
       is_active=prompt.is_active,
       is_latest=prompt.is_latest,
       ...
   ))
   ```
   Similar addition required for any sandbox seeding of `EvaluationCase` (not currently seeded by sandbox — no change needed there today).

2. **In-memory SQLite partial-unique sanity test.** Fresh engine, insert two rows with same key and `is_active=True, is_latest=True` → IntegrityError. Same rows with one flipped to `is_active=False` → OK.

`create_engine("sqlite:///:memory:")` + `StaticPool` (already used in `tests/test_eval_runner.py`) is the right fixture.

---

## 8. Test strategy

Place tests in `tests/test_versioning_helpers.py` (single module — the helper is a small, tight surface). Extend existing fixtures via pytest `conftest`.

**Fixtures:** reuse the `engine()` fixture shape from `tests/test_eval_runner.py` and `tests/prompts/test_yaml_sync.py` (both use `create_engine("sqlite://", ..., StaticPool)` + `init_pipeline_db(e)`). Add a new module-local `engine` fixture matching that pattern — **do not** add to `tests/conftest.py` since other tests already have their own.

```python
# tests/test_versioning_helpers.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, select

from llm_pipeline.db import init_pipeline_db
from llm_pipeline.db.prompt import Prompt
from llm_pipeline.db.versioning import (
    get_latest, save_new_version, soft_delete_latest,
)
from llm_pipeline.evals.models import EvaluationCase, EvaluationDataset


@pytest.fixture
def engine():
    e = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_pipeline_db(e)
    return e


@pytest.fixture
def seeded_dataset(engine):
    with Session(engine) as session:
        ds = EvaluationDataset(name="t", target_type="step", target_name="s")
        session.add(ds)
        session.commit()
        return ds.id
```

### 8.1 `test_save_new_version_bumps_and_flips_prior`

```python
def test_save_new_version_bumps_and_flips_prior(engine, seeded_dataset):
    with Session(engine) as session:
        v1 = save_new_version(
            session, EvaluationCase,
            key_filters={"dataset_id": seeded_dataset, "name": "c1"},
            new_fields={"inputs": {"x": 1}},
        )
        assert v1.version == "1.0"
        assert v1.is_latest is True

        v2 = save_new_version(
            session, EvaluationCase,
            key_filters={"dataset_id": seeded_dataset, "name": "c1"},
            new_fields={"inputs": {"x": 2}},
        )
        session.commit()

        session.refresh(v1)
        assert v1.is_latest is False
        assert v1.is_active is True  # historical rows stay active
        assert v2.version == "1.1"
        assert v2.is_latest is True
```

### 8.2 `test_partial_unique_index_prevents_two_latest_active`

Guards that the DB invariant actually fires (catches bugs where the helper is bypassed).

```python
def test_partial_unique_index_prevents_two_latest_active(engine, seeded_dataset):
    with Session(engine) as session:
        session.add(EvaluationCase(
            dataset_id=seeded_dataset, name="c1", inputs={},
            version="1.0", is_active=True, is_latest=True,
        ))
        session.commit()

        session.add(EvaluationCase(
            dataset_id=seeded_dataset, name="c1", inputs={},
            version="1.1", is_active=True, is_latest=True,
        ))
        with pytest.raises(IntegrityError):
            session.commit()
```

### 8.3 `test_soft_delete_then_recreate_resets_version`

```python
def test_soft_delete_then_recreate_resets_version(engine, seeded_dataset):
    with Session(engine) as session:
        for _ in range(3):
            save_new_version(
                session, EvaluationCase,
                key_filters={"dataset_id": seeded_dataset, "name": "c1"},
                new_fields={"inputs": {}},
            )
        session.commit()

        current = get_latest(session, EvaluationCase,
                             dataset_id=seeded_dataset, name="c1")
        assert current.version == "1.2"

        soft_delete_latest(session, EvaluationCase,
                           dataset_id=seeded_dataset, name="c1")
        session.commit()

        assert get_latest(session, EvaluationCase,
                          dataset_id=seeded_dataset, name="c1") is None

        recreated = save_new_version(
            session, EvaluationCase,
            key_filters={"dataset_id": seeded_dataset, "name": "c1"},
            new_fields={"inputs": {}},
        )
        session.commit()
        assert recreated.version == "1.0"

        # Historical rows intact
        all_c1 = session.exec(
            select(EvaluationCase).where(EvaluationCase.name == "c1")
        ).all()
        assert len(all_c1) == 4  # 3 versioned + 1 fresh post-delete
```

### 8.4 `test_get_latest_ignores_inactive_and_non_latest`

```python
def test_get_latest_ignores_inactive_and_non_latest(engine, seeded_dataset):
    with Session(engine) as session:
        save_new_version(session, EvaluationCase,
                         {"dataset_id": seeded_dataset, "name": "c1"},
                         {"inputs": {"v": 1}})
        save_new_version(session, EvaluationCase,
                         {"dataset_id": seeded_dataset, "name": "c1"},
                         {"inputs": {"v": 2}})
        session.commit()

        row = get_latest(session, EvaluationCase,
                         dataset_id=seeded_dataset, name="c1")
        assert row.inputs == {"v": 2}
        assert row.is_latest is True and row.is_active is True
```

### 8.5 `test_evaluation_run_populates_snapshot_columns` (integration)

In `tests/test_eval_runner.py`, extend an existing test or add:

```python
def test_run_populates_snapshots(engine, seeded_dataset):
    # … set up runner and run …
    with Session(engine) as session:
        run = session.exec(select(EvaluationRun)).first()
        assert isinstance(run.case_versions, dict)
        assert isinstance(run.prompt_versions, dict)
        assert isinstance(run.model_snapshot, dict)
        # int-keyed-dict-as-string-keyed invariant
        for k in run.case_versions:
            assert isinstance(k, str)
        # values look like versions
        for v in run.case_versions.values():
            assert "." in v
```

### 8.6 `test_compare_view_skips_mismatch_when_snapshot_null` (legacy compat)

Exercises decision #9. Belongs in `tests/ui/test_evals_routes.py` alongside existing compare-view tests.

```python
def test_compare_view_skips_mismatch_when_snapshots_null(client, engine):
    # Seed an EvaluationRun with case_versions=None (legacy row)
    # Hit the compare route; assert response carries no "mismatch" badge
    # for that run.
    ...
```

### 8.7 Suggested additional tests (belt-and-braces)

- `test_save_new_version_forbids_managed_cols` — ValueError when `new_fields` contains `is_latest` etc.
- `test_explicit_version_must_be_greater` — ValueError if caller passes `version="1.0"` when prior is `"1.1"`.
- `test_bump_minor_edge_cases` — unit test of `_bump_minor`: `"1.9" -> "1.10"`, `"1" -> "1.1"`, `"1.2.3" -> "1.2.4"`.

---

## 9. Migration script idiom

Do NOT add a `scripts/` directory. The project has no precedent for one-off scripts (confirmed via `Glob scripts/**/*.py` — no matches). Existing migration style: additive ALTER TABLE driven from `_migrate_add_columns` at startup, inside `llm_pipeline/db/__init__.py`. Match it.

**Prescribed change to `_migrate_add_columns`:**

```python
_MIGRATIONS = [
    ... existing entries ...
    ("prompts", "is_latest", "INTEGER DEFAULT 1"),
    ("eval_cases", "is_latest", "INTEGER DEFAULT 1"),
    ("eval_cases", "is_active", "INTEGER DEFAULT 1"),
    ("eval_cases", "version", "VARCHAR(20) DEFAULT '1.0'"),
    ("eval_cases", "updated_at", "TIMESTAMP"),
    ("eval_runs", "case_versions", "TEXT"),
    ("eval_runs", "prompt_versions", "TEXT"),
    ("eval_runs", "model_snapshot", "TEXT"),
    ("eval_runs", "instructions_schema_snapshot", "TEXT"),
]
```

**Separately**, step 1 requires:
- dropping the legacy `uq_prompts_key_type` unique constraint (name lookup, then `DROP INDEX`), and
- creating the partial unique indexes (`uq_prompts_active_latest`, `uq_eval_cases_dataset_name_active_latest`), and
- the `eval_cases` dedupe `UPDATE ... ROW_NUMBER()` step.

Per step 1, these go in a dedicated function (e.g. `_migrate_partial_unique_indexes(engine)`) called from `init_pipeline_db` right after `_migrate_add_columns(engine)`, using raw DDL (matches `add_missing_indexes` style). Cross-reference: step 1 § "drop old unique + add partial uniques" (line 191).

**Execution order inside `init_pipeline_db`:**

```python
SQLModel.metadata.create_all(engine, tables=[...])   # existing
_migrate_add_columns(engine)                         # columns exist
_migrate_partial_unique_indexes(engine)              # NEW (step 1)
add_missing_indexes(engine)                          # existing
```

Ordering matters: partial-unique-index creation must come after column creation (columns referenced in the `WHERE` clause must exist).

---

## 10. Typing gotchas

- **`Optional[dict]` with SQLModel + Pydantic v2.** Works as written in existing code (`llm_pipeline/evals/models.py` lines 38, 58, 63). The `sa_column=Column(JSON)` overrides SQLModel's native column inference; the Pydantic-level type stays `Optional[dict]` → column nullable. Keep `Optional[X]` in field declarations.
- **`Optional[dict]` vs `dict | None`:** project mixes both. Model files (`db/prompt.py`, `evals/models.py`, `state.py`) all use `Optional[...]`. Helper files (`evals/runner.py`) use `X | None`. Recommendation: **`Optional[...]` for SQLModel fields, `X | None` for helper/service function signatures.** Matches existing precedent — don't churn.
- **Python version target:** `requires-python = ">=3.11"`. Both syntaxes work at 3.11. `type T = ...` (PEP 695) does NOT work at 3.11 — do not introduce it. Use `TypeVar("T")` (as in `versioning.py` above).
- **`dict[str, str]` generics in signatures:** supported since 3.9. Use directly, no `Dict` import needed from `typing`.
- **`from __future__ import annotations`** — already used in `llm_pipeline/sandbox.py`, `evals/runner.py`. Keep it in the new `versioning.py` module so the forward-ref `T` in `-> T:` resolves cleanly.
- **SQLModel equality warnings:** `Prompt.is_active == True` triggers `noqa: E712` — already the pattern used by `prompts/service.py` line 27 and `yaml_sync.py`. Keep the `# noqa: E712` comment.

---

## Summary of files to create / modify

| File | Change |
|---|---|
| `llm_pipeline/db/versioning.py` | NEW — `save_new_version`, `get_latest`, `soft_delete_latest`, `_bump_minor` |
| `llm_pipeline/db/prompt.py` | ADD `is_latest` field; DROP legacy `uq_prompts_key_type` + `ix_prompts_active` |
| `llm_pipeline/evals/models.py` | ADD `version`, `is_active`, `is_latest`, `updated_at` to `EvaluationCase`; ADD 4 snapshot JSON columns to `EvaluationRun` |
| `llm_pipeline/db/__init__.py` | EXTEND `_migrate_add_columns` with new cols; ADD `_migrate_partial_unique_indexes` per step 1 |
| `llm_pipeline/sandbox.py` | `create_sandbox_engine` seeding: copy `is_latest` on `Prompt` |
| `llm_pipeline/prompts/service.py` | `get_prompt` / `prompt_exists` read paths: add `is_latest == True` |
| `llm_pipeline/evals/runner.py` | populate new snapshot columns on `EvaluationRun`; `EvaluationCaseResult.case_id` references exact version row id (already does — confirm) |
| `tests/test_versioning_helpers.py` | NEW — test cases 8.1–8.4, 8.7 |
| `tests/test_eval_runner.py` | ADD test 8.5 |
| `tests/ui/test_evals_routes.py` | ADD test 8.6 |
