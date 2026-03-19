# Step 1: Codebase Architecture Research

## 1. Package Structure

```
llm_pipeline/
  __init__.py            # top-level re-exports, __all__, __version__
  pipeline.py            # PipelineConfig (ABC) - core orchestrator (~1100 lines)
  step.py                # LLMStep (ABC), LLMResultMixin, step_definition decorator
  strategy.py            # PipelineStrategy (ABC), PipelineStrategies (ABC), StepDefinition (dataclass)
  context.py             # PipelineContext (BaseModel), PipelineInputData (BaseModel)
  extraction.py          # PipelineExtraction (ABC) - LLM results -> DB models
  transformation.py      # PipelineTransformation (ABC) - data structure changes
  registry.py            # PipelineDatabaseRegistry (ABC) - declares managed DB models
  agent_registry.py      # AgentRegistry (ABC), AgentSpec (dataclass)
  agent_builders.py      # StepDeps (dataclass), build_step_agent() factory
  state.py               # PipelineStepState, PipelineRunInstance, PipelineRun (SQLModel tables)
  types.py               # ArrayValidationConfig, ValidationContext, StepCallParams (TypedDict)
  naming.py              # to_snake_case() utility
  validators.py          # not_found_validator(), array_length_validator() factories
  consensus.py           # ConsensusStrategy and implementations
  introspection.py       # PipelineIntrospector - class-level metadata extraction
  toolsets.py            # EventEmittingToolset (pydantic-ai WrapperToolset)
  db/
    __init__.py          # init_pipeline_db(), get_engine(), get_session()
    prompt.py            # Prompt (SQLModel table)
  prompts/
    __init__.py          # re-exports
    service.py           # PromptService - DB-backed prompt retrieval + formatting
    loader.py            # YAML file loading, sync_prompts()
    variables.py         # VariableResolver Protocol
  session/
    __init__.py
    readonly.py          # ReadOnlySession wrapper
  events/
    __init__.py          # re-exports all event types, emitters, handlers
    types.py             # 30+ frozen dataclass event types
    emitter.py           # PipelineEventEmitter (ABC), CompositeEmitter
    handlers.py          # LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler
    models.py            # PipelineEventRecord (SQLModel table)
  demo/
    __init__.py          # exports TextAnalyzerPipeline
    pipeline.py          # complete reference implementation (all classes in one file)
    prompts.py           # inline prompt dicts + seed_prompts()
  ui/                    # FastAPI UI (out of scope for creator)
```

## 2. Core Class Hierarchy and Patterns

### 2.1 `__init_subclass__` Declarative Configuration Pattern

Every base class uses `__init_subclass__(**kwargs)` to accept configuration at class definition time. This is THE core pattern.

```python
# Pattern: class definition time configuration via keyword args
class MyPipeline(PipelineConfig,
                 registry=MyRegistry,
                 strategies=MyStrategies,
                 agent_registry=MyAgentRegistry):
    pass

class MyRegistry(PipelineDatabaseRegistry, models=[ModelA, ModelB]):
    pass

class MyStrategies(PipelineStrategies, strategies=[StrategyA, StrategyB]):
    pass

class MyAgentRegistry(AgentRegistry, agents={"step_name": OutputModel}):
    pass

class MyExtraction(PipelineExtraction, model=SomeModel):
    pass

class MyTransformation(PipelineTransformation, input_type=X, output_type=Y):
    pass
```

Key behavior:
- Stores config on `ClassVar` (e.g., `cls.MODELS = models`)
- Validates naming conventions (raises `ValueError` on mismatch)
- Skips validation for intermediate base classes (`cls.__name__.startswith('_')` or `cls.__bases__[0] is not BaseClass`)
- `PipelineStrategy.__init_subclass__` auto-generates `cls.NAME` and `cls.DISPLAY_NAME` from class name

### 2.2 Strict Naming Convention Enforcement

All names are enforced at class definition time:

| Class Type | Required Suffix | Prefix Derivation | Related Names |
|---|---|---|---|
| `PipelineConfig` | `Pipeline` | `XxxPipeline` -> `Xxx` | `XxxRegistry`, `XxxStrategies`, `XxxAgentRegistry` |
| `LLMStep` | `Step` | `XxxStep` -> `Xxx` | `XxxInstructions`, `XxxTransformation`, `XxxContext` |
| `PipelineStrategy` | `Strategy` | `XxxStrategy` -> `xxx` (NAME) | - |
| `PipelineExtraction` | `Extraction` | - | - |

