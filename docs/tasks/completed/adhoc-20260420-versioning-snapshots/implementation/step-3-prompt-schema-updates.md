# IMPLEMENTATION - STEP 3: PROMPT SCHEMA UPDATES
**Status:** completed

## Summary
Added `is_latest` boolean column to `Prompt` model and replaced legacy `UniqueConstraint` with partial unique index + supporting composite indexes per VALIDATED_RESEARCH section 2.1.

## Files
**Created:** none
**Modified:** `llm_pipeline/db/prompt.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/db/prompt.py`
Added `is_latest` field, dropped `UniqueConstraint` and `ix_prompts_active` index, added partial unique index and two supporting indexes. Updated imports (`Index, text` from sqlalchemy; removed `UniqueConstraint`).

```
# Before
from sqlalchemy import UniqueConstraint

is_active: bool = Field(default=True)
created_at: datetime = ...

__table_args__ = (
    UniqueConstraint('prompt_key', 'prompt_type', name='uq_prompts_key_type'),
    Index("ix_prompts_active", "is_active"),
    Index("ix_prompts_category_step", "category", "step_name"),
)

# After
from sqlalchemy import Index, text

is_active: bool = Field(default=True)
is_latest: bool = Field(default=True, index=True)
created_at: datetime = ...

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

## Decisions
### None
No additional decisions required; implementation follows VALIDATED_RESEARCH section 2.1 exactly.

## Verification
[x] `is_latest` field placed after `is_active` with correct type, default, and index
[x] `UniqueConstraint` removed from `__table_args__`
[x] `ix_prompts_active` index removed (A7 - redundant)
[x] Partial unique index `uq_prompts_active_latest` matches spec (sqlite_where + postgresql_where)
[x] `ix_prompts_key_type_live` composite index present
[x] `ix_prompts_category_step` retained
[x] `ix_prompts_key_type_version` added for version lookups
[x] Imports updated: `from sqlalchemy import Index, text`; `UniqueConstraint` removed
[x] Committed as 8ac73d59

## Commit Reference
`8ac73d59` - feat(db): add is_latest to Prompt, replace unique constraint with partial unique index
