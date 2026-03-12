# Research Summary

## Executive Summary

Consolidated findings from two domain research agents (codebase architecture + app factory/registry). Both agents accurately mapped the current create_app() signature, registry types, PipelineConfig constructor, trigger_run() call site, and importlib.metadata API. One contradiction found between the two docs regarding default model fallback chain -- resolved by CEO decision: Option C (param > env > None, warn at startup, 400 at execution). One pre-existing naming bug identified in PipelineIntrospector. All core assumptions about factory closure shape, merge order, backward compatibility, and Python 3.11+ API compatibility verified against source code.

## Domain Findings

### Registry Type Signatures
**Source:** step-1, step-2, verified against app.py L17-21, runs.py L185-225, pipelines.py L84-133

- `pipeline_registry`: `dict[str, Callable]` -- factory callables keyed by pipeline name
- `introspection_registry`: `Dict[str, Type[PipelineConfig]]` -- class types keyed by pipeline name
- Factory call site (runs.py L223): `factory(run_id=run_id, engine=engine, event_emitter=bridge, input_data=body.input_data or {})` -- passes `input_data` kwarg that PipelineConfig.__init__ does not accept
- Both docs correctly identify `**kwargs` as the solution for absorbing `input_data`

### Factory Closure Design
**Source:** step-1 section 4, step-2 section 8, verified against pipeline.py L161-170

- `PipelineConfig.__init__` requires `model: str` (no default), optional `run_id`, `engine`, `event_emitter`
- Proposed closure shape correctly captures `model` at creation time, passes `run_id`/`engine`/`event_emitter` at call time, uses `**kwargs` for forward-compat
- Verified: closure does NOT need to pass `input_data` to `__init__` -- trigger_run passes it to `execute()` separately (runs.py L224)

### Entry Point Discovery API
**Source:** step-1 section 5, step-2 section 5, verified against pyproject.toml L10

- `importlib.metadata.entry_points(group="llm_pipeline.pipelines")` -- group kwarg available since Python 3.9
- `requires-python = ">=3.11"` in pyproject.toml -- no compatibility concern
- `ep.load()` can raise ImportError, AttributeError, or arbitrary exceptions during module load
- No existing `[project.entry-points]` section in pyproject.toml (task 3 adds it)

### Discovery Insertion Point & Merge Order
**Source:** step-1 section 9, step-2 section 8, verified against app.py L62-69

- Discovery after engine init (L62-66), before registry assignment (L68-69)
- Merge: `{**discovered, **(explicit or {})}` -- explicit registries override auto-discovered
- Matches PRD: "1. Scan entry points (auto), 2. Apply CLI overrides (manual)"

### seed_prompts Contract
**Source:** step-1 section 6, step-2 section 7, verified against db/prompt.py L40-43

- Optional classmethod on PipelineConfig subclasses: `seed_prompts(engine: Engine) -> None`
- Idempotent via UniqueConstraint('prompt_key', 'prompt_type', name='uq_prompts_key_type') on Prompt model
- Detection: `hasattr(cls, 'seed_prompts') and callable(cls.seed_prompts)`
- Does not exist in codebase yet -- task 3 creates first implementation

### CLI Call Sites & Backward Compatibility
**Source:** step-1 section 7, step-2 section 4, verified against cli.py

- Three call sites: _run_ui L46, _run_dev_mode L82, _create_dev_app L109
- All pass only `db_path=args.db` -- new params with defaults are backward-compatible
- `_create_dev_app()` (uvicorn reload factory) reads from env vars -- auto_discover=True default means discovery runs in reload mode too (correct behavior)

### Error Handling Patterns
**Source:** step-2 section 6, verified against pipelines.py L107-108, prompt loader

