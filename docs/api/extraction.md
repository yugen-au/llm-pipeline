# PipelineExtraction API Reference

## Overview

`PipelineExtraction` handles conversion of LLM results into database models. Each extraction is responsible for one model type and has access to pipeline context and state.

Extractions are defined alongside their step and configured using `default_extractions`:

```python
@step_definition(
    result_class=SemanticMappingInstructions,
    default_extractions=[LaneExtraction],
)
class SemanticMappingStep(LLMStep):
    pass
```

## Module

```python
from llm_pipeline.extraction import PipelineExtraction
```

## Class Definition

```python
class PipelineExtraction(ABC):
    """Base class for data extraction logic."""

    MODEL: ClassVar[Type[SQLModel]] = None
```

### Class Parameters

Extractions must specify their model at class definition time using class call syntax:

```python
class LaneExtraction(PipelineExtraction, model=Lane):
    def default(self, results: List[SemanticMappingInstructions]) -> List[Lane]:
        # Extraction logic
        return lanes
```

**Parameters:**
- `model` (Type[SQLModel], required): Database model class this extraction produces

**Raises:**
- `ValueError`: If model not provided for concrete extraction
- `ValueError`: If class name doesn't end with 'Extraction'

### Naming Convention

Extraction classes must follow the naming convention: `{ModelName}Extraction`

**Valid examples:**
- `LaneExtraction`
- `RateExtraction`
- `DestinationExtraction`

**Invalid examples:**
- `LaneProcessor` (missing 'Extraction' suffix)
- `ExtractLane` (wrong order)

**Escape hatch:** Prefix class name with underscore (`_BaseExtraction`) for intermediate abstract classes.

## Initialization

```python
def __init__(self, pipeline: PipelineConfig)
```

Initialize extraction with pipeline reference. Validates that the extraction's MODEL is in the pipeline's registry.

**Parameters:**
- `pipeline` (PipelineConfig): Reference to the pipeline instance

**Raises:**
- `ValueError`: If MODEL is not in pipeline's registry

**Example:**
```python
extraction = LaneExtraction(pipeline)
# Validates Lane is in pipeline.REGISTRY.get_models()
```

## Class Attributes

### MODEL

```python
MODEL: ClassVar[Type[SQLModel]] = None
```

Database model class this extraction produces. Set via class parameter during definition.

## Instance Attributes

### pipeline

```python
pipeline: PipelineConfig
```

Reference to the pipeline instance. Provides access to:
- `pipeline.context`: All step results, DataFrame, metadata
- `pipeline.get_extractions(Model)`: Previously extracted models
- `pipeline.session`: Database session (read-only wrapper)
- `pipeline._real_session`: Actual database session (for writes)
- `pipeline.instructions`: LLM instructions from steps

## Methods

### extract()

```python
def extract(self, results: List[Any]) -> List[SQLModel]
```

Auto-detect and call the appropriate extraction method using smart method detection.

**Parameters:**
- `results` (List[Any]): List of LLM result objects from execute_llm_step()

**Returns:**
- `List[SQLModel]`: List of validated model instances ready for database insertion

**Raises:**
- `NotImplementedError`: If no extraction methods defined
- `NotImplementedError`: If multiple methods exist with no default or strategy match
- `ValueError`: If instances contain invalid data (from _validate_instances)

**Method Detection Priority:**

| Priority | Condition | Action |
|----------|-----------|--------|
| 1 | Subclass defines `default()` method | Use `default()` |
| 2 | Current strategy name matches method name | Use strategy-specific method |
| 3 | Exactly ONE custom method (not `extract`) | Use that method |
| 4 | No custom methods | Raise NotImplementedError |
| 5 | Multiple methods, no default/match | Raise NotImplementedError |

**Example patterns:**

