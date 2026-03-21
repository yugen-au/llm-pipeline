# IMPLEMENTATION - STEP 1: ENHANCE MODELS
**Status:** completed

## Summary
Added `draft_id` to CompileRequest and `field`/`severity` to CompileError. No structural changes to CompileResponse (errors list already present).

## Files
**Created:** none
**Modified:** llm_pipeline/ui/routes/editor.py
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/editor.py`
Added two fields to CompileError and one field to CompileRequest.

```
# Before
class CompileRequest(BaseModel):
    strategies: list[EditorStrategy]

class CompileError(BaseModel):
    strategy_name: str
    step_ref: str
    message: str

# After
class CompileRequest(BaseModel):
    strategies: list[EditorStrategy]
    draft_id: int | None = None

class CompileError(BaseModel):
    strategy_name: str
    step_ref: str
    message: str
    field: str | None = None
    severity: Literal["error", "warning"] = "error"
```

## Decisions
### Field defaults
**Choice:** `field=None`, `severity="error"` as defaults
**Rationale:** Backward compatible -- existing compile callers send no field/severity and get error-level defaults. Literal type already imported at module top.

### draft_id placement
**Choice:** Added to CompileRequest (not CompileResponse)
**Rationale:** draft_id is input-only; response shape unchanged. Step 3 will use it for stateful write path.

## Verification
[x] CompileError has `field: str | None = None`
[x] CompileError has `severity: Literal["error", "warning"] = "error"`
[x] CompileRequest has `draft_id: int | None = None`
[x] CompileResponse unchanged
[x] `Literal` already imported at line 4 -- no new import needed
[x] Existing compile_pipeline() callers unaffected (new fields have defaults)
