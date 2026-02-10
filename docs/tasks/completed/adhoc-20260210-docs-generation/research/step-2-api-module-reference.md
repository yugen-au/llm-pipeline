# llm-pipeline API Module Reference

Complete catalog of public APIs, classes, functions, and usage patterns for the llm-pipeline library.

## Package Information

- **Package Name**: `llm-pipeline`
- **Version**: 0.1.0
- **Python**: >=3.11
- **License**: MIT

## Installation

```bash
pip install llm-pipeline              # Core library
pip install llm-pipeline[gemini]     # With Gemini provider support
pip install llm-pipeline[dev]        # Development dependencies
```

## Top-Level Imports

All core classes are re-exported from `llm_pipeline` for convenient import:

```python
from llm_pipeline import (
    # Core
    PipelineConfig,
    LLMStep,
    LLMResultMixin,
    step_definition,

    # Strategy
    PipelineStrategy,
    PipelineStrategies,
    StepDefinition,

    # Data handling
    PipelineContext,
    PipelineExtraction,
    PipelineTransformation,
    PipelineDatabaseRegistry,

    # State
    PipelineStepState,
    PipelineRunInstance,

    # Types
    ArrayValidationConfig,
    ValidationContext,

    # DB
    init_pipeline_db,

    # Session
    ReadOnlySession,
)
```

---

## Module: `llm_pipeline.pipeline`

### Class: `PipelineConfig`

**Base class for LLM pipeline configurations.**

Abstract base class managing step results, context, data, extractions, strategies, and registry.

#### Class Definition

```python
class PipelineConfig(ABC):
    REGISTRY: ClassVar[Type[PipelineDatabaseRegistry]] = None
    STRATEGIES: ClassVar[Type[PipelineStrategies]] = None
```

#### Constructor

```python
def __init__(
    self,
    strategies: Optional[List[PipelineStrategy]] = None,
    session: Optional[Session] = None,
    engine: Optional[Engine] = None,
    provider: Optional[LLMProvider] = None,
    variable_resolver: Optional[VariableResolver] = None,
)
```

**Parameters:**
- `strategies`: Optional list of PipelineStrategy instances. Uses class-level STRATEGIES if None.
- `session`: Optional database session. Overrides engine if provided.
- `engine`: Optional SQLAlchemy engine. Auto-creates SQLite if both session and engine are None.
- `provider`: LLMProvider instance for LLM calls (required for execute()).
- `variable_resolver`: Optional VariableResolver for prompt variable classes.

#### Subclass Definition

```python
class MyPipeline(
    PipelineConfig,
    registry=MyRegistry,
    strategies=MyStrategies
):
    pass
```

**Naming Convention:**
- Pipeline class name must end with `Pipeline` suffix
- Registry must be named `{Prefix}Registry`
- Strategies must be named `{Prefix}Strategies`

#### Properties

```python
@property
def instructions(self) -> MappingProxyType:
    """Read-only access to LLM step instructions."""

@property
def context(self) -> Dict[str, Any]:
    """Read-write access to derived context values."""

@property
def pipeline_name(self) -> str:
    """Auto-derived pipeline name (CamelCase -> snake_case, remove Pipeline)."""
```

#### Public Attributes

- `data: StepKeyDict` - Data storage with step-based keys
- `extractions: Dict[Type[SQLModel], List[SQLModel]]` - Extracted database models
- `run_id: str` - UUID identifying this pipeline run
- `session: ReadOnlySession` - Read-only database session wrapper

#### Methods

##### `execute()`

```python
def execute(
    self,
    data: Any,
    initial_context: Dict[str, Any],
    use_cache: bool = False,
    consensus_polling: Optional[Dict[str, Any]] = None,
) -> PipelineConfig:
```

Execute pipeline steps with optional caching and consensus polling.

**Parameters:**
- `data`: Input data to process
- `initial_context`: Initial context values
- `use_cache`: Enable result caching based on input hash and prompt version
- `consensus_polling`: Optional dict with keys:
  - `enable`: bool - Enable consensus polling
  - `consensus_threshold`: int - Number of matching responses required (default: 3)
  - `maximum_step_calls`: int - Maximum LLM calls per step (default: 5)

**Returns:** Self (for chaining)

##### `get_data()`

```python
def get_data(self, key: str = "current") -> Any:
```

Retrieve data by key with validation.

**Parameters:**
- `key`: One of:
  - `"current"` - Most recent step's data
  - `"raw"` - Original input data
  - `"sanitized"` - Sanitized version of current data
  - Step class or step name - Data from specific step

**Returns:** Data for the requested key

**Raises:** `ValueError` if accessing data from non-executed step

##### `get_instructions()`

```python
def get_instructions(self, key) -> Any:
```

Retrieve step instructions with execution order validation.

**Parameters:**
- `key`: Step class or step name

**Returns:** List of instruction objects for that step

##### `get_extractions()`

