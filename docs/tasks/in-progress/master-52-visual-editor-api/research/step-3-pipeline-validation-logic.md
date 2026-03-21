# Step 3: Pipeline Validation Logic Deep-Dive

## Validation Architecture Overview

PipelineConfig validation occurs across three distinct layers, each triggered at different lifecycle stages. The compile endpoint must understand all three to determine which validations can be replicated for JSON-based draft pipelines.

## Layer 1: Class Definition Time (`__init_subclass__`)

Triggered when Python classes are **defined** (import time). These validations enforce naming conventions and structural type constraints.

### PipelineConfig.__init_subclass__ (pipeline.py L160-207)

```python
# Validates when registry=, strategies=, or agent_registry= are passed:
# 1. Class name must end with "Pipeline"
# 2. Registry class must be named "{Prefix}Registry"
# 3. Strategies class must be named "{Prefix}Strategies"
# 4. AgentRegistry class must be named "{Prefix}AgentRegistry"
# 5. INPUT_DATA must be PipelineInputData subclass if declared
```

**Error types raised:**
- `ValueError("Pipeline class '{name}' must end with 'Pipeline' suffix.")`
- `ValueError("Registry for {Pipeline} must be named '{Expected}', got '{Actual}'")`
- `ValueError("Strategies for {Pipeline} must be named '{Expected}', got '{Actual}'")`
- `ValueError("AgentRegistry for {Pipeline} must be named '{Expected}', got '{Actual}'")`
- `TypeError("{Pipeline}.INPUT_DATA must be a PipelineInputData subclass, got {actual!r}")`

### PipelineStrategy.__init_subclass__ (strategy.py L163-205)

```python
# 1. Class name must end with "Strategy"
# 2. Auto-generates NAME (snake_case) and DISPLAY_NAME (Title Case)
```

**Error:** `ValueError("Strategy class '{name}' must end with 'Strategy' suffix.")`

### PipelineStrategies.__init_subclass__ (strategy.py L286-307)

```python
# 1. Must provide strategies= list for concrete classes
```

**Error:** `ValueError("{Name} must specify strategies parameter when defining the class: class {Name}(PipelineStrategies, strategies=[...])")`

### step_definition decorator (step.py L41-138)

```python
# 1. Step class must end with "Step"
# 2. Instructions class must be named "{StepPrefix}Instructions"
# 3. Transformation class must be named "{StepPrefix}Transformation" (if provided)
# 4. Context class must be named "{StepPrefix}Context" (if provided)
```

**Errors:**
- `ValueError("{class} must follow naming convention: {StepName}Step")`
- `ValueError("Instruction class for {Step} must be named '{Expected}', got '{Actual}'")`
- `ValueError("Transformation class for {Step} must be named '{Expected}', got '{Actual}'")`
- `ValueError("Context class for {Step} must be named '{Expected}', got '{Actual}'")`

### PipelineDatabaseRegistry.__init_subclass__ (registry.py L36-57)

```python
# 1. Must provide models= list for concrete classes
```

**Error:** `ValueError("{Name} must specify models parameter when defining the class: class {Name}(PipelineDatabaseRegistry, models=[...])")`

### AgentRegistry.__init_subclass__ (agent_registry.py L54-74)

```python
# 1. Must provide agents= dict for concrete classes
```

**Error:** `ValueError("{Name} must specify agents parameter when defining the class: class {Name}(AgentRegistry, agents={...})")`

### Relevance to compile endpoint

**Not replicable for JSON-based drafts.** These enforce Python class naming conventions at import time. Draft pipelines have no Python classes. However, step-ref names from introspection metadata already passed these checks when the Python classes were originally defined.

## Layer 2: Instance Creation (`__init__`)

Triggered when a pipeline is **instantiated**. These are the core structural validations.

### PipelineConfig.__init__ signature (pipeline.py L209-291)

```python
def __init__(
    self,
    model: str,                                    # REQUIRED - LLM model string
    strategies: Optional[List[PipelineStrategy]] = None,
    session: Optional[Session] = None,
    engine: Optional[Engine] = None,
    variable_resolver: Optional[VariableResolver] = None,
    event_emitter: Optional[PipelineEventEmitter] = None,
    run_id: Optional[str] = None,
    instrumentation_settings: Any | None = None,
)
```

**Critical deviation from task 52 spec:** The spec suggests `pipeline_class(provider=None)` but the actual constructor requires `model: str` (a non-optional string). There is no `provider` parameter. Instantiation for validation-only would need a dummy model string like `"test:dummy"`.

