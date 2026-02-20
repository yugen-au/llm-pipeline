# PLANNING

## Summary

Create `llm_pipeline/introspection.py` with a `PipelineIntrospector` class that extracts pipeline metadata via pure class-level introspection (no DB, no LLM, no instantiation of PipelineConfig/Extraction/Transformation). Metadata covers: pipeline name, registry models, strategies (name, display_name, steps), step-level data (prompt keys, instruction schema, context schema, extractions, transformation types), and deduped execution order. Class-level caching prevents repeated introspection. Also updates `create_app()` with an optional `introspection_registry` param (backward-compatible) and exports `PipelineIntrospector` from the top-level package.

## Plugin & Agents

**Plugin:** python-development, backend-development
**Subagents:** [available agents]
**Skills:** none

## Phases

1. **Core module**: Implement `llm_pipeline/introspection.py` with `PipelineIntrospector`
2. **Integration**: Update `create_app()`, export from `__init__.py`, write tests

## Architecture Decisions

### Instance-Based Introspector with Class-Level Cache

**Choice:** `PipelineIntrospector(pipeline_cls)` constructor with `_cache: ClassVar[Dict]` keyed by `pipeline_cls` id.

**Rationale:** Task 24 spec shows `PipelineIntrospector(_pipeline_registry[pipeline_name])` - instance-based is required. Class-level dict cache avoids repeated strategy instantiation and schema extraction across multiple callers. `functools.lru_cache` is unsuitable for instance methods; class-level dict is explicit and inspectable.

**Alternatives:** Static/module-level functions (rejected - task 24 spec mandates instance); per-instance cache (rejected - misses cross-caller dedup).

### Strategy Instantiation with Defensive Try/Except

**Choice:** `strategy_class()` called inside `try/except Exception` per strategy.

**Rationale:** `PipelineStrategy` base has no `__init__` override (validated). Concrete subclasses COULD override. Wrapping ensures one broken strategy doesn't block introspection of others. Error info captured in strategy metadata as `"error"` key.

**Alternatives:** Assume no override (rejected - VALIDATED_RESEARCH.md flags as open item); require strategies to never override __init__ (not enforceable).

### Per-Class Regex for Name Derivation

**Choice:** Three distinct name-derivation helpers matching exact source regexes.

**Rationale:** `pipeline.py` uses single regex `([a-z0-9])([A-Z])`. `strategy.py` `__init_subclass__` uses double regex (`([A-Z]+)([A-Z][a-z])` then `([a-z\d])([A-Z])`). `step.py` uses single regex `([a-z0-9])([A-Z])`. Diverging would produce wrong names for consecutive-capital class names (e.g., `HTTPParserStrategy` -> `http_parser` vs `h_t_t_p_parser`).

**Alternatives:** Single shared regex (rejected - produces wrong names for strategy classes with consecutive caps).

### BaseModel Check Before Schema Extraction

**Choice:** `issubclass(cls, BaseModel)` guard before `model_json_schema()`; fall back to `{"type": cls.__name__}` for non-Pydantic types.

**Rationale:** `PipelineTransformation.INPUT_TYPE/OUTPUT_TYPE` can be non-Pydantic (e.g., `pd.DataFrame`, `dict`). `model_json_schema()` would raise `PydanticUserError`. VALIDATED_RESEARCH.md confirms this as open item needing guard.

**Alternatives:** Try/except around schema call (acceptable but less explicit); always return None for transformation types (loses partial info).

### Extraction Method Discovery via dir() Comparison

**Choice:** `set(dir(extraction_cls)) - set(dir(PipelineExtraction))`, filter callables not starting with `_` and not named `extract`.

**Rationale:** This mirrors the runtime logic in `PipelineExtraction.extract()` which does the same comparison on instance dir(). Class-level dir() is equivalent since methods are defined on the class. Validated in VALIDATED_RESEARCH.md.

**Alternatives:** `inspect.getmembers()` (equivalent but heavier); `vars(cls)` (misses inherited methods from intermediate bases).

### Separate introspection_registry Parameter on create_app()