```python
def get_extractions(self, model_class: Type[TModel]) -> List[TModel]:
```

Retrieve extracted instances of a model type with validation.

**Parameters:**
- `model_class`: SQLModel class from registry

**Returns:** List of extracted instances

**Raises:**
- `ValueError` if model not in registry
- `ValueError` if accessing before extraction step executes

##### `store_extractions()`

```python
def store_extractions(
    self,
    model_class: Type[SQLModel],
    instances: List[SQLModel]
) -> None:
```

Store extracted database models on pipeline.

##### `save()`

```python
def save(
    self,
    session: Session = None,
    tables: Optional[List[Type[SQLModel]]] = None,
) -> Dict[str, int]:
```

Save extracted database instances to database.

**Parameters:**
- `session`: Optional session. Uses pipeline session if None.
- `tables`: Optional list of models to save. Saves all registry models if None.

**Returns:** Dict with counts like `{"lanes_saved": 5, "rates_saved": 10}`

##### `clear_cache()`

```python
def clear_cache(self) -> int:
```

Clear cached step state for this run.

**Returns:** Number of cached steps cleared

##### `ensure_table()`

```python
def ensure_table(self, model_class: Type[SQLModel], session: Session) -> None:
```

Create table for model if it doesn't exist.

##### `sanitize()`

```python
def sanitize(self, data: Any) -> str:
```

Override for custom data sanitization. Default: `str(data)`

##### `close()`

```python
def close(self) -> None:
```

Close database session if pipeline owns it.

---

## Module: `llm_pipeline.step`

### Class: `LLMStep`

**Base class for LLM-powered pipeline steps.**

Abstract base class implementing the interface for pipeline steps that make LLM calls.

#### Constructor

```python
def __init__(
    self,
    system_instruction_key: str,
    user_prompt_key: str,
    instructions: Type[BaseModel],
    pipeline: PipelineConfig
):
```

**Parameters:**
- `system_instruction_key`: Database key for system instruction prompt
- `user_prompt_key`: Database key for user prompt template
- `instructions`: Pydantic model class for validating LLM responses
- `pipeline`: Reference to parent pipeline

#### Properties

```python
@property
def step_name(self) -> str:
    """Auto-derived step name (CamelCase -> snake_case, remove 'Step')."""
```

#### Abstract Methods

```python
@abstractmethod
def prepare_calls(self) -> List[StepCallParams]:
    """Prepare LLM call(s) for this step based on pipeline context."""
```

Returns list of dicts with:
- `variables`: PromptVariables instance with template variables
- `array_validation`: Optional ArrayValidationConfig
- `validation_context`: Optional ValidationContext

#### Overridable Methods

```python
def process_instructions(self, instructions: List[Any]) -> Dict[str, Any]:
    """Process raw LLM instructions to extract derived context values."""
    # Default: returns empty dict

def should_skip(self) -> bool:
    """Determine if this step should be skipped based on context."""
    # Default: returns False

def log_instructions(self, instructions: List[Any]) -> None:
    """Log step instructions to console."""
    # Default: no-op

def extract_data(self, instructions: List[Any]) -> None:
    """Extract database models from LLM instructions."""
    # Automatically delegates to registered extraction classes
```

#### Helper Methods

```python
def create_llm_call(
    self,
    variables: Dict[str, Any],
    system_instruction_key: Optional[str] = None,
    user_prompt_key: Optional[str] = None,
    instructions: Optional[Type[BaseModel]] = None,
    **extra_params
) -> ExecuteLLMStepParams:
```

Create ExecuteLLMStepParams dict with defaults from step config. Auto-instantiates System variables if variable_resolver configured.

```python
def store_extractions(
    self,
    model_class: Type[SQLModel],
    instances: List[SQLModel]
) -> None:
```

Store extracted database models on pipeline.

---

### Class: `LLMResultMixin`

**Mixin for standardized LLM result fields.**

All LLM step result schemas should inherit from this to ensure confidence scoring and notes fields.

#### Definition

```python
class LLMResultMixin(BaseModel):
    confidence_score: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="Confidence in this analysis (0-1)"
    )
    notes: str | None = Field(
        default=None,
        description="General observations, reasoning, or additional context"
    )
```

#### Class Methods

```python
@classmethod
def get_example(cls):
    """Get an example instance from class.example dict."""

@classmethod
def create_failure(cls, reason: str, **safe_defaults):
    """Create a failure result with confidence=0.0 and failure note."""
```

#### Usage

```python
class MyInstructions(LLMResultMixin):
    table_type: str
    num_rows: int

    example = {
        "table_type": "lane_based",
        "num_rows": 10,
        "confidence_score": 0.95,
        "notes": "Clear structure detected"
    }
```

---

### Decorator: `step_definition`

**Auto-generate factory function for creating step definitions.**

Stores configuration on class and provides `create_definition()` method.

#### Signature