- Codebase consistently uses `logger.getLogger(__name__)` + broad `except Exception` + `logger.warning()`
- Aligns with PRD: "Entry point loading errors are logged as warnings, not fatal"

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Should create_app() hardcode a default model fallback ("google-gla:gemini-2.0-flash-lite") when neither default_model param nor LLM_PIPELINE_MODEL env var is set? Step-1 says yes (param > env > hardcoded), step-2 says no (param > env > None, fail at runtime). | **Option C**: param > env > None. At discovery time: log warning "No default model configured. Set --model or LLM_PIPELINE_MODEL. Pipeline execution will fail without a model." At trigger_run time: return 400/422 if model still None. No hardcoded fallback -- "google-gla:gemini-2.0-flash-lite" belongs to demo pipeline only (task 3). Rationale: discovery and execution are separate concerns; missing model shouldn't block UI startup, browsing, or introspection. | Factory closure receives `model: Optional[str]` instead of `model: str`. Discovery + introspection work without model. Execution-time validation needed in trigger_run (or factory). Demo pipeline (task 3) sets its own default model independently. |

## Assumptions Validated
- [x] `pipeline_registry` type is `dict[str, Callable]` with factory signature matching trigger_run() call at runs.py L223
- [x] `introspection_registry` type is `Dict[str, Type[PipelineConfig]]` consumed by PipelineIntrospector
- [x] PipelineConfig.__init__ requires `model: str` with no default -- factory must supply it
- [x] `importlib.metadata.entry_points(group=...)` kwarg is stable on Python 3.11+
- [x] New create_app() params with defaults are backward-compatible with all 3 CLI call sites
- [x] `issubclass(cls, PipelineConfig)` works (PipelineConfig is ABC); TypeError from non-type arg caught by broad except
- [x] Merge order `{**discovered, **(explicit or {})}` correctly gives precedence to explicit registries
- [x] Discovery runs correctly in uvicorn reload mode via _create_dev_app() with auto_discover=True default
- [x] Prompt model has UniqueConstraint on (prompt_key, prompt_type) enabling idempotent seed_prompts
- [x] PipelineConfig.__init_subclass__ validates Pipeline suffix, Registry/Strategies naming conventions
- [x] Model resolution: param > env > None (CEO decision). No hardcoded fallback. Warn at startup, 400 at execution time. Demo pipeline owns its own default (task 3)

## Open Items
- **PipelineIntrospector._pipeline_name single-regex bug** -- uses `([a-z0-9])([A-Z])` single regex (introspection.py L48) while `PipelineConfig.pipeline_name` uses `to_snake_case()` double-regex (naming.py L35-36). Diverges on consecutive-caps names (e.g. "HTTPProxyPipeline" -> "httpproxy" vs "http_proxy"). Pre-existing, not caused by task 1, but discovery will expose it if entry point names don't match. Track separately.
- **ep.name vs class-derived pipeline_name convention** -- if entry point name differs from class-derived name, list endpoint returns ep.name but detail metadata returns class-derived pipeline_name. Not blocking but should document convention: ep.name SHOULD match `to_snake_case(ClassName, strip_suffix="Pipeline")`.
- **seed_prompts error isolation** -- step-1 ambiguous about whether seed_prompts failure rolls back pipeline registration. Step-2 implies it doesn't (seed called after register). Recommend: separate try/except for seed_prompts with warning log, pipeline stays registered regardless.
- **Factory closure model type change** -- CEO decision means factory closure captures `model: Optional[str]` not `model: str`. PipelineConfig.__init__ requires `model: str` (no default). Need execution-time guard: either in factory (raise before calling __init__) or in trigger_run (return 400 before calling factory). Recommend: guard in trigger_run for clean HTTP error response.

## Recommendations for Planning
1. Model resolution chain: `default_model` param > `LLM_PIPELINE_MODEL` env var > None. create_app() calls `os.environ.get("LLM_PIPELINE_MODEL")` as fallback. If None, log warning at startup. Guard execution in trigger_run with 400 response if model is None at call time
2. Implement seed_prompts call in its own try/except, separate from the entry point load/validate/register block -- ensures pipeline is usable even if prompt seeding fails
3. Use ep.name as registry key (not class-derived name) for both registries -- this matches how task 2's --pipelines will work (module PIPELINE_REGISTRY dict keys)
4. Add logger to app.py (`logger = logging.getLogger(__name__)`) following codebase convention
5. Log discovered pipeline count and names at INFO level after discovery completes (aids debugging)
6. Consider filing a separate issue for the PipelineIntrospector single-regex naming bug before it causes confusion with real consecutive-caps pipeline names
7. Factory closure should be a private module-level function `_make_pipeline_factory(cls, model)` for testability
