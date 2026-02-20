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
