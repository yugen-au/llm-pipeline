# PipelineTransformation API Reference

## Overview

`PipelineTransformation` handles data structure changes (unpivoting, normalizing, etc.) with type validation and smart method detection. Each transformation validates input/output types and applies changes based on LLM instructions.

Transformations are defined alongside their step and configured using `default_transformations`:

```python
@step_definition(
    result_class=UnpivotInstructions,
    default_transformations=[UnpivotTransformation],
)
class UnpivotDetectionStep(LLMStep):
    pass
```

## Module

```python
from llm_pipeline.transformation import PipelineTransformation
```

## Class Definition

```python
class PipelineTransformation(ABC):
    """Base class for data transformation logic."""

    INPUT_TYPE: ClassVar[Type] = None
    OUTPUT_TYPE: ClassVar[Type] = None
```

### Class Parameters

Transformations must specify input and output types at class definition time using class call syntax:

```python
import pandas as pd

class UnpivotTransformation(PipelineTransformation,
                            input_type=pd.DataFrame,
                            output_type=pd.DataFrame):
    def default(self, data: pd.DataFrame, instructions: UnpivotInstructions) -> pd.DataFrame:
        # Transformation logic
        return transformed_df
```

**Parameters:**
- `input_type` (Type, required): Expected type of input data
- `output_type` (Type, required): Expected type of output data

**Raises:**
- `ValueError`: If input_type or output_type not provided for concrete transformation

**Escape hatch:** Prefix class name with underscore (`_BaseTransformation`) for intermediate abstract classes.

## Initialization

```python
def __init__(self, pipeline: PipelineConfig)
```

Initialize transformation with pipeline reference.

**Parameters:**
- `pipeline` (PipelineConfig): Reference to the pipeline instance

**Example:**
```python
transformation = UnpivotTransformation(pipeline)
```

## Class Attributes

### INPUT_TYPE

```python
INPUT_TYPE: ClassVar[Type] = None
```

Expected type of input data. Set via class parameter during definition. Used by `_validate_input()` for type checking.

### OUTPUT_TYPE

```python
OUTPUT_TYPE: ClassVar[Type] = None
```

Expected type of output data. Set via class parameter during definition. Used by `_validate_output()` for type checking.

## Instance Attributes

### pipeline

```python
pipeline: PipelineConfig
```

Reference to the pipeline instance. Provides access to:
- `pipeline.context`: Derived values and metadata
- `pipeline.instructions`: LLM instructions from steps
- `pipeline.get_data()`: Access to current and previous data states
- `pipeline.get_raw_data()`: Original input data
- `pipeline.get_current_data()`: Current transformed data
- `pipeline.get_sanitized_data()`: Sanitized data

## Methods

### transform()

```python
def transform(self, data: Any, instructions: Any) -> Any
```

Auto-detect and call the appropriate transformation method using smart method detection.

**Parameters:**
- `data` (Any): Input data to transform (validated against INPUT_TYPE)
- `instructions` (Any): LLM instructions for how to transform

**Returns:**
- `Any`: Transformed data (validated against OUTPUT_TYPE) or original data if passthrough

**Raises:**
- `TypeError`: If input/output data doesn't match expected types
- `NotImplementedError`: If multiple methods exist and none named 'default'

**Method Detection Priority:**

| Priority | Condition | Action |
|----------|-----------|--------|
| 1 | Subclass defines `default()` method | Use `default()` |
| 2 | Exactly ONE custom method (not `transform`) | Use that method |
| 3 | No custom methods | Passthrough (return data unchanged) |
| 4 | Multiple methods, no default | Raise NotImplementedError |

**CRITICAL:** Transformation does NOT support strategy-specific routing. Only extraction has strategy-name matching. Transformation supports: default → single → passthrough → error.

**Example patterns:**

```python
# Pattern 1: No methods (passthrough)
class NoOpTransformation(PipelineTransformation,
                         input_type=pd.DataFrame,
                         output_type=pd.DataFrame):
    pass  # Returns data unchanged

# Pattern 2: Single method (any name)
class UnpivotTransformation(PipelineTransformation,
                            input_type=pd.DataFrame,
                            output_type=pd.DataFrame):
    def unpivot_data(self, data, instructions):
        # Auto-detected as only method
        return transformed_df

# Pattern 3: Explicit default
class NormalizeTransformation(PipelineTransformation,
                              input_type=pd.DataFrame,
                              output_type=pd.DataFrame):
    def default(self, data, instructions):
        # Always used
        return normalized_df
```

