# Research: Pydantic v2 Input Schema Patterns for PipelineInputData

## 1. Pydantic v2 BaseModel as Schema Declaration Base Class

### Pattern: Minimal Abstract Base

The established codebase pattern (see `PipelineContext` in `context.py`) uses a minimal BaseModel base with `pass` body. Subclasses declare fields.

```python
# context.py (existing)
class PipelineContext(BaseModel):
    pass

# Proposed -- same pattern
class PipelineInputData(BaseModel):
    """Base class for declaring pipeline input schemas for UI form generation."""
    pass
```

Subclasses declare typed fields with full Pydantic v2 annotation support:

```python
class MyPipelineInput(PipelineInputData):
    document_text: str
    processing_mode: Literal['fast', 'accurate'] = 'fast'
    options: Optional[ProcessingOptions] = None
```

### Why BaseModel (not dataclass or TypedDict)

- `model_json_schema()` -- generates JSON Schema for UI form rendering
- `model_validate()` -- validates arbitrary dicts at runtime with detailed errors
- `model_dump()` / `model_dump_json()` -- serialization
- Full Field() metadata support (title, description, examples, json_schema_extra)
- Nested model support for complex input structures
- Consistent with all other base classes in llm-pipeline (PipelineContext, instruction models, etc.)

---

## 2. model_json_schema() for UI Form Generation

### Basic Schema Generation

```python
class ShippingInput(PipelineInputData):
    origin: str = Field(title="Origin City", description="Shipment origin")
    destination: str = Field(title="Destination City")
    weight_kg: float = Field(gt=0, title="Weight (kg)")
    service_level: Literal['express', 'standard', 'economy'] = 'standard'
    fragile: bool = False

schema = ShippingInput.model_json_schema()
```

Produces:

```json
{
  "title": "ShippingInput",
  "type": "object",
  "properties": {
    "origin": {"title": "Origin City", "description": "Shipment origin", "type": "string"},
    "destination": {"title": "Destination City", "type": "string"},
    "weight_kg": {"title": "Weight (kg)", "type": "number", "exclusiveMinimum": 0},
    "service_level": {
      "title": "Service Level",
      "enum": ["express", "standard", "economy"],
      "default": "standard",
      "type": "string"
    },
    "fragile": {"title": "Fragile", "default": false, "type": "boolean"}
  },
  "required": ["origin", "destination", "weight_kg"]
}
```

### Field Metadata -> UI Hints

| Pydantic Field Param | JSON Schema Output | UI Form Usage |
|---|---|---|
| `title="Label"` | `"title": "Label"` | Form field label |
| `description="Help"` | `"description": "Help"` | Help text / tooltip |
| `default=value` | `"default": value` | Pre-filled value |
| `examples=[...]` | `"examples": [...]` | Placeholder / example text |
| `Literal['a','b']` | `"enum": ["a","b"]` | Dropdown / select |
| `Optional[T]` | nullable in schema | Field not required |
| `gt=0, le=100` | `"exclusiveMinimum": 0, "maximum": 100` | Input validation hints |
| `min_length=1` | `"minLength": 1` | Required text indicator |
| `max_length=500` | `"maxLength": 500` | Character limit |
| `pattern=r"..."` | `"pattern": "..."` | Regex validation |

### Custom UI Hints via json_schema_extra

For UI-specific metadata not covered by standard JSON Schema:

```python
class MyInput(PipelineInputData):
    file_content: str = Field(
        json_schema_extra={"x-ui-widget": "textarea", "x-ui-rows": 10}
    )
    priority: int = Field(
        ge=1, le=5,
        json_schema_extra={"x-ui-widget": "slider"}
    )
```

Or at model level via `model_config`:

```python
class MyInput(PipelineInputData):
    model_config = ConfigDict(
        json_schema_extra={"x-ui-form-layout": "two-column"}
    )
```

### Type -> Widget Mapping (for UI consumers)

