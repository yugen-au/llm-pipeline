# IMPLEMENTATION - STEP 2: STRUCTURAL VALIDATIONS
**Status:** completed

## Summary
Added 4 structural validation passes to compile_pipeline() after the existing step-ref existence check: duplicate step_ref detection, empty strategy detection, position gap/duplicate detection, and prompt key existence checking for registered steps.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/routes/editor.py
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/editor.py`

Added import for `Prompt` from `llm_pipeline.db.prompt`.

Added `_collect_registered_prompt_keys()` helper that builds step_name -> [prompt_keys] mapping from introspection metadata (system_key, user_key). Wrapped in try/except matching existing `_collect_registered_steps` pattern -- skips pipelines that fail introspection.

Added 4 validation passes in `compile_pipeline()`:

**Pass 2 - Duplicate step_ref:** Counts occurrences of each step_ref per strategy, emits error with `field="step_ref"` when count > 1.

**Pass 3 - Empty strategies:** Checks `len(strategy.steps) == 0`, emits error with `step_ref=""`, `field="steps"`, message format `"Strategy '{name}' has no steps"`.

**Pass 4 - Position gaps/duplicates:** Collects positions per strategy, checks for duplicate positions first, then checks if sorted positions match expected `range(0, N)`. Emits error with `field="position"`. Only emits gap error when no duplicate positions (avoids double-reporting).

**Pass 5 - Prompt key existence:** Collects expected prompt keys for registered steps via `_collect_registered_prompt_keys()`, does single batch query `select(Prompt.prompt_key).where(Prompt.prompt_key.in_(...))`, emits warning (not error) with `field="prompt_key"` for missing keys.

Changed `valid` calculation from `len(errors) == 0` to `not any(e.severity == "error" for e in errors)` so warnings (prompt key issues) don't mark pipeline as invalid.

## Decisions
### valid flag considers severity
**Choice:** `valid` is True when no "error"-severity items exist, even if warnings present
**Rationale:** Prompt key warnings are advisory (step may not need prompts yet). Frontend should show warnings but not block save/deploy.

### Single batch query for prompt keys
**Choice:** Collect all expected keys across all strategies, query once, then distribute results
**Rationale:** Avoids N+1 queries. Single SELECT with IN clause is efficient for any reasonable number of prompt keys.

### Position validation: duplicate check before gap check
**Choice:** Only emit gap error when no duplicate positions found
**Rationale:** Duplicate positions inherently create gaps; reporting both would be noisy and redundant.

## Verification
[x] Python syntax check passes
[x] Runtime import succeeds
[x] All 4 validation passes implemented in correct order (2-5)
[x] Prompt key check uses try/except pattern matching _collect_registered_steps
[x] CompileError fields match plan: field, severity set correctly per pass

## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
[x] Prompt key existence query missing `Prompt.is_active` filter -- inactive prompts treated as present, suppressing warnings

### Changes Made
#### File: `llm_pipeline/ui/routes/editor.py`
Added `Prompt.is_active.is_(True)` to the where clause in Pass 5 prompt key query.
```
# Before
stmt = select(Prompt.prompt_key).where(
    Prompt.prompt_key.in_(list(all_expected_keys))
)

# After
stmt = select(Prompt.prompt_key).where(
    Prompt.prompt_key.in_(list(all_expected_keys)),
    Prompt.is_active.is_(True),
)
```

### Verification
[x] Python syntax check passes
[x] Runtime import succeeds
[x] Query now filters on `is_active` index (`ix_prompts_active`)