### Pre-validation checks (L240-248)

```python
if self.REGISTRY is None:
    raise ValueError(f"{cls} must specify registry parameter when defining the class.")
if self.STRATEGIES is None and strategies is None:
    raise ValueError(f"{cls} must specify strategies parameter when defining the class.")
```

### _build_execution_order() (pipeline.py L334-349)

Collects all unique steps across all strategies. Assigns position indices. Maps extraction models to their owning step class. Maps transformation steps.

```python
def _build_execution_order(self) -> None:
    all_steps = []
    for strategy in self._strategies:
        for step_def in strategy.get_steps():
            step_class = step_def.step_class
            if step_class not in [s.step_class for s in all_steps]:
                all_steps.append(step_def)
    for position, step_def in enumerate(all_steps):
        step_class = step_def.step_class
        self._step_order[step_class] = position
        for extraction_class in step_def.extractions:
            model = extraction_class.MODEL
            self._model_extraction_step[model] = step_class
        if step_def.transformation:
            self._step_data_transformations[step_class] = step_class
```

**No errors raised.** Purely builds internal state. Safe to run. Only needs strategy instances with `get_steps()`.

### _validate_foreign_key_dependencies() (pipeline.py L368-385)

Checks that registry models with FK references appear AFTER their FK targets in the registry model list.

```python
def _validate_foreign_key_dependencies(self) -> None:
    if not self.REGISTRY or not hasattr(self.REGISTRY, "MODELS"):
        return
    registry_models = self.REGISTRY.MODELS
    model_positions = {model: i for i, model in enumerate(registry_models)}
    for model in registry_models:
        dependencies = self._get_foreign_key_dependencies(model)
        model_position = model_positions[model]
        for dependency in dependencies:
            if dependency not in model_positions:
                continue
            if model_positions[dependency] > model_position:
                raise ValueError(
                    f"Foreign key dependency error in {self.REGISTRY.__name__}:\n"
                    f"  '{model.__name__}' at position {model_position}, "
                    f"but FK to '{dependency.__name__}' at position "
                    f"{model_positions[dependency]}.\n"
                    f"Move '{dependency.__name__}' before '{model.__name__}'."
                )
```

**Error format:**
```
Foreign key dependency error in {RegistryName}:
  '{ModelName}' at position {N}, but FK to '{DepName}' at position {M}.
Move '{DepName}' before '{ModelName}'.
```

**Dependencies:** Needs REGISTRY.MODELS (list of SQLModel classes with `__table__` attributes). Inspects actual SQLAlchemy column FK metadata. Requires live Python class references.

### _validate_registry_order() (pipeline.py L387-404)

Checks that registry model ordering matches the step execution order for extraction.

```python
def _validate_registry_order(self) -> None:
    if not self.REGISTRY or not hasattr(self.REGISTRY, "MODELS"):
        return
    registry_models = self.REGISTRY.MODELS
    extracted_models = [m for m in registry_models if m in self._model_extraction_step]
    for i, model in enumerate(extracted_models):
        extraction_step = self._model_extraction_step[model]
        extraction_position = self._step_order[extraction_step]
        for prev_model in extracted_models[:i]:
            prev_step = self._model_extraction_step[prev_model]
            prev_position = self._step_order[prev_step]
            if prev_position > extraction_position:
                raise ValueError(
                    f"Extraction order mismatch in {self.REGISTRY.__name__}:\n"
                    f"  '{prev_model.__name__}' before '{model.__name__}' in "
                    f"registry, but extracted later.\n"
                    f"Reorder registry to match extraction order."
                )
```

**Error format:**
```
Extraction order mismatch in {RegistryName}:
  '{PrevModel}' before '{Model}' in registry, but extracted later.
Reorder registry to match extraction order.
```

**Dependencies:** Needs `_step_order` and `_model_extraction_step` (built by `_build_execution_order()`), plus REGISTRY.MODELS.

### DB session setup (L279-291)

```python
if session is not None:
    self._real_session = session
else:
    if engine is None:
        engine = init_pipeline_db()  # Creates auto-SQLite
    else:
        init_pipeline_db(engine)
    self._real_session = Session(engine)
self.session = ReadOnlySession(self._real_session)
```

**Side effect:** If no session/engine provided, creates an auto-SQLite DB. This means instantiation for validation-only has an unwanted side effect of creating a temporary database file.

## Layer 3: Runtime (`execute()`)

Triggered during pipeline execution. Not relevant for compile-time validation but documented for completeness.