| Python Type | JSON Schema Type | Suggested Widget |
|---|---|---|
| `str` | `string` | Text input |
| `int` | `integer` | Number input |
| `float` | `number` | Number input (decimal) |
| `bool` | `boolean` | Checkbox / toggle |
| `Literal[...]` | `string` + `enum` | Select / dropdown |
| `Enum` | `string` + `enum` | Select / dropdown |
| `Optional[T]` | nullable | Optional field |
| `List[T]` | `array` | Multi-input / tags |
| `BaseModel` (nested) | `object` + `$defs` | Nested form group |
| `date` / `datetime` | `string` + `format` | Date picker |

### Nested Models and $defs

Pydantic v2 handles nested models via `$defs` (formerly `definitions`):

```python
class Address(BaseModel):
    street: str
    city: str
    country: str = "US"

class OrderInput(PipelineInputData):
    customer_name: str
    shipping_address: Address
    billing_address: Optional[Address] = None
```

Schema uses `$ref` and `$defs` for nested types, which UI frameworks can render as grouped sections.

---

## 3. ClassVar Usage: INPUT_DATA on PipelineConfig

### Existing ClassVar Pattern in Codebase

```python
# pipeline.py (current)
class PipelineConfig(ABC):
    REGISTRY: ClassVar[Type["PipelineDatabaseRegistry"]] = None
    STRATEGIES: ClassVar[Type["PipelineStrategies"]] = None
```

Both use `__init_subclass__` with keyword params and enforce naming conventions. However, INPUT_DATA differs:

| Aspect | REGISTRY/STRATEGIES | INPUT_DATA |
|---|---|---|
| Required? | Yes (validated in __init__) | No (optional) |
| Naming convention? | Strict ({Prefix}Registry, {Prefix}Strategies) | Not needed |
| Set via | `__init_subclass__(registry=, strategies=)` | Direct ClassVar override |

### Recommended Pattern

Since INPUT_DATA is optional and doesn't need naming validation, a plain ClassVar with Optional type is simplest:

```python
class PipelineConfig(ABC):
    REGISTRY: ClassVar[Type["PipelineDatabaseRegistry"]] = None
    STRATEGIES: ClassVar[Type["PipelineStrategies"]] = None
    INPUT_DATA: ClassVar[Optional[Type["PipelineInputData"]]] = None  # NEW
```

Usage by pipeline authors:

```python
class ShippingPipeline(PipelineConfig,
                       registry=ShippingRegistry,
                       strategies=ShippingStrategies):
    INPUT_DATA = ShippingInput  # Simple override
```

Alternative: `__init_subclass__` keyword param (not recommended for this case):

```python
# Would work but adds complexity for an optional feature
class ShippingPipeline(PipelineConfig,
                       registry=ShippingRegistry,
                       strategies=ShippingStrategies,
                       input_data=ShippingInput):  # keyword param
    pass
```

The plain ClassVar approach is simpler and consistent with how optional class-level config should work. The `__init_subclass__` pattern should be reserved for required config with validation.

### Type Import Considerations

Since PipelineInputData will be in `context.py` and PipelineConfig is in `pipeline.py`, use TYPE_CHECKING guard:

```python
# pipeline.py
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from llm_pipeline.context import PipelineInputData
```

---

## 4. Runtime Validation Patterns

### model_validate() for Dict Input

```python
# In execute() or a validation helper
input_cls = self.__class__.INPUT_DATA
if input_cls is not None and input_data is not None:
    try:
        validated = input_cls.model_validate(input_data)
    except ValidationError as e:
        raise ValueError(f"Input validation failed: {e}") from e
```

Key `model_validate()` behaviors:
- Accepts `dict`, `BaseModel`, or arbitrary objects (with `from_attributes=True`)
- Returns validated model instance
- Raises `pydantic.ValidationError` with per-field errors
- Supports `strict=True` for no type coercion
- Supports `context=` for cross-field validation

### ValidationError Details

Pydantic v2 ValidationError provides structured error info useful for UI feedback:

```python
try:
    validated = ShippingInput.model_validate({"weight_kg": -5})
except ValidationError as e:
    for error in e.errors():
        # {'type': 'greater_than', 'loc': ('weight_kg',), 'msg': '...', 'input': -5}
        field_path = error['loc']
        message = error['msg']
```

### Where Validation Fits in execute()