```python
def step_definition(
    instructions: Type[BaseModel],
    default_system_key: Optional[str] = None,
    default_user_key: Optional[str] = None,
    default_extractions: Optional[List] = None,
    default_transformation=None,
    context: Optional[Type] = None,
):
```

**Parameters:**
- `instructions`: Pydantic instruction class (must be named `{StepName}Instructions`)
- `default_system_key`: Default system instruction prompt key
- `default_user_key`: Default user prompt template key
- `default_extractions`: List of PipelineExtraction classes
- `default_transformation`: PipelineTransformation class (must be named `{StepName}Transformation`)
- `context`: Context class this step produces (must be named `{StepName}Context`)

#### Usage

```python
@step_definition(
    instructions=TableTypeDetectionInstructions,
    default_system_key="table_type_detection",
    default_user_key="table_type_detection",
    context=TableTypeDetectionContext
)
class TableTypeDetectionStep(LLMStep):
    def prepare_calls(self) -> List[StepCallParams]:
        return [{"variables": {"sheet_data": self.pipeline.get_data("current")}}]

    def process_instructions(self, instructions) -> TableTypeDetectionContext:
        return TableTypeDetectionContext(table_type=instructions[0].table_type)
```

#### Auto-Generated Method

```python
@classmethod
def create_definition(
    cls,
    system_instruction_key: Optional[str] = None,
    user_prompt_key: Optional[str] = None,
    extractions: Optional[List] = None,
    transformation=None,
    **kwargs
) -> StepDefinition:
```

---

## Module: `llm_pipeline.strategy`

### Class: `PipelineStrategy`

**Base class for pipeline strategies.**

Abstract base class defining when a strategy applies and what steps it provides.

#### Definition

```python
class PipelineStrategy(ABC):
    NAME: ClassVar[str]          # Auto-generated from class name
    DISPLAY_NAME: ClassVar[str]  # Auto-generated for UI
```

**Naming Convention:**
- Class name must end with `Strategy` suffix
- `LaneBasedStrategy` -> `NAME = "lane_based"`, `DISPLAY_NAME = "Lane Based"`

#### Properties

```python
@property
def name(self) -> str:
    """Strategy name (auto-generated from class name)."""

@property
def display_name(self) -> str:
    """Human-readable strategy name."""
```

#### Abstract Methods

```python
@abstractmethod
def can_handle(self, context: Dict[str, Any]) -> bool:
    """Determine if this strategy can handle the current context."""

@abstractmethod
def get_steps(self) -> List[StepDefinition]:
    """Define all steps for this strategy."""
```

#### Usage

```python
class LaneBasedStrategy(PipelineStrategy):
    def can_handle(self, context: Dict[str, Any]) -> bool:
        return context.get("table_type") == "lane_based"

    def get_steps(self) -> List[StepDefinition]:
        return [
            ConstraintExtractionStep.create_definition(),
            SemanticMappingStep.create_definition(
                extractions=[LaneExtraction, RateExtraction]
            ),
        ]
```

---

### Class: `PipelineStrategies`

**Base class for declaring pipeline strategies.**

Declarative way to define which strategies a pipeline uses.

#### Definition

```python
class PipelineStrategies(ABC):
    STRATEGIES: ClassVar[List[Type[PipelineStrategy]]] = []
```

#### Subclass Definition

```python
class MyPipelineStrategies(PipelineStrategies, strategies=[
    LaneBasedStrategy,
    DestinationBasedStrategy,
    GlobalRatesStrategy,
]):
    pass
```

**Naming Convention:**
- Must match pipeline prefix: `MyPipelineStrategies` for `MyPipeline`

#### Class Methods

```python
@classmethod
def create_instances(cls) -> List[PipelineStrategy]:
    """Create instances of all configured strategies."""

@classmethod
def get_strategy_names(cls) -> List[str]:
    """Get names of all configured strategies."""
```

---

### Dataclass: `StepDefinition`

**Definition of a pipeline step with configuration.**

Connects step class with prompts, extractions, transformation, and context.

#### Definition

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
```

#### Methods

```python
def create_step(self, pipeline: PipelineConfig):
    """
    Create configured step instance with pipeline reference.

    Auto-discovers prompt keys if not provided:
    1. Strategy-level: step_name.strategy_name
    2. Step-level: step_name
    3. Error if none found
    """
```

---

## Module: `llm_pipeline.context`

### Class: `PipelineContext`

**Base class for step context contributions.**

Steps that add values to pipeline context should define a Context class inheriting from this.

#### Definition

```python
class PipelineContext(BaseModel):
    pass
```

**Naming Convention:**
- Context class must be named `{StepName}Context`

#### Usage

```python
class TableTypeDetectionContext(PipelineContext):
    table_type: str

@step_definition(
    instructions=TableTypeDetectionInstructions,
    context=TableTypeDetectionContext
)
class TableTypeDetectionStep(LLMStep):
    def process_instructions(self, instructions) -> TableTypeDetectionContext:
        return TableTypeDetectionContext(
            table_type=instructions[0].table_type.value
        )