### AGENT_REGISTRY check (pipeline.py L527-530)

```python
if self.AGENT_REGISTRY is None:
    raise ValueError(f"{cls} must specify agent_registry= parameter.")
```

### INPUT_DATA validation (pipeline.py L541-554)

```python
if cls.INPUT_DATA is not None:
    if input_data is None or not input_data:
        raise ValueError(f"Pipeline '{name}' requires input_data matching {cls.INPUT_DATA.__name__} schema...")
    try:
        self._validated_input = cls.INPUT_DATA.model_validate(input_data)
    except ValidationError as e:
        raise ValueError(f"Pipeline '{name}' input_data validation failed: {e}") from e
```

### _validate_step_access() (pipeline.py L406-436)

Runtime ordering guard -- prevents steps from accessing results of not-yet-executed steps.

### _validate_and_merge_context() (pipeline.py L438-468)

Validates that `process_instructions()` returns the correct context type.

## Step Definition and Dynamic Pipeline Construction

### step_definition decorator pattern

The `@step_definition` decorator (step.py) stores config on the class and provides `create_definition()` classmethod:

```python
@step_definition(
    instructions=SentimentAnalysisInstructions,
    default_system_key="sentiment_analysis",
    default_user_key="sentiment_analysis",
    context=SentimentAnalysisContext,
)
class SentimentAnalysisStep(LLMStep):
    ...
```

This sets class attributes: `INSTRUCTIONS`, `DEFAULT_SYSTEM_KEY`, `DEFAULT_USER_KEY`, `DEFAULT_EXTRACTIONS`, `DEFAULT_TRANSFORMATION`, `CONTEXT`.

`create_definition()` returns a `StepDefinition` dataclass wrapping all config:

```python
StepDefinition(
    step_class=cls,
    system_instruction_key=...,
    user_prompt_key=...,
    instructions=cls.INSTRUCTIONS,
    extractions=...,
    transformation=...,
    context=cls.CONTEXT,
)
```

### Pipeline wiring pattern (from demo/pipeline.py, creator/pipeline.py)

Pipelines are wired at class definition, not runtime:

```python
class TextAnalyzerPipeline(
    PipelineConfig,
    registry=TextAnalyzerRegistry,
    strategies=TextAnalyzerStrategies,
    agent_registry=TextAnalyzerAgentRegistry,
):
    INPUT_DATA: ClassVar[type] = TextAnalyzerInputData
```

### No dynamic pipeline construction exists

The task 52 spec references `build_pipeline_class(request.pipeline_structure)` but **no such function exists in the codebase**. Pipelines are always statically defined via Python class inheritance. Dynamic construction would require:

1. Dynamically creating `PipelineStrategy` subclasses
2. Dynamically creating `PipelineStrategies` subclasses
3. Dynamically creating `PipelineConfig` subclasses with `type()` or metaclass machinery

This is possible but complex and potentially dangerous (arbitrary code execution concerns).

## Existing Compile Endpoint Analysis

The compile endpoint (`llm_pipeline/ui/routes/editor.py`) already implements Level 1 structural validation:

### Current validation (L128-161)

```python
@router.post("/compile", response_model=CompileResponse)
def compile_pipeline(body: CompileRequest, request: Request) -> CompileResponse:
    # 1. Build set of known registered step names (from introspection)
    registered_steps = set(_collect_registered_steps(introspection_registry).keys())
    # 2. Build set of non-errored draft step names (from DB)
    draft_names = set(session.exec(select(DraftStep.name).where(...)).all())
    # 3. Check each step_ref exists in known set
    known = registered_steps | draft_names
    for strategy in body.strategies:
        for step in strategy.steps:
            if step.step_ref not in known:
                errors.append(CompileError(...))
```

### Current request/response shapes

```python
class CompileRequest(BaseModel):
    strategies: list[EditorStrategy]

class EditorStrategy(BaseModel):
    strategy_name: str
    steps: list[EditorStep]

class EditorStep(BaseModel):
    step_ref: str
    source: Literal["draft", "registered"]
    position: int

class CompileResponse(BaseModel):
    valid: bool
    errors: list[CompileError]

class CompileError(BaseModel):
    strategy_name: str
    step_ref: str
    message: str
```

### Missing from current compile: pipeline_name field

The current `CompileRequest` has no `pipeline_name` field. The task 51 research proposed including it but the implementation dropped it. The `DraftPipeline.name` is set separately via the CRUD endpoints.