```python
# Pattern 1: Single method (any name)
class LaneExtraction(PipelineExtraction, model=Lane):
    def extract_lanes(self, results):
        # Auto-detected as only method
        return lanes

# Pattern 2: Explicit default
class RateExtraction(PipelineExtraction, model=Rate):
    def default(self, results):
        # Always used
        return rates

# Pattern 3: Strategy-specific methods
class DestinationExtraction(PipelineExtraction, model=Destination):
    def lane_based(self, results):
        # Used when strategy.name == "lane_based"
        return destinations

    def zone_based(self, results):
        # Used when strategy.name == "zone_based"
        return destinations
```

### _validate_instance()

```python
def _validate_instance(self, instance: SQLModel, index: int) -> None
```

Validate a single model instance before database insertion. Catches validation issues that SQLModel with `table=True` doesn't catch.

**Parameters:**
- `instance` (SQLModel): Model instance to validate
- `index` (int): Index in the list (for error messages)

**Raises:**
- `ValueError`: If instance contains invalid data

**Validation checks:**

1. **Decimal fields for NaN/Infinity** - Prevents silent database failures
2. **Required fields for NULL** - Prevents NOT NULL constraint violations
3. **Foreign key fields for NULL** - Prevents FK constraint violations

**Example:**
```python
# Validates this instance
lane = Lane(
    rate_card_id=1,  # FK - cannot be None
    origin="NYC",    # Required - cannot be None
    rate=Decimal("10.50")  # Cannot be NaN or Infinity
)
extraction._validate_instance(lane, 0)
```

**Error examples:**
```python
# NaN in Decimal field
lane.rate = Decimal('NaN')
# ValueError: Invalid Lane at index 0: Field 'rate' cannot be NaN

# NULL in required field
lane.origin = None
# ValueError: Invalid Lane at index 0: Required field 'origin' cannot be None

# NULL in foreign key
lane.rate_card_id = None
# ValueError: Invalid Lane at index 0: Foreign key field 'rate_card_id' cannot be None
```

**Note:** Primary key fields named 'id' are exempted from FK validation (auto-generated).

### _validate_instances()

```python
def _validate_instances(self, instances: List[SQLModel]) -> List[SQLModel]
```

Validate all extracted instances before returning to pipeline. Calls `_validate_instance()` for each instance.

**Parameters:**
- `instances` (List[SQLModel]): List of model instances from extraction method

**Returns:**
- `List[SQLModel]`: Same list of instances (validation raises on error)

**Raises:**
- `ValueError`: If any instance contains invalid data

**Why this exists:** SQLModel with `table=True` doesn't run Pydantic validation. This method manually validates critical constraints to catch errors at extraction time rather than database insertion time.

**Example:**
```python
class LaneExtraction(PipelineExtraction, model=Lane):
    def default(self, results):
        lanes = [...]  # Extract from results
        return self._validate_instances(lanes)
        # Called automatically by extract(), but can be called manually
```

## Smart Method Detection Examples

### Single Method Auto-Detection

```python
class LaneExtraction(PipelineExtraction, model=Lane):
    def extract_from_semantic_mapping(self, results):
        """Auto-detected as the only custom method."""
        df = self.pipeline.context['df']
        rate_card_id = self.pipeline.context['rate_card_id']

        lanes = []
        for instruction in results[0].lane_mappings:
            lane = Lane(
                rate_card_id=rate_card_id,
                origin=instruction.origin,
                destination=instruction.destination
            )
            lanes.append(lane)

        return lanes
```

### Explicit Default Method

```python
class RateExtraction(PipelineExtraction, model=Rate):
    def default(self, results):
        """Always used regardless of strategy."""
        df = self.pipeline.context['df']
        lanes = self.pipeline.get_extractions(Lane)

        rates = []
        for lane in lanes:
            for _, row in df.iterrows():
                rate = Rate(
                    lane_id=lane.id,
                    amount=Decimal(str(row['rate'])),
                    currency='USD'
                )
                rates.append(rate)

        return rates
```

### Strategy-Specific Methods