```

---

## Module: `llm_pipeline.extraction`

### Class: `PipelineExtraction`

**Base class for data extraction logic.**

Abstract base class for creating database model instances from LLM results.

#### Definition

```python
class PipelineExtraction(ABC):
    MODEL: ClassVar[Type[SQLModel]] = None
```

#### Subclass Definition

```python
class LaneExtraction(PipelineExtraction, model=Lane):
    def default(self, results: List[SemanticMappingInstructions]) -> List[Lane]:
        # Extraction logic
        return lanes
```

**Naming Convention:**
- Class name must end with `Extraction` suffix

#### Constructor

```python
def __init__(self, pipeline: PipelineConfig):
    """Initialize with pipeline reference. Validates MODEL in registry."""
```

#### Methods

##### `extract()` (Auto-dispatch)

```python
def extract(self, results: List[any]) -> List[SQLModel]:
    """
    Auto-detect and call the appropriate extraction method.

    Method detection priority:
    1. Explicit 'default' method -> always used
    2. Method matching current strategy name -> auto-routed
    3. Exactly one custom method -> auto-detected
    4. Otherwise -> error (ambiguous)
    """
```

#### Method Naming Patterns

```python
# Pattern 1: Single method (any name) - auto-detected
class SimpleExtraction(PipelineExtraction, model=MyModel):
    def extract_models(self, results):
        return [MyModel(...)]

# Pattern 2: Explicit default - always used
class DefaultExtraction(PipelineExtraction, model=MyModel):
    def default(self, results):
        return [MyModel(...)]

# Pattern 3: Strategy-specific methods
class MultiStrategyExtraction(PipelineExtraction, model=MyModel):
    def lane_based(self, results):  # Called by LaneBasedStrategy
        return [MyModel(...)]

    def destination_based(self, results):  # Called by DestinationBasedStrategy
        return [MyModel(...)]
```

#### Validation

Auto-validates extracted instances for:
- NaN/Infinity in Decimal fields
- NULL in required fields
- NULL in foreign key fields

**Raises:** `ValueError` with detailed error if validation fails

---

## Module: `llm_pipeline.transformation`

### Class: `PipelineTransformation`

**Base class for data transformation logic.**

Abstract base class for data structure changes with type validation.

#### Definition

```python
class PipelineTransformation(ABC):
    INPUT_TYPE: ClassVar[Type] = None
    OUTPUT_TYPE: ClassVar[Type] = None
```

#### Subclass Definition

```python
class UnpivotTransformation(
    PipelineTransformation,
    input_type=pd.DataFrame,
    output_type=pd.DataFrame
):
    def default(self, data: pd.DataFrame, instructions: UnpivotInstructions) -> pd.DataFrame:
        # Transformation logic
        return transformed_df
```

#### Constructor

```python
def __init__(self, pipeline: PipelineConfig):
    """Initialize with pipeline reference."""
```

#### Methods

##### `transform()` (Auto-dispatch)

```python
def transform(self, data: Any, instructions: Any) -> Any:
    """
    Auto-detect and call the appropriate transformation method.

    Method detection priority:
    1. Explicit 'default' method -> always used
    2. Exactly one custom method -> auto-detected
    3. No methods defined -> passthrough (returns data unchanged)
    4. Otherwise -> error (ambiguous)
    """
```

#### Method Naming Patterns

```python
# Pattern 1: No methods - passthrough
class PassthroughTransformation(PipelineTransformation, input_type=Any, output_type=Any):
    pass  # Returns data unchanged

# Pattern 2: Single method
class SimpleTransformation(PipelineTransformation, input_type=pd.DataFrame, output_type=pd.DataFrame):
    def transform_data(self, data, instructions):
        return data.melt(...)

# Pattern 3: Explicit default
class DefaultTransformation(PipelineTransformation, input_type=pd.DataFrame, output_type=pd.DataFrame):
    def default(self, data, instructions):
        return data.melt(...)
```

---

## Module: `llm_pipeline.registry`

### Class: `PipelineDatabaseRegistry`

**Base class for pipeline database registries.**

Declares which database models a pipeline manages and their insertion order.

#### Definition

```python
class PipelineDatabaseRegistry(ABC):
    MODELS: ClassVar[List[Type[SQLModel]]] = []
```

#### Subclass Definition

```python
class MyPipelineRegistry(PipelineDatabaseRegistry, models=[
    Vendor,      # No dependencies
    RateCard,    # Depends on Vendor
    Lane,        # Depends on RateCard
    Rate,        # Depends on Lane
]):
    pass
```

**Naming Convention:**
- Must match pipeline prefix: `MyPipelineRegistry` for `MyPipeline`

**Important:**
- Models must be ordered by foreign key dependencies
- Parent models before child models

#### Class Methods

```python
@classmethod
def get_models(cls) -> List[Type[SQLModel]]:
    """Get all managed models in insertion order."""