### _validate_input()

```python
def _validate_input(self, data: Any) -> None
```

Validate input data matches expected INPUT_TYPE.

**Parameters:**
- `data` (Any): Input data to validate

**Raises:**
- `TypeError`: If data doesn't match INPUT_TYPE

**Example:**
```python
# INPUT_TYPE = pd.DataFrame
transformation._validate_input(df)  # OK
transformation._validate_input([1, 2, 3])  # TypeError
```

**Error message:**
```
TypeError: UnpivotTransformation expects input type DataFrame but got list
```

### _validate_output()

```python
def _validate_output(self, data: Any) -> None
```

Validate output data matches expected OUTPUT_TYPE.

**Parameters:**
- `data` (Any): Output data to validate

**Raises:**
- `TypeError`: If data doesn't match OUTPUT_TYPE

**Example:**
```python
# OUTPUT_TYPE = pd.DataFrame
result = transformation.default(df, instructions)
transformation._validate_output(result)  # Validates return type
```

**Error message:**
```
TypeError: UnpivotTransformation must return type DataFrame but returned dict
```

## Smart Method Detection Examples

### Passthrough (No Methods)

```python
import pandas as pd

class PassthroughTransformation(PipelineTransformation,
                                input_type=pd.DataFrame,
                                output_type=pd.DataFrame):
    """Returns data unchanged."""
    pass  # No methods defined - auto-passthrough
```

### Single Method Auto-Detection

```python
import pandas as pd

class UnpivotTransformation(PipelineTransformation,
                            input_type=pd.DataFrame,
                            output_type=pd.DataFrame):
    def unpivot_based_on_instructions(self, data, instructions):
        """Auto-detected as the only custom method."""
        # Get unpivot columns from LLM instructions
        id_cols = instructions.identifier_columns
        value_cols = instructions.value_columns

        # Perform unpivot
        unpivoted = pd.melt(
            data,
            id_vars=id_cols,
            value_vars=value_cols,
            var_name='metric',
            value_name='value'
        )

        return unpivoted
```

### Explicit Default Method

```python
import pandas as pd

class NormalizeTransformation(PipelineTransformation,
                               input_type=pd.DataFrame,
                               output_type=pd.DataFrame):
    def default(self, data, instructions):
        """Always used regardless of other factors."""
        # Normalize column names
        data.columns = [col.lower().replace(' ', '_') for col in data.columns]

        # Normalize data types
        for col, dtype in instructions.column_types.items():
            if col in data.columns:
                data[col] = data[col].astype(dtype)

        return data
```

### Type Conversion Transformation

```python
import pandas as pd
from typing import Dict

class DictToDataFrameTransformation(PipelineTransformation,
                                     input_type=dict,
                                     output_type=pd.DataFrame):
    def default(self, data: Dict, instructions):
        """Convert dict to DataFrame."""
        # Validate input type (dict)
        # Convert to DataFrame
        df = pd.DataFrame([data])
        # Validate output type (DataFrame)
        return df
```

## Access Pipeline State

Transformations have full access to pipeline state:

```python
class ContextAwareTransformation(PipelineTransformation,
                                  input_type=pd.DataFrame,
                                  output_type=pd.DataFrame):
    def default(self, data, instructions):
        # Access context metadata
        rate_card_id = self.pipeline.context['rate_card_id']
        table_type = self.pipeline.context['table_type']

        # Access previous step instructions
        semantic_instructions = self.pipeline.instructions['SemanticMappingStep']

        # Access previous data states
        raw_data = self.pipeline.get_raw_data()
        current_data = self.pipeline.get_current_data()

        # Apply transformation based on context
        if table_type == 'lane_based':
            data['rate_card_id'] = rate_card_id
            data['type'] = 'lane'
        elif table_type == 'zone_based':
            data['rate_card_id'] = rate_card_id
            data['type'] = 'zone'

        return data
```

## Type Validation Examples

### Pandas DataFrame Transformation

```python
import pandas as pd

class DataFrameTransformation(PipelineTransformation,
                               input_type=pd.DataFrame,
                               output_type=pd.DataFrame):
    def default(self, data: pd.DataFrame, instructions) -> pd.DataFrame:
        # Input validated as DataFrame
        # Perform transformation
        result = data.copy()
        # Output validated as DataFrame
        return result
```

### Dict to Dict Transformation

