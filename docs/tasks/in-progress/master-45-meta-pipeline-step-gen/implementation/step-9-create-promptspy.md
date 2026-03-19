# IMPLEMENTATION - STEP 9: CREATE PROMPTS.PY
**Status:** completed

## Summary
Created `llm_pipeline/creator/prompts.py` with 8 prompt seed dicts (system+user for each of the 4 meta-pipeline steps) and `seed_prompts()` function following the exact pattern from `llm_pipeline/demo/prompts.py`.

## Files
**Created:** `llm_pipeline/creator/prompts.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/creator/prompts.py`
New file. Contains:
- 4 system prompt dicts: `REQUIREMENTS_ANALYSIS_SYSTEM`, `CODE_GENERATION_SYSTEM`, `PROMPT_GENERATION_SYSTEM`, `CODE_VALIDATION_SYSTEM`
- 4 user prompt dicts: `REQUIREMENTS_ANALYSIS_USER`, `CODE_GENERATION_USER`, `PROMPT_GENERATION_USER`, `CODE_VALIDATION_USER`
- `ALL_PROMPTS: list[dict]` with all 8 dicts
- `seed_prompts(cls, engine)` that creates `GenerationRecord` table then idempotently inserts prompts by (prompt_key, prompt_type)
- `__all__ = ["ALL_PROMPTS", "seed_prompts"]`

## Decisions
### seed_prompts table creation
**Choice:** Creates `GenerationRecord.__table__` via `SQLModel.metadata.create_all()` (same pattern as demo creates `Topic.__table__`).
**Rationale:** PLAN.md step 9 item 10 specifies this. GenerationRecord is the only creator-specific table; ensures it exists before any pipeline run calls seed_prompts.

### required_variables consistency
**Choice:** `required_variables` lists exactly match `{placeholder}` names in `content` strings.
**Rationale:** Verified programmatically. Prevents runtime KeyError when prompts are rendered with str.format().

## Verification
- [x] `from llm_pipeline.creator.prompts import ALL_PROMPTS, seed_prompts` imports cleanly
- [x] `len(ALL_PROMPTS) == 8`
- [x] All 8 dicts have required keys: prompt_key, prompt_name, prompt_type, category, step_name, content, required_variables, description
- [x] All dicts have `category == "step_creator"`
- [x] `required_variables` in each user prompt matches `{placeholders}` in content
- [x] System prompts have `required_variables == []`
