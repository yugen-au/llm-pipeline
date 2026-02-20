# Task Summary

## Work Completed

Implemented `PipelineIntrospector`, a pure class-level introspection service that extracts pipeline metadata (strategies, steps, schemas, prompt keys, extraction models, registry models, execution order) with no DB, FastAPI, or LLM dependencies. Added an optional `introspection_registry` parameter to `create_app()` for task 24 consumption. Exported `PipelineIntrospector` from the top-level package. Wrote 43 tests covering all metadata paths, caching, schema edge cases, broken strategy handling, and Pydantic/non-Pydantic transformation types. Went through one review cycle: 1 MEDIUM and 2 LOW issues fixed (double strategy instantiation, transformation test gap, redundant filter), 1 LOW accepted (extra metadata fields for task 24).

## Files Changed

### Created

| File | Purpose |
| --- | --- |
| `llm_pipeline/introspection.py` | `PipelineIntrospector` class - class-level cache, regex-matched name derivation per source module, defensive strategy instantiation, Pydantic/non-Pydantic schema extraction, extraction method discovery via `dir()` diff |
| `tests/test_introspection.py` | 43 tests across 9 test classes covering all introspection paths |

### Modified

| File | Changes |
| --- | --- |
| `llm_pipeline/ui/app.py` | Added `introspection_registry: Optional[Dict[str, Type["PipelineConfig"]]] = None` param to `create_app()`; stored on `app.state.introspection_registry`; `from __future__ import annotations` + `TYPE_CHECKING` guard for circular import avoidance |
| `llm_pipeline/__init__.py` | Added `from llm_pipeline.introspection import PipelineIntrospector` and `"PipelineIntrospector"` to `__all__` under `# Introspection` comment |

## Commits Made

| Hash | Message |
| --- | --- |
| `92e9ce8` | `docs(implementation-A): master-23-introspection-service` |
| `8899b4e` | `docs(implementation-B): master-23-introspection-service` |
| `198d325` | `docs(implementation-B): master-23-introspection-service` |
| `e9dc4df` | `docs(implementation-B): master-23-introspection-service` |
| `272e37c` | `docs(fixing-review-A): master-23-introspection-service` |
| `9580bbe` | `docs(fixing-review-B): master-23-introspection-service` |

## Deviations from Plan

- Step entries include extra fields `context_class`, `context_schema`, `action_after` not listed in PLAN.md success criteria. Accepted: task 24 will consume these fields; simple attribute reads on already-available objects.
- `_introspect_strategy()` signature changed post-review to accept pre-resolved `step_defs` (from double-instantiation fix). Behavior matches plan intent.

## Issues Encountered

### MEDIUM - Double strategy instantiation in get_metadata()
Each strategy class was instantiated twice per `get_metadata()` call: once in `_introspect_strategy()` and again in the execution_order derivation loop. Negligible in practice (results are cached after first call) but wasteful on cache miss for pipelines with many strategies.

**Resolution:** Refactored `get_metadata()` to build a `resolved` list of `(strategy_cls, step_defs, error)` tuples in a single pass. Both `_introspect_strategy()` and the execution_order loop consume the same resolved list. Commit `272e37c`.

### LOW - No test coverage for transformation introspection path
Initial test pipeline (`WidgetPipeline`) had no transformation, leaving `_introspect_strategy()` L177-191 (transformation dict construction) untested. The non-Pydantic schema fallback was tested separately but the full path was not.

**Resolution:** Added `TestTransformation` class (11 tests) with three pipelines: `ScanPipeline` (Pydantic `TransformInput`/`TransformOutput`), `GadgetPipeline` (non-Pydantic `PlainInput`/`PlainOutput`), `WidgetPipeline` (no transformation). Covers class_name, type names, schema extraction, fallback, and null case. Commit `9580bbe`.

### LOW - Redundant "extract" filter in _get_extraction_methods
`m != "extract"` filter was redundant: `"extract"` is already in `set(dir(PipelineExtraction))` so the set difference removes it before the filter runs. Harmless but misleading.

**Resolution:** Removed the explicit filter. Set difference already handles exclusion. Commit `272e37c`.

### Pre-existing - test_events_router_prefix failure
`tests/test_ui.py::TestRoutersIncluded::test_events_router_prefix` asserts `r.prefix == "/events"` but actual prefix is `"/runs/{run_id}/events"`. Present on `dev` before this task. Not introduced here.

**Resolution:** Not resolved; pre-existing from task 21. Requires separate fix task.

### Pre-existing - WAL test isolation failure
`tests/ui/test_wal.py::TestWALMode::test_file_based_sqlite_sets_wal` fails in full suite (journal_mode returns `delete` instead of `wal`) but passes in isolation. DB state bleed from test ordering.

**Resolution:** Not resolved; pre-existing test isolation issue. Requires separate fix task.

## Success Criteria

- [x] `llm_pipeline/introspection.py` exists with `PipelineIntrospector` class
- [x] `PipelineIntrospector` importable from `llm_pipeline` top-level package
- [x] `get_metadata()` returns dict with keys: `pipeline_name`, `registry_models`, `strategies`, `execution_order`
- [x] Each strategy entry contains `name`, `display_name`, `class_name`, `steps`
- [x] Each step entry contains `step_name`, `system_key`, `user_key`, `instructions_class`, `instructions_schema`, `extractions`, `transformation`
- [x] `instructions_schema` is valid JSON Schema dict for Pydantic instruction classes
- [x] Non-Pydantic transformation types do not raise; return `{"type": type_name}` fallback
- [x] Broken strategy `__init__` does not propagate exception; captured in `"error"` key
- [x] Calling `get_metadata()` twice returns cached result (same object, `is` check passes)
- [x] `create_app()` still works with no `introspection_registry` argument (backward-compat)
- [x] `create_app()` stores `introspection_registry` on `app.state.introspection_registry`
- [x] All new tests pass with `pytest` (43/43 introspection tests pass)
- [x] No imports of `fastapi`, `sqlalchemy`, or `sqlmodel` in `introspection.py`

## Recommendations for Follow-up

1. Task 21 pre-existing failure: fix `test_events_router_prefix` - assert should match actual prefix `"/runs/{run_id}/events"` or route should be corrected.
2. WAL test isolation: give `test_file_based_sqlite_sets_wal` its own temp DB path guaranteed not shared with other tests in full suite run.
3. Task 24 (planned): consume `app.state.introspection_registry` via `PipelineIntrospector` to serve pipeline metadata over HTTP. `context_class`, `context_schema`, `action_after` fields in step metadata are pre-populated for this.
4. Consider adding `__repr__` to `PipelineIntrospector` for clearer debugging output in REPL sessions.
5. Consider documenting the class-level cache lifetime (process-lifetime) in module docstring; callers dynamically redefining pipeline classes at runtime will get stale cache entries.
