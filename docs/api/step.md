# Step API Reference

## Overview

The step module provides base classes and decorators for implementing LLM-powered pipeline steps. Every step in an LLM pipeline extends `LLMStep` and uses the `@step_definition` decorator to configure defaults and enable factory-based instantiation.

## Module: `llm_pipeline.step`

### Classes

- [`LLMStep`](#llmstep) - Abstract base class for all pipeline steps
- [`LLMResultMixin`](#llmresultmixin) - Pydantic mixin for standardized instruction schemas

### Decorators

- [`@step_definition`](#step_definition) - Auto-generates factory methods and enforces naming conventions

### Functions

---

## LLMStep

Abstract base class for all LLM-powered pipeline steps.

**Inheritance:** `ABC` (Python abstract base class)

**Purpose:** Each step implements this interface to prepare LLM calls based on context and process results into final outputs.

### Constructor

```python
def __init__(
    self,
    system_instruction_key: str,
    user_prompt_key: str,
    instructions: Type[BaseModel],
    pipeline: PipelineConfig
)
```

**Parameters:**

- `system_instruction_key` (str) - Database key for system prompt (e.g., `"constraint_extraction"`)
- `user_prompt_key` (str) - Database key for user prompt template
- `instructions` (Type[BaseModel]) - Pydantic class defining expected LLM output structure
- `pipeline` (PipelineConfig) - Parent pipeline instance providing context and session access

**Stored Attributes:**

- `self.system_instruction_key` - System prompt key
- `self.user_prompt_key` - User prompt key
- `self.instructions` - Instruction schema class
- `self.pipeline` - Reference to parent pipeline

### Properties

#### `step_name`

Auto-derived step name from class name.

```python
@property
def step_name(self) -> str
```

**Returns:** Snake_case version of class name with `Step` suffix removed

**Example:**

```python
class ConstraintExtractionStep(LLMStep):
    pass

step.step_name  # "constraint_extraction"
```

**Validation:** Raises `ValueError` if class name doesn't end with `Step` suffix

### Abstract Methods

These methods **must** be implemented by all concrete step classes.

#### `prepare_calls()`

Prepare LLM call parameters based on current pipeline context.

```python
@abstractmethod
def prepare_calls(self) -> List[StepCallParams]
```

**Returns:** List of `StepCallParams` dictionaries, one per LLM call to execute

**Purpose:** This is where steps examine `self.pipeline.context` and `self.pipeline.data` to determine what LLM calls to make. A step may return multiple calls (e.g., one per table row).

**Example:**

```python
def prepare_calls(self) -> List[StepCallParams]:
    tables = self.pipeline.context.get('tables', [])
    calls = []
    for table_data in tables:
        calls.append(self.create_llm_call(
            variables={'table_content': table_data}
        ))
    return calls
```

### Overridable Methods

These methods have default implementations but can be customized.

#### `process_instructions()`

Extract derived context values from LLM instruction results.

```python
def process_instructions(self, instructions: List[Any]) -> Dict[str, Any]
```

**Parameters:**

- `instructions` (List[Any]) - List of LLM result objects (validated against `self.instructions` schema)

**Returns:** Dictionary of context updates to merge into `pipeline.context`

**Default:** Returns empty dict (no context updates)

**Example:**

```python
def process_instructions(self, instructions: List[Any]) -> Dict[str, Any]:
    # Extract high-level insights from all instruction results
    all_categories = []
    for instr in instructions:
        all_categories.extend(instr.categories)

    return {
        'detected_categories': list(set(all_categories)),
        'total_items_processed': len(instructions)
    }
```

#### `should_skip()`

Determine if step should be skipped based on current context.

```python
def should_skip(self) -> bool
```

**Returns:** `True` to skip step execution, `False` to execute normally

**Default:** Returns `False` (never skip)

**Example:**

```python
def should_skip(self) -> bool:
    # Skip if no tables detected in previous step
    return not self.pipeline.context.get('tables')
```

#### `log_instructions()`

Custom logging for instruction results.

```python
def log_instructions(self, instructions: List[Any]) -> None
```

**Parameters:**

- `instructions` (List[Any]) - List of validated instruction results

**Default:** No-op (does nothing)

**Example:**

```python
def log_instructions(self, instructions: List[Any]) -> None:
    for idx, instr in enumerate(instructions):
        logger.info(f"Table {idx}: {instr.table_type}, {len(instr.rows)} rows")
```

### Helper Methods

#### `create_llm_call()`

Create LLM call parameters with defaults from step configuration.

```python
def create_llm_call(
    self,
    variables: Dict[str, Any],
    system_instruction_key: Optional[str] = None,
    user_prompt_key: Optional[str] = None,
    instructions: Optional[Type[BaseModel]] = None,
    **extra_params
) -> ExecuteLLMStepParams
```

**Parameters:**

- `variables` (Dict[str, Any]) - User prompt template variables (required)
- `system_instruction_key` (str, optional) - Override default system prompt key
- `user_prompt_key` (str, optional) - Override default user prompt key
- `instructions` (Type[BaseModel], optional) - Override default instruction schema
- `**extra_params` - Additional parameters merged into result

**Returns:** `ExecuteLLMStepParams` dictionary ready for `execute_llm_step()`

**Automatic Variable Resolution:**

If `pipeline._variable_resolver` is configured, this method automatically instantiates system variables for the given system prompt key.

**Example:**

```python
# Use defaults from step configuration
call = self.create_llm_call(variables={'table': table_data})

# Override system prompt for specific call
call = self.create_llm_call(
    variables={'table': table_data},
    system_instruction_key='special_extraction'
)
```

#### `store_extractions()`

Store extracted database models on the pipeline.

```python
def store_extractions(
    self,
    model_class: Type[SQLModel],
    instances: List[SQLModel]
) -> None
```

**Parameters:**

- `model_class` (Type[SQLModel]) - The model class being stored (used as dict key)
- `instances` (List[SQLModel]) - List of model instances to store

**Purpose:** Registers extracted models in `pipeline.extractions[model_class]` for later database persistence.

**Example:**

```python
constraints = [Constraint(name="Weight limit", value=500), ...]
self.store_extractions(Constraint, constraints)
```

#### `extract_data()`

Extract database models from LLM instructions using registered extraction classes.

```python
def extract_data(self, instructions: List[Any]) -> None
```

**Parameters:**

- `instructions` (List[Any]) - List of validated LLM instruction results

**Purpose:** Automatically delegates to all extraction classes registered on the step definition via `_extractions` attribute. Each extraction class processes the instructions and returns model instances.

**Two-Phase Write Pattern:**

This method implements Phase 1 of the two-phase write pattern:

1. Calls `extraction.extract(instructions)` to get model instances
2. Calls `self.pipeline._real_session.add(instance)` for each instance
3. Calls `self.pipeline._real_session.flush()` to assign database IDs
4. Transaction is NOT committed yet (happens in `pipeline.save()`)

**Purpose of flush():** Assigning IDs during execution enables later extractions to reference these IDs via foreign keys within the same pipeline run.

**Example:**

```python
# In step's main execution flow:
instructions = pipeline.execute_step(...)
self.extract_data(instructions)  # Automatic extraction via registered classes

# Later in pipeline.save():
session.commit()  # Phase 2: finalize transaction
```

**Note:** Most steps don't call this directly. The pipeline orchestrator calls it automatically after each step execution.

---

## LLMResultMixin

Pydantic mixin providing standardized fields for all LLM instruction schemas.

**Inheritance:** `BaseModel` (Pydantic base class)

**Purpose:** All instruction classes should inherit from this mixin to include confidence scoring and notes fields.

### Fields

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

**Field Details:**

- `confidence_score` (float) - Confidence level between 0.0 and 1.0 (default: 0.95)
- `notes` (str | None) - Optional reasoning or context from LLM

### Class Validation

#### `__init_subclass__()`

Validates that subclass `example` attribute matches class schema.

```python
def __init_subclass__(cls, **kwargs)
```

**Purpose:** If a subclass defines `cls.example`, this validates the example can instantiate the class successfully. Raises `ValueError` on validation failure.

**Example:**

```python
class ConstraintInstructions(LLMResultMixin):
    constraints: List[str]

    example = {
        'constraints': ['Weight limit', 'Size restriction'],
        'confidence_score': 0.9,
        'notes': 'Clear constraints found'
    }
    # Validation passes - example matches schema
```

```python
class BadInstructions(LLMResultMixin):
    count: int

    example = {
        'count': 'not a number'  # Wrong type
    }
    # Raises ValueError at class definition time
```

### Class Methods

#### `get_example()`

Retrieve an instantiated example object for this instruction class.

```python
@classmethod
def get_example(cls) -> Optional[BaseModel]
```

**Returns:** Instance of the class using `cls.example` dict, or `None` if no example defined

**Example:**

```python
class MyInstructions(LLMResultMixin):
    value: int
    example = {'value': 42, 'confidence_score': 1.0}

example_obj = MyInstructions.get_example()
print(example_obj.value)  # 42
```

#### `create_failure()`

Create a failure result instance with zero confidence.

```python
@classmethod
def create_failure(cls, reason: str, **safe_defaults) -> BaseModel
```

**Parameters:**

- `reason` (str) - Failure description (stored in `notes` field)
- `**safe_defaults` - Additional field values for safe defaults

**Returns:** Instance with `confidence_score=0.0` and `notes=f"Failed: {reason}"`

**Example:**

```python
result = ConstraintInstructions.create_failure(
    reason="Table parsing failed",
    constraints=[]  # Safe default for required field
)
# result.confidence_score == 0.0
# result.notes == "Failed: Table parsing failed"
```

---

## @step_definition

Decorator that auto-generates factory methods and enforces naming conventions.

### Signature

```python
def step_definition(
    instructions: Type[BaseModel],
    default_system_key: Optional[str] = None,
    default_user_key: Optional[str] = None,
    default_extractions: Optional[List] = None,
    default_transformation=None,
    context: Optional[Type] = None,
)
```

### Parameters

- `instructions` (Type[BaseModel]) - Instruction schema class (must extend `LLMResultMixin`)
- `default_system_key` (str, optional) - Default system prompt key for this step
- `default_user_key` (str, optional) - Default user prompt key for this step
- `default_extractions` (List, optional) - Default extraction classes for this step
- `default_transformation` (class, optional) - Default transformation class for this step
- `context` (Type, optional) - Context class this step produces

### Naming Validation

The decorator enforces strict naming conventions at class definition time:

1. **Step Class:** Must end with `Step` suffix
2. **Instruction Class:** Must be `{StepName}Instructions` (where `{StepName}` is step class name minus `Step`)
3. **Transformation Class:** Must be `{StepName}Transformation` (if provided)
4. **Context Class:** Must be `{StepName}Context` (if provided)

**Example (Valid):**

```python
@step_definition(
    instructions=ConstraintExtractionInstructions,
    default_system_key='constraint_extraction',
    default_user_key='extract_constraints',
    default_extractions=[ConstraintExtraction]
)
class ConstraintExtractionStep(LLMStep):
    pass
```

**Example (Invalid):**

```python
@step_definition(
    instructions=MyInstructions,  # Wrong name!
    # ...
)
class ConstraintExtractionStep(LLMStep):
    pass
# Raises ValueError: Instruction class must be named 'ConstraintExtractionInstructions'
```

### Class Attributes Set

The decorator stores configuration as class attributes:

- `INSTRUCTIONS` - Instruction schema class
- `DEFAULT_SYSTEM_KEY` - Default system prompt key
- `DEFAULT_USER_KEY` - Default user prompt key
- `DEFAULT_EXTRACTIONS` - Default extraction classes list
- `DEFAULT_TRANSFORMATION` - Default transformation class
- `CONTEXT` - Context class this step produces

### Factory Method: `create_definition()`

The decorator adds a `create_definition()` classmethod to the step class.

```python
@classmethod
def create_definition(
    cls,
    system_instruction_key: Optional[str] = None,
    user_prompt_key: Optional[str] = None,
    extractions: Optional[List] = None,
    transformation=None,
    **kwargs
) -> StepDefinition
```

**Parameters:**

- `system_instruction_key` (str, optional) - Override default system prompt key
- `user_prompt_key` (str, optional) - Override default user prompt key
- `extractions` (List, optional) - Override default extraction classes
- `transformation` (class, optional) - Override default transformation class
- `**kwargs` - Additional parameters passed to `StepDefinition`

**Returns:** `StepDefinition` instance configured with step class and defaults

**Usage Pattern:**

```python
# Use defaults from decorator
step_def = ConstraintExtractionStep.create_definition()

# Override specific values
step_def = ConstraintExtractionStep.create_definition(
    system_instruction_key='custom_extraction',
    extractions=[CustomExtraction]
)
```

### Complete Example

```python
from llm_pipeline import LLMStep, LLMResultMixin, step_definition
from pydantic import BaseModel

# 1. Define instruction schema
class ConstraintExtractionInstructions(LLMResultMixin):
    constraints: List[str]
    table_type: str

    example = {
        'constraints': ['Weight limit: 500kg', 'Size limit: 2m x 2m'],
        'table_type': 'lane_based',
        'confidence_score': 0.95,
        'notes': 'Found standard constraint format'
    }

# 2. Define extraction class
class ConstraintExtraction(PipelineExtraction):
    MODEL = Constraint

    def default(self, instructions: List[ConstraintExtractionInstructions]) -> List[Constraint]:
        constraints = []
        for instr in instructions:
            for constraint_text in instr.constraints:
                constraints.append(Constraint(text=constraint_text))
        return constraints

# 3. Define step with decorator
@step_definition(
    instructions=ConstraintExtractionInstructions,
    default_system_key='constraint_extraction',
    default_user_key='extract_constraints',
    default_extractions=[ConstraintExtraction]
)
class ConstraintExtractionStep(LLMStep):
    def prepare_calls(self) -> List[StepCallParams]:
        tables = self.pipeline.context.get('tables', [])
        return [
            self.create_llm_call(variables={'table': table})
            for table in tables
        ]

# 4. Use factory to create step definition
step_def = ConstraintExtractionStep.create_definition()

# 5. Register in strategy
class MyStrategy(PipelineStrategy):
    STEPS = [step_def]
```

---

## Module Exports

```python
__all__ = ["LLMStep", "LLMResultMixin", "step_definition"]
```

---

## Usage Patterns

### Basic Step Implementation

```python
from llm_pipeline import LLMStep, LLMResultMixin, step_definition
from typing import List

class MyInstructions(LLMResultMixin):
    result: str

@step_definition(
    instructions=MyInstructions,
    default_system_key='my_step',
    default_user_key='my_prompt'
)
class MyStep(LLMStep):
    def prepare_calls(self) -> List[StepCallParams]:
        return [self.create_llm_call(variables={'input': 'data'})]

# Create step definition for strategy
step_def = MyStep.create_definition()
```

### Multi-Call Step

```python
@step_definition(
    instructions=RowAnalysisInstructions,
    default_system_key='row_analysis',
    default_user_key='analyze_row'
)
class RowAnalysisStep(LLMStep):
    def prepare_calls(self) -> List[StepCallParams]:
        rows = self.pipeline.context.get('rows', [])
        # Create one LLM call per row
        return [
            self.create_llm_call(variables={'row_data': row})
            for row in rows
        ]

    def process_instructions(self, instructions: List[RowAnalysisInstructions]) -> Dict[str, Any]:
        # Aggregate results from all rows
        total_confidence = sum(i.confidence_score for i in instructions) / len(instructions)
        return {'average_confidence': total_confidence}
```

### Conditional Step Execution

```python
@step_definition(
    instructions=ValidationInstructions,
    default_system_key='validation'
)
class ValidationStep(LLMStep):
    def should_skip(self) -> bool:
        # Skip if previous step had low confidence
        return self.pipeline.context.get('average_confidence', 1.0) < 0.5

    def prepare_calls(self) -> List[StepCallParams]:
        return [self.create_llm_call(variables={'data': self.pipeline.data})]
```

### Step with Custom Logging

```python
@step_definition(
    instructions=ClassificationInstructions,
    default_system_key='classify'
)
class ClassificationStep(LLMStep):
    def log_instructions(self, instructions: List[ClassificationInstructions]) -> None:
        for instr in instructions:
            logger.info(f"Classified as: {instr.category} (confidence: {instr.confidence_score})")

    def prepare_calls(self) -> List[StepCallParams]:
        return [self.create_llm_call(variables={'text': self.pipeline.context['text']})]
```

---

## See Also

- [Pipeline API Reference](pipeline.md) - `PipelineConfig` class and data management
- [Strategy API Reference](strategy.md) - `PipelineStrategy` and step definition registration
- [Extraction API Reference](extraction.md) - `PipelineExtraction` for database model extraction
- [Pipeline API Reference](pipeline.md) - Pipeline execution and validation layers
- [Getting Started Guide](../guides/getting-started.md) - Complete working examples
