# IMPLEMENTATION - STEP 6: PROMPT READ-SITE UPDATES
**Status:** completed

## Summary
Added `is_latest==True` (and `is_active==True` where applicable) filters to all prompt read sites across the codebase, ensuring only the current version row is returned in runtime queries.

## Files
**Created:** none
**Modified:**
- llm_pipeline/prompts/resolver.py
- llm_pipeline/prompts/service.py
- llm_pipeline/pipeline.py
- llm_pipeline/introspection.py
- llm_pipeline/ui/routes/editor.py
- llm_pipeline/ui/routes/evals.py
- llm_pipeline/ui/routes/pipelines.py
- llm_pipeline/ui/routes/prompts.py
- llm_pipeline/ui/app.py
- llm_pipeline/sandbox.py
- llm_pipeline/evals/runner.py
**Deleted:** none

## Changes
### File: `llm_pipeline/prompts/resolver.py`
Tag #1: Added `Prompt.is_latest == True` to `_lookup_prompt_key` query.

### File: `llm_pipeline/prompts/service.py`
Tags #2, #3: Added `Prompt.is_latest == True` to `get_prompt` stmt and `prompt_exists` query.

### File: `llm_pipeline/pipeline.py`
Tags #4, #5: Added `Prompt.is_active == True` and `Prompt.is_latest == True` to both `_find_cached_state` and `_save_step_state` prompt lookups.

### File: `llm_pipeline/introspection.py`
Tag #6: Added `Prompt.is_latest == True` to `enrich_with_prompt_readiness` query.

### File: `llm_pipeline/ui/routes/editor.py`
Tag #7: Replaced `Prompt.is_active.is_(True)` with `Prompt.is_active == True` and added `Prompt.is_latest == True` in compile endpoint prompt-key check.

### File: `llm_pipeline/ui/routes/evals.py`
Tag #8: Added `Prompt.is_active == True` and `Prompt.is_latest == True` to `_fetch` helper in prod-prompts endpoint.

### File: `llm_pipeline/ui/routes/pipelines.py`
Tag #9: Added `Prompt.is_active == True` and `Prompt.is_latest == True` to step-prompts query.

### File: `llm_pipeline/ui/routes/prompts.py`
Tag #10: Added `Prompt.is_latest == True` as default in `_apply_filters` (list endpoint).
Tags #12, #13: Already using `get_latest`/`soft_delete_latest` from prior step.
Tag #14: Added `Prompt.is_latest == True` to variable-schema endpoint.

### File: `llm_pipeline/ui/app.py`
Tag #17: Added `Prompt.is_latest == True` to `_sync_variable_definitions` query.

### File: `llm_pipeline/sandbox.py`
Tag #16: Added `Prompt.is_active == True` and `Prompt.is_latest == True` to sandbox seed query.

### File: `llm_pipeline/evals/runner.py`
Tag #18: Added `Prompt.is_latest == True` defence-in-depth to sandbox variant override lookups (system + user).

### Files: `llm_pipeline/creator/prompts.py`, `llm_pipeline/creator/integrator.py`
Tags #19, #20: Already converted to `get_latest(...)` in prior step. No changes needed.

## Decisions
### Detail endpoint excluded from is_latest filter
**Choice:** `GET /prompts/{prompt_key}` detail endpoint intentionally shows ALL versions for a given key (including historical).
**Rationale:** The endpoint docstring states it shows "everything for a given key" - this is the version-history view. The list endpoint handles active/latest filtering for browsing.

### Sandbox seed filtered at source
**Choice:** Filter sandbox seed query by both `is_active` and `is_latest` rather than copying all rows.
**Rationale:** Sandbox only needs current prompts for execution; copying historical versions wastes memory and could cause ambiguity in sandbox queries.

## Verification
[x] All 17+ read sites audited via grep for `select(Prompt)`
[x] `uv run pytest tests/prompts/ tests/test_versioning_helpers.py` passes (50 tests)
[x] Pre-existing test failure unrelated (creator/test_sandbox.py attribute error)
[x] No remaining unfiltered `select(Prompt)` except intentional detail-view endpoint
