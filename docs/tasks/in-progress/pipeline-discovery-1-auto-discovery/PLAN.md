# PLANNING

## Summary
Add `auto_discover` and `default_model` params to `create_app()`. Before route registration, scan the `llm_pipeline.pipelines` entry point group via `importlib.metadata`, validate each loaded class as a `PipelineConfig` subclass, build factory closures capturing `model`, and merge discovered entries into `pipeline_registry` and `introspection_registry` (explicit overrides discovered). Warn at startup if model is None; guard execution in `trigger_run` with 400 if model still None at call time.

## Plugin & Agents
**Plugin:** python-development, backend-development
**Subagents:** [available agents]
**Skills:** none

## Phases
1. **Implementation**: Add discovery logic to `app.py` and model guard to `runs.py`

## Architecture Decisions

### Discovery module vs inline
**Choice:** Inline discovery in `app.py` using a private `_make_pipeline_factory` module-level helper; no separate `discovery.py`
**Rationale:** Discovery is called once at app startup and has no other consumers in this task. Task 2 imports modules manually and passes them to `create_app()` -- the factory helper may be shared later but is premature to extract now. Keeping it in `app.py` avoids adding a public module to the package surface.
**Alternatives:** Separate `llm_pipeline/discovery.py` module -- adds testability but unnecessary surface for a 30-line function

### Registry key: ep.name vs class-derived name
**Choice:** Use `ep.name` (entry point name) as registry key for both registries
**Rationale:** VALIDATED_RESEARCH recommendation: ep.name is controlled by the publisher, is stable, and matches the key task 2's `--pipelines` PIPELINE_REGISTRY dict will use. Class-derived name via `to_snake_case()` diverges for consecutive-caps names (pre-existing PipelineIntrospector bug -- tracked separately).
**Alternatives:** Class-derived `pipeline_name` -- introduces mismatch risk until introspection bug is fixed

### seed_prompts error isolation
**Choice:** Separate `try/except` for `seed_prompts` call; pipeline stays registered even if seeding fails
**Rationale:** VALIDATED_RESEARCH open item: seeding failure must not block pipeline registration. Separate block ensures registration + factory are in the registry before seed attempt.
**Alternatives:** Single try/except covering load+validate+register+seed -- rollback on seed failure would silently drop a valid pipeline

### Model None guard location
**Choice:** Guard in `trigger_run` (runs.py) with HTTP 422; factory closure stores `model: Optional[str]`
**Rationale:** CEO decision (VALIDATED_RESEARCH Q&A): missing model should not block UI startup, browsing, or introspection. Guard at execution boundary gives clean HTTP error with actionable message.
**Alternatives:** Guard in factory closure before calling `__init__` -- raises RuntimeError, not HTTP error; harder to surface to client

### Merge order
**Choice:** `{**discovered, **(explicit or {})}` -- explicit registries passed to `create_app()` override auto-discovered
**Rationale:** Verified in VALIDATED_RESEARCH against PRD: "1. Scan entry points (auto), 2. Apply CLI overrides (manual)". Explicit always wins.
**Alternatives:** Discovered overrides explicit -- inverts PRD intent

## Implementation Steps

### Step 1: Add discovery logic to app.py
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /python/importlib_metadata
**Group:** A

1. Add `import logging`, `import os`, `importlib.metadata` imports to `llm_pipeline/ui/app.py`
2. Add `logger = logging.getLogger(__name__)` at module level
3. Add `_make_pipeline_factory(cls, model)` private function below logger:
   - Signature: `(cls: Type[PipelineConfig], model: Optional[str]) -> Callable`
   - Returns closure capturing `cls` and `model`; closure signature `(run_id, engine, event_emitter, **kwargs) -> PipelineConfig`
   - Closure body: `return cls(model=model, run_id=run_id, engine=engine, event_emitter=event_emitter)`
4. Add `_discover_pipelines(engine, default_model)` private function:
   - Calls `importlib.metadata.entry_points(group="llm_pipeline.pipelines")`
   - For each `ep`: wraps load+validate+register in `try/except Exception` with `logger.warning`
   - Validates: `inspect.isclass(cls)` and `issubclass(cls, PipelineConfig)`
   - Builds: factory via `_make_pipeline_factory(cls, default_model)`
   - Appends to local `pipeline_reg` and `introspection_reg` dicts keyed by `ep.name`
   - After registration success: separate `try/except` for `seed_prompts(engine)` if `hasattr(cls, "seed_prompts") and callable(cls.seed_prompts)`
   - Returns `(pipeline_reg, introspection_reg)` tuple
   - Logs discovered names at INFO after loop completes
