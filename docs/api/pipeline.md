# Pipeline API Reference

## Overview

The pipeline module provides the core orchestration engine for declarative LLM pipeline execution. `PipelineConfig` manages step execution, context flow, data transformations, database extractions, and state tracking.

## Module: `llm_pipeline.pipeline`

### Classes

- [`PipelineConfig`](#pipelineconfig) - Abstract base class for pipeline orchestration
- [`StepKeyDict`](#stepkeydict) - Dictionary that normalizes Step class keys to snake_case

---

## PipelineConfig

Abstract base class for defining and executing LLM pipelines.

**Inheritance:** `ABC` (Python abstract base class)

**Purpose:** Orchestrates multi-step LLM execution with automatic context management, data transformation, database extraction, state tracking, and caching.

### Class-Level Configuration

Pipelines are defined using `__init_subclass__` with class parameters:

```python
class MyPipeline(PipelineConfig,
                 registry=MyRegistry,
                 strategies=MyStrategies):
    pass
```

**Parameters:**

- `registry` (Type[PipelineDatabaseRegistry]) - Database registry with FK-ordered models
- `strategies` (Type[PipelineStrategies]) - Strategy registry for step selection

**Naming Validation:**

The metaclass enforces strict naming conventions at class definition time:

1. **Pipeline Class:** Must end with `Pipeline` suffix
2. **Registry Class:** Must be `{PipelineName}Registry` (where `{PipelineName}` is pipeline class name minus `Pipeline`)
3. **Strategies Class:** Must be `{PipelineName}Strategies`

**Example (Valid):**

```python
class RateCardPipeline(PipelineConfig,
                       registry=RateCardRegistry,
                       strategies=RateCardStrategies):
    pass
```

**Example (Invalid):**

```python
class RateCardPipeline(PipelineConfig,
                       registry=CardRegistry,  # Wrong name!
                       strategies=RateCardStrategies):
    pass
# Raises ValueError: Registry must be named 'RateCardRegistry'
```

### Class Attributes

- `REGISTRY` (ClassVar[Type[PipelineDatabaseRegistry]]) - Database registry class (set via `__init_subclass__`)
- `STRATEGIES` (ClassVar[Type[PipelineStrategies]]) - Strategies registry class (set via `__init_subclass__`)

### Constructor

```python
def __init__(
    self,
    strategies: Optional[List[PipelineStrategy]] = None,
    session: Optional[Session] = None,
    engine: Optional[Engine] = None,
    model: Optional[str] = None,
    variable_resolver: Optional[VariableResolver] = None,
)
```

**Parameters:**

- `strategies` (List[PipelineStrategy], optional) - Strategy instances. If `None`, instantiates from `STRATEGIES.create_instances()`
- `session` (Session, optional) - Existing database session. Overrides `engine` if provided
- `engine` (Engine, optional) - SQLAlchemy engine. Auto-SQLite if both `session` and `engine` are `None`
- `model` (str, optional) - pydantic-ai model string (e.g., `'google-gla:gemini-2.0-flash-lite'`), required for `execute()`
- `variable_resolver` (VariableResolver, optional) - Variable resolver for prompt template variables

**Database Session Hierarchy:**

1. If `session` provided: uses that session (pipeline does NOT own it, will not close it)
2. Else if `engine` provided: creates new session from engine (pipeline owns and closes)
3. Else: auto-initializes SQLite database and creates session (pipeline owns and closes)

**Auto-Initialization:**

The constructor automatically:
- Validates `REGISTRY` and `STRATEGIES` are configured
- Initializes strategy instances if not provided
- Builds execution order from all strategies
- Validates foreign key dependencies in registry
- Validates registry order matches extraction order
- Creates unique `run_id` for traceability
- Wraps session in `ReadOnlySession` for safe read access

**Example:**

```python
# Auto-SQLite for development
pipeline = MyPipeline(model='google-gla:gemini-2.0-flash-lite')

# Production with explicit database
from sqlalchemy import create_engine
engine = create_engine("postgresql://user:pass@localhost/db")
pipeline = MyPipeline(engine=engine, model='google-gla:gemini-2.0-flash-lite')

# With variable resolver for prompt variables
resolver = VariableResolver(variable_classes=[DateVariables, ConfigVariables])
pipeline = MyPipeline(model='google-gla:gemini-2.0-flash-lite', variable_resolver=resolver)
```

### Properties

#### `pipeline_name`

Auto-derived pipeline name from class name.

```python
@property
def pipeline_name(self) -> str
```

**Returns:** Snake_case version of class name with `Pipeline` suffix removed

**Example:**

```python
class RateCardPipeline(PipelineConfig, ...):
    pass

pipeline = RateCardPipeline()
print(pipeline.pipeline_name)  # "rate_card"
```

**Validation:** Raises `ValueError` if class name doesn't end with `Pipeline` suffix

#### `instructions`

Read-only access to LLM step instruction results.

```python
@property
def instructions(self) -> MappingProxyType
```

**Returns:** Immutable mapping of step names to instruction lists

**Key Types:** Accepts both string keys and Step class keys (auto-normalized via `StepKeyDict`)

**Example:**

```python
# After execution
instructions = pipeline.instructions['constraint_extraction']
# or
instructions = pipeline.instructions[ConstraintExtractionStep]

# Both return List[ConstraintExtractionInstructions]
```

**Note:** Returns `MappingProxyType` (read-only view). Use `pipeline.get_instructions(key)` for step-order validation.

#### `context`

Read-write access to derived context values.

```python
@property
def context(self) -> Dict[str, Any]
```

**Returns:** Mutable dictionary of context values built from step results

**Purpose:** Steps use `process_instructions()` to add context that later steps can use for decision-making.

**Example:**

```python
# Step adds context
def process_instructions(self, instructions):
    return {'table_type': instructions[0].table_type}

# Later step uses context
def prepare_calls(self):
    table_type = self.pipeline.context.get('table_type')
    if table_type == 'lane_based':
        # Lane-specific logic
```

### Data Access Methods

#### `get_raw_data()`

Retrieve the original input data.

```python
def get_raw_data(self) -> Any
```

**Returns:** Raw data passed to `execute(data, ...)`

**Example:**

```python
pipeline.execute(data=pdf_bytes, initial_context={})
raw = pipeline.get_raw_data()  # Returns pdf_bytes
```

#### `get_current_data()`

Retrieve the most recent transformed data.

```python
def get_current_data(self) -> Any
```

**Returns:** Most recent step transformation result, or raw data if no transformations applied

**Search Order:**

1. Last step transformation (most recent non-raw, non-sanitized key)
2. Raw data if no transformations exist
3. `None` if no data

**Example:**

```python
# After multiple transformation steps
pipeline.execute(data=pdf_bytes, ...)
# Step 1: transforms to DataFrame
# Step 2: transforms DataFrame to dict
current = pipeline.get_current_data()  # Returns dict from step 2
```

#### `get_sanitized_data()`

Retrieve the sanitized (string) version of current data.

```python
def get_sanitized_data(self) -> Any
```

**Returns:** String representation of data via `sanitize()` method

**Purpose:** Used for LLM prompts requiring string input. Automatically updated on each transformation.

**Example:**

```python
sanitized = pipeline.get_sanitized_data()
# Returns result of sanitize(get_current_data())
```

#### `get_data()`

Flexible data retrieval with step-order validation.

```python
def get_data(self, key: str = "current") -> Any
```

**Parameters:**

- `key` (str | Type) - Data key to retrieve

**Special Keys:**

- `"current"` - Calls `get_current_data()`
- `"raw"` - Calls `get_raw_data()`
- `"sanitized"` - Calls `get_sanitized_data()`
- Step class or step name - Returns transformation result from specific step

**Step-Order Validation:** If `key` is a Step class, validates that step has already executed. Raises `ValueError` if accessing future step data.

**Example:**

```python
# Special keys
current = pipeline.get_data("current")
raw = pipeline.get_data("raw")

# Specific step (with validation)
data = pipeline.get_data(ParseTableStep)  # OK if step already ran
data = pipeline.get_data(FutureStep)      # Raises ValueError
```

#### `set_data()`

Store transformed data from a step.

```python
def set_data(self, data: Any, step_name: str) -> None
```

**Parameters:**

- `data` (Any) - Transformed data to store
- `step_name` (str) - Step name key

**Side Effects:**

1. Stores data in `self.data[step_name]`
2. Updates `self.data["sanitized"]` via `sanitize(data)`

**Example:**

```python
# Called by PipelineTransformation.transform()
pipeline.set_data(transformed_df, step_name='parse_table')
```

**Note:** Typically called by transformation classes, not directly by user code.

#### `get_instructions()`

Retrieve instruction results from a step with validation.

```python
def get_instructions(self, key: str | Type) -> Any
```

**Parameters:**

- `key` (str | Type) - Step name or Step class

**Returns:** List of instruction objects from the step

**Step-Order Validation:** If `key` is a Step class, validates that step has already executed.

**Example:**

```python
# After step execution
instructions = pipeline.get_instructions('constraint_extraction')
# or
instructions = pipeline.get_instructions(ConstraintExtractionStep)
```

### Extraction Methods

#### `store_extractions()`

Store extracted database models.

```python
def store_extractions(
    self,
    model_class: Type[SQLModel],
    instances: List[SQLModel]
) -> None
```

**Parameters:**

- `model_class` (Type[SQLModel]) - Model class being stored (used as dict key)
- `instances` (List[SQLModel]) - List of model instances to store

**Purpose:** Registers extracted models in `pipeline.extractions[model_class]` for later persistence via `save()`.

**Example:**

```python
constraints = [Constraint(name="Weight", value=500), ...]
pipeline.store_extractions(Constraint, constraints)
```

**Note:** Typically called by `PipelineExtraction.extract()`, not directly by user code.

#### `get_extractions()`

Retrieve extracted database models with validation.

```python
def get_extractions(self, model_class: Type[TModel]) -> List[TModel]
```

**Parameters:**

- `model_class` (Type[SQLModel]) - Model class to retrieve

**Returns:** List of extracted instances of `model_class`

**Validation:**

1. Verifies `model_class` is in `REGISTRY.get_models()`
2. If model has extraction step, validates that step has executed
3. Validates step-order if accessing from another extraction

**Example:**

```python
# After extraction step
constraints = pipeline.get_extractions(Constraint)
for c in constraints:
    print(c.name, c.value)
```

**Foreign Key Access Pattern:**

```python
# LaneExtraction can reference already-extracted Location instances
class LaneExtraction(PipelineExtraction):
    MODEL = Lane

    def default(self, instructions):
        locations = self.pipeline.get_extractions(Location)
        lanes = []
        for instr in instructions:
            location = locations[instr.location_index]
            lanes.append(Lane(name=instr.name, location_id=location.id))
        return lanes
```

### Execution Methods

#### `execute()`

Execute all pipeline steps with optional caching and consensus polling.

```python
def execute(
    self,
    data: Any,
    initial_context: Dict[str, Any],
    use_cache: bool = False,
    consensus_polling: Optional[Dict[str, Any]] = None,
) -> PipelineConfig
```

**Parameters:**

- `data` (Any) - Input data for pipeline (e.g., PDF bytes, DataFrame, JSON)
- `initial_context` (Dict[str, Any]) - Initial context for strategy selection
- `use_cache` (bool) - Enable step result caching (default: `False`)
- `consensus_polling` (Dict[str, Any], optional) - Consensus polling configuration

**Returns:** Self (for method chaining)

**Consensus Polling Configuration:**

```python
consensus_polling = {
    'enable': True,
    'consensus_threshold': 3,     # Matching results required
    'maximum_step_calls': 5,      # Max attempts before fallback
}
```

**Execution Flow:**

1. Initialize context from `initial_context`
2. Store raw data and sanitized data in `self.data`
3. For each step position:
   - Select strategy via `strategy.can_handle(context)`
   - Get step definition from strategy
   - Check if step should skip via `step.should_skip()`
   - Check cache if `use_cache=True`
   - Prepare LLM calls via `step.prepare_calls()`
   - Execute calls (with consensus if enabled)
   - Process instructions via `step.process_instructions()` → update context
   - Apply transformation if configured
   - Extract database models via `step.extract_data()`
   - Save step state for caching
   - Execute post-action if configured
4. Return self

**Two-Phase Write Pattern:**

During extraction (within `execute()`):
1. **Phase 1 (extraction):** `_real_session.add()` + `_real_session.flush()` assigns database IDs
2. **Phase 2 (save):** User calls `pipeline.save()` which commits transaction

**Purpose:** Flushing during execution enables later extractions to reference foreign key IDs from earlier extractions within the same run.

**Example:**

```python
pipeline = MyPipeline(model='google-gla:gemini-2.0-flash-lite')

# Basic execution
pipeline.execute(
    data=pdf_bytes,
    initial_context={'source_file': 'rates.pdf'}
)

# With caching
pipeline.execute(
    data=pdf_bytes,
    initial_context={'source_file': 'rates.pdf'},
    use_cache=True
)

# With consensus polling
pipeline.execute(
    data=pdf_bytes,
    initial_context={'source_file': 'rates.pdf'},
    consensus_polling={
        'enable': True,
        'consensus_threshold': 3,
        'maximum_step_calls': 5
    }
)

# Method chaining
results = pipeline.execute(data, context).save()
```

**Validation:**

- Raises `ValueError` if `model` not set
- Raises `ValueError` if no strategies registered
- Validates consensus config if enabled (threshold >= 2, max >= threshold)

#### `save()`

Persist extracted database models to database.

```python
def save(
    self,
    session: Session = None,
    tables: Optional[List[Type[SQLModel]]] = None,
) -> Dict[str, int]
```

**Parameters:**

- `session` (Session, optional) - Database session. Uses pipeline's session if `None`
- `tables` (List[Type[SQLModel]], optional) - Specific models to save. Saves all registry models if `None`

**Returns:** Dictionary with save counts (e.g., `{'constraints_saved': 5, 'lanes_saved': 12}`)

**Two-Phase Write Pattern:**

This method completes Phase 2 of the two-phase write:
1. Ensures all tables exist via `ensure_table()`
2. Retrieves extractions via `get_extractions()` (already added/flushed during execution)
3. Tracks instances via `PipelineRunInstance` for traceability
4. Commits transaction

**Example:**

```python
# Save all extracted models
results = pipeline.save()
print(results)  # {'constraints_saved': 5, 'destinations_saved': 3}

# Save specific models only
results = pipeline.save(tables=[Constraint, Lane])

# Use external session
with Session(engine) as session:
    results = pipeline.save(session=session)
    session.commit()  # Caller controls commit
```

**Validation:**

- Raises `AttributeError` if `REGISTRY` not defined
- Raises `ValueError` if `tables` contains models not in registry

#### `ensure_table()`

Ensure database table exists for a model.

```python
def ensure_table(self, model_class: Type[SQLModel], session: Session) -> None
```

**Parameters:**

- `model_class` (Type[SQLModel]) - Model class to create table for
- `session` (Session) - Database session

**Purpose:** Creates table if it doesn't exist. Idempotent operation.

**Validation:** Raises `ValueError` if `model_class` not in registry

**Example:**

```python
pipeline.ensure_table(Constraint, session)
```

**Note:** Automatically called by `save()` for all models being saved.

### Cache Methods

#### `clear_cache()`

Clear cached step results for this pipeline run.

```python
def clear_cache(self) -> int
```

**Returns:** Count of cleared cache entries

**Known Limitation:** This method has a bug - it uses `self.session` (ReadOnlySession) instead of `self._real_session` for delete/commit operations. This will raise `RuntimeError` if called.

**Workaround:** Currently none. Avoid using this method until fixed.

**Example:**

```python
# WARNING: Currently broken
# count = pipeline.clear_cache()
```

**Issue:** Uses ReadOnlySession for write operations (delete, commit)

### Customization Methods

#### `sanitize()`

Customize data sanitization for LLM prompts.

```python
def sanitize(self, data: Any) -> str
```

**Parameters:**

- `data` (Any) - Data to sanitize

**Returns:** String representation suitable for LLM prompts

**Default Implementation:** Returns `str(data)` for non-strings, passthrough for strings

**Override Pattern:**

```python
class MyPipeline(PipelineConfig, ...):
    def sanitize(self, data: Any) -> str:
        if isinstance(data, pd.DataFrame):
            return data.to_markdown()
        elif isinstance(data, dict):
            return json.dumps(data, indent=2)
        return str(data)
```

**Purpose:** Allows customizing how complex data structures (DataFrames, dicts, etc.) are converted to strings for LLM consumption.

### Consensus Polling Helpers

These static methods implement consensus polling logic used by `execute()`.

#### `_smart_compare()`

Compare two values with field-specific rules.

```python
@staticmethod
def _smart_compare(
    value1: Any,
    value2: Any,
    field_name: str = "",
    mixin_fields: Optional[set] = None
) -> bool
```

**Parameters:**

- `value1`, `value2` (Any) - Values to compare
- `field_name` (str) - Field name for mixin exclusion
- `mixin_fields` (set, optional) - Set of mixin field names to exclude

**Returns:** `True` if values match, `False` otherwise

**Comparison Rules:**

1. **Mixin fields** (confidence_score, notes): Always match (`True`)
2. **Strings**: Always match (`True`) - LLMs phrase differently
3. **None values**: Always match (`True`)
4. **Numbers/booleans**: Exact match required
5. **Lists**: Must have same length, elements compared recursively
6. **Dicts**: Must have same keys, values compared recursively

**Example:**

```python
# Numbers require exact match
PipelineConfig._smart_compare(5, 5)     # True
PipelineConfig._smart_compare(5, 6)     # False

# Strings always match (different LLM phrasing)
PipelineConfig._smart_compare("Heavy items", "Large packages")  # True

# Lists must have same length
PipelineConfig._smart_compare([1, 2], [1, 3])  # True (length matches)
PipelineConfig._smart_compare([1, 2], [1])     # False (length differs)
```

#### `_instructions_match()`

Compare two instruction objects for consensus matching.

```python
@staticmethod
def _instructions_match(instr1: BaseModel, instr2: BaseModel) -> bool
```

**Parameters:**

- `instr1`, `instr2` (BaseModel) - Instruction objects to compare

**Returns:** `True` if instructions match according to `_smart_compare()` rules

**Purpose:** Determines if two LLM results agree for consensus polling. Automatically excludes mixin fields (confidence_score, notes).

**Example:**

```python
instr1 = ConstraintInstructions(constraints=["Weight limit"], confidence_score=0.9)
instr2 = ConstraintInstructions(constraints=["Weight limit"], confidence_score=0.8)

# Matches despite different confidence (mixin field excluded)
PipelineConfig._instructions_match(instr1, instr2)  # True
```

#### `_get_mixin_fields()`

Extract mixin field names from a model class.

```python
@staticmethod
def _get_mixin_fields(model_class: Type[BaseModel]) -> set
```

**Parameters:**

- `model_class` (Type[BaseModel]) - Model class to inspect

**Returns:** Set of field names from `LLMResultMixin` (e.g., `{'confidence_score', 'notes'}`)

**Example:**

```python
class MyInstructions(LLMResultMixin):
    value: int

fields = PipelineConfig._get_mixin_fields(MyInstructions)
# Returns {'confidence_score', 'notes'}
```

### Session Management

#### `close()`

Close the database session if pipeline owns it.

```python
def close(self) -> None
```

**Behavior:**

- If pipeline owns session (created from engine or auto-SQLite): closes session
- If pipeline received external session: does nothing (caller owns lifecycle)

**Example:**

```python
pipeline = MyPipeline(model='google-gla:gemini-2.0-flash-lite')
try:
    pipeline.execute(data, context).save()
finally:
    pipeline.close()

# Or use context manager pattern
with MyPipeline(model='google-gla:gemini-2.0-flash-lite') as pipeline:
    pipeline.execute(data, context).save()
```

### Internal Validation Methods

These methods are called automatically during construction and execution.

#### `_build_execution_order()`

Build step execution order from all strategies.

**Purpose:** Builds internal mappings:
- `_step_order`: Maps step classes to position indices
- `_model_extraction_step`: Maps model classes to extraction step classes
- `_step_data_transformations`: Maps step classes to transformation classes

**Called:** During `__init__()`

#### `_validate_foreign_key_dependencies()`

Validate foreign key dependencies respect registry order.

**Purpose:** Ensures models in registry are ordered such that FK dependencies appear before dependent models.

**Example Error:**

```
Foreign key dependency error in MyRegistry:
  'Lane' at position 1, but FK to 'Location' at position 2.
Move 'Location' before 'Lane'.
```

**Called:** During `__init__()`

#### `_validate_registry_order()`

Validate registry order matches extraction order.

**Purpose:** Ensures models extracted earlier appear earlier in registry.

**Example Error:**

```
Extraction order mismatch in MyRegistry:
  'Location' before 'Lane' in registry, but extracted later.
Reorder registry to match extraction order.
```

**Called:** During `__init__()`

#### `_validate_step_access()`

Validate step access respects execution order.

**Purpose:** Prevents steps from accessing data/instructions/extractions from future steps.

**Example Error:**

```
Step execution order error:
  ParseTableStep (step 1) attempts to access instructions from ConstraintExtractionStep (step 3).
Steps can only access instructions from previously executed steps.
```

**Called:** By `get_data()`, `get_instructions()`, `get_extractions()`

---

## StepKeyDict

Dictionary subclass that normalizes Step class keys to snake_case.

**Inheritance:** `dict`

**Purpose:** Allows accessing pipeline data/instructions using either step name strings or Step class objects.

### Key Normalization

Converts Step classes to snake_case step names:

```python
ConstraintExtractionStep  →  "constraint_extraction"
ParseTableStep            →  "parse_table"
MyStep                    →  "my"
```

**Algorithm:**

1. Check if key is a type ending with `Step`
2. Remove `Step` suffix
3. Convert CamelCase to snake_case
4. Return lowercase result

### Methods

All standard dict methods work with normalized keys:

#### `__getitem__()`

```python
def __getitem__(self, key: str | Type) -> Any
```

**Example:**

```python
data = StepKeyDict()
data[ParseTableStep] = df
# Same as: data["parse_table"] = df

value = data[ParseTableStep]
# Same as: value = data["parse_table"]
```

#### `__setitem__()`

```python
def __setitem__(self, key: str | Type, value: Any) -> None
```

#### `__contains__()`

```python
def __contains__(self, key: str | Type) -> bool
```

**Example:**

```python
if ParseTableStep in pipeline.data:
    # Same as: if "parse_table" in pipeline.data
```

#### `get()`

```python
def get(self, key: str | Type, default=None) -> Any
```

#### `pop()`

```python
def pop(self, key: str | Type, *args) -> Any
```

### Usage Patterns

```python
# Both of these are equivalent:
pipeline.data[ParseTableStep] = df
pipeline.data["parse_table"] = df

# Both retrieve the same value:
df1 = pipeline.data[ParseTableStep]
df2 = pipeline.data["parse_table"]
assert df1 is df2

# Both check existence:
ParseTableStep in pipeline.data
"parse_table" in pipeline.data
```

---

## Module Exports

```python
__all__ = ["PipelineConfig"]
```

Note: `StepKeyDict` is internal (not exported), used by `PipelineConfig.data` and `PipelineConfig._instructions`.

---

## Usage Patterns

### Basic Pipeline Definition

```python
from llm_pipeline import PipelineConfig

class RateCardPipeline(PipelineConfig,
                       registry=RateCardRegistry,
                       strategies=RateCardStrategies):
    pass

# Initialize with pydantic-ai model string
pipeline = RateCardPipeline(model='google-gla:gemini-2.0-flash-lite')

# Execute
pipeline.execute(
    data=pdf_bytes,
    initial_context={'source': 'rates.pdf'}
)

# Save results
results = pipeline.save()
print(results)  # {'constraints_saved': 5, 'lanes_saved': 12}
```

### Custom Sanitization

```python
import pandas as pd
import json

class MyPipeline(PipelineConfig, ...):
    def sanitize(self, data: Any) -> str:
        if isinstance(data, pd.DataFrame):
            return data.to_markdown(index=False)
        elif isinstance(data, dict):
            return json.dumps(data, indent=2)
        elif isinstance(data, list):
            return '\n'.join(str(item) for item in data)
        return str(data)
```

### With Caching

```python
# First run (fresh execution)
pipeline1 = MyPipeline(model='google-gla:gemini-2.0-flash-lite')
pipeline1.execute(data, context, use_cache=True).save()

# Second run (uses cache if inputs unchanged)
pipeline2 = MyPipeline(model='google-gla:gemini-2.0-flash-lite')
pipeline2.execute(data, context, use_cache=True).save()
```

**Cache Invalidation:**

Cache is invalidated if:
- Input data changes (different `prepare_calls()` result)
- Prompt version changes (system or user prompt updated)
- Context changes (different `initial_context`)

### With Consensus Polling

```python
pipeline = MyPipeline(model='google-gla:gemini-2.0-flash-lite')

# Require 3 matching results, max 5 attempts per call
pipeline.execute(
    data=pdf_bytes,
    initial_context={'source': 'rates.pdf'},
    consensus_polling={
        'enable': True,
        'consensus_threshold': 3,
        'maximum_step_calls': 5
    }
)

# If consensus not reached after 5 attempts:
# - Groups results by matching instructions
# - Returns most common response
```

### With Variable Resolver

```python
from llm_pipeline.prompts import VariableResolver

class DateVariables(BaseModel):
    current_date: str
    current_year: str

resolver = VariableResolver(variable_classes=[DateVariables])
pipeline = MyPipeline(model='google-gla:gemini-2.0-flash-lite', variable_resolver=resolver)

# Steps can now use {current_date} and {current_year} in prompts
```

### Accessing Extractions from Other Steps

```python
class LaneExtraction(PipelineExtraction):
    MODEL = Lane

    def default(self, instructions: List[LaneInstructions]) -> List[Lane]:
        # Access previously extracted models
        locations = self.pipeline.get_extractions(Location)

        lanes = []
        for instr in instructions:
            # Use FK from earlier extraction
            location = locations[instr.location_index]
            lanes.append(Lane(
                name=instr.lane_name,
                location_id=location.id  # ID assigned during flush
            ))
        return lanes
```

### External Session Management

```python
from sqlalchemy import create_engine
from sqlmodel import Session

engine = create_engine("postgresql://localhost/mydb")

# Pipeline does NOT own this session
with Session(engine) as session:
    pipeline = MyPipeline(session=session, model='google-gla:gemini-2.0-flash-lite')
    pipeline.execute(data, context)
    results = pipeline.save(session=session)
    session.commit()
    # Session closed by context manager
```

### Strategy Selection

```python
# Context determines which strategy executes
context = {'table_type': 'lane_based'}
pipeline.execute(data, context)
# Selects LaneBasedStrategy if can_handle(context) returns True

context = {'table_type': 'destination_based'}
pipeline.execute(data, context)
# Selects DestinationBasedStrategy
```

---

## See Also

- [Step API Reference](step.md) - `LLMStep` and step definition system
- [Strategy API Reference](strategy.md) - `PipelineStrategy` and strategy selection
- [Extraction API Reference](extraction.md) - `PipelineExtraction` for database extraction
- [Transformation API Reference](transformation.md) - `PipelineTransformation` for data transformation
- [State API Reference](state.md) - `PipelineStepState` and caching
- [Registry API Reference](registry.md) - `PipelineDatabaseRegistry` and FK ordering
- [Getting Started Guide](../guides/getting-started.md) - Complete walkthrough
- [Architecture Overview](../architecture/overview.md) - Design philosophy and patterns