```python
from typing import Dict

class DictTransformation(PipelineTransformation,
                         input_type=dict,
                         output_type=dict):
    def default(self, data: Dict, instructions) -> Dict:
        # Input validated as dict
        result = {k: v.upper() if isinstance(v, str) else v
                  for k, v in data.items()}
        # Output validated as dict
        return result
```

### List to DataFrame Transformation

```python
import pandas as pd
from typing import List

class ListToDataFrameTransformation(PipelineTransformation,
                                     input_type=list,
                                     output_type=pd.DataFrame):
    def default(self, data: List, instructions) -> pd.DataFrame:
        # Input validated as list
        df = pd.DataFrame(data)
        # Output validated as DataFrame
        return df
```

## Unpivot Example

Complete example showing unpivot transformation:

```python
import pandas as pd
from pydantic import BaseModel
from typing import List

# Define instruction model
class UnpivotInstructions(BaseModel):
    identifier_columns: List[str]
    value_columns: List[str]
    variable_name: str
    value_name: str

# Define transformation
class UnpivotTransformation(PipelineTransformation,
                            input_type=pd.DataFrame,
                            output_type=pd.DataFrame):
    def default(self, data: pd.DataFrame, instructions: UnpivotInstructions) -> pd.DataFrame:
        """
        Unpivot DataFrame based on LLM-identified columns.

        Example:
            Input DataFrame:
                origin | destination | rate_usd | rate_eur
                NYC    | LAX         | 100      | 85
                NYC    | SFO         | 120      | 102

            Instructions:
                identifier_columns: ['origin', 'destination']
                value_columns: ['rate_usd', 'rate_eur']
                variable_name: 'currency'
                value_name: 'rate'

            Output DataFrame:
                origin | destination | currency  | rate
                NYC    | LAX         | rate_usd  | 100
                NYC    | LAX         | rate_eur  | 85
                NYC    | SFO         | rate_usd  | 120
                NYC    | SFO         | rate_eur  | 102
        """
        unpivoted = pd.melt(
            data,
            id_vars=instructions.identifier_columns,
            value_vars=instructions.value_columns,
            var_name=instructions.variable_name,
            value_name=instructions.value_name
        )

        return unpivoted

# Configure in step
@step_definition(
    result_class=UnpivotInstructions,
    default_transformations=[UnpivotTransformation],
)
class UnpivotDetectionStep(LLMStep):
    pass
```

## Error Handling

### Common Errors

**Missing Types:**
```python
class MyTransformation(PipelineTransformation):
    pass

# ValueError: MyTransformation must specify input_type and output_type parameters:
# class MyTransformation(PipelineTransformation, input_type=YourType, output_type=YourType)
```

**Input Type Mismatch:**
```python
class DataFrameTransformation(PipelineTransformation,
                               input_type=pd.DataFrame,
                               output_type=pd.DataFrame):
    def default(self, data, instructions):
        return data

# Called with wrong type
transformation.transform([1, 2, 3], instructions)

# TypeError: DataFrameTransformation expects input type DataFrame but got list
```

**Output Type Mismatch:**
```python
class DataFrameTransformation(PipelineTransformation,
                               input_type=pd.DataFrame,
                               output_type=pd.DataFrame):
    def default(self, data, instructions):
        return data.to_dict()  # Wrong return type

# TypeError: DataFrameTransformation must return type DataFrame but returned dict
```

**Ambiguous Methods:**
```python
class MyTransformation(PipelineTransformation,
                       input_type=pd.DataFrame,
                       output_type=pd.DataFrame):
    def method_a(self, data, instructions):
        return data

    def method_b(self, data, instructions):
        return data

# NotImplementedError: MyTransformation has multiple transformation methods ['method_a', 'method_b']
# but no 'default' method. Either:
#   1. Rename one method to 'default', or
#   2. Specify the method name explicitly in the strategy
```

## Best Practices

### Always Specify Types

```python
import pandas as pd

# Good - explicit types
class UnpivotTransformation(PipelineTransformation,
                            input_type=pd.DataFrame,
                            output_type=pd.DataFrame):
    def default(self, data, instructions):
        return transformed_df

# Bad - no types
class UnpivotTransformation(PipelineTransformation):
    def default(self, data, instructions):
        return transformed_df
```

### Use Explicit Default for Clarity

```python
# Good - clear intent
class NormalizeTransformation(PipelineTransformation,
                              input_type=pd.DataFrame,
                              output_type=pd.DataFrame):
    def default(self, data, instructions):
        return normalized_df

# Acceptable - auto-detected
class NormalizeTransformation(PipelineTransformation,
                              input_type=pd.DataFrame,
                              output_type=pd.DataFrame):
    def normalize(self, data, instructions):
        return normalized_df
```

