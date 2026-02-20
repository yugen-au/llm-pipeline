# IMPLEMENTATION - STEP 2: UPDATE CREATE_APP
**Status:** completed

## Summary
Added optional `introspection_registry` parameter to `create_app()` in `llm_pipeline/ui/app.py`. Fully backward-compatible; stored on `app.state.introspection_registry`. Uses `TYPE_CHECKING` guard to avoid circular imports with `PipelineConfig`.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/app.py
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/app.py`
Added `introspection_registry` param, TYPE_CHECKING import for PipelineConfig, stored on app.state.

```python
# Before
from typing import Optional

def create_app(
    db_path: Optional[str] = None,
    cors_origins: Optional[list] = None,
    pipeline_registry: Optional[dict] = None,
) -> FastAPI:

    app.state.pipeline_registry = pipeline_registry or {}

# After
from __future__ import annotations
from typing import TYPE_CHECKING, Dict, Optional, Type

if TYPE_CHECKING:
    from llm_pipeline.pipeline import PipelineConfig

def create_app(
    db_path: Optional[str] = None,
    cors_origins: Optional[list] = None,
    pipeline_registry: Optional[dict] = None,
    introspection_registry: Optional[Dict[str, Type[PipelineConfig]]] = None,
) -> FastAPI:

    app.state.pipeline_registry = pipeline_registry or {}
    app.state.introspection_registry = introspection_registry or {}
```

## Decisions
### from __future__ import annotations
**Choice:** Added `from __future__ import annotations` for PEP 604 style and to ensure string annotations work cleanly with TYPE_CHECKING guard.
**Rationale:** Ensures `Type[PipelineConfig]` in signature is not evaluated at runtime, avoiding circular import without needing manual string quoting.

## Verification
[x] All existing create_app() tests pass (17/17; 1 pre-existing failure in unrelated events prefix test)
[x] No new parameter required - Optional with None default
[x] TYPE_CHECKING guard prevents circular import at runtime
[x] app.state.introspection_registry defaults to {} when not provided
