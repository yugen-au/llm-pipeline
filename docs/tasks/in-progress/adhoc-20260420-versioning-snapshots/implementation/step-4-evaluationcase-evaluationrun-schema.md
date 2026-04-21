# IMPLEMENTATION - STEP 4: EVALUATIONCASE + EVALUATIONRUN SCHEMA
**Status:** completed

## Summary
Added versioning columns to EvaluationCase and run-snapshot JSON columns to EvaluationRun, with partial unique index enforcement per VALIDATED_RESEARCH sections 2.2 and 2.3.

## Files
**Created:** none
**Modified:** llm_pipeline/evals/models.py
**Deleted:** none

## Changes
### File: `llm_pipeline/evals/models.py`

Added `text` to sqlalchemy imports. Added four columns to EvaluationCase: `version` (str, default "1.0"), `is_active` (bool, default True), `is_latest` (bool, default True, indexed), `updated_at` (datetime, default utc_now). Added partial unique index `uq_eval_cases_active_latest` on (dataset_id, name) WHERE is_active AND is_latest, plus supporting indexes `ix_eval_cases_dataset_live` and `ix_eval_cases_dataset_name_version`. Added four nullable JSON snapshot columns to EvaluationRun after delta_snapshot: `case_versions`, `prompt_versions`, `model_snapshot`, `instructions_schema_snapshot`.

```
# Before (imports)
from sqlalchemy import Index

# After (imports)
from sqlalchemy import Index, text
```

```
# Before (EvaluationCase columns + table_args)
metadata_: Optional[dict] = Field(default=None, sa_column=Column(JSON))
created_at: datetime = Field(default_factory=utc_now)

__table_args__ = (
    Index("ix_eval_cases_dataset", "dataset_id"),
)

# After
metadata_: Optional[dict] = Field(default=None, sa_column=Column(JSON))
version: str = Field(default="1.0", max_length=20)
is_active: bool = Field(default=True)
is_latest: bool = Field(default=True, index=True)
created_at: datetime = Field(default_factory=utc_now)
updated_at: datetime = Field(default_factory=utc_now)

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

```
# Before (EvaluationRun - after delta_snapshot)
delta_snapshot: Optional[dict] = Field(default=None, sa_column=Column(JSON))

# After
delta_snapshot: Optional[dict] = Field(default=None, sa_column=Column(JSON))
case_versions: Optional[dict] = Field(default=None, sa_column=Column(JSON))
prompt_versions: Optional[dict] = Field(default=None, sa_column=Column(JSON))
model_snapshot: Optional[dict] = Field(default=None, sa_column=Column(JSON))
instructions_schema_snapshot: Optional[dict] = Field(default=None, sa_column=Column(JSON))
```

## Decisions
None - all decisions follow VALIDATED_RESEARCH spec exactly.

## Verification
[x] EvaluationCase columns match VALIDATED_RESEARCH section 2.2 exactly
[x] EvaluationCase __table_args__ match section 2.2 exactly (partial unique + 3 supporting indexes)
[x] EvaluationRun snapshot columns match section 2.3 exactly (4 nullable JSON columns after delta_snapshot)
[x] Import of `text` from sqlalchemy added
[x] Existing imports (JSON, Column, Optional, datetime, utc_now) already present
