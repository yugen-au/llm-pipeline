# Multi-Strategy Pipeline Example

## What You'll Learn

- Define multiple strategies for handling different data variants
- Implement context-based strategy selection with `can_handle()`
- Create strategy-specific extraction methods
- Configure strategy priority order
- Build pipelines that adapt to runtime data patterns

## Prerequisites

- Complete [Basic Pipeline Example](basic-pipeline.md)
- Understanding of Python inheritance and abstract classes
- Familiarity with the strategy pattern

## Time Estimate

30-45 minutes

## Final Result

A rate card parser that automatically selects the appropriate parsing strategy based on detected table type:
- **Lane-Based Strategy**: Origin-destination pairs with rates per lane
- **Destination-Based Strategy**: Destination-only with service level variants
- **Global Rates Strategy**: Flat fees with no location columns

---

## Why Multiple Strategies?

Real-world data often comes in multiple formats that require different processing logic. The strategy pattern lets you:

1. **Isolate variant logic**: Each strategy handles one data format independently
2. **Select at runtime**: Pipeline chooses strategy based on detected patterns
3. **Share common steps**: Steps can have default implementations or strategy-specific variants
4. **Maintain clarity**: Strategy classes make data variants explicit in code

---

## 1. Define Your Strategies

### Strategy Selection Logic

Each strategy implements `can_handle()` to determine if it should process the current data:

```python
from llm_pipeline import PipelineStrategy, StepDefinition
from typing import Dict, Any, List

class LaneBasedStrategy(PipelineStrategy):
    """Strategy for tables with origin and destination columns."""

    def can_handle(self, context: Dict[str, Any]) -> bool:
        """Check if this is a lane-based table."""
        # Step 1 hasn't run yet, so accept initially
        table_type = context.get('table_type')
        if table_type is None:
            return True  # Let detection step run

        # After step 1, only handle lane_based tables
        return table_type == 'lane_based'

    def get_steps(self) -> List[StepDefinition]:
        """Define the complete pipeline for lane-based tables."""
        return [
            TableTypeDetectionDef(),
            ConstraintExtractionDef(),
            LocationIdentificationDef(),
            LocationNormalizationDef(),
            UnpivotDetectionDef(),
            SemanticMappingDef(),
            SemanticTransformationDef(),
            ChargeDefinitionDef(),
        ]
```

**Key Points:**

- `can_handle()` receives the current pipeline context
- Return `True` initially to allow detection steps to run
- After detection, check context values to filter strategies
- All strategies define complete step sequences

### Multiple Strategy Definitions

```python
class DestinationBasedStrategy(PipelineStrategy):
    """Strategy for tables with destination columns only."""

    def can_handle(self, context: Dict[str, Any]) -> bool:
        table_type = context.get('table_type')
        if table_type is None:
            return True
        return table_type == 'destination_based'

    def get_steps(self) -> List[StepDefinition]:
        return [
            TableTypeDetectionDef(),
            ConstraintExtractionDef(),
            LocationIdentificationDef(),
            LocationNormalizationDef(),
            UnpivotDetectionDef(),
            SemanticMappingDef(),
            SemanticTransformationDef(),
            ChargeDefinitionDef(),
        ]


class GlobalRatesStrategy(PipelineStrategy):
    """Strategy for global flat fees with no locations."""

    def can_handle(self, context: Dict[str, Any]) -> bool:
        table_type = context.get('table_type')
        if table_type is None:
            return True
        return table_type == 'global_rates'

    def get_steps(self) -> List[StepDefinition]:
        return [
            TableTypeDetectionDef(),
            ConstraintExtractionDef(),
            ItemIdentificationDef(),  # Different step for global rates
            UnpivotDetectionDef(),
            SemanticMappingDef(),
            # No lane extraction for global rates
            SemanticTransformationDef(extractions=[]),
            ChargeDefinitionDef(),
        ]
```

**Notice:**
- GlobalRatesStrategy uses `ItemIdentificationDef()` instead of `LocationIdentificationDef()`
- It passes `extractions=[]` to `SemanticTransformationDef()` to skip lane extraction
- Strategies can define completely different step sequences