```

---

## Module: `llm_pipeline.state`

### Class: `PipelineStepState`

**Audit trail and caching state for pipeline steps.**

SQLModel table tracking step executions for any pipeline.

#### Definition

```python
class PipelineStepState(SQLModel, table=True):
    __tablename__ = "pipeline_step_states"

    id: Optional[int]
    pipeline_name: str
    run_id: str
    step_name: str
    step_number: int
    input_hash: str
    result_data: dict  # JSON column
    context_snapshot: dict  # JSON column
    prompt_system_key: Optional[str]
    prompt_user_key: Optional[str]
    prompt_version: Optional[str]
    model: Optional[str]
    created_at: datetime
    execution_time_ms: Optional[int]
```

**Indexes:**
- `ix_pipeline_step_states_run` on (run_id, step_number)
- `ix_pipeline_step_states_cache` on (pipeline_name, step_name, input_hash)

---

### Class: `PipelineRunInstance`

**Links created database instances to pipeline runs.**

Generic linking table for traceability.

#### Definition

```python
class PipelineRunInstance(SQLModel, table=True):
    __tablename__ = "pipeline_run_instances"

    id: Optional[int]
    run_id: str
    model_type: str
    model_id: int
    created_at: datetime
```

**Indexes:**
- `ix_pipeline_run_instances_run` on (run_id)
- `ix_pipeline_run_instances_model` on (model_type, model_id)

---

## Module: `llm_pipeline.types`

### Dataclass: `ArrayValidationConfig`

**Configuration for validating LLM array responses.**

Used when LLM returns array that should match input array in length/order.

#### Definition

```python
@dataclass
class ArrayValidationConfig:
    input_array: List[Any]
    match_field: str = "original"
    filter_empty_inputs: bool = False
    allow_reordering: bool = True
    strip_number_prefix: bool = True
```

#### Usage

```python
array_validation = ArrayValidationConfig(
    input_array=df["Location"].tolist(),
    match_field="original",
    allow_reordering=True
)
```

---

### Dataclass: `ValidationContext`

**Context data for Pydantic model validators.**

Allows validators to access external data not in LLM response.

#### Definition

```python
@dataclass
class ValidationContext:
    data: Dict[str, Any]

    def get(self, key: str, default: Any = None) -> Any:
    def __getitem__(self, key: str) -> Any:
    def __contains__(self, key: str) -> bool:
    def to_dict(self) -> Dict[str, Any]:
```

#### Usage

```python
validation_context = ValidationContext(
    num_rows=len(df),
    num_cols=len(df.columns)
)

# In Pydantic validator:
@field_validator('header_row')
def validate_header_row(cls, v, info: ValidationInfo):
    context = info.context
    if v >= context['num_rows']:
        raise ValueError("header_row exceeds sheet dimensions")
    return v
```

---

### TypedDict: `StepCallParams`

**Parameters from step's prepare_calls().**

```python
class StepCallParams(TypedDict, total=False):
    variables: Any  # PromptVariables instance
    array_validation: Optional[Any]
    validation_context: Optional[Any]
```

---

### TypedDict: `ExecuteLLMStepParams`

**Full parameters for execute_llm_step().**

```python
class ExecuteLLMStepParams(StepCallParams):
    system_instruction_key: str
    user_prompt_key: str
    result_class: Type[BaseModel]
    context: Dict[str, Any]
    system_variables: Optional[Any]
```

---

## Module: `llm_pipeline.db`

### Function: `init_pipeline_db()`

```python
def init_pipeline_db(engine: Optional[Engine] = None) -> Engine:
    """
    Initialize pipeline database tables.

    Creates PipelineStepState, PipelineRunInstance, and Prompt tables.

    Args:
        engine: Optional SQLAlchemy engine. Creates auto-SQLite if None.

    Returns:
        The engine used (created or provided).
    """
```

---

### Function: `get_engine()`

```python
def get_engine() -> Engine:
    """Get current engine, initializing if needed."""
```

---

### Function: `get_session()`

```python
def get_session() -> Session:
    """Get a new database session."""
```

---

### Function: `get_default_db_path()`

```python
def get_default_db_path() -> Path:
    """
    Get default SQLite database path.

    Uses LLM_PIPELINE_DB env var if set,
    otherwise .llm_pipeline/pipeline.db in cwd.
    """
```

---

## Module: `llm_pipeline.session`

### Class: `ReadOnlySession`

**Read-only wrapper for SQLModel Session.**

Prevents accidental database writes during step execution.

#### Constructor

```python
def __init__(self, session: Session):
    """Initialize with underlying session."""
