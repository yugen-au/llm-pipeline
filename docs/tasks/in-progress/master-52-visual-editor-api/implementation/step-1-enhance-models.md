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

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] EditorStep.position accepts negative ints breaking range(0, N) gap check -- added `Field(ge=0)`
[x] EditorStep.step_ref unbounded string -- added `Field(max_length=200)`
[x] EditorStrategy.strategy_name unbounded string -- added `Field(max_length=200)`
[x] CompileRequest.strategies list has no max length -- added `Field(max_length=100)`
[x] EditorStrategy.steps list has no max length -- added `Field(max_length=500)`

### Changes Made
#### File: `llm_pipeline/ui/routes/editor.py`
Added `Field` import from pydantic. Applied validation constraints to all request model fields.

```
# Before
from pydantic import BaseModel

class EditorStep(BaseModel):
    step_ref: str
    source: Literal["draft", "registered"]
    position: int

class EditorStrategy(BaseModel):
    strategy_name: str
    steps: list[EditorStep]

class CompileRequest(BaseModel):
    strategies: list[EditorStrategy]

# After
from pydantic import BaseModel, Field

class EditorStep(BaseModel):
    step_ref: str = Field(max_length=200)
    source: Literal["draft", "registered"]
    position: int = Field(ge=0)

class EditorStrategy(BaseModel):
    strategy_name: str = Field(max_length=200)
    steps: list[EditorStep] = Field(max_length=500)

class CompileRequest(BaseModel):
    strategies: list[EditorStrategy] = Field(max_length=100)
```

### Verification
[x] Negative position rejected by Pydantic before reaching compile logic
[x] String fields bounded at 200 chars
[x] List fields bounded (100 strategies, 500 steps per strategy)
[x] `Field` imported from pydantic
[x] Existing valid requests unaffected (constraints are generous upper bounds)