---

## 2. Register Your Strategies

Create a strategies container using declarative syntax:

```python
from llm_pipeline import PipelineStrategies

class RateCardParserStrategies(
    PipelineStrategies,
    strategies=[
        LaneBasedStrategy,
        DestinationBasedStrategy,
        GlobalRatesStrategy,
    ]
):
    """
    Strategies for rate card parsing.

    Strategies are tried in order. First matching strategy is used.
    Order matters: place more specific strategies before generic ones.
    """
```

**Strategy Priority:**
- Strategies are tried in the order listed
- First strategy where `can_handle()` returns `True` is selected
- Order matters if multiple strategies could match the same context

---

## 3. Create Strategy-Specific Extractions

Extraction classes can define multiple methods for different strategies:

```python
from llm_pipeline import PipelineExtraction
from typing import List
from .models import Lane

class LaneExtraction(PipelineExtraction, model=Lane):
    """
    Extract lane data from semantic mapping results.

    Supports multiple strategies with different location patterns.
    """

    def lane_based(self, results: List[SemanticMappingInstructions]) -> List[Lane]:
        """Extract lanes from origin-destination pairs."""
        result = results[0]
        df = self.pipeline.get_current_data()
        rate_card_id = self.pipeline.context['rate_card_id']

        lanes = []
        for _, row in df.iterrows():
            lane = Lane(
                rate_card_id=rate_card_id,
                origin=row.get('Origin'),
                destination=row.get('Destination'),
                service_level=row.get('Service Level')
            )
            lanes.append(lane)

        return lanes

    def destination_based(self, results: List[SemanticMappingInstructions]) -> List[Lane]:
        """Extract lanes from destination-only tables."""
        result = results[0]
        df = self.pipeline.get_current_data()
        rate_card_id = self.pipeline.context['rate_card_id']

        lanes = []
        for _, row in df.iterrows():
            lane = Lane(
                rate_card_id=rate_card_id,
                origin=None,  # No origin for destination-based
                destination=row.get('Destination'),
                service_level=row.get('Service Level')
            )
            lanes.append(lane)

        return lanes
```

**Method Detection Priority:**

The framework auto-detects which method to call:

1. **Explicit `default()` method** → always used if defined
2. **Strategy-specific method** → matches current strategy name (e.g., `lane_based()` for `LaneBasedStrategy`)
3. **Single custom method** → auto-detected if only one method defined
4. **Error** → if multiple methods exist but none match strategy or default

**Common Patterns:**

```python
# Pattern 1: Explicit default
class MyExtraction(PipelineExtraction, model=MyModel):
    def default(self, results):
        """This is always used regardless of strategy."""
        pass

# Pattern 2: Strategy-specific methods
class MyExtraction(PipelineExtraction, model=MyModel):
    def lane_based(self, results):
        """Used when LaneBasedStrategy is active."""
        pass

    def global_rates(self, results):
        """Used when GlobalRatesStrategy is active."""
        pass

# Pattern 3: Single method (any name)
class MyExtraction(PipelineExtraction, model=MyModel):
    def extract_data(self, results):
        """Only method, so auto-detected."""
        pass
```

---

## 4. Configure Your Pipeline

Connect strategies to your pipeline:

```python
from llm_pipeline import PipelineConfig, PipelineDatabaseRegistry
from .models import Vendor, RateCard, Lane, ChargeType, Rate

class RateCardParserRegistry(
    PipelineDatabaseRegistry,
    models=[
        Vendor,
        RateCard,
        Lane,
        ChargeType,
        Rate,
    ]
):
    """Database models managed by this pipeline."""


class RateCardParserPipeline(
    PipelineConfig,
    registry=RateCardParserRegistry,
    strategies=RateCardParserStrategies
):
    """
    Multi-strategy rate card parser.

    Execution flow:
    1. All strategies run step 1 (table type detection)
    2. Detection step sets context['table_type']
    3. For remaining steps, only matching strategy continues
    4. Strategy-specific extraction methods are auto-routed
    """

    def sanitize(self, data: pd.DataFrame) -> str:
        """Convert DataFrame to LLM-friendly format."""
        return data.to_csv(sep='|', index=False)
```

