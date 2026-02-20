# Research Summary

## Executive Summary

Validated research findings from step-1 (codebase architecture) and step-2 (introspection patterns) against actual source code. Core claims hold: ClassVar-based introspection works, strategy instantiation is safe, Pydantic schema extraction is viable. Found 2 critical integration issues (file placement behind FastAPI guard, pipeline_registry type mismatch), 2 medium issues (regex inconsistency, non-Pydantic transformation types), and 1 minor issue (StepDefinition type annotation vs runtime behavior).

## Domain Findings

### Class-Level Attribute Access
**Source:** step-1-codebase-architecture.md, step-2-introspection-patterns.md

All 14 classes validated. ClassVar attributes set via `__init_subclass__` or `@step_definition` decorator are accessible on class types without instantiation. Confirmed for: `PipelineConfig.REGISTRY/STRATEGIES`, `PipelineStrategies.STRATEGIES`, `PipelineStrategy.NAME/DISPLAY_NAME`, `PipelineExtraction.MODEL`, `PipelineTransformation.INPUT_TYPE/OUTPUT_TYPE`, `PipelineDatabaseRegistry.MODELS`, and `LLMStep.INSTRUCTIONS/DEFAULT_SYSTEM_KEY/DEFAULT_USER_KEY/DEFAULT_EXTRACTIONS/DEFAULT_TRANSFORMATION/CONTEXT`.

### Safe Strategy Instantiation
**Source:** step-1, step-2

VALIDATED: `PipelineStrategy` has NO `__init__` override. Only `__init_subclass__`, properties, and abstract methods. `strategy_class()` calls ABC default constructor - no side effects, no DB, no IO. `get_steps()` returns `List[StepDefinition]` (dataclass instances) - pure data.

CAVEAT: Concrete strategy subclasses COULD override `__init__` with parameters. Research assumes they don't. Introspector should wrap in try/except for robustness.

### StepDefinition Type Annotation vs Runtime
**Source:** step-1, step-2

Research claims prompt keys "can be None". ACTUAL type annotation is `str` (not `Optional[str]`). However, `create_definition()` classmethod passes `None` through when defaults are None, and `create_step()` explicitly handles `None` values. Runtime behavior matches research claims despite incorrect type annotation. Introspector must handle both `str` and `None` values.

### Naming Convention Regex Differences
**Source:** step-2

Research section 1.3 shows a single regex for all name derivations. ACTUAL CODE uses different regexes:
- `PipelineConfig.pipeline_name`: single regex `re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()`
- `PipelineStrategy.__init_subclass__`: TWO regexes - first `([A-Z]+)([A-Z][a-z])` then `([a-z\d])([A-Z])`
- `LLMStep.step_name`: single regex matching pipeline pattern

The double-regex handles consecutive capitals differently (e.g., "HTTPHandler" -> "http_handler" vs "h_t_t_p_handler"). Introspector MUST use the correct regex for each class type.

### Execution Order Algorithm
**Source:** step-1, step-2

VALIDATED: `_build_execution_order()` deduplicates by `step_class` (first occurrence wins), iterating strategies then steps in order. Research algorithm is functionally correct. Actual code also maps `_model_extraction_step` (model -> step class) and `_step_data_transformations` (step class -> step class) - these could be useful introspection metadata not captured in the proposed output shape.

### Pydantic Schema Extraction
**Source:** step-2

VALIDATED: `model_json_schema()` works for all Pydantic/SQLModel classes (instructions, context, extraction models). `model_fields` provides field-level detail.

CAVEAT: `PipelineTransformation.INPUT_TYPE/OUTPUT_TYPE` may be non-Pydantic types (e.g., `pd.DataFrame`, `dict`). `model_json_schema()` would fail on these. Introspector must check `issubclass(type_cls, BaseModel)` before calling schema methods, falling back to `type.__name__` string representation.

### Extraction Method Discovery
**Source:** step-1, step-2

VALIDATED: `dir(extraction_class) - dir(PipelineExtraction)` correctly discovers custom methods on the class level. Works equivalently to the instance-level `dir(self)` in the actual `extract()` method since methods are defined on the class.

### Pipeline Registry Integration Gap
**Source:** step-1

`create_app()` signature: `pipeline_registry: Optional[dict] = None` with docstring: "factory has signature `(run_id, engine) -> pipeline`". This stores **factory callables**, not `Type[PipelineConfig]`. Task 24 expects `_pipeline_registry: Dict[str, Type[PipelineConfig]]`. The introspector needs class types for ClassVar access. These are incompatible unless:
- Pipeline classes are callable (they are, but `__init__` has side effects)
- Registry stores both factory and type
- Separate registration mechanism added

### File Placement: FastAPI Import Guard
**Source:** validated against llm_pipeline/ui/__init__.py

`ui/__init__.py` raises `ImportError` if FastAPI not installed. Importing `llm_pipeline.ui.introspection` triggers this guard (Python executes `__init__.py` when importing any submodule). This means introspection is unusable without FastAPI, contradicting the "no dependencies" goal. The introspector has zero FastAPI dependency - it's pure Python + Pydantic.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Should introspection.py live outside ui/ to avoid FastAPI dependency? | PENDING | If yes, changes file location and import paths for task 24 |
| How will pipeline classes be registered for introspection given app.state.pipeline_registry stores factory callables not types? | PENDING | Determines integration approach between tasks 23 and 24 |

## Assumptions Validated
- [x] ClassVar attributes accessible without instantiation (verified all 7 class types)
- [x] PipelineStrategy() base constructor has no side effects (no __init__ override)
- [x] get_steps() returns pure StepDefinition dataclass list (no DB, no IO)
- [x] model_json_schema() works for instruction/context/SQLModel classes
- [x] Extraction method names discoverable via dir() comparison
- [x] PipelineConfig.__init__() has DB side effects - must avoid
- [x] PipelineExtraction.__init__() requires pipeline instance - must avoid
- [x] PipelineTransformation.__init__() requires pipeline instance - must avoid
- [x] StepDefinition.create_step() requires DB - must avoid
- [x] LLMResultMixin.example validated at import time, safe to read

## Open Items
- File placement: `llm_pipeline/ui/introspection.py` blocked by FastAPI import guard for non-UI usage
- Pipeline registry type: factory callable vs Type[PipelineConfig] mismatch between app.state and introspector needs
- Concrete strategy __init__ overrides: need defensive try/except around `strategy_class()`
- Transformation INPUT_TYPE/OUTPUT_TYPE: need type-check before calling model_json_schema()
- Naming regex: must use per-class-type regex (single for pipeline/step, double for strategy)

## Recommendations for Planning
1. Resolve file placement before implementation - either move to `llm_pipeline/introspection.py` or make `ui/__init__.py` guard conditional (lazy import)
2. Define pipeline registration contract for introspection: should `create_app()` accept `Dict[str, Type[PipelineConfig]]` separately from factory registry?
3. Wrap strategy instantiation in try/except with clear error reporting for strategies with custom __init__
4. Add BaseModel subclass check before calling model_json_schema() on transformation types
5. Use correct per-class regex functions (extract from source or import from respective modules to avoid drift)
6. Consider exposing model-to-step and step-to-transformation mappings from execution order for richer metadata