```python
class DestinationExtraction(PipelineExtraction, model=Destination):
    """Routes to different methods based on current strategy."""

    def lane_based(self, results):
        """Called when pipeline._current_strategy.name == 'lane_based'"""
        instructions = results[0]
        destinations = []

        for mapping in instructions.lane_mappings:
            dest = Destination(
                name=mapping.destination,
                type='lane'
            )
            destinations.append(dest)

        return destinations

    def zone_based(self, results):
        """Called when pipeline._current_strategy.name == 'zone_based'"""
        instructions = results[0]
        destinations = []

        for zone in instructions.zones:
            dest = Destination(
                name=zone.name,
                type='zone'
            )
            destinations.append(dest)

        return destinations
```

## Access Pipeline State

Extractions have full access to pipeline state:

```python
class ComplexExtraction(PipelineExtraction, model=ComplexModel):
    def default(self, results):
        # Access context (DataFrame, IDs, metadata)
        df = self.pipeline.context['df']
        rate_card_id = self.pipeline.context['rate_card_id']

        # Access previously extracted models
        lanes = self.pipeline.get_extractions(Lane)
        rates = self.pipeline.get_extractions(Rate)

        # Access LLM instructions from other steps
        semantic_instructions = self.pipeline.instructions['SemanticMappingStep']
        unpivot_instructions = self.pipeline.instructions['UnpivotDetectionStep']

        # Access database session (read-only)
        existing_records = self.pipeline.session.query(OtherModel).all()

        # Create instances with FK references
        models = []
        for lane in lanes:
            model = ComplexModel(
                lane_id=lane.id,  # FK to extracted Lane
                data=df.to_dict()
            )
            models.append(model)

        return models
```

## Foreign Key Dependencies

Extractions can reference previously extracted models via foreign keys. The framework ensures correct execution order:

```python
# Step 1: Extract parent models
class LaneExtraction(PipelineExtraction, model=Lane):
    def default(self, results):
        return lanes  # ID assigned via _real_session.flush()

# Step 2: Extract child models with FK references
class RateExtraction(PipelineExtraction, model=Rate):
    def default(self, results):
        lanes = self.pipeline.get_extractions(Lane)

        rates = []
        for lane in lanes:
            rate = Rate(
                lane_id=lane.id,  # FK available after flush()
                amount=Decimal("10.50")
            )
            rates.append(rate)

        return rates
```

**How it works:**
1. `extract_data()` calls `_real_session.add()` and `_real_session.flush()`
2. Flush assigns database IDs to instances
3. Later extractions can reference these IDs as foreign keys
4. `save()` calls `session.commit()` to finalize transaction

## Validation Best Practices

### Always Validate Decimals

```python
class RateExtraction(PipelineExtraction, model=Rate):
    def default(self, results):
        df = self.pipeline.context['df']
        rates = []

        for _, row in df.iterrows():
            # Filter out invalid values
            if pd.isna(row['rate']) or row['rate'] in [float('inf'), float('-inf')]:
                continue  # Skip invalid rows

            rate = Rate(
                amount=Decimal(str(row['rate'])),
                currency='USD'
            )
            rates.append(rate)

        return rates  # _validate_instances() checks for NaN/Infinity
```

### Always Populate Required Fields

```python
class LaneExtraction(PipelineExtraction, model=Lane):
    def default(self, results):
        lanes = []

        for mapping in results[0].lane_mappings:
            # Validate required fields before creating instance
            if not mapping.origin or not mapping.destination:
                continue  # Skip incomplete mappings

            lane = Lane(
                rate_card_id=self.pipeline.context['rate_card_id'],  # Required FK
                origin=mapping.origin,  # Required
                destination=mapping.destination  # Required
            )
            lanes.append(lane)

        return lanes  # _validate_instances() checks for None
```

### Handle Optional Foreign Keys

```python
class AddressExtraction(PipelineExtraction, model=Address):
    def default(self, results):
        addresses = []

        for addr_data in results[0].addresses:
            # Optional FK - can be None
            country_id = None
            if addr_data.country_code:
                countries = self.pipeline.get_extractions(Country)
                country = next((c for c in countries if c.code == addr_data.country_code), None)
                country_id = country.id if country else None

            address = Address(
                street=addr_data.street,
                country_id=country_id  # Optional FK - None is OK
            )
            addresses.append(address)

        return addresses
```