```

#### Allowed Operations (Read)

- `query(*args, **kwargs)` - SQLAlchemy queries
- `exec(*args, **kwargs)` - SQLModel queries
- `get(*args, **kwargs)` - Get by primary key
- `execute(*args, **kwargs)` - Raw SQL
- `scalar(*args, **kwargs)` - Scalar result
- `scalars(*args, **kwargs)` - Scalars result

#### Blocked Operations (Write)

Raises `RuntimeError`:
- `add()`, `add_all()` - Insert
- `delete()` - Delete
- `flush()`, `commit()` - Persist changes
- `merge()` - Merge instances
- `refresh()`, `expire()`, `expire_all()` - State management
- `expunge()`, `expunge_all()` - Session management

---

## Module: `llm_pipeline.llm`

### Abstract Class: `LLMProvider`

**Abstract base for LLM providers.**

#### Abstract Method

```python
@abstractmethod
def call_structured(
    self,
    prompt: str,
    system_instruction: str,
    result_class: Type[BaseModel],
    max_retries: int = 3,
    not_found_indicators: Optional[List[str]] = None,
    strict_types: bool = True,
    array_validation: Optional[Any] = None,
    validation_context: Optional[Any] = None,
    **kwargs,
) -> Optional[Dict[str, Any]]:
    """
    Call LLM with structured output validation and retry logic.

    Returns:
        Validated JSON response dict, or None if all retries failed.
    """
```

---

### Class: `GeminiProvider`

**Google Gemini LLM provider implementation.**

Requires: `pip install llm-pipeline[gemini]`

#### Constructor

```python
def __init__(
    self,
    api_key: Optional[str] = None,
    model_name: str = "gemini-2.0-flash-lite",
    rate_limiter: Optional[RateLimiter] = None,
):
    """
    Initialize Gemini provider.

    Args:
        api_key: Gemini API key. Falls back to GEMINI_API_KEY env var.
        model_name: Model to use (default: gemini-2.0-flash-lite).
        rate_limiter: Optional RateLimiter. Creates default if None.
    """
```

#### Usage

```python
from llm_pipeline.llm.gemini import GeminiProvider

provider = GeminiProvider(
    api_key="your-api-key",
    model_name="gemini-2.0-flash-lite"
)

pipeline = MyPipeline(provider=provider)
```

---

### Class: `RateLimiter`

**Sliding window rate limiter for API calls.**

#### Constructor

```python
def __init__(self, max_requests: int, time_window_seconds: float):
    """
    Initialize rate limiter.

    Args:
        max_requests: Max requests allowed in time window
        time_window_seconds: Time window in seconds (e.g., 60 for per-minute)
    """
```

#### Methods

```python
def wait_if_needed(self) -> None:
    """Wait if necessary to comply with rate limit."""

def get_wait_time(self) -> float:
    """Get seconds to wait before next request (0 if can request now)."""

def reset(self) -> None:
    """Clear all recorded request times."""
```

---

### Function: `flatten_schema()`

```python
def flatten_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten Pydantic JSON schema by inlining all $ref references.

    Removes $defs section and replaces $ref pointers with actual definitions.
    """
```

---

### Function: `format_schema_for_llm()`

```python
def format_schema_for_llm(result_class: Type[LLMResultMixin]) -> str:
    """
    Format Pydantic model into clear, LLM-friendly instructions.

    Generates JSON schema, flattens it, and presents with example.
    """
```

---

### Function: `execute_llm_step()`

```python
def execute_llm_step(
    system_instruction_key: str,
    user_prompt_key: str,
    variables: Any,
    result_class: Type[T],
    provider: Any = None,
    prompt_service: Any = None,
    context: Optional[Dict[str, Any]] = None,
    array_validation: Optional[ArrayValidationConfig] = None,
    system_variables: Optional[Any] = None,
    validation_context: Optional[ValidationContext] = None,
) -> T:
    """
    Generic executor for LLM-based pipeline steps.

    Handles:
    1. Retrieving prompts from database
    2. Calling LLM with structured output
    3. Validating response with Pydantic
    4. Returning result or calling create_failure()

    Returns:
        Validated Pydantic result object
    """
```

---

### Validation Functions

```python
def validate_structured_output(
    response_json: Any,
    expected_schema: Dict[str, Any],
    strict_types: bool = True,
) -> Tuple[bool, List[str]]:
    """Validate response matches expected schema structure."""

def validate_array_response(
    response_json: Dict[str, Any],
    config: ArrayValidationConfig,
    attempt: int,
) -> Tuple[bool, List[str]]:
    """Validate LLM array response matches input array."""

def check_not_found_response(
    response_text: str,
    not_found_indicators: List[str]
) -> bool:
    """Check if LLM response indicates it couldn't find info."""

def extract_retry_delay_from_error(error: Exception) -> Optional[float]:
    """Extract retry delay from rate limit error."""

def strip_number_prefix(text: str) -> str:
    """Strip leading number and dot/parenthesis from text."""
