# IMPLEMENTATION - STEP 1: CREATE INTROSPECTION MODULE
**Status:** completed

## Summary
Created `llm_pipeline/introspection.py` with `PipelineIntrospector` class implementing pure class-level introspection. No DB, LLM, or FastAPI dependencies. All 13 substeps from PLAN.md completed.

## Files
**Created:** `llm_pipeline/introspection.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/introspection.py`
New module with `PipelineIntrospector` class containing:
- `_cache: ClassVar[Dict[int, Dict]]` keyed by `id(pipeline_cls)` for cross-caller dedup
- `__init__(self, pipeline_cls)` storing reference
- `_pipeline_name(cls)` - single regex from pipeline.py L244-245
- `_strategy_name(cls)` - double regex from strategy.py L188-191
- `_step_name(cls)` - single regex from step.py L260-261
- `_get_schema(cls)` - BaseModel guard before `model_json_schema()`, fallback to `{"type": name}`
- `_get_extraction_methods(extraction_cls)` - `dir()` comparison with PipelineExtraction base
- `_introspect_strategy(strategy_cls)` - defensive try/except around instantiation + get_steps()
- `get_metadata()` - cached, returns `pipeline_name`, `registry_models`, `strategies`, `execution_order`
- `execution_order` deduplication by step_class (first occurrence wins)
- `__all__ = ["PipelineIntrospector"]`

## Decisions
### Cache Key: id() vs class type
**Choice:** `id(self._pipeline_cls)` as cache key
**Rationale:** Plan specified `id(pipeline_cls)`. Class types are hashable so either works, but id() matches the plan spec exactly.

### Static methods for name derivation
**Choice:** `@staticmethod` for `_pipeline_name`, `_strategy_name`, `_step_name`, `_get_schema`, `_get_extraction_methods`
**Rationale:** These don't need instance state; static makes them testable in isolation and reusable.

### Strategy NAME/DISPLAY_NAME fallback
**Choice:** Use `getattr(cls, "NAME", self._strategy_name(cls))` with fallback
**Rationale:** Concrete strategies set NAME via `__init_subclass__`, but the fallback handles edge cases where a strategy might not have gone through normal subclass init.

## Verification
[x] Module has no imports of fastapi, sqlalchemy, or sqlmodel
[x] `from llm_pipeline.introspection import PipelineIntrospector` succeeds
[x] `get_metadata()` returns dict with keys: pipeline_name, registry_models, strategies, execution_order
[x] Each strategy entry has name, display_name, class_name, steps
[x] Each step entry has step_name, system_key, user_key, instructions_class, instructions_schema, extractions
[x] Each extraction entry has class_name, model_class, methods list
[x] `_get_schema()` with non-Pydantic type returns `{"type": type_name}` without raising
[x] `_get_schema(None)` returns None
[x] Broken strategy `__init__` returns error dict, not exception
[x] `get_metadata()` called twice returns same cached object (identity check passes)
[x] execution_order is deduplicated list of step name strings
[x] Existing tests pass (505 passed, pre-existing UI failures only)

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] MEDIUM - Double strategy instantiation: strategy_cls() called twice per get_metadata() -- once in _introspect_strategy() and again in execution_order loop. Refactored to instantiate once.
[x] LOW - Redundant "extract" filter in _get_extraction_methods(): `m != "extract"` unnecessary since "extract" already in set(dir(PipelineExtraction)).

### Changes Made
#### File: `llm_pipeline/introspection.py`
**Fix 1:** Moved strategy instantiation + get_steps() into get_metadata() as a single resolution pass. Results stored in `resolved: List[tuple]` (strategy_cls, step_defs, error). `_introspect_strategy()` now takes pre-resolved step_defs instead of instantiating itself. Error-case strategies handled directly in get_metadata(). execution_order loop reuses same resolved list.

```
# Before: _introspect_strategy() instantiated, then execution_order loop instantiated again
strategies = [self._introspect_strategy(s_cls) for s_cls in strategy_classes]
for s_cls in strategy_classes:
    instance = s_cls()  # DUPLICATE
    step_defs = instance.get_steps()

# After: single resolution pass, both consumers use resolved list
resolved = []
for s_cls in strategy_classes:
    try:
        instance = s_cls()
        step_defs = instance.get_steps()
        resolved.append((s_cls, step_defs, None))
    except Exception as exc:
        resolved.append((s_cls, None, exc))
# _introspect_strategy(s_cls, step_defs) and execution_order both read from resolved
```

**Fix 2:** Removed `and m != "extract"` from _get_extraction_methods() filter.

```
# Before
if callable(...) and not m.startswith("_") and m != "extract"

# After
if callable(...) and not m.startswith("_")
```

### Verification
[x] get_metadata() output identical to before (same JSON structure, same values)
[x] Caching still works (identity check passes)
[x] Broken strategy still produces error dict with "error" key
[x] _get_extraction_methods still returns ["default"] for WidgetExtraction
[x] 520 tests pass (excluding pre-existing UI failures)