### Handle Edge Cases

```python
import pandas as pd

class SafeUnpivotTransformation(PipelineTransformation,
                                 input_type=pd.DataFrame,
                                 output_type=pd.DataFrame):
    def default(self, data, instructions):
        # Validate columns exist
        missing = set(instructions.identifier_columns) - set(data.columns)
        if missing:
            raise ValueError(f"Identifier columns not found: {missing}")

        missing_values = set(instructions.value_columns) - set(data.columns)
        if missing_values:
            raise ValueError(f"Value columns not found: {missing_values}")

        # Perform unpivot
        unpivoted = pd.melt(
            data,
            id_vars=instructions.identifier_columns,
            value_vars=instructions.value_columns,
            var_name=instructions.variable_name,
            value_name=instructions.value_name
        )

        return unpivoted
```

### Use Type Hints

```python
import pandas as pd
from typing import Any

class UnpivotTransformation(PipelineTransformation,
                            input_type=pd.DataFrame,
                            output_type=pd.DataFrame):
    def default(self, data: pd.DataFrame, instructions: Any) -> pd.DataFrame:
        """Type hints improve IDE support and code clarity."""
        return transformed_df
```

## Complete Example

```python
import pandas as pd
from pydantic import BaseModel
from typing import List
from llm_pipeline.transformation import PipelineTransformation
from llm_pipeline.step import LLMStep, step_definition

# 1. Define instruction model
class UnpivotInstructions(BaseModel):
    """LLM result for unpivot detection."""
    identifier_columns: List[str]
    value_columns: List[str]
    variable_name: str = 'variable'
    value_name: str = 'value'

    class Config:
        # Example for LLM
        example = {
            'identifier_columns': ['origin', 'destination'],
            'value_columns': ['rate_usd', 'rate_eur'],
            'variable_name': 'currency',
            'value_name': 'rate'
        }

# 2. Define transformation
class UnpivotTransformation(PipelineTransformation,
                            input_type=pd.DataFrame,
                            output_type=pd.DataFrame):
    """Unpivot DataFrame based on LLM instructions."""

    def default(self, data: pd.DataFrame, instructions: UnpivotInstructions) -> pd.DataFrame:
        # Validate columns exist
        all_cols = set(instructions.identifier_columns + instructions.value_columns)
        missing = all_cols - set(data.columns)
        if missing:
            raise ValueError(f"Columns not found in DataFrame: {missing}")

        # Perform unpivot
        unpivoted = pd.melt(
            data,
            id_vars=instructions.identifier_columns,
            value_vars=instructions.value_columns,
            var_name=instructions.variable_name,
            value_name=instructions.value_name
        )

        # Clean up
        unpivoted = unpivoted.dropna(subset=[instructions.value_name])
        unpivoted = unpivoted.reset_index(drop=True)

        return unpivoted

# 3. Configure in step
@step_definition(
    result_class=UnpivotInstructions,
    default_transformations=[UnpivotTransformation],
)
class UnpivotDetectionStep(LLMStep):
    """Detects unpivot structure and applies transformation."""
    pass

# Usage in pipeline
class MyPipeline(PipelineConfig):
    registry = MyRegistry
    strategies = [MyStrategy]
    steps = [UnpivotDetectionStep]

# Execute
pipeline = MyPipeline(context={'df': input_df})
pipeline.execute()

# Access transformed data
transformed_df = pipeline.get_current_data()
```

## Method Detection Priority Table

| Priority | Condition | Action | Example |
|----------|-----------|--------|---------|
| 1 | `default()` method exists | Use `default()` | Always called |
| 2 | Exactly one custom method | Use that method | `unpivot()` auto-detected |
| 3 | No custom methods | Passthrough | Return data unchanged |
| 4 | Multiple methods, no default | Error | Must add `default()` |

**CRITICAL CORRECTION:** Transformation does NOT check strategy name. Only extraction has Priority 2 (strategy-specific routing). Transformation routing: default → single → passthrough → error.

## See Also

- [PipelineExtraction API Reference](extraction.md) - Data extraction to models
- [PipelineConfig API Reference](pipeline.md) - Access pipeline state
- [LLMStep API Reference](step.md) - Step definitions
- [Architecture: Design Patterns](../architecture/patterns.md) - Smart method detection pattern