```

---

## Module: `llm_pipeline.prompts`

### Class: `Prompt`

**SQLModel for prompt storage.**

#### Definition

```python
class Prompt(SQLModel, table=True):
    __tablename__ = "prompts"

    id: Optional[int]
    prompt_key: str  # Unique identifier
    prompt_name: str
    prompt_type: str  # 'system' or 'user'
    category: Optional[str]
    step_name: Optional[str]
    content: str  # Template with {variables}
    required_variables: Optional[List[str]]  # Auto-extracted
    description: Optional[str]
    version: str = "1.0"
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]
```

---

### Class: `PromptService`

**Service for retrieving prompts from database.**

#### Constructor

```python
def __init__(self, session: Session):
```

#### Methods

```python
def get_prompt(
    self,
    prompt_key: str,
    prompt_type: str = 'system',
    context: Optional[dict] = None,
    fallback: Optional[str] = None
) -> str:
    """Get prompt by key and type."""

def get_system_instruction(
    self,
    step_name: str,
    fallback: Optional[str] = None
) -> str:
    """Get system instruction for pipeline step."""

def get_system_prompt(
    self,
    prompt_key: str,
    variables: dict,
    variable_instance: Optional[Any] = None,
    context: Optional[dict] = None,
    fallback: Optional[str] = None
) -> str:
    """Get system prompt template and format with variables."""

def get_user_prompt(
    self,
    prompt_key: str,
    variables: dict,
    variable_instance: Optional[Any] = None,
    context: Optional[dict] = None,
    fallback: Optional[str] = None
) -> str:
    """Get user prompt template and format with variables."""

def prompt_exists(self, prompt_key: str) -> bool:
    """Check if prompt exists in database."""
```

---

### Function: `sync_prompts()`

```python
def sync_prompts(
    bind,
    prompts_dir: Optional[Path] = None,
    force: bool = False
) -> Dict[str, int]:
    """
    Sync prompts from YAML files to database.

    Behavior:
    - Inserts new prompts (new prompt_key)
    - Updates existing if version increased
    - Skips if version unchanged (idempotent)
    - Force flag updates all regardless of version
    - Auto-extracts required_variables from content

    Returns:
        Dict with 'inserted', 'updated', 'skipped' counts
    """