Snake case conversion uses `to_snake_case(name, strip_suffix)` from `naming.py`:
- Double regex: handles consecutive capitals (HTMLParser -> html_parser)
- `ConstraintExtractionStep` -> `constraint_extraction` (strip "Step")
- `LaneBasedStrategy` -> `lane_based` (strip "Strategy")

### 2.3 PipelineConfig (pipeline.py)

ABC. The central orchestrator.

**ClassVars (set via `__init_subclass__`):**
- `REGISTRY: Type[PipelineDatabaseRegistry]` - required
- `STRATEGIES: Type[PipelineStrategies]` - required
- `AGENT_REGISTRY: Type[AgentRegistry]` - required for execute()
- `INPUT_DATA: Type[PipelineInputData]` - optional, must be PipelineInputData subclass

**Constructor (`__init__`):**
```python
def __init__(self, model, strategies=None, session=None, engine=None,
             variable_resolver=None, event_emitter=None, run_id=None,
             instrumentation_settings=None):
```
- `model`: pydantic-ai model string (e.g. `'google-gla:gemini-2.0-flash-lite'`)
- Creates session: explicit session > engine > auto-SQLite (via `init_pipeline_db()`)
- Wraps real session in `ReadOnlySession` for step access
- Calls `_build_execution_order()`, `_validate_foreign_key_dependencies()`, `_validate_registry_order()`

**Execution (`execute()`):**
1. Creates `PipelineRun` record
2. Validates `input_data` against `INPUT_DATA` schema if declared
3. Iterates step indices 0..max_steps:
   - Selects strategy via `strategy.can_handle(context)`
   - Creates step via `step_def.create_step(pipeline=self)`
   - Handles caching (optional)
   - Calls `step.prepare_calls()` -> builds agent -> `agent.run_sync()` -> `step.process_instructions()` -> merge context -> `step.extract_data()`
   - Saves state, logs instructions, handles transformations
4. Updates `PipelineRun` status

**Key properties:**
- `pipeline_name`: auto-derived from class name (`TextAnalyzerPipeline` -> `text_analyzer`)
- `context`: dict of derived values from steps
- `instructions`: read-only MappingProxyType of step results
- `validated_input`: PipelineInputData instance or raw dict

### 2.4 LLMStep (step.py)

ABC. Base for step implementations.

**Constructor params:** `system_instruction_key`, `user_prompt_key`, `instructions` (Pydantic model type), `pipeline` (PipelineConfig ref)

**Key methods:**
- `prepare_calls() -> List[StepCallParams]` - ABSTRACT, REQUIRED
- `process_instructions(instructions: List[Any]) -> Dict|PipelineContext` - optional, default returns {}
- `should_skip() -> bool` - optional, default False
- `log_instructions(instructions)` - optional logging hook
- `extract_data(instructions)` - auto-delegates to extraction classes
- `build_user_prompt(variables, prompt_service, context)` - renders user prompt
- `get_agent(registry)` -> `(output_type, tools)` - looks up in AgentRegistry
- `step_name` property: auto-derived from class name

**StepCallParams (TypedDict):**
```python
class StepCallParams(TypedDict, total=False):
    variables: Any              # REQUIRED - template variables
    array_validation: Optional[Any]
    validation_context: Optional[Any]
```

### 2.5 step_definition Decorator

Connects step class with its configuration. Adds `create_definition()` classmethod.

```python
@step_definition(
    instructions=XxxInstructions,        # REQUIRED - Pydantic model for LLM output
    default_system_key="xxx",            # Optional - DB prompt key
    default_user_key="xxx",              # Optional - DB prompt key
    default_extractions=[XxxExtraction], # Optional - extraction classes
    default_transformation=XxxTransformation, # Optional
    context=XxxContext,                  # Optional - PipelineContext subclass
)
class XxxStep(LLMStep):
    ...
```

Enforces naming: instructions must be `{StepPrefix}Instructions`, transformation must be `{StepPrefix}Transformation`, context must be `{StepPrefix}Context`.

The `create_definition()` classmethod produces a `StepDefinition` dataclass.

### 2.6 StepDefinition (strategy.py)

Dataclass connecting step class to its full configuration:

```python
@dataclass
class StepDefinition:
    step_class: Type
    system_instruction_key: str
    user_prompt_key: str
    instructions: Type
    action_after: Optional[str] = None
    extractions: List[Type[PipelineExtraction]] = field(default_factory=list)
    transformation: Optional[Type[PipelineTransformation]] = None
    context: Optional[Type] = None
    agent_name: str | None = None
    not_found_indicators: list[str] | None = None
    consensus_strategy: ConsensusStrategy | None = None
```

`create_step(pipeline)` method:
- Auto-discovers prompt keys from DB if not provided (strategy-level > step-level fallback)
- Instantiates step class, attaches `_extractions`, `_transformation`, `_context`, `_agent_name`

### 2.7 LLMResultMixin (step.py)

Base for all LLM instruction/output schemas:

```python
class LLMResultMixin(BaseModel):
    confidence_score: float = Field(default=0.95, ge=0.0, le=1.0)
    notes: str | None = Field(default=None)
```

Features:
- `__init_subclass__` validates `example` ClassVar dict if present
- `get_example()` returns validated instance from `example`
- `create_failure(reason, **safe_defaults)` returns failure result with confidence=0.0

### 2.8 PipelineStrategy / PipelineStrategies (strategy.py)

**PipelineStrategy (ABC):**
- `can_handle(context: Dict) -> bool` - ABSTRACT
- `get_steps() -> List[StepDefinition]` - ABSTRACT
- Auto-generates `NAME` and `DISPLAY_NAME` from class name via `__init_subclass__`
- `name` / `display_name` properties read from `cls.NAME` / `cls.DISPLAY_NAME`

**PipelineStrategies (ABC):**
- Configured via `strategies=[...]` keyword arg
- `create_instances()` -> list of instantiated strategies
- `get_strategy_names()` -> list of strategy name strings

### 2.9 AgentRegistry / AgentSpec (agent_registry.py)

```python
class AgentRegistry(ABC):
    AGENTS: ClassVar[dict[str, Type[BaseModel] | AgentSpec]] = {}

    @classmethod
    def get_output_type(cls, step_name) -> Type[BaseModel]

    @classmethod
    def get_tools(cls, step_name) -> list[Any]
```

Maps step names to output types and optional tools. Used by `LLMStep.get_agent()` and `build_step_agent()`.

### 2.10 build_step_agent / StepDeps (agent_builders.py)

**StepDeps (dataclass):** Dependency injection container for pydantic-ai agents:
- `session`, `pipeline_context`, `prompt_service` - core
- `run_id`, `pipeline_name`, `step_name` - execution metadata
- `event_emitter`, `variable_resolver` - optional
- `array_validation`, `validation_context` - per-call config
- `extra: dict` - extensible bag for domain-specific deps

**build_step_agent():** Factory creating `Agent[StepDeps, Any]`:
- Registers `@agent.instructions` that resolves system prompt from DB at runtime
- Registers output validators
- Wraps tools in `EventEmittingToolset` if provided
- Uses `defer_model_check=True` for runtime model selection

### 2.11 PipelineExtraction (extraction.py)

ABC. Converts LLM results into SQLModel instances.

- Configured via `model=SomeModel` keyword arg
- Must end with `Extraction` suffix
- `extract()` auto-detects method: `default()` > strategy-match > single custom method
- `_validate_instances()` validates before DB insertion (NaN, NULL checks)
- Constructor validates `MODEL` is in pipeline's `REGISTRY`

### 2.12 PipelineTransformation (transformation.py)

ABC. Data structure changes with type validation.

- Configured via `input_type=X, output_type=Y` keyword args
- `transform()` auto-detects method: `default()` > single custom > passthrough
- Validates input/output types

### 2.13 PipelineDatabaseRegistry (registry.py)

ABC. Declares managed DB models.

- Configured via `models=[...]` keyword arg (insertion order = FK dependency order)
- `get_models()` returns the list (raises if empty)
- Empty models list (`models=[]`) is valid for pipelines without DB extractions -- `_validate_registry_order` and `_validate_foreign_key_dependencies` iterate safely over empty lists

### 2.14 PipelineContext (context.py)

Simple Pydantic BaseModel base class for step context contributions. Steps return instances; pipeline merges via `model_dump()` into `self._context` dict.

### 2.15 PipelineInputData (context.py)

Base class for validated pipeline input. Pipeline validates `input_data` against `cls.INPUT_DATA.model_validate()` in `execute()`.