5. Update `create_app()` signature: add `auto_discover: bool = True` and `default_model: Optional[str] = None` params
6. Update docstring to document both new params
7. Add model resolution after engine init (before registry assignment):
   - `resolved_model = default_model or os.environ.get("LLM_PIPELINE_MODEL")`
   - If `resolved_model is None`: `logger.warning("No default model configured. Set LLM_PIPELINE_MODEL or pass default_model. Pipeline execution will fail without a model.")`
8. Add discovery block (after engine init, before registry assignment at current L68-69):
   - `if auto_discover:` call `_discover_pipelines(app.state.engine, resolved_model)`
   - Merge: `app.state.pipeline_registry = {**discovered_pipeline, **(pipeline_registry or {})}`
   - Merge: `app.state.introspection_registry = {**discovered_introspection, **(introspection_registry or {})}`
   - Else: `app.state.pipeline_registry = pipeline_registry or {}`; `app.state.introspection_registry = introspection_registry or {}`

### Step 2: Add model None guard to trigger_run
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. In `llm_pipeline/ui/routes/runs.py` `trigger_run()`, after factory lookup (after current L207), add guard:
   - Call `factory` to check if model stored is None by storing model on `app.state` OR pass model check through app.state
   - Simplest approach: store `app.state.default_model = resolved_model` in `create_app()` after resolution
   - In `trigger_run`: retrieve `default_model = getattr(request.app.state, "default_model", None)`; if `default_model is None`: raise `HTTPException(status_code=422, detail="No model configured. Set LLM_PIPELINE_MODEL env var or pass --model flag.")`
   - Note: `app.state.default_model` must be set in Step 1 alongside the warning log

## Risks & Mitigations
| Risk | Impact | Mitigation |
| --- | --- | --- |
| `ep.load()` raises ImportError for missing optional dep of an entry point | Medium | Broad `except Exception` with `logger.warning` per VALIDATED_RESEARCH error handling pattern |
| `issubclass()` raises TypeError if `ep.load()` returns non-type | Low | Caught by same broad `except Exception` block |
| seed_prompts failure silently drops pipeline from registry | High | Separate `try/except` block for seed call; pipeline already appended to reg dicts before seed attempt |
| model=None propagates into PipelineConfig.__init__ which requires `model: str` | High | 422 guard in trigger_run before factory call (Step 2); factory closure still captures None but is never called without this guard |
| Discovery runs in uvicorn reload mode and re-seeds prompts on each reload | Low | seed_prompts idempotent via UniqueConstraint on (prompt_key, prompt_type) per VALIDATED_RESEARCH |
| PipelineIntrospector regex bug causes ep.name vs class-derived name mismatch | Low | Using ep.name as registry key avoids the bug for now; tracked as separate pre-existing issue |

## Success Criteria
- [ ] `create_app()` accepts `auto_discover=True` and `default_model=None` without breaking existing call sites in `cli.py`
- [ ] Entry points in group `llm_pipeline.pipelines` are loaded and registered in both `app.state.pipeline_registry` and `app.state.introspection_registry` under `ep.name` key
- [ ] Explicit `pipeline_registry` / `introspection_registry` params override auto-discovered entries
- [ ] `seed_prompts(engine)` called on classes that have it; failure logs warning but does not unregister the pipeline
- [ ] Load errors logged as `logger.warning`, not raised; app starts normally with zero entry points on error
- [ ] Startup warning logged when `default_model` is None and `LLM_PIPELINE_MODEL` not set
- [ ] `trigger_run` returns HTTP 422 with actionable message when `default_model` is None at call time
- [ ] `auto_discover=False` disables discovery; registries fall back to explicit params only

## Phase Recommendation
**Risk Level:** low
**Reasoning:** All assumptions validated in VALIDATED_RESEARCH. Changes are additive (new params with defaults). Two isolated files modified. No schema changes. Existing tests unaffected by default param values. Downstream tasks 2 and 3 depend on this interface but are not yet implemented.
**Suggested Exclusions:** testing, review