```

---

### Function: `load_all_prompts()`

```python
def load_all_prompts(prompts_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load all prompts from YAML files in prompts directory."""
```

---

### Function: `get_prompts_dir()`

```python
def get_prompts_dir() -> Path:
    """
    Get prompts directory from environment or use default.

    Environment: PROMPTS_DIR
    Default: ./prompts (relative to cwd)
    """
```

---

### Function: `extract_variables_from_content()`

```python
def extract_variables_from_content(content: str) -> List[str]:
    """
    Extract variable names from prompt content.

    Finds all {variable_name} patterns.
    """
```

---

### Protocol: `VariableResolver`

**Protocol for resolving prompt variable classes.**

#### Method

```python
def resolve(
    self,
    prompt_key: str,
    prompt_type: str
) -> Optional[Type[BaseModel]]:
    """
    Resolve prompt key and type to variable class.

    Args:
        prompt_key: The prompt key (e.g., 'semantic_mapping')
        prompt_type: The prompt type ('system' or 'user')

    Returns:
        Pydantic BaseModel subclass for variables, or None
    """
```

#### Usage

```python
class MyVariableResolver:
    def resolve(self, prompt_key: str, prompt_type: str) -> Type[BaseModel] | None:
        # Look up variable class for this prompt
        return my_variable_registry.get(prompt_key, prompt_type)

pipeline = MyPipeline(
    provider=GeminiProvider(),
    variable_resolver=MyVariableResolver()
)
```

---

## Environment Variables

- `GEMINI_API_KEY` - Gemini API key (if not passed to constructor)
- `LLM_PIPELINE_DB` - SQLite database path (default: .llm_pipeline/pipeline.db)
- `PROMPTS_DIR` - Prompts directory (default: ./prompts)

---

## Complete Usage Example

```python
from llm_pipeline import (
    PipelineConfig,
    PipelineStrategy,
    PipelineStrategies,
    PipelineDatabaseRegistry,
    LLMStep,
    LLMResultMixin,
    step_definition,
    PipelineExtraction,
    init_pipeline_db,
)
from llm_pipeline.llm.gemini import GeminiProvider
from sqlmodel import SQLModel, Field
from typing import Optional, List, Dict, Any

# 1. Define database models
class Lane(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    origin: str
    destination: str

# 2. Define registry
class MyRegistry(PipelineDatabaseRegistry, models=[Lane]):
    pass

# 3. Define instructions
class ConstraintExtractionInstructions(LLMResultMixin):
    num_lanes: int
    example = {"num_lanes": 5, "confidence_score": 0.95, "notes": ""}

# 4. Define extraction
class LaneExtraction(PipelineExtraction, model=Lane):
    def default(self, results: List[ConstraintExtractionInstructions]) -> List[Lane]:
        # Extraction logic here
        return [Lane(origin="NYC", destination="LA")]

# 5. Define step
@step_definition(
    instructions=ConstraintExtractionInstructions,
    default_system_key="constraint_extraction",
    default_user_key="constraint_extraction",
    default_extractions=[LaneExtraction],
)
class ConstraintExtractionStep(LLMStep):
    def prepare_calls(self) -> List[Dict[str, Any]]:
        return [{"variables": {"data": self.pipeline.get_data("current")}}]

# 6. Define strategy
class SimpleStrategy(PipelineStrategy):
    def can_handle(self, context: Dict[str, Any]) -> bool:
        return True

    def get_steps(self):
        return [ConstraintExtractionStep.create_definition()]

# 7. Define strategies collection
class MyStrategies(PipelineStrategies, strategies=[SimpleStrategy]):
    pass

# 8. Define pipeline
class MyPipeline(PipelineConfig, registry=MyRegistry, strategies=MyStrategies):
    pass

# 9. Use pipeline
provider = GeminiProvider(api_key="your-key")
engine = init_pipeline_db()

pipeline = MyPipeline(provider=provider, engine=engine)
result = pipeline.execute(
    data="sample data",
    initial_context={},
    use_cache=True
)

# Save extracted data
counts = pipeline.save()
print(f"Saved: {counts}")

# Access results
lanes = pipeline.get_extractions(Lane)
print(f"Extracted {len(lanes)} lanes")
```

---

## Design Patterns

### Naming Conventions

All classes follow strict naming conventions for auto-generation:

- **Pipeline**: `{Name}Pipeline` -> `name` (snake_case)
- **Registry**: `{Name}Registry` (must match pipeline)
- **Strategies**: `{Name}Strategies` (must match pipeline)
- **Strategy**: `{Name}Strategy` -> `name` (snake_case)
- **Step**: `{Name}Step` -> `name` (snake_case)
- **Instructions**: `{StepName}Instructions` (must match step)
- **Context**: `{StepName}Context` (must match step)
- **Transformation**: `{StepName}Transformation` (must match step)
- **Extraction**: `{ModelName}Extraction`

### Dependency Injection

Pipeline accepts dependencies via constructor:

```python
pipeline = MyPipeline(
    provider=GeminiProvider(),           # Required for execute()
    engine=my_engine,                    # Optional (auto-SQLite if omitted)
    session=my_session,                  # Optional (overrides engine)
    variable_resolver=MyVariableResolver(), # Optional
)
```

### Step Execution Order

Pipeline executes steps sequentially:

1. Check if step should skip (`should_skip()`)
2. Prepare LLM call(s) (`prepare_calls()`)
3. Execute LLM call(s) with caching/consensus if configured
4. Process instructions to extract context (`process_instructions()`)
5. Apply data transformation if configured
6. Extract database models if configured (`extract_data()`)
7. Log results (`log_instructions()`)
8. Execute action_after callback if configured

### Execution Order Validation

Pipeline validates access order:

- Steps can only access data/instructions from previously executed steps
- Extractions can only access models extracted in earlier steps
- Raises `ValueError` with detailed error if order violated

### Foreign Key Validation

Registry validates foreign key dependencies:

- Parent models must appear before child models in MODELS list
- Raises `ValueError` with guidance if order incorrect

---

## Common Patterns

### Multi-Call Steps

```python
def prepare_calls(self) -> List[StepCallParams]:
    lanes = self.pipeline.get_extractions(Lane)
    return [
        {"variables": {"lane": lane}}
        for lane in lanes
    ]
```

### Conditional Skip

```python
def should_skip(self) -> bool:
    table_type = self.pipeline.context.get("table_type")
    return table_type != "lane_based"
```

### Context Contribution

```python
def process_instructions(self, instructions) -> MyContext:
    return MyContext(
        table_type=instructions[0].table_type,
        num_rows=instructions[0].num_rows
    )
```

### Array Validation

```python
def prepare_calls(self) -> List[StepCallParams]:
    df = self.pipeline.get_data("current")
    return [{
        "variables": {"data": df},
        "array_validation": ArrayValidationConfig(
            input_array=df["Location"].tolist(),
            match_field="original",
            allow_reordering=True
        )
    }]
```

### Custom Sanitization

```python
class MyPipeline(PipelineConfig, ...):
    def sanitize(self, data: Any) -> str:
        if isinstance(data, pd.DataFrame):
            return data.head(5).to_string()
        return str(data)
```

---

## Summary

The llm-pipeline library provides a declarative framework for orchestrating multi-step LLM pipelines with:

- **Type-safe** configuration via Pydantic models
- **Declarative** pipeline definition with naming conventions
- **Automatic** state tracking and caching
- **Validated** execution order and dependencies
- **Strategy-based** conditional logic
- **Provider-agnostic** LLM integration
- **Database-backed** prompt management

All public APIs follow consistent patterns for discoverability and maintainability.
