# Research Summary

## Executive Summary

Validated research findings from step-1 (codebase architecture) and step-2 (introspection patterns) against actual source code. Core claims hold: ClassVar-based introspection works, strategy instantiation is safe, Pydantic schema extraction is viable. Two critical integration issues identified and RESOLVED via CEO decisions: file placement moved to `llm_pipeline/introspection.py` (avoids FastAPI guard), and `create_app()` will accept a separate `Dict[str, Type[PipelineConfig]]` for introspection. Three medium/minor implementation concerns remain as actionable recommendations (not blockers).

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

### Pipeline Registry Integration (RESOLVED)
**Source:** step-1, CEO decision

`create_app()` currently stores factory callables `(run_id, engine) -> pipeline`, not `Type[PipelineConfig]`. CEO decision: `create_app()` will accept an **additional** `Dict[str, Type[PipelineConfig]]` parameter for introspection, keeping the existing factory registry unchanged. Task 24 will implement this second parameter.

### File Placement (RESOLVED)
**Source:** validated against llm_pipeline/ui/__init__.py, CEO decision

CEO decision: `introspection.py` lives at `llm_pipeline/introspection.py` (NOT `ui/`). This avoids the FastAPI import guard in `ui/__init__.py` and allows introspection without FastAPI installed. Pure Python + Pydantic dependency only. Research step-2 imports section needs updating: `from llm_pipeline.introspection import PipelineIntrospector` (not `from llm_pipeline.ui.introspection`).

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Should introspection.py live outside ui/ to avoid FastAPI dependency? | YES - `llm_pipeline/introspection.py` | Changes file location from research proposal. All import paths in task 23/24 must reference `llm_pipeline.introspection` not `llm_pipeline.ui.introspection`. Task 24 route imports from top-level package. |
| How will pipeline classes be registered for introspection given app.state.pipeline_registry stores factory callables not types? | Separate `Dict[str, Type[PipelineConfig]]` param on `create_app()` | Task 24 adds new parameter alongside existing factory registry. No changes to existing factory-based pipeline execution. Introspector receives class types directly. |

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
- [x] File placement at `llm_pipeline/introspection.py` avoids FastAPI guard (CEO confirmed)
- [x] Separate introspection registry `Dict[str, Type[PipelineConfig]]` on create_app() (CEO confirmed)

## Open Items
- Concrete strategy __init__ overrides: need defensive try/except around `strategy_class()` (implementation detail, not a blocker)
- Transformation INPUT_TYPE/OUTPUT_TYPE: need BaseModel subclass check before model_json_schema() (implementation detail, not a blocker)
- Naming regex: must use per-class-type regex - single for pipeline/step, double for strategy (implementation detail, not a blocker)

## Recommendations for Planning
1. File: `llm_pipeline/introspection.py` - imports only from core `llm_pipeline` modules (pipeline, extraction, transformation, strategy, context), no ui/FastAPI/DB imports
2. Wrap `strategy_class()` in try/except to handle potential custom __init__ overrides gracefully
3. Guard `model_json_schema()` calls with `issubclass(cls, BaseModel)` check; fall back to `type.__name__` for non-Pydantic types like DataFrame
4. Use correct per-class regex: import or replicate the exact regex from each module (`pipeline.py` single-regex, `strategy.py` double-regex, `step.py` single-regex) to avoid naming drift
5. Consider exposing model-to-step and step-to-transformation mappings from execution order for richer metadata output
6. Task 24 scope: add `introspection_registry: Optional[Dict[str, Type[PipelineConfig]]]` param to `create_app()`, store on `app.state`, route imports `PipelineIntrospector` from `llm_pipeline.introspection`