---

## 5. Execution Flow

### Step-by-Step Strategy Selection

When you execute the pipeline:

```python
pipeline = RateCardParserPipeline()
pipeline.execute(df, {
    'rate_card_id': 1,
    'vendor_id': 1,
})
```

The framework orchestrates strategy selection **per-step**:

```
Step 1: Table Type Detection
  → LaneBasedStrategy.can_handle(context) → True (table_type is None)
  → Use LaneBasedStrategy.get_steps()[0]
  → Execute TableTypeDetectionStep
  → Sets context['table_type'] = 'lane_based'

Step 2: Constraint Extraction
  → LaneBasedStrategy.can_handle(context) → True (table_type == 'lane_based')
  → DestinationBasedStrategy.can_handle(context) → False
  → GlobalRatesStrategy.can_handle(context) → False
  → Use LaneBasedStrategy.get_steps()[1]
  → Execute ConstraintExtractionStep

Step 3-8: Continue with LaneBasedStrategy
  → Only LaneBasedStrategy matches context
  → Execute remaining steps from LaneBasedStrategy.get_steps()
```

**Key Insight:** Strategy selection happens **before each step**, not once at the beginning. This allows early steps to gather information that later steps use for selection.

---

## 6. Context-Driven Selection

### Detection Step Pattern

Create a step that populates context for strategy selection:

```python
@step_definition(
    instructions=TableTypeInstructions,
    default_transformation=None,  # No data transformation
)
class TableTypeDetectionStep(LLMStep):
    """
    Step 1: Detect table type to determine strategy.

    Sets context['table_type'] for later strategy selection.
    """

    def prepare_calls(self) -> List[StepCallParams]:
        df = self.pipeline.get_current_data()

        # Analyze column names to detect type
        variables = TableTypeVariables(
            column_names=", ".join(df.columns),
            sample_rows=df.head(5).to_csv(sep='|')
        )

        return [{"variables": variables}]

    def log_instructions(self, instructions: List[TableTypeInstructions]) -> None:
        if instructions:
            # Store in context for strategy selection
            self.pipeline.context['table_type'] = instructions[0].table_type
            logger.info(f"  -> Detected table type: {instructions[0].table_type}")
```

### Context Keys for Selection

Common context patterns:

```python
# Pattern 1: Type/variant detection
context['table_type'] = 'lane_based'
context['format_version'] = 'v2'

# Pattern 2: Feature flags
context['has_origin'] = True
context['has_destination'] = True
context['has_service_levels'] = True

# Pattern 3: Complexity indicators
context['num_location_columns'] = 2
context['requires_unpivot'] = True
```

---

## 7. Complete Example

### File Structure

```
rate_card_parser/
├── __init__.py
├── models.py              # Database models
├── pipeline.py            # Pipeline + strategies
└── steps/
    ├── __init__.py
    ├── table_type.py      # Detection step
    ├── constraint_extraction.py
    ├── location_identification.py
    └── semantic_mapping.py
```

### models.py

```python
from sqlmodel import SQLModel, Field
from typing import Optional
from decimal import Decimal

class Lane(SQLModel, table=True):
    __tablename__ = 'lanes'

    id: Optional[int] = Field(default=None, primary_key=True)
    rate_card_id: int = Field(foreign_key="rate_cards.id")
    origin: Optional[str] = None
    destination: Optional[str] = None
    service_level: Optional[str] = None
```

### pipeline.py (Complete)

