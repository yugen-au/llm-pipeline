# IMPLEMENTATION - STEP 1: DISCOVERY LOGIC
**Status:** completed

## Summary
Added entry-point-based pipeline auto-discovery to `create_app()`. Scans `llm_pipeline.pipelines` group via `importlib.metadata`, validates loaded classes as `PipelineConfig` subclasses, builds factory closures capturing model, and merges discovered entries into both registries with explicit overrides winning.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/app.py
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/app.py`

Added imports: `importlib.metadata`, `inspect`, `logging`, `os`, `Callable`, `Tuple`. Added `logger`. Added `_make_pipeline_factory()` and `_discover_pipelines()` private helpers. Extended `create_app()` with `auto_discover` and `default_model` params. Model resolution (param > env > None) with warning. Discovery merges with explicit overrides winning.

```
# Before (imports)
from typing import TYPE_CHECKING, Dict, Optional, Type

# After (imports)
import importlib.metadata
import inspect
import logging
import os
from typing import TYPE_CHECKING, Callable, Dict, Optional, Tuple, Type
```

```
# Before (registry assignment, L68-69)
app.state.pipeline_registry = pipeline_registry or {}
app.state.introspection_registry = introspection_registry or {}

# After (model resolution + discovery + merge)
resolved_model = default_model or os.environ.get("LLM_PIPELINE_MODEL")
if resolved_model is None:
    logger.warning("No default model configured...")
app.state.default_model = resolved_model

if auto_discover:
    discovered_pipeline, discovered_introspection = _discover_pipelines(...)
    app.state.pipeline_registry = {**discovered_pipeline, **(pipeline_registry or {})}
    app.state.introspection_registry = {**discovered_introspection, **(introspection_registry or {})}
else:
    app.state.pipeline_registry = pipeline_registry or {}
    app.state.introspection_registry = introspection_registry or {}
```

## Decisions
### Registry key convention
**Choice:** `ep.name` as registry key for both registries
**Rationale:** Stable, publisher-controlled, matches task 2 CLI --pipelines dict keys. Avoids PipelineIntrospector single-regex naming bug.

### seed_prompts isolation
**Choice:** Separate try/except for seed_prompts after successful registration
**Rationale:** Pipeline stays registered even if seeding fails. Avoids silent pipeline loss.

### Factory closure kwargs
**Choice:** `**kwargs` in factory closure to absorb `input_data` from trigger_run call site
**Rationale:** trigger_run passes `input_data=...` to factory (runs.py L223) which PipelineConfig.__init__ does not accept. kwargs absorbs it cleanly.

### No hardcoded default model
**Choice:** param > env > None with warning; no hardcoded fallback
**Rationale:** CEO decision from VALIDATED_RESEARCH. Demo pipeline (task 3) owns its own default.

## Verification
[x] Imports resolve without error
[x] All 952 existing tests pass (0 failures, 6 skipped)
[x] create_app() backward compatible -- new params have defaults matching prior behavior
[x] auto_discover=True (default) scans entry points
[x] auto_discover=False skips discovery, uses explicit params only
[x] Explicit registries override discovered via {**discovered, **(explicit or {})}
[x] seed_prompts failure does not unregister pipeline (separate try/except)
[x] Load errors logged as warnings, not raised
[x] Model=None logs startup warning
[x] app.state.default_model set for Step 2 trigger_run guard