**Choice:** Add `introspection_registry: Optional[Dict[str, Type[PipelineConfig]]] = None` to `create_app()`, stored on `app.state.introspection_registry`.

**Rationale:** CEO decision. Existing `pipeline_registry` stores factory callables `(run_id, engine) -> pipeline` - changing its values would break task execution. A separate param keeps concerns separated. Task 24 will read from `app.state.introspection_registry`.

**Alternatives:** Reuse existing `pipeline_registry` with type union (rejected - breaks existing callers); auto-derive from factory registry (rejected - factories are callables, not types).

## Implementation Steps

### Step 1: Create llm_pipeline/introspection.py

**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /llmstxt/pydantic_dev_llms-full_txt
**Group:** A

1. Create `llm_pipeline/introspection.py` with module docstring explaining no FastAPI/DB/LLM dependencies.
2. Add imports: `re`, `functools`, `typing` (Any, ClassVar, Dict, List, Optional, Type), `pydantic.BaseModel`.
3. Define `PipelineIntrospector` class with `_cache: ClassVar[Dict] = {}`.
4. Implement `__init__(self, pipeline_cls: Type["PipelineConfig"])` storing `self._pipeline_cls`.
5. Implement `_pipeline_name(cls) -> str` using single regex `re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()` on class name minus `Pipeline` suffix (matches `pipeline.py` line 245 exactly).
6. Implement `_strategy_name(cls) -> str` using double regex from `strategy.py` lines 189-191: first `([A-Z]+)([A-Z][a-z])` then `([a-z\d])([A-Z])`, strip `Strategy` suffix, lowercase.
7. Implement `_step_name(cls) -> str` using single regex `re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()` on class name minus `Step` suffix (matches `step.py` line 261).
8. Implement `_get_schema(cls) -> Optional[dict]`: return `cls.model_json_schema()` if `issubclass(cls, BaseModel)`, else `{"type": cls.__name__}` for non-None types, else `None`.
9. Implement `_get_extraction_methods(extraction_cls) -> List[str]`: compute `set(dir(extraction_cls)) - set(dir(PipelineExtraction))`, filter `callable` and not `startswith("_")` and not `"extract"`, return sorted list.
10. Implement `_introspect_strategy(strategy_cls) -> dict`: wrap `strategy_cls()` in try/except; if success call `instance.get_steps()` and build step list; if failure return dict with `"error"` key. For each `StepDefinition`: derive step_name, read `INSTRUCTIONS`, `DEFAULT_SYSTEM_KEY`, `DEFAULT_USER_KEY`, `DEFAULT_EXTRACTIONS`, `DEFAULT_TRANSFORMATION`, `CONTEXT` from step class ClassVars; build extractions list and transformation dict.
11. Implement `get_metadata() -> dict`: check `_cache` by `id(self._pipeline_cls)`; if hit return cached; otherwise build full metadata dict with keys: `pipeline_name`, `registry_models`, `strategies`, `execution_order`; store in `_cache`; return.
12. `execution_order` derived by iterating `STRATEGIES.STRATEGIES`, calling `strategy_cls()`, `get_steps()` (with try/except), deduplicating by `step_class` (first occurrence wins), collecting `step_name` strings.
13. Add `__all__ = ["PipelineIntrospector"]`.

### Step 2: Update llm_pipeline/ui/app.py

**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. Read current `create_app()` signature in `llm_pipeline/ui/app.py`.
2. Add `introspection_registry: Optional[Dict[str, Type["PipelineConfig"]]] = None` parameter after `pipeline_registry`.
3. Add `from typing import Type` import if not already present (check existing imports).
4. Store on app state: `app.state.introspection_registry = introspection_registry or {}`.
5. Add TYPE_CHECKING import block for `PipelineConfig` type hint to avoid circular import: `from typing import TYPE_CHECKING` and `if TYPE_CHECKING: from llm_pipeline.pipeline import PipelineConfig`. Use string annotation `"PipelineConfig"` in signature.

### Step 3: Write tests/test_introspection.py

