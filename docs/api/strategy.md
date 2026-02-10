# Strategy API Reference

## Overview

The strategy system provides a flexible way to handle different execution paths within a pipeline based on runtime context. A strategy defines when it applies and what steps it provides.

## Module: `llm_pipeline.strategy`

### Classes

- [`StepDefinition`](#stepdefinition) - Configuration for a pipeline step
- [`PipelineStrategy`](#pipelinestrategy) - Base class for strategy implementations
- [`PipelineStrategies`](#pipelinestrategies) - Declarative strategy configuration

---

## StepDefinition

Dataclass that connects a step class with its configuration, including prompts, extractions, transformations, and context.

### Class Definition

```python
@dataclass
class StepDefinition:
    step_class: Type
    system_instruction_key: str
    user_prompt_key: str
    instructions: Type
    action_after: Optional[str] = None
    extractions: List[Type['PipelineExtraction']] = field(default_factory=list)
    transformation: Optional[Type['PipelineTransformation']] = None
    context: Optional[Type] = None
```

### Attributes

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `step_class` | `Type` | Yes | LLMStep subclass to execute |
| `system_instruction_key` | `str` | Yes* | Prompt key for system instruction (supports auto-discovery) |
| `user_prompt_key` | `str` | Yes* | Prompt key for user prompt (supports auto-discovery) |
| `instructions` | `Type` | Yes | Pydantic model class for LLM response structure |
| `action_after` | `Optional[str]` | No | Post-step action name (e.g., 'save') |
| `extractions` | `List[Type['PipelineExtraction']]` | No | Extraction classes to process LLM output |
| `transformation` | `Optional[Type['PipelineTransformation']]` | No | Transformation class for data conversion |
| `context` | `Optional[Type]` | No | Context class for step input data |

**Note:** `system_instruction_key` and `user_prompt_key` support auto-discovery if set to `None`. See [Prompt Auto-Discovery](#prompt-auto-discovery).

### Methods

#### `create_step(pipeline: 'PipelineConfig') -> LLMStep`

Creates configured step instance with pipeline reference and auto-discovered prompts.

**Parameters:**
- `pipeline` (`PipelineConfig`): Reference to pipeline instance

**Returns:**
- Instantiated step with prompts configured and pipeline reference

**Raises:**
- `ValueError`: If no prompts found via auto-discovery or explicit keys

**Example:**

```python
definition = StepDefinition(
    step_class=ConstraintExtractionStep,
    system_instruction_key=None,  # Auto-discover
    user_prompt_key=None,         # Auto-discover
    instructions=ConstraintInstructions,
    extractions=[LaneConstraintExtraction],
    context=RateCardContext
)

step = definition.create_step(pipeline)
```

### Prompt Auto-Discovery

When `system_instruction_key` or `user_prompt_key` is `None`, `create_step()` searches the database for prompts in this order:

1. **Strategy-level**: `{step_name}.{strategy_name}` (e.g., `constraint_extraction.lane_based`)
2. **Step-level**: `{step_name}` (e.g., `constraint_extraction`)
3. **Error**: If no prompts found

The `step_name` is derived from the step class name by:
1. Removing `Step` suffix (`ConstraintExtractionStep` → `ConstraintExtraction`)
2. Converting to snake_case (`ConstraintExtraction` → `constraint_extraction`)

**Example Search Path:**

For `LaneBasedStrategy` executing `ConstraintExtractionStep`:

```
1. constraint_extraction.lane_based  (strategy-level)
2. constraint_extraction              (step-level)
3. ValueError                         (no prompts found)
```

---

## PipelineStrategy

Abstract base class for pipeline strategies. Each strategy defines when it applies (`can_handle`) and what steps it provides (`get_steps`).

### Class Definition

```python
class PipelineStrategy(ABC):
    """Base class for pipeline strategies."""
```

### Naming Convention

**Required:** Class name must end with `Strategy` suffix (enforced at class definition time).

**Examples:**
- `LaneBasedStrategy` ✓
- `DestinationBasedStrategy` ✓
- `GlobalRatesStrategy` ✓
- `LaneBased` ✗ (missing suffix)

### Auto-Generated Properties

When a strategy class is defined, `__init_subclass__` automatically generates:

| Property | Generated From | Example |
|----------|---------------|---------|
| `NAME` | Class name → snake_case | `LaneBasedStrategy` → `"lane_based"` |
| `DISPLAY_NAME` | Class name → Title Case | `LaneBasedStrategy` → `"Lane Based"` |

### Properties

#### `name: str`

Strategy identifier (auto-generated from class name).

**Example:**
```python
strategy = LaneBasedStrategy()
print(strategy.name)  # "lane_based"
```

#### `display_name: str`

Human-readable strategy name (auto-generated from class name).

**Example:**
```python
strategy = LaneBasedStrategy()
print(strategy.display_name)  # "Lane Based"
```

### Abstract Methods

#### `can_handle(context: Dict[str, Any]) -> bool`

Determines if this strategy can handle the current context. Called before each step to select the appropriate strategy.

**Parameters:**
- `context` (`Dict[str, Any]`): Current pipeline context

**Returns:**
- `True` if this strategy should provide steps, `False` otherwise

**Example:**

```python
class LaneBasedStrategy(PipelineStrategy):
    def can_handle(self, context: Dict[str, Any]) -> bool:
        return context.get('table_type') == 'lane_based'
```

#### `get_steps() -> List[StepDefinition]`

Defines all steps for this strategy in execution order.

**Returns:**
- List of `StepDefinition` objects

**Example:**

```python
class LaneBasedStrategy(PipelineStrategy):
    def get_steps(self) -> List[StepDefinition]:
        return [
            StepDefinition(
                step_class=ConstraintExtractionStep,
                system_instruction_key='constraint_extraction.lane_based',
                user_prompt_key='constraint_extraction.lane_based',
                instructions=ConstraintInstructions,
                extractions=[LaneConstraintExtraction],
                context=RateCardContext
            ),
            StepDefinition(
                step_class=RateExtractionStep,
                system_instruction_key='rate_extraction.lane_based',
                user_prompt_key='rate_extraction.lane_based',
                instructions=RateInstructions,
                extractions=[LaneRateExtraction],
                context=RateCardContext
            )
        ]
```

### Validation

The `__init_subclass__` method validates:

1. **Naming convention**: Class name must end with `Strategy`
2. **Direct subclassing**: Only validates concrete classes that directly subclass `PipelineStrategy`
3. **Escape hatch**: Classes starting with `_` skip validation (for intermediate abstract classes)

**Example:**

```python
# Valid
class LaneBasedStrategy(PipelineStrategy):
    pass

# Valid (intermediate base)
class _BaseStrategy(PipelineStrategy):
    pass

# Invalid - raises ValueError
class LaneHandler(PipelineStrategy):
    pass
```

---

## PipelineStrategies

Base class for declarative strategy configuration. Similar to `PipelineDatabaseRegistry`, provides a centralized way to define which strategies a pipeline uses.

### Class Definition

```python
class PipelineStrategies(ABC):
    STRATEGIES: ClassVar[List[Type[PipelineStrategy]]] = []
```

### Usage

Strategies must be configured at class definition time using class call syntax:

```python
class RateCardParserStrategies(PipelineStrategies, strategies=[
    LaneBasedStrategy,
    DestinationBasedStrategy,
    GlobalRatesStrategy,
]):
    pass
```

Then reference in pipeline:

```python
class MyPipeline(PipelineConfig,
                registry=MyRegistry,
                strategies=MyStrategies,
                extractions=MyExtractions):
    pass
```

### Class Variables

#### `STRATEGIES: ClassVar[List[Type[PipelineStrategy]]]`

List of strategy classes configured for this pipeline.

### Class Methods

#### `create_instances() -> List[PipelineStrategy]`

Creates instances of all configured strategies.

**Returns:**
- List of instantiated strategy objects

**Raises:**
- `ValueError`: If `STRATEGIES` not configured

**Example:**

```python
strategies = RateCardParserStrategies.create_instances()
# [LaneBasedStrategy(), DestinationBasedStrategy(), GlobalRatesStrategy()]
```

#### `get_strategy_names() -> List[str]`

Gets names of all configured strategies.

**Returns:**
- List of strategy names

**Example:**

```python
names = RateCardParserStrategies.get_strategy_names()
# ["lane_based", "destination_based", "global_rates"]
```

### Validation

The `__init_subclass__` method validates:

1. **Strategies parameter required**: Concrete classes must provide `strategies=` parameter
2. **Escape hatch**: Classes starting with `_` skip validation

**Example:**

```python
# Valid
class MyStrategies(PipelineStrategies, strategies=[Strategy1, Strategy2]):
    pass

# Valid (intermediate base)
class _BaseStrategies(PipelineStrategies):
    pass

# Invalid - raises ValueError
class MyStrategies(PipelineStrategies):
    pass
```

---

## Strategy Selection Flow

The pipeline orchestrates execution by looping through step positions and selecting the appropriate strategy for each position:

1. **For each step position**:
   1. Loop through configured strategies
   2. Call `strategy.can_handle(context)` for each
   3. Use first strategy where `can_handle()` returns `True`
   4. Get step definition from strategy's `get_steps()` at current position
   5. Execute step

2. **Context parameter**: The `context` dict passed to `can_handle()` contains runtime data that determines which strategy applies (e.g., `context['table_type']` for table-based routing).

3. **Strategy priority**: Strategies are checked in the order they appear in the `strategies=` parameter.

**Example Flow:**

```python
# Given
context = {'table_type': 'lane_based'}
strategies = [LaneBasedStrategy(), DestinationBasedStrategy(), GlobalRatesStrategy()]

# For step position 0:
LaneBasedStrategy().can_handle(context)        # True -> use this strategy
DestinationBasedStrategy().can_handle(context) # Not checked
GlobalRatesStrategy().can_handle(context)      # Not checked

step_def = LaneBasedStrategy().get_steps()[0]
step = step_def.create_step(pipeline)
step.execute()
```

---

## Complete Example

### Define Strategies

```python
from llm_pipeline.strategy import PipelineStrategy, StepDefinition
from typing import List, Dict, Any

class LaneBasedStrategy(PipelineStrategy):
    def can_handle(self, context: Dict[str, Any]) -> bool:
        return context.get('table_type') == 'lane_based'

    def get_steps(self) -> List[StepDefinition]:
        return [
            StepDefinition(
                step_class=ConstraintExtractionStep,
                system_instruction_key='constraint_extraction.lane_based',
                user_prompt_key='constraint_extraction.lane_based',
                instructions=ConstraintInstructions,
                extractions=[LaneConstraintExtraction],
                context=RateCardContext
            )
        ]

class DestinationBasedStrategy(PipelineStrategy):
    def can_handle(self, context: Dict[str, Any]) -> bool:
        return context.get('table_type') == 'destination_based'

    def get_steps(self) -> List[StepDefinition]:
        return [
            StepDefinition(
                step_class=ConstraintExtractionStep,
                system_instruction_key='constraint_extraction.destination_based',
                user_prompt_key='constraint_extraction.destination_based',
                instructions=ConstraintInstructions,
                extractions=[DestinationConstraintExtraction],
                context=RateCardContext
            )
        ]
```

### Configure Strategy Collection

```python
from llm_pipeline.strategy import PipelineStrategies

class RateCardParserStrategies(PipelineStrategies, strategies=[
    LaneBasedStrategy,
    DestinationBasedStrategy,
]):
    pass
```

### Use in Pipeline

```python
from llm_pipeline.pipeline import PipelineConfig

class RateCardParserPipeline(PipelineConfig,
                             registry=RateCardParserRegistry,
                             strategies=RateCardParserStrategies,
                             extractions=RateCardParserExtractions):
    pass

# Execute
pipeline = RateCardParserPipeline(session=session)
pipeline.execute(context={'table_type': 'lane_based'})
```

---

## See Also

- [Pipeline API Reference](pipeline.md) - `PipelineConfig` and execution
- [Step API Reference](step.md) - `LLMStep` and `@step_definition`
- [Extraction API Reference](extraction.md) - Strategy-specific extraction methods
- [Prompt Management Guide](../guides/prompts.md) - Prompt auto-discovery
- [Multi-Strategy Pipeline Example](../guides/multi-strategy.md) - Working examples