```python
import pandas as pd
from typing import Dict, Any, List

from llm_pipeline import (
    PipelineConfig,
    PipelineDatabaseRegistry,
    PipelineStrategy,
    PipelineStrategies,
    StepDefinition,
)
from .models import Vendor, RateCard, Lane, ChargeType, Rate
from .steps import (
    TableTypeDetectionDef,
    ConstraintExtractionDef,
    LocationIdentificationDef,
    ItemIdentificationDef,
    SemanticMappingDef,
    SemanticTransformationDef,
    ChargeDefinitionDef,
)

# ============================================================================
# REGISTRY
# ============================================================================

class RateCardParserRegistry(
    PipelineDatabaseRegistry,
    models=[Vendor, RateCard, Lane, ChargeType, Rate]
):
    """Models managed by rate card parser."""

# ============================================================================
# STRATEGIES
# ============================================================================

class LaneBasedStrategy(PipelineStrategy):
    """Strategy for lane-based rate tables."""

    def can_handle(self, context: Dict[str, Any]) -> bool:
        table_type = context.get('table_type')
        if table_type is None:
            return True
        return table_type == 'lane_based'

    def get_steps(self) -> List[StepDefinition]:
        return [
            TableTypeDetectionDef(),
            ConstraintExtractionDef(),
            LocationIdentificationDef(),
            SemanticMappingDef(),
            SemanticTransformationDef(),
            ChargeDefinitionDef(),
        ]


class DestinationBasedStrategy(PipelineStrategy):
    """Strategy for destination-based rate tables."""

    def can_handle(self, context: Dict[str, Any]) -> bool:
        table_type = context.get('table_type')
        if table_type is None:
            return True
        return table_type == 'destination_based'

    def get_steps(self) -> List[StepDefinition]:
        return [
            TableTypeDetectionDef(),
            ConstraintExtractionDef(),
            LocationIdentificationDef(),
            SemanticMappingDef(),
            SemanticTransformationDef(),
            ChargeDefinitionDef(),
        ]


class GlobalRatesStrategy(PipelineStrategy):
    """Strategy for global rates tables."""

    def can_handle(self, context: Dict[str, Any]) -> bool:
        table_type = context.get('table_type')
        if table_type is None:
            return True
        return table_type == 'global_rates'

    def get_steps(self) -> List[StepDefinition]:
        return [
            TableTypeDetectionDef(),
            ConstraintExtractionDef(),
            ItemIdentificationDef(),  # Different from other strategies
            SemanticMappingDef(),
            SemanticTransformationDef(extractions=[]),  # No lane extraction
            ChargeDefinitionDef(),
        ]


class RateCardParserStrategies(
    PipelineStrategies,
    strategies=[
        LaneBasedStrategy,
        DestinationBasedStrategy,
        GlobalRatesStrategy,
    ]
):
    """Strategies for rate card parsing."""

# ============================================================================
# PIPELINE
# ============================================================================

class RateCardParserPipeline(
    PipelineConfig,
    registry=RateCardParserRegistry,
    strategies=RateCardParserStrategies
):
    """Multi-strategy rate card parser."""

    def sanitize(self, data: pd.DataFrame) -> str:
        return data.to_csv(sep='|', index=False)
```

### Usage

```python
from sqlmodel import Session, create_engine
import pandas as pd

# Setup
engine = create_engine("sqlite:///rates.db")
session = Session(engine)

# Sample data
df = pd.DataFrame({
    'Origin': ['NYC', 'LAX', 'ORD'],
    'Destination': ['SFO', 'JFK', 'ATL'],
    'Standard Rate': [100, 150, 120],
    'Express Rate': [150, 200, 180],
})

# Execute pipeline
pipeline = RateCardParserPipeline()
pipeline.execute(df, {
    'rate_card_id': 1,
    'vendor_id': 1,
})

# Check which strategy was used
print(f"Table type: {pipeline.context['table_type']}")
print(f"Strategy: {pipeline._current_strategy.name}")

# Access results
lanes = pipeline.get_extractions(Lane)
print(f"Extracted {len(lanes)} lanes")

# Save to database
results = pipeline.save(session)
```

---

## 8. Troubleshooting

### Multiple Strategies Match

**Problem:** More than one strategy returns `True` from `can_handle()`.

