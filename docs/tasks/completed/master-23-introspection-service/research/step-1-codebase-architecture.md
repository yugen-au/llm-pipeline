# Step 1: Codebase Architecture Research - Pipeline Introspection Service

## Objective

Map all pipeline classes and their introspectable attributes to design a `PipelineIntrospector` that extracts metadata without instantiating pipelines.

---

## Core Classes & Introspection Points

### 1. PipelineConfig (llm_pipeline/pipeline.py)

**Class-level attributes (accessible without instantiation):**
- `REGISTRY` - set by `__init_subclass__(cls, registry=, strategies=)`
- `STRATEGIES` - set by `__init_subclass__(cls, registry=, strategies=)`

**Naming convention:** Class must end with `'Pipeline'`. Auto-derives `pipeline_name` via snake_case (`RateCardParserPipeline` -> `rate_card_parser`).

**Naming validation:** Registry must be `{PipelineName}Registry`, Strategies must be `{PipelineName}Strategies`.

**Key methods for introspection context:**
- `_build_execution_order()` - iterates strategies -> `get_steps()` -> deduplicates step classes -> builds `_step_order` dict. This is the canonical execution order logic.
- `pipeline_name` property - auto-derived from class name (needs instance, but can be replicated statically)

**Instance-only attributes (NOT available for introspection):**
- `_strategies` (list of strategy instances) - created in `__init__`
- `_step_order` (dict of step_class -> position) - built in `__init__`
- `_model_extraction_step` - maps model -> step class
- `_step_data_transformations` - maps step class -> transformation

**Introspection approach:** Access `REGISTRY` and `STRATEGIES` as class attrs. Replicate `_build_execution_order()` logic statically by instantiating strategies (safe, no side effects) and calling `get_steps()`.

---

### 2. PipelineStrategies (llm_pipeline/strategy.py)

**Class-level attributes:**
- `STRATEGIES: ClassVar[List[Type[PipelineStrategy]]]` - list of strategy classes, set via `__init_subclass__(cls, strategies=[...])`

**Classmethods (no instance needed):**
- `create_instances()` -> `List[PipelineStrategy]` - instantiates all strategies
- `get_strategy_names()` -> `List[str]` - instantiates to get `.name` from each

**Declaration pattern:**
```python
class MyStrategies(PipelineStrategies, strategies=[
    LaneBasedStrategy,
    DestinationBasedStrategy,
]):
    pass
```

**Introspection approach:** Access `STRATEGIES` class attr directly for the list of strategy classes. Use `get_strategy_names()` classmethod for names.

---

### 3. PipelineStrategy (llm_pipeline/strategy.py)

**Class-level attributes (set by `__init_subclass__`):**
- `NAME` - snake_case auto-generated from class name (e.g., `LaneBasedStrategy` -> `lane_based`)
- `DISPLAY_NAME` - title case auto-generated (e.g., `Lane Based`)

**Instance properties:**
- `name` -> returns `self.NAME`
- `display_name` -> returns `self.DISPLAY_NAME`

**Abstract methods (require instance):**
- `can_handle(context: Dict[str, Any]) -> bool` - determines strategy applicability (runtime only)
- `get_steps() -> List[StepDefinition]` - returns step definitions in order

**Naming convention:** Must end with `'Strategy'`.

**Introspection approach:** `NAME` and `DISPLAY_NAME` are class attributes, accessible without instance. For `get_steps()`, instantiate strategy with `strategy_class()` (parameterless, no side effects) then call `.get_steps()`.

---

### 4. StepDefinition (llm_pipeline/strategy.py)

**Dataclass with all fields directly accessible:**

| Field | Type | Description |
|---|---|---|
| `step_class` | `Type` | The LLMStep subclass |
| `system_instruction_key` | `str` | System prompt key (can be None for auto-discovery) |
| `user_prompt_key` | `str` | User prompt key (can be None for auto-discovery) |
| `instructions` | `Type` | Pydantic model for LLM response parsing |
| `action_after` | `Optional[str]` | Pipeline method to call after step |
| `extractions` | `List[Type[PipelineExtraction]]` | Extraction classes |
| `transformation` | `Optional[Type[PipelineTransformation]]` | Transformation class |
| `context` | `Optional[Type]` | PipelineContext subclass this step produces |

**Auto-discovery of prompt keys:** When `system_instruction_key` or `user_prompt_key` is `None`, `create_step()` queries DB for prompts using pattern `{step_name}.{strategy_name}` or `{step_name}`. This is runtime-only behavior.

**Introspection approach:** All fields are plain dataclass attributes - directly accessible. For prompt keys that are `None`, note they are "auto-discovered from DB at runtime".

---

### 5. LLMStep (llm_pipeline/step.py)

**Class-level attributes (set by `@step_definition` decorator):**
- `INSTRUCTIONS` - Pydantic instruction model class
- `DEFAULT_SYSTEM_KEY` - default system prompt key
- `DEFAULT_USER_KEY` - default user prompt key
- `DEFAULT_EXTRACTIONS` - default extraction classes list
- `DEFAULT_TRANSFORMATION` - default transformation class
- `CONTEXT` - context class this step produces