**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. Create `tests/test_introspection.py`.
2. Import test fixtures from `test_pipeline.py` domain classes by redefining minimal versions (or import if structured to allow it): define `WidgetDetectionInstructions`, `WidgetExtraction`, `WidgetStrategies`, `WidgetPipeline` in test file using the same pattern as `tests/test_pipeline.py`.
3. Test `get_metadata()` returns dict with correct `pipeline_name` (`"widget"` from `WidgetPipeline`).
4. Test `strategies` list has correct length matching `WidgetStrategies.STRATEGIES`.
5. Test each strategy entry has `name`, `display_name`, `class_name`, `steps`.
6. Test step entry has `step_name`, `system_key`, `user_key`, `instructions_class`, `instructions_schema` (valid JSON Schema dict), `extractions`.
7. Test extraction entry has `class_name`, `model_class`, `methods` list.
8. Test `execution_order` is a list of step name strings, deduplicated.
9. Test `registry_models` list contains model class names.
10. Test caching: call `get_metadata()` twice on same pipeline_cls, assert same object returned (identity check via `is`).
11. Test `_get_schema()` with non-Pydantic type returns `{"type": type_name}` not raising.
12. Test broken strategy (mock a strategy whose `__init__` raises) returns error dict not exception.

### Step 4: Export PipelineIntrospector from llm_pipeline/__init__.py

**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. Read `llm_pipeline/__init__.py`.
2. Add import: `from llm_pipeline.introspection import PipelineIntrospector`.
3. Add `"PipelineIntrospector"` to `__all__` list under a `# Introspection` comment.

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Concrete strategy subclass overrides `__init__` with required args | Medium | Wrap `strategy_cls()` in try/except; capture error in metadata dict |
| `INPUT_TYPE`/`OUTPUT_TYPE` is non-Pydantic (e.g., `pd.DataFrame`) | Medium | Guard with `issubclass(cls, BaseModel)` before `model_json_schema()`; fall back to `{"type": cls.__name__}` |
| Wrong step/strategy names due to regex mismatch | High | Use exact regex copies from source modules per class type; covered by tests |
| Cache returns stale data for dynamically redefined classes | Low | Document cache is process-lifetime; acceptable for production use |
| `create_app()` callers break due to signature change | Low | New param is `Optional` with `None` default; fully backward-compatible |
| Circular import between `introspection.py` and `pipeline.py` | Medium | Use `TYPE_CHECKING` guard for `PipelineConfig` type hint; runtime imports not needed |

## Success Criteria

- [ ] `llm_pipeline/introspection.py` exists with `PipelineIntrospector` class
- [ ] `PipelineIntrospector` importable from `llm_pipeline` top-level package
- [ ] `get_metadata()` returns dict with keys: `pipeline_name`, `registry_models`, `strategies`, `execution_order`
- [ ] Each strategy entry contains `name`, `display_name`, `class_name`, `steps`
- [ ] Each step entry contains `step_name`, `system_key`, `user_key`, `instructions_class`, `instructions_schema`, `extractions`, `transformation`
- [ ] `instructions_schema` is valid JSON Schema dict for Pydantic instruction classes
- [ ] Non-Pydantic transformation types do not raise; return `{"type": type_name}` fallback
- [ ] Broken strategy `__init__` does not propagate exception; captured in `"error"` key
- [ ] Calling `get_metadata()` twice returns cached result (same object)
- [ ] `create_app()` still works with no `introspection_registry` argument (backward-compat)
- [ ] `create_app()` stores `introspection_registry` on `app.state.introspection_registry`
- [ ] All new tests pass with `pytest`
- [ ] No imports of `fastapi`, `sqlalchemy`, or `sqlmodel` in `introspection.py`

## Phase Recommendation

**Risk Level:** low
**Reasoning:** Self-contained new module; existing code touched minimally (one optional param added to `create_app()`, one export added to `__init__.py`). No schema changes, no DB migrations, no runtime behavior changes. Pure class-level introspection is deterministic and side-effect-free.
**Suggested Exclusions:** testing, review
