# IMPLEMENTATION - STEP 1: IMPLEMENT ENDPOINTS
**Status:** completed

## Summary
Implemented two REST endpoints in `llm_pipeline/ui/routes/pipelines.py`: GET list (all registered pipelines with summary counts) and GET detail (full introspection metadata for a single pipeline). Added six Pydantic response models.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/routes/pipelines.py
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/pipelines.py`
Replaced empty router shell with full endpoint implementation: imports, 6 Pydantic models, 2 endpoint functions.

```
# Before
"""Pipeline configurations route module."""
from fastapi import APIRouter

router = APIRouter(prefix="/pipelines", tags=["pipelines"])

# After
- Added imports: logging, typing (Any/Dict/List/Optional), HTTPException, Request, BaseModel, PipelineIntrospector
- PipelineListItem: name, strategy_count, step_count, has_input_schema, registry_model_count, error
- PipelineListResponse: pipelines list wrapper (no pagination -- CEO decision)
- StepMetadata: step fields with Any for schema/extraction/transformation dicts
- StrategyMetadata: name, display_name, class_name, steps list, optional error
- PipelineMetadata: pipeline_name, registry_models, strategies, execution_order
- GET "" (list_pipelines): sorted iteration, per-pipeline try/except, error flag pattern
- GET "/{name}" (get_pipeline): 404 if missing, 500 on introspection failure
```

## Decisions
### Use `Any` for nested schema fields in detail models
**Choice:** StepMetadata uses `Optional[Any]` for instructions_schema, context_schema, extractions, transformation
**Rationale:** Avoids tight coupling to introspector internals. These are JSON-serializable dicts/lists whose shape may evolve. Plan explicitly calls for this.

### Sync def endpoints with Request parameter
**Choice:** Sync functions using `request.app.state.introspection_registry`
**Rationale:** Matches existing non-DB access pattern (trigger_run in runs.py). No DB dependency needed -- pure class-level introspection.

## Verification
[x] Imports resolve (`python -c "from llm_pipeline.ui.routes.pipelines import ..."` passes)
[x] No changes to app.py (router already wired at line 72, 79)
[x] Response shape matches frontend contract: `{ pipelines: [...] }` for list, introspector dict shape for detail
[x] PipelineListItem includes all 6 fields per CEO decision
[x] Alphabetical sort via `sorted(registry.items(), key=lambda x: x[0])`
[x] Per-pipeline error handling with error flag + null counts + has_input_schema=False
[x] 404 for unknown name, 500 for introspection failure on detail endpoint

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] Remove unused `Dict` import from typing imports

### Changes Made
#### File: `llm_pipeline/ui/routes/pipelines.py`
Removed unused `Dict` from typing import line. Code only uses builtin `dict` annotation.
```
# Before
from typing import Any, Dict, List, Optional

# After
from typing import Any, List, Optional
```

### Verification
[x] Imports resolve (`python -c "from llm_pipeline.ui.routes.pipelines import ..."` passes)
[x] No other references to `Dict` in file