**Solution:** The framework uses the **first** matching strategy. Reorder your strategies list:

```python
class MyStrategies(
    PipelineStrategies,
    strategies=[
        SpecificStrategy,    # Try specific first
        GeneralStrategy,     # Then general
    ]
):
    pass
```

### No Strategy Matches

**Problem:** All strategies return `False` from `can_handle()`.

**Error:**
```
ValueError: No strategy can handle current context: {'table_type': 'unknown'}
```

**Solution:** Add a fallback strategy that always matches:

```python
class FallbackStrategy(PipelineStrategy):
    def can_handle(self, context: Dict[str, Any]) -> bool:
        return True  # Always match as last resort

    def get_steps(self) -> List[StepDefinition]:
        return [ErrorHandlingDef()]
```

### Wrong Extraction Method Called

**Problem:** Strategy-specific extraction method not being called.

**Debug:**
```python
# Add logging to extraction class
class MyExtraction(PipelineExtraction, model=MyModel):
    def lane_based(self, results):
        print(f"Current strategy: {self.pipeline._current_strategy.name}")
        # ...
```

**Common Causes:**
1. Method name doesn't match strategy name (case-sensitive)
2. Strategy's `NAME` property is incorrect
3. Multiple methods exist but no `default` or strategy match

---

## 9. Best Practices

### Strategy Organization

```python
# Good: Clear strategy responsibilities
class LaneBasedStrategy(PipelineStrategy):
    """Handles origin-destination pairs."""

class DestinationBasedStrategy(PipelineStrategy):
    """Handles destination-only tables."""

# Bad: Overlapping responsibilities
class ComplexStrategy(PipelineStrategy):
    """Handles many things..."""  # Too vague
```

### Context Keys

```python
# Good: Descriptive, namespaced keys
context['table_type'] = 'lane_based'
context['detection.has_origin'] = True
context['validation.row_count'] = 100

# Bad: Generic keys that might conflict
context['type'] = 'lane'
context['flag'] = True
context['count'] = 100
```

### Strategy Selection Timing

```python
# Good: Early detection sets context
def can_handle(self, context: Dict[str, Any]) -> bool:
    table_type = context.get('table_type')
    if table_type is None:
        return True  # Allow detection to run
    return table_type == 'lane_based'

# Bad: Assumes detection already ran
def can_handle(self, context: Dict[str, Any]) -> bool:
    return context['table_type'] == 'lane_based'  # KeyError if not set!
```

### Extraction Method Naming

```python
# Good: Match strategy.NAME exactly
class LaneBasedStrategy(PipelineStrategy):
    # NAME = 'lane_based' (auto-generated)
    pass

class MyExtraction(PipelineExtraction, model=MyModel):
    def lane_based(self, results):  # Matches strategy.NAME
        pass

# Bad: Name mismatch
class MyExtraction(PipelineExtraction, model=MyModel):
    def LaneBased(self, results):  # Wrong: case mismatch
        pass

    def lanes(self, results):  # Wrong: different name
        pass
```

---

## Summary

You've learned to build multi-strategy pipelines:

- **Strategy Definition**: `can_handle()` for runtime selection, `get_steps()` for step sequences
- **Strategy Registration**: Declarative `PipelineStrategies` with priority ordering
- **Strategy-Specific Extractions**: Multiple methods auto-routed by strategy name
- **Context-Driven Selection**: Detection steps populate context for later strategy filtering
- **Execution Flow**: Per-step strategy selection with first-match wins

## Next Steps

- [Prompt Management Guide](prompts.md): Organize prompts for multi-strategy pipelines
- [Advanced Patterns](advanced-patterns.md): Nested strategies and dynamic step generation
- [Testing Strategies](testing-strategies.md): Test framework for strategy selection logic

## Additional Resources

- [Strategy API Reference](../api/strategy.md): Complete `PipelineStrategy` documentation
- [Extraction API Reference](../api/extraction.md): Method detection priority rules
- [Design Patterns](../architecture/patterns.md): Strategy pattern implementation details
