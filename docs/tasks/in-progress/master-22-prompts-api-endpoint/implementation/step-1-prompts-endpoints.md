# IMPLEMENTATION - STEP 1: PROMPTS ENDPOINTS
**Status:** completed

## Summary
Implemented GET /api/prompts (paginated list with filters) and GET /api/prompts/{prompt_key} (grouped detail) in the existing prompts router stub. Added response models, query params model, helper functions, and two sync def endpoints following exact patterns from runs.py.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/routes/prompts.py
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/prompts.py`
Replaced 4-line stub with full implementation: response models (PromptItem, PromptListResponse, PromptVariant, PromptDetailResponse), query params model (PromptListParams), helpers (_resolve_variables, _to_prompt_item, _apply_filters), and two endpoints (list_prompts, get_prompt).

```
# Before
"""Prompts route module."""
from fastapi import APIRouter

router = APIRouter(prefix="/prompts", tags=["prompts"])

# After
"""Prompts route module -- list and detail endpoints."""
# ... 170 lines with imports, models, helpers, endpoints
# See full file at llm_pipeline/ui/routes/prompts.py
```

Key implementation details:
- Response models: plain Pydantic BaseModel (not SQLModel), matching runs.py convention
- PromptListParams: category, step_name, prompt_type, is_active (default True), offset, limit
- _resolve_variables: returns stored required_variables when non-null, fallback to extract_variables_from_content()
- list_prompts: count + data query with filters, order_by(prompt_key, prompt_type), offset/limit
- get_prompt: queries all rows for prompt_key (no is_active filter), 404 if none, returns grouped wrapper

## Decisions
### Variable Resolution Strategy
**Choice:** Hybrid -- stored value when non-null, extract_variables_from_content fallback when null
**Rationale:** Synced rows have stored values (fast path). Manual/pre-sync rows may have null. Fallback returns [] for content with no {var} patterns, which is consistent with stored [].

### Detail Endpoint Active Filtering
**Choice:** No is_active filter on GET /{prompt_key} -- returns all variants regardless of status
**Rationale:** Detail endpoint shows complete state for a key. List endpoint handles active filtering for browsing. Documented in docstring.

## Verification
[x] Module imports cleanly (python -c "from llm_pipeline.ui.routes.prompts import ...")
[x] All 152 existing UI tests pass (pytest tests/ui/ -x -q)
[x] No regressions in runs, steps, events tests
[x] Follows exact patterns from runs.py (sync def, DBSession, BaseModel, comment banners, _apply_filters)
[x] Router already mounted in app.py -- no app changes needed

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] MEDIUM - DRY violation: get_prompt duplicated field mapping instead of reusing _to_prompt_item
[x] LOW - PromptVariant duplicated PromptItem fields; replaced with type alias

### Changes Made
#### File: `llm_pipeline/ui/routes/prompts.py`
Made PromptVariant a type alias for PromptItem (identical fields) and replaced manual mapping in get_prompt with _to_prompt_item reuse.

```
# Before (PromptVariant was a separate class with same fields)
class PromptVariant(BaseModel):
    id: int
    prompt_key: str
    ...  # 12 more identical fields

# After
PromptVariant = PromptItem

# Before (get_prompt manually mapped all fields)
variants=[PromptVariant(id=r.id, prompt_key=r.prompt_key, ...) for r in rows]

# After
variants=[_to_prompt_item(r) for r in rows]
```

### Verification
[x] Module imports cleanly, PromptVariant is PromptItem confirmed
[x] All 169 UI tests pass (pytest tests/ui/ -x -q)
[x] No regressions