## Feasibility: Validation Without Full Provider/Agent Setup

### What CAN be validated from JSON/metadata alone

| Validation | Feasible | How |
|------------|----------|-----|
| Step-ref existence | YES (done) | Cross-ref against introspection_registry + DraftStep DB |
| Duplicate steps within strategy | YES | Check step_ref uniqueness per strategy |
| Empty strategies | YES | Check each strategy has >= 1 step |
| Sequential positions | YES | Check positions are 0, 1, 2... |
| Step ordering (extraction deps) | PARTIAL | Requires introspection metadata for extraction model info |
| FK ordering | NO | Requires live SQLModel classes with `__table__` metadata |
| Prompt key existence | YES | Query Prompt table for system/user keys |
| Schema compatibility | NO | Would need JSON schema comparison logic |

### What CANNOT be validated without Python classes

1. **FK dependency ordering** -- `_validate_foreign_key_dependencies()` inspects `model.__table__.columns` for `foreign_keys`. This is SQLAlchemy metadata that only exists on real table classes.

2. **Full extraction order validation** -- `_validate_registry_order()` maps extraction classes to their `MODEL` attributes. Draft steps don't have real extraction classes.

3. **Context type validation** -- `_validate_and_merge_context()` uses `isinstance()` checks requiring real Python types.

### Recommended validation approach for compile endpoint enhancement

For registered steps: Use `PipelineIntrospector` metadata which already contains extraction class names, model class names, transformation info, and context schemas. Build a parallel validator that operates on this metadata.

For draft steps: Use `DraftStep.generated_code` dict which contains step structure info. Limited validation possible -- mainly existence and status checks.

## Error Parsing Strategy

All existing validation errors are plain `ValueError` or `TypeError` with formatted strings. There are no custom exception classes with structured data.

### Option A: Parse existing error strings (fragile)

```python
import re
FK_PATTERN = re.compile(
    r"Foreign key dependency error in (.+?):\n"
    r"\s+'(.+?)' at position (\d+), but FK to '(.+?)' at position (\d+)"
)
```

### Option B: Custom exceptions with structured data (recommended for new code)

```python
class PipelineValidationError(ValueError):
    def __init__(self, errors: list[CompileError]):
        self.errors = errors
        super().__init__(f"{len(errors)} validation error(s)")
```

### Option C: Parallel validator returning structured errors directly (best for compile)

```python
def validate_pipeline_structure(
    strategies: list[EditorStrategy],
    registered_metadata: dict[str, dict],
    draft_metadata: dict[str, DraftStep],
) -> list[CompileError]:
    errors = []
    # ... structural checks producing CompileError instances directly
    return errors
```

Option C avoids the need to parse error strings entirely. The compile endpoint already follows this pattern.

## StepDefinition.create_step() and Prompt Discovery

`create_step()` (strategy.py L48-143) has a significant dependency: it queries the Prompt DB table to auto-discover prompt keys when they're None. This means validation of prompt availability requires a DB session.

```python
def create_step(self, pipeline):
    # If keys are None, queries Prompt table for:
    # 1. "{step_name}.{strategy_name}" (strategy-scoped)
    # 2. "{step_name}" (step-scoped)
    # Raises ValueError if no prompts found at all
```

**Error:** `ValueError("No prompts found for {StepClassName}. Searched for:\n  - {step_name}.{strategy_name}\n  - {step_name}\nPlease provide explicit keys or ensure prompts exist in database.")`

This validation CAN be replicated for the compile endpoint since it has access to the DB engine and can query the Prompt table directly.

## Summary of Findings

1. **Three validation layers**: class-definition, instance-creation, runtime. Only instance-creation validations are relevant for compile.

2. **Instance-creation requires `model: str`** (not `provider=None` as spec suggests). Also triggers DB session creation as side effect.

3. **No `build_pipeline_class()` exists** in codebase. Dynamic class construction would need to be built from scratch.

4. **Existing compile endpoint** already handles step-ref existence checks. Enhancement should add: duplicate detection, position sequencing, and metadata-based ordering validation where feasible.

5. **FK ordering validation impossible** for JSON-only drafts (needs SQLAlchemy table metadata). Extraction ordering validation partial (needs introspection metadata).

6. **Best approach**: Parallel validator producing `CompileError` instances directly, using introspection metadata for registered steps and DraftStep DB records for draft steps. No class instantiation needed.

7. **Prompt validation possible**: Compile endpoint can query Prompt table to verify prompt keys exist for each step, using step_name derivation from introspection metadata.