## 3. Prompt System

### 3.1 DB Model (db/prompt.py)

```python
class Prompt(SQLModel, table=True):
    prompt_key: str          # e.g. "sentiment_analysis"
    prompt_name: str         # human-readable name
    prompt_type: str         # "system" or "user"
    category: Optional[str]  # pipeline category
    step_name: Optional[str] # step this belongs to
    content: str             # template with {variable} placeholders
    required_variables: Optional[List[str]]  # auto-extracted from content
    version: str = "1.0"
    is_active: bool = True
```

Unique constraint: `(prompt_key, prompt_type)`.

### 3.2 PromptService (prompts/service.py)

- `get_prompt(prompt_key, prompt_type, context, fallback)` - retrieves from DB
- `get_system_prompt(prompt_key, variables, ...)` - retrieves + formats with `{var}` substitution
- `get_user_prompt(prompt_key, variables, ...)` - same for user prompts

### 3.3 Seeding Pattern (demo/prompts.py)

```python
ALL_PROMPTS: list[dict] = [
    {"prompt_key": "sentiment_analysis", "prompt_type": "system", "content": "...", ...},
    {"prompt_key": "sentiment_analysis", "prompt_type": "user", "content": "...", ...},
]

def seed_prompts(cls, engine):
    # Create tables, idempotently insert prompts
    with Session(engine) as session:
        for prompt_data in ALL_PROMPTS:
            existing = session.exec(select(Prompt).where(...)).first()
            if existing is None:
                session.add(Prompt(**prompt_data))
        session.commit()
```

Pipeline exposes this via:
```python
class TextAnalyzerPipeline(PipelineConfig, ...):
    @classmethod
    def seed_prompts(cls, engine):
        from llm_pipeline.demo.prompts import seed_prompts
        seed_prompts(cls, engine)
```

## 4. Build System and Dependencies

### 4.1 pyproject.toml

- Build: `hatchling`
- Core deps: `pydantic>=2.0`, `sqlmodel>=0.0.14`, `sqlalchemy>=2.0`, `pyyaml>=6.0`, `pydantic-ai>=1.0.5`, `python-dotenv>=1.0`
- Optional: `[ui]`, `[otel]`, `[dev]`
- Entry points: `[project.entry-points."llm_pipeline.pipelines"]` for pipeline discovery
- Wheel includes `llm_pipeline/` package + frontend dist artifacts

### 4.2 Test Structure

- pytest in `tests/` directory
- `conftest.py` provides shared mock builders
- Tests create in-memory SQLite engines, define test domain models (Widget, etc.)
- Import from `llm_pipeline` top-level or submodules as needed

## 5. Reference Implementation Analysis (TextAnalyzer Demo)

Complete pipeline in `demo/pipeline.py` (~290 lines). Single file containing:

1. **InputData:** `TextAnalyzerInputData(PipelineInputData)` with `text: str` field
2. **DB Models:** `TopicItem(BaseModel)` (LLM shape), `Topic(SQLModel, table=True)` (DB record)
3. **Registry:** `TextAnalyzerRegistry(PipelineDatabaseRegistry, models=[Topic])`
4. **Instructions (3):** Each extends `LLMResultMixin`, has `example: ClassVar[dict]`
5. **Contexts (3):** Each extends `PipelineContext` with step-specific fields
6. **Extraction (1):** `TopicExtraction(PipelineExtraction, model=Topic)` with `default()` method
7. **Steps (3):** Each decorated with `@step_definition`, implements `prepare_calls()` and `process_instructions()`
8. **AgentRegistry:** `TextAnalyzerAgentRegistry(AgentRegistry, agents={...})` mapping 3 step names
9. **Strategy:** Single `DefaultStrategy(PipelineStrategy)` with `can_handle() -> True` and `get_steps()` returning 3 step definitions
10. **Strategies:** `TextAnalyzerStrategies(PipelineStrategies, strategies=[DefaultStrategy])`
11. **Pipeline:** `TextAnalyzerPipeline(PipelineConfig, registry=..., strategies=..., agent_registry=...)` with `INPUT_DATA` ClassVar and `seed_prompts()` classmethod

## 6. Extension Points for Creator Package

### 6.1 What Creator Must Implement

Following exact codebase patterns, `llm_pipeline/creator/` needs:

```
llm_pipeline/creator/
  __init__.py                 # re-exports StepCreatorPipeline
  pipeline.py                 # all classes: input, instructions, contexts, steps, registries, strategy, pipeline
  prompts.py                  # inline prompt dicts + seed_prompts()
  templates/                  # Jinja2 templates for code generation
    step.py.j2
    instructions.py.j2
    extraction.py.j2
    prompts.yaml.j2
```

### 6.2 Classes to Create (following naming conventions)

| Class | Base | Notes |
|---|---|---|
| `StepCreatorInputData` | `PipelineInputData` | NL description input |
| `RequirementsAnalysisInstructions` | `LLMResultMixin` | fields, validation_rules, extraction_targets |
| `RequirementsAnalysisContext` | `PipelineContext` | structured requirements |
| `RequirementsAnalysisStep` | `LLMStep` | @step_definition decorated |
| `CodeGenerationInstructions` | `LLMResultMixin` | generated Python source |
| `CodeGenerationContext` | `PipelineContext` | code artifacts |
| `CodeGenerationStep` | `LLMStep` | @step_definition decorated |
| `PromptGenerationInstructions` | `LLMResultMixin` | generated YAML prompts |
| `PromptGenerationContext` | `PipelineContext` | prompt artifacts |
| `PromptGenerationStep` | `LLMStep` | @step_definition decorated |
| `ValidationInstructions` | `LLMResultMixin` | validation report |
| `ValidationContext` | `PipelineContext` | validation results |
| `ValidationStep` | `LLMStep` | @step_definition decorated |
| `StepCreatorRegistry` | `PipelineDatabaseRegistry` | `models=[]` (no DB extractions) |
| `StepCreatorAgentRegistry` | `AgentRegistry` | 4 step mappings |
| `DefaultStrategy` | `PipelineStrategy` | always-true, returns 4 step defs |
| `StepCreatorStrategies` | `PipelineStrategies` | `strategies=[DefaultStrategy]` |
| `StepCreatorPipeline` | `PipelineConfig` | wires all together |

### 6.3 Empty Registry Validity

Verified: `StepCreatorRegistry(PipelineDatabaseRegistry, models=[])` is safe because:
- `__init_subclass__` sets `cls.MODELS = []` (truthy check bypassed since models parameter is not None)
- `_validate_foreign_key_dependencies()` guards with `if not self.REGISTRY or not hasattr(self.REGISTRY, 'MODELS'): return`, then iterates empty list
- `_validate_registry_order()` accesses `self.REGISTRY.MODELS` directly and iterates; empty list = no-op
- `get_models()` raises if `not cls.MODELS` but is only called from `PipelineExtraction.__init__()` -- no extractions = never called

### 6.4 Dependency Addition

Jinja2 should be an optional dependency:
```toml
[project.optional-dependencies]
creator = ["jinja2>=3.0"]
```

### 6.5 Entry Point Registration

```toml
[project.entry-points."llm_pipeline.pipelines"]
step_creator = "llm_pipeline.creator:StepCreatorPipeline"
```

## 7. Key Patterns the Creator Must Follow

1. **All `__init_subclass__` config** -- never runtime configuration for class-level concerns
2. **Naming convention enforcement** -- all names derivable from class name prefixes
3. **`step_definition` decorator** on every step class
4. **`LLMResultMixin` base** for all instruction schemas with `example: ClassVar[dict]`
5. **`PipelineContext` subclass** for each step's context contribution
6. **`prepare_calls() -> List[StepCallParams]`** returning dicts with `variables` key
7. **`process_instructions(instructions) -> Context`** returning context instance
8. **`seed_prompts()` pattern** for prompt initialization
9. **`__all__` exports** in every module
10. **TYPE_CHECKING imports** for circular dependency avoidance
11. **`to_snake_case()`** for all name derivations
12. **`StepKeyDict`** allows both string and Step class keys for pipeline data access

## 8. Upstream/Downstream Task Context

### Upstream: Task 18 (done)
Export event system in `__init__.py`. All events, emitters, handlers exported. Completed -- no deviations.

### Downstream: Task 46 (pending) - OUT OF SCOPE
Docker sandbox for testing generated code. Depends on task 45.

### Downstream: Task 47 (pending) - OUT OF SCOPE
Auto-integration (StepIntegrator) that writes files and updates strategy/registry/prompts. Depends on tasks 45+46.