Looking at `execute()` flow (pipeline.py L424-817):

1. Parameter setup (L432-466)
2. Pipeline run record creation (L471-478)
3. Event emission (L480-484)
4. Step loop (L489-771)

Input validation should happen at step 1, before pipeline run creation. If validation fails, no run record should be created. Pattern:

```python
def execute(self, data=None, initial_context=None, input_data=None, ...):
    # Validate input_data against schema FIRST
    if self.__class__.INPUT_DATA is not None and input_data is not None:
        validated = self.__class__.INPUT_DATA.model_validate(input_data)
        # Merge validated data into context or use as data
```

### model_validate_json() for JSON String Input

For API/WebSocket scenarios where input arrives as JSON string:

```python
validated = ShippingInput.model_validate_json(json_string)
```

---

## 5. Best Practices for Extensible Base Classes

### Keep Base Class Minimal

```python
class PipelineInputData(BaseModel):
    """Base for pipeline input schema declarations. Subclass to define fields."""
    pass
```

Do NOT add:
- Default fields (pollutes all subclass schemas)
- Validators (constrains subclass freedom)
- Custom `model_config` (subclasses should control their own config)

### Allow but Don't Require model_config

Subclasses can customize:

```python
class MyInput(PipelineInputData):
    model_config = ConfigDict(
        title="My Pipeline Input",
        json_schema_extra={"x-ui-layout": "wizard"},
        str_strip_whitespace=True,
    )
    name: str
```

### Support Validators in Subclasses

Subclasses can use all Pydantic v2 validator patterns:

```python
class MyInput(PipelineInputData):
    start_date: date
    end_date: date

    @model_validator(mode='after')
    def validate_date_range(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be after start_date")
        return self
```

### Discriminated Unions for Complex Inputs

For pipelines with mode-dependent input shapes:

```python
class FastModeInput(PipelineInputData):
    mode: Literal['fast'] = 'fast'
    batch_size: int = 100

class AccurateModeInput(PipelineInputData):
    mode: Literal['accurate'] = 'accurate'
    confidence_threshold: float = 0.95

# Union type for schema generation
PipelineInput = Annotated[
    Union[FastModeInput, AccurateModeInput],
    Discriminator('mode')
]
```

---

## 6. Integration Points in Existing Codebase

### PipelineIntrospector (introspection.py)

`_get_schema()` already handles BaseModel subclasses via `model_json_schema()`. The `get_metadata()` method needs to include INPUT_DATA schema:

```python
# In get_metadata():
input_data_cls = getattr(self._pipeline_cls, "INPUT_DATA", None)
metadata["input_data_schema"] = self._get_schema(input_data_cls)
```

### UI Routes (ui/routes/pipelines.py)

Already prepared:
- `PipelineListItem.has_input_schema: bool = False` -- set based on INPUT_DATA presence
- `PipelineMetadata.pipeline_input_schema: Optional[Any] = None` -- populated from introspection

### UI Routes (ui/routes/runs.py)

- `TriggerRunRequest.input_data: Optional[Dict[str, Any]]` -- already exists
- `trigger_run()` passes `input_data` to factory and `initial_context` -- validation should happen here or in execute()

### Exports (__init__.py)

Add `PipelineInputData` to imports and `__all__`.

---

## 7. Summary of Recommended Approach

1. **Base class**: `PipelineInputData(BaseModel)` with `pass` body in `context.py`
2. **ClassVar**: `INPUT_DATA: ClassVar[Optional[Type["PipelineInputData"]]] = None` on PipelineConfig (plain override, no __init_subclass__ keyword)
3. **Schema generation**: `model_json_schema()` (already handled by PipelineIntrospector._get_schema)
4. **Runtime validation**: `model_validate(input_dict)` in execute() before pipeline run creation
5. **Error handling**: Catch `ValidationError`, wrap in clear error with field-level detail
6. **Introspection**: Add `input_data_schema` to PipelineIntrospector.get_metadata()
7. **UI integration**: Populate existing `pipeline_input_schema` and `has_input_schema` fields
8. **Export**: Add to `__init__.py` imports and `__all__`
