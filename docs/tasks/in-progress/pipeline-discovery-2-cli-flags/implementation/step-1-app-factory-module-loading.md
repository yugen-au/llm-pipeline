# IMPLEMENTATION - STEP 1: APP FACTORY MODULE LOADING
**Status:** completed

## Summary
Added `_load_pipeline_modules` helper to `app.py` and extended `create_app` with `pipeline_modules: Optional[List[str]] = None`. The helper imports modules via `importlib.import_module`, scans for concrete `PipelineConfig` subclasses via `inspect`, builds factories with `_make_pipeline_factory`, calls `seed_prompts`, and returns registry dicts. Merge order: auto-discovered < module-loaded < explicit registry.

## Files
**Created:** none
**Modified:** `llm_pipeline/ui/app.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/app.py`

**Imports added:** `import importlib`, `List` to typing imports, `from llm_pipeline.naming import to_snake_case` (runtime, not TYPE_CHECKING).

**New function `_load_pipeline_modules`** (L107-168): placed after `_discover_pipelines`. Signature: `(module_paths: List[str], default_model: Optional[str], engine: Engine) -> Tuple[Dict[str, Callable], Dict[str, Type[PipelineConfig]]]`. For each module path: imports via `importlib.import_module` (raises `ValueError` wrapping `ImportError` on failure), scans with `inspect.getmembers(mod, inspect.isclass)`, filters `issubclass(cls, PipelineConfig) and cls is not PipelineConfig and not inspect.isabstract(cls)`, raises `ValueError` if no subclasses found. Derives registry keys via `to_snake_case(cls.__name__, strip_suffix="Pipeline")`. Calls `seed_prompts` per class with isolated try/except (same pattern as `_discover_pipelines`).

**`create_app` signature extended:** added `pipeline_modules: Optional[List[str]] = None` after `default_model`. Docstring updated.

**Registry merge logic updated:** module-loaded pipelines are resolved after engine init/model resolution, before the auto-discover block. Merge order:
- `auto_discover=True`: `{**discovered, **module_loaded, **(explicit or {})}`
- `auto_discover=False`: `{**module_loaded, **(explicit or {})}`

```
# Before (registry setup)
if auto_discover:
    discovered_pipeline, discovered_introspection = _discover_pipelines(...)
    app.state.pipeline_registry = {**discovered_pipeline, **(pipeline_registry or {})}
    ...
else:
    app.state.pipeline_registry = pipeline_registry or {}
    ...

# After (registry setup)
if pipeline_modules:
    module_pipeline, module_introspection = _load_pipeline_modules(...)
else:
    module_pipeline: Dict[str, Callable] = {}
    module_introspection: Dict[str, Type[PipelineConfig]] = {}

if auto_discover:
    discovered_pipeline, discovered_introspection = _discover_pipelines(...)
    app.state.pipeline_registry = {**discovered_pipeline, **module_pipeline, **(pipeline_registry or {})}
    ...
else:
    app.state.pipeline_registry = {**module_pipeline, **(pipeline_registry or {})}
    ...
```

## Decisions
### Runtime import for to_snake_case
**Choice:** Top-level `from llm_pipeline.naming import to_snake_case` (not inside TYPE_CHECKING)
**Rationale:** Used at runtime inside `_load_pipeline_modules`; naming.py is lightweight stdlib-only module

### ValueError wrapping ImportError
**Choice:** `raise ValueError(...) from e` instead of re-raising raw ImportError
**Rationale:** Plan specifies ValueError; distinguishes user-requested module failures from library import errors (CLI catches ValueError separately from ImportError UI-deps guard)

## Verification
[x] `from llm_pipeline.ui.app import _load_pipeline_modules, create_app` succeeds
[x] Function signatures match plan spec
[x] `create_app(pipeline_modules=None)` default is backward-compatible
[x] 197/197 UI tests pass (excluding pre-existing CLI test failures from Step 3 scope)
[x] Pre-existing CLI test failures are caused by new `pipeline_modules` kwarg in `assert_called_once_with` -- confirms passthrough works, fix is Step 3