**Classmethod (added by decorator):**
- `create_definition(system_instruction_key=, user_prompt_key=, extractions=, transformation=)` -> `StepDefinition`

**Instance properties:**
- `step_name` - auto-derived from class name (`ConstraintExtractionStep` -> `constraint_extraction`)

**Naming convention:** Must end with `'Step'`.

**Abstract method:** `prepare_calls() -> List[StepCallParams]`

**Introspection approach:** Access class attributes (`INSTRUCTIONS`, `DEFAULT_SYSTEM_KEY`, etc.) directly. Replicate `step_name` derivation statically from class name. No need to instantiate.

---

### 6. step_definition Decorator (llm_pipeline/step.py)

Sets the following on the step class:
- `INSTRUCTIONS`, `DEFAULT_SYSTEM_KEY`, `DEFAULT_USER_KEY`, `DEFAULT_EXTRACTIONS`, `DEFAULT_TRANSFORMATION`, `CONTEXT`

**Validation at decoration time:**
- Step class name must end with `'Step'`
- Instructions class name must be `{StepNamePrefix}Instructions`
- Transformation class name must be `{StepNamePrefix}Transformation` (if provided)
- Context class name must be `{StepNamePrefix}Context` (if provided)

**Introspection approach:** Check `hasattr(step_class, 'INSTRUCTIONS')` to detect if decorated. If yes, all class attrs are available. If not, metadata comes from the StepDefinition dataclass fields instead.

---

### 7. PipelineExtraction (llm_pipeline/extraction.py)

**Class-level attributes:**
- `MODEL: ClassVar[Type[SQLModel]]` - target DB model, set via `__init_subclass__(cls, model=)`

**Method detection (for introspection of extraction variants):**
- `default` method -> always used
- Strategy-matching method (e.g., `lane_based`) -> used when strategy matches
- Single custom method -> auto-detected
- Multiple custom methods -> error (ambiguous)

**Naming convention:** Must end with `'Extraction'`.

**Introspection approach:** Access `MODEL` class attr. Inspect custom methods (filter `dir(cls) - dir(PipelineExtraction)`) to discover extraction method names/variants.

---

### 8. PipelineTransformation (llm_pipeline/transformation.py)

**Class-level attributes:**
- `INPUT_TYPE: ClassVar[Type]` - set via `__init_subclass__(cls, input_type=, output_type=)`
- `OUTPUT_TYPE: ClassVar[Type]`

**Method detection:** Same pattern as PipelineExtraction (default, single custom, multiple -> error).

**Naming convention:** Must end with `'Transformation'`.

**Introspection approach:** Access `INPUT_TYPE` and `OUTPUT_TYPE` class attrs directly.

---

### 9. PipelineContext (llm_pipeline/context.py)

**Base class:** `pydantic.BaseModel`

**Naming convention:** `{StepNamePrefix}Context`

**Introspection approach:** Use `model_fields` to get field names, types, defaults. Use `model_json_schema()` for full JSON Schema.

---

### 10. PipelineDatabaseRegistry (llm_pipeline/registry.py)

**Class-level attributes:**
- `MODELS: ClassVar[List[Type[SQLModel]]]` - ordered list of DB models, set via `__init_subclass__(cls, models=[...])`

**Classmethod:**
- `get_models() -> List[Type[SQLModel]]` - returns MODELS list

**Introspection approach:** Call `get_models()` classmethod or access `MODELS` directly.

---

### 11. LLMResultMixin (llm_pipeline/step.py)

**Base class for instruction models. Provides:**
- `confidence_score: float` (0-1)
- `notes: str | None`
- `example: dict` class attr (optional, validated in `__init_subclass__`)
- `get_example()` classmethod

**Introspection approach:** Check if instruction class inherits from `LLMResultMixin`. If so, extract `example` dict if present.

---

### 12. State Models (llm_pipeline/state.py)

**PipelineStepState** (SQLModel, table=True):
- Fields: pipeline_name, run_id, step_name, step_number, input_hash, result_data (JSON), context_snapshot (JSON), prompt_system_key, prompt_user_key, prompt_version, model, created_at, execution_time_ms

**PipelineRunInstance** (SQLModel, table=True):
- Fields: run_id, model_type, model_id, created_at

**PipelineRun** (SQLModel, table=True):
- Fields: run_id, pipeline_name, status, started_at, completed_at, step_count, total_time_ms

These are DB models for tracking execution state. Not directly introspectable from pipeline class, but their schemas are useful metadata.

---

### 13. LLMProvider (llm_pipeline/llm/provider.py)

**Abstract base class.** Single abstract method: `call_structured(...)`.
- Concrete implementation: `GeminiProvider` (llm_pipeline/llm/gemini.py)

