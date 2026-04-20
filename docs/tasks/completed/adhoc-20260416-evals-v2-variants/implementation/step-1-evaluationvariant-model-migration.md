# IMPLEMENTATION - STEP 1: EVALUATIONVARIANT MODEL + MIGRATION
**Status:** completed

## Summary
Added `EvaluationVariant` SQLModel table (`eval_variants`) and extended `EvaluationRun` with nullable `variant_id` FK + `delta_snapshot` JSON column. Registered new table in `init_pipeline_db()` and added migration rows so existing DBs gain the two columns on next startup. Added tests covering fresh-DB creation, FK, index, round-trip persistence, and migration against a pre-existing schema.

## Files
**Created:** tests/test_eval_variants.py
**Modified:** llm_pipeline/evals/models.py, llm_pipeline/db/__init__.py
**Deleted:** none

## Changes

### File: `llm_pipeline/evals/models.py`
Added `EvaluationVariant` class (table=True) after `EvaluationCaseResult`. Extended `EvaluationRun` with `variant_id` (Optional[int], FK `eval_variants.id`) and `delta_snapshot` (Optional[dict], JSON column). Updated `__all__`.

```
# Before
class EvaluationRun(SQLModel, table=True):
    ...
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = Field(default=None)

    __table_args__ = (
        Index("ix_eval_runs_dataset", "dataset_id"),
    )

# After
class EvaluationRun(SQLModel, table=True):
    ...
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = Field(default=None)
    variant_id: Optional[int] = Field(default=None, foreign_key="eval_variants.id")
    delta_snapshot: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    __table_args__ = (
        Index("ix_eval_runs_dataset", "dataset_id"),
    )


class EvaluationVariant(SQLModel, table=True):
    __tablename__ = "eval_variants"

    id: Optional[int] = Field(default=None, primary_key=True)
    dataset_id: int = Field(foreign_key="eval_datasets.id", index=True)
    name: str = Field(max_length=200)
    description: Optional[str] = Field(default=None)
    delta: dict = Field(sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    __table_args__ = (
        Index("ix_eval_variants_dataset", "dataset_id"),
    )
```

### File: `llm_pipeline/db/__init__.py`
Imported `EvaluationVariant`; appended `EvaluationVariant.__table__` to `init_pipeline_db()` tables list (after `EvaluationCaseResult.__table__`); added two migration rows for `eval_runs`.

```
# Before
from llm_pipeline.evals.models import EvaluationDataset, EvaluationCase, EvaluationRun, EvaluationCaseResult
...
        ("pipeline_reviews", "input_data", "TEXT"),
    ]
...
            EvaluationCaseResult.__table__,
        ],

# After
from llm_pipeline.evals.models import EvaluationDataset, EvaluationCase, EvaluationRun, EvaluationCaseResult, EvaluationVariant
...
        ("pipeline_reviews", "input_data", "TEXT"),
        ("eval_runs", "variant_id", "INTEGER"),
        ("eval_runs", "delta_snapshot", "TEXT"),
    ]
...
            EvaluationCaseResult.__table__,
            EvaluationVariant.__table__,
        ],
```

### File: `tests/test_eval_variants.py` (new)
Two test classes: `TestFreshDbCreation` (7 tests — table creation, column set, FK to eval_datasets, dataset_id index, eval_runs new columns, variant round-trip, run+delta_snapshot round-trip) and `TestMigrationOnExistingDb` (2 tests — columns added to pre-existing eval_runs, idempotent second run).

## Decisions

### Placement of new `EvaluationRun` fields
**Choice:** Added `variant_id` and `delta_snapshot` at the end of `EvaluationRun`'s field list (after `completed_at`).
**Rationale:** Keeps new additive columns grouped; matches the `_migrate_add_columns` path where legacy DBs append columns at end.

### Dataset_id index explicit Index() vs index=True
**Choice:** Used both (`index=True` on the Field + explicit `Index("ix_eval_variants_dataset", ...)` in `__table_args__`).
**Rationale:** Matches existing pattern on `EvaluationCase` and `EvaluationRun`. Explicit named index ensures the name is stable and testable.

### Test isolation — closing sessions before asserting
**Choice:** Capture PKs inside the write session; reopen for reads; assert within the read session.
**Rationale:** First test pass hit `DetachedInstanceError` when accessing `.id` of a committed object after the session closed. Fixed by keeping assertions within an open session.

## Verification
- [x] `init_pipeline_db()` creates `eval_variants` table on fresh SQLite
- [x] `eval_variants` has correct columns (id, dataset_id, name, description, delta, created_at, updated_at)
- [x] FK `eval_variants.dataset_id -> eval_datasets.id` present
- [x] Index `ix_eval_variants_dataset` exists
- [x] `eval_runs` on fresh DB has `variant_id` + `delta_snapshot` columns
- [x] Legacy `eval_runs` (pre-existing table without new cols) gains `variant_id` + `delta_snapshot` after running `init_pipeline_db()`
- [x] Migration is idempotent (second init run does not raise)
- [x] Variant + run round-trip persistence works (JSON dict delta retrievable)
- [x] `__all__` exports `EvaluationVariant`
- [x] All 9 new tests pass
- [x] Existing `tests/test_init_pipeline_db.py`, `tests/test_eval_runner.py`, `tests/test_eval_yaml_sync.py` continue to pass
- [x] Pre-existing failures in `tests/test_evaluators.py::TestFieldMatchEvaluator` confirmed unrelated via `git stash` baseline check