## Error Handling

### Common Errors

**Model Not in Registry:**
```python
class MyExtraction(PipelineExtraction, model=MyModel):
    pass

# ValueError: MyExtraction.MODEL (MyModel) is not in MyPipelineRegistry.
# Valid models: [Lane, Rate, Destination]
```

**Invalid Naming:**
```python
class LaneProcessor(PipelineExtraction, model=Lane):
    pass

# ValueError: LaneProcessor must follow naming convention: {ModelName}Extraction
# Example: LaneExtraction, RateExtraction
```

**Missing Model:**
```python
class LaneExtraction(PipelineExtraction):
    pass

# ValueError: LaneExtraction must specify model parameter when defining the class:
# class LaneExtraction(PipelineExtraction, model=YourModel)
```

**No Extraction Methods:**
```python
class LaneExtraction(PipelineExtraction, model=Lane):
    pass  # No methods defined

# NotImplementedError: LaneExtraction has no extraction methods defined.
# Add a 'default' method or a custom extraction method.
```

**Ambiguous Methods:**
```python
class LaneExtraction(PipelineExtraction, model=Lane):
    def method_a(self, results): ...
    def method_b(self, results): ...

# NotImplementedError: LaneExtraction has multiple extraction methods ['method_a', 'method_b']
# but no matching method for current strategy 'lane_based' and no 'default' method.
```

**Validation Failures:**
```python
# NaN in Decimal field
# ValueError: Invalid Rate at index 0: Field 'amount' cannot be NaN.
# Check extraction logic to filter out NaN values.

# NULL in required field
# ValueError: Invalid Lane at index 0: Required field 'origin' cannot be None.
# This would violate NOT NULL constraint on database insertion.

# NULL in foreign key
# ValueError: Invalid Rate at index 0: Foreign key field 'lane_id' cannot be None.
# This would violate foreign key constraint on database insertion.
```

## Complete Example

```python
from llm_pipeline.extraction import PipelineExtraction
from decimal import Decimal
import pandas as pd

# Define models
class Lane(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    rate_card_id: int = Field(foreign_key="rate_card.id")
    origin: str
    destination: str

class Rate(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    lane_id: int = Field(foreign_key="lane.id")
    amount: Decimal
    currency: str

# Define extractions
class LaneExtraction(PipelineExtraction, model=Lane):
    def default(self, results):
        """Extract lanes from semantic mapping instructions."""
        rate_card_id = self.pipeline.context['rate_card_id']

        lanes = []
        for mapping in results[0].lane_mappings:
            if not mapping.origin or not mapping.destination:
                continue  # Skip incomplete

            lane = Lane(
                rate_card_id=rate_card_id,
                origin=mapping.origin,
                destination=mapping.destination
            )
            lanes.append(lane)

        return lanes  # Auto-validated by extract()

class RateExtraction(PipelineExtraction, model=Rate):
    def default(self, results):
        """Extract rates from DataFrame using extracted lanes."""
        df = self.pipeline.context['df']
        lanes = self.pipeline.get_extractions(Lane)

        rates = []
        for lane in lanes:
            # Find matching rows in DataFrame
            matches = df[
                (df['origin'] == lane.origin) &
                (df['destination'] == lane.destination)
            ]

            for _, row in matches.iterrows():
                # Validate before creating instance
                if pd.isna(row['rate']):
                    continue

                rate = Rate(
                    lane_id=lane.id,  # FK assigned after flush()
                    amount=Decimal(str(row['rate'])),
                    currency='USD'
                )
                rates.append(rate)

        return rates  # Auto-validated by extract()

# Configure in step
@step_definition(
    result_class=SemanticMappingInstructions,
    default_extractions=[LaneExtraction, RateExtraction],
)
class SemanticMappingStep(LLMStep):
    pass
```

## See Also

- [PipelineConfig API Reference](pipeline.md) - Access pipeline state
- [PipelineTransformation API Reference](transformation.md) - Data transformations
- [LLMStep API Reference](step.md) - Step definitions
- [State API Reference](state.md) - Execution state tracking