**Not directly part of pipeline introspection** - the pipeline class doesn't declare which provider it uses (passed at runtime via constructor).

---

### 14. Prompt Model (llm_pipeline/db/prompt.py)

**Prompt** (SQLModel, table=True):
- Fields: prompt_key, prompt_name, prompt_type (system/user), category, step_name, content, required_variables (JSON), description, version, is_active

**Relevant for introspection:** When step prompt keys are `None`, they're auto-discovered from DB using `prompt_key` matching `{step_name}` or `{step_name}.{strategy_name}`.

---

## Introspection Flow (without instantiation)

```
PipelineConfig subclass (class attrs only)
  |
  +-- REGISTRY (class attr) -> PipelineDatabaseRegistry subclass
  |     +-- MODELS (class attr) -> [SQLModel classes in insertion order]
  |           +-- each model: model_json_schema(), model_fields, __tablename__
  |
  +-- STRATEGIES (class attr) -> PipelineStrategies subclass
        +-- STRATEGIES (class attr) -> [PipelineStrategy classes]
              +-- each strategy class:
                    +-- NAME (class attr), DISPLAY_NAME (class attr)
                    +-- strategy_class().get_steps() -> [StepDefinition]  # safe, no side effects
                          +-- each StepDefinition:
                                +-- step_class -> INSTRUCTIONS, step_name derivation
                                +-- system_instruction_key, user_prompt_key (may be None)
                                +-- instructions -> model_json_schema()
                                +-- extractions -> [PipelineExtraction classes]
                                |     +-- each: MODEL (class attr), custom method names
                                +-- transformation -> PipelineTransformation class
                                |     +-- INPUT_TYPE, OUTPUT_TYPE (class attrs)
                                +-- context -> PipelineContext subclass
                                      +-- model_fields, model_json_schema()
```

## Merged Execution Order Logic

From `PipelineConfig._build_execution_order()`:
1. Iterate strategies in order
2. For each strategy, iterate `get_steps()` results
3. Deduplicate by `step_class` (first occurrence wins)
4. Position = order of first appearance
5. Track which extraction models map to which step
6. Track which steps have transformations

The introspector should replicate this logic using the strategy instances' `get_steps()` return values.

---

## Edge Cases & Notes

1. **Strategies may share step classes** - `_build_execution_order` deduplicates. Introspector should show per-strategy step lists AND merged order.

2. **Prompt keys may be None** - auto-discovered from DB at runtime. Introspector can only report static keys; should flag None keys as "DB auto-discovery".

3. **Step classes may or may not use `@step_definition` decorator** - check `hasattr(step_class, 'INSTRUCTIONS')`. If not decorated, metadata comes from StepDefinition fields.

4. **PipelineStrategy.get_steps() requires instance** but `__init__` is parameterless (ABC default). Safe to call `strategy_class().get_steps()`.

5. **Extraction method detection** - can introspect custom methods by comparing `dir(extraction_class)` vs `dir(PipelineExtraction)`.

6. **No provider introspection needed** - provider is a runtime dependency, not declared on the pipeline class.

---

## Caching Strategy

All metadata is static for a given pipeline class. Recommended:
- Cache key: `id(pipeline_class)` or `pipeline_class.__qualname__`
- Cache invalidation: not needed unless class is redefined (hot reload scenario)
- Implementation: `functools.lru_cache` on `get_metadata()` or a class-level `_cache` dict

---

## Upstream Task 19 Deviations (relevant)

- `app.py` accepts `pipeline_registry: Optional[dict]` param, stored as `app.state.pipeline_registry`
- This is a dict of name -> factory callable, different from the introspection approach (which works with pipeline classes directly)
- Task 24 expects `_pipeline_registry: Dict[str, Type[PipelineConfig]]` in the routes module
- Potential integration: The introspector should accept `Type[PipelineConfig]` and the routes layer can convert from app.state.pipeline_registry

## Downstream Task 24 (out of scope, for reference)

Task 24 will consume `PipelineIntrospector` via:
- `GET /pipelines` - list registered pipelines with summary metadata
- `GET /pipelines/{pipeline_name}` - full introspection data
- Uses `app.state.pipeline_registry` from task 19's `create_app()`

---

## Proposed PipelineIntrospector API Surface

```python
class PipelineIntrospector:
    def __init__(self, pipeline_class: Type[PipelineConfig]): ...

    def get_metadata(self) -> dict:
        """Full introspection: name, strategies, steps, schemas, registry."""

    def get_pipeline_name(self) -> str:
        """Derive pipeline name from class name."""

    def get_strategies(self) -> list[dict]:
        """Extract strategy metadata: name, display_name, steps."""

    def get_execution_order(self) -> list[dict]:
        """Merged execution order across all strategies."""

    def get_registry_models(self) -> list[dict]:
        """DB model schemas from registry."""

    def get_step_metadata(self, step_def: StepDefinition) -> dict:
        """Extract single step: prompt keys, instructions schema, extractions, etc."""
```
