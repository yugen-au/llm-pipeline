# Step 2: Pydantic Schema Research

## Overview

Research into how Pydantic v2 models expose JSON Schema for frontend form generation, what the backend API currently returns, and what gaps exist.

---

## 1. PipelineInputData -- Current State

**PipelineInputData does not exist yet.** It is defined in task 43 (pending, depends only on task 18 which is done). The PRD (FR-PI-004, FR-FE-008, US-016) describes it as:

- New Pydantic BaseModel subclass analogous to `PipelineContext`
- Lives in `llm_pipeline/context.py` (or new file)
- Pipelines declare `INPUT_DATA: ClassVar[Type[PipelineInputData]]` on `PipelineConfig`
- UI generates form fields from schema; falls back to JSON editor when undefined
- Task 43 details show planned code:

```python
class PipelineInputData(BaseModel):
    '''Base class for pipeline input schemas used for UI form generation.'''
    pass

# Example subclass:
class MyPipelineInput(PipelineInputData):
    document_text: str
    processing_mode: Literal['fast', 'accurate'] = 'fast'
    options: Optional[ProcessingOptions] = None
```

### Implication for Task 38

Task 38 references `pipelineData?.input_schema` but:
- `PipelineMetadata` (backend response model) has NO `input_schema` field
- `PipelineMetadata` TypeScript interface has NO `input_schema` field
- `PipelineIntrospector.get_metadata()` does NOT extract pipeline-level input schema
- The `has_input_schema` boolean on `PipelineListItem` is derived from step-level `instructions_schema` presence, not a pipeline-level input schema

---

## 2. What the Backend API Currently Returns

### GET /api/pipelines (list)

```json
{
  "pipelines": [
    {
      "name": "widget",
      "strategy_count": 1,
      "step_count": 1,
      "has_input_schema": true,
      "registry_model_count": 1,
      "error": null
    }
  ]
}
```

`has_input_schema` is `true` when ANY step has a non-null `instructions_schema`. This is step-level, not pipeline-level input data.

### GET /api/pipelines/{name} (detail)

Returns `PipelineMetadata`:

```json
{
  "pipeline_name": "widget",
  "registry_models": ["WidgetModel"],
  "strategies": [{
    "name": "primary",
    "display_name": "PrimaryStrategy",
    "class_name": "PrimaryStrategy",
    "steps": [{
      "step_name": "widget_detection",
      "class_name": "WidgetDetectionStep",
      "system_key": "widget.system",
      "user_key": "widget.user",
      "instructions_class": "WidgetDetectionInstructions",
      "instructions_schema": { ... },  // <-- Pydantic JSON Schema
      "context_class": "WidgetDetectionContext",
      "context_schema": { ... },
      "extractions": [...],
      "transformation": null,
      "action_after": null
    }]
  }],
  "execution_order": ["widget_detection"]
}
```

**No top-level `input_schema` field exists.** The only schema data is per-step `instructions_schema` and `context_schema`.

---

## 3. Pydantic v2 model_json_schema() Output Patterns

All schemas follow JSON Schema draft 2020-12. Key patterns:

### 3.1 Simple Types

```python
class SimpleInput(BaseModel):
    document_text: str
    processing_mode: Literal['fast', 'accurate'] = 'fast'
    max_tokens: int = Field(default=1000, ge=1, le=10000, description='Max tokens')
    verbose: bool = False
```

Produces:

```json
{
  "properties": {
    "document_text": { "title": "Document Text", "type": "string" },
    "processing_mode": {
      "default": "fast",
      "enum": ["fast", "accurate"],
      "title": "Processing Mode",
      "type": "string"
    },
    "max_tokens": {
      "default": 1000,
      "description": "Max tokens",
      "maximum": 10000,
      "minimum": 1,
      "title": "Max Tokens",
      "type": "integer"
    },
    "verbose": { "default": false, "title": "Verbose", "type": "boolean" }
  },
  "required": ["document_text"],
  "title": "SimpleInput",
  "type": "object"
}
```

### 3.2 Nested Models with Enum

```python
class Priority(str, Enum):
    LOW = 'low'; MEDIUM = 'medium'; HIGH = 'high'

class ProcessingOptions(BaseModel):
    priority: Priority = Priority.MEDIUM
    timeout_seconds: Optional[int] = None

class NestedInput(BaseModel):
    name: str = Field(description='Pipeline run name')
    options: ProcessingOptions = ProcessingOptions()
    tags: List[str] = []
```

Produces schema with `$defs` section and `$ref` pointers:

```json
{
  "$defs": {
    "Priority": { "enum": ["low","medium","high"], "title": "Priority", "type": "string" },
    "ProcessingOptions": {
      "properties": {
        "priority": { "$ref": "#/$defs/Priority", "default": "medium" },
        "timeout_seconds": {
          "anyOf": [{"type":"integer"}, {"type":"null"}],
          "default": null, "title": "Timeout Seconds"
        }
      },
      "title": "ProcessingOptions", "type": "object"
    }
  },
  "properties": {
    "name": { "description": "Pipeline run name", "title": "Name", "type": "string" },
    "options": { "$ref": "#/$defs/ProcessingOptions", "default": {"priority":"medium","timeout_seconds":null} },
    "tags": { "default": [], "items": {"type":"string"}, "title": "Tags", "type": "array" }
  },
  "required": ["name"],
  "title": "NestedInput", "type": "object"
}
```

### 3.3 Optional / Union Types (anyOf pattern)

```python
optional_field: Optional[int] = None
# -> "anyOf": [{"type":"integer"}, {"type":"null"}], "default": null

union_field: Union[str, int] = 'default'
# -> "anyOf": [{"type":"string"}, {"type":"integer"}], "default": "default"
```

### 3.4 Array of Objects

```python
items: List[SubItem] = []
# -> "items": {"$ref": "#/$defs/SubItem"}, "type": "array"
```

### 3.5 Dict/Freeform

```python
metadata: Dict[str, Any] = {}
# -> "additionalProperties": true, "type": "object"
```

---

## 4. Field Type -> Form Field Mapping

| JSON Schema Pattern | Form Widget | Detection Logic |
|---|---|---|
| `type: "string"` | Text input | Direct type check |
| `type: "string" + enum: [...]` | Select dropdown | Has `enum` array |
| `type: "integer"` | Number input (step=1) | Direct type check |
| `type: "number"` | Number input (step=any) | Direct type check |
| `type: "boolean"` | Checkbox / toggle | Direct type check |
| `type: "array" + items.type: "string"` | Repeatable text inputs | Array of primitives |
| `type: "array" + items.$ref` | Repeatable fieldsets | Array of objects |
| `$ref: "#/$defs/X"` | Nested fieldset | Resolve from $defs |
| `type: "object" + additionalProperties` | JSON editor | Freeform object |
| `anyOf: [{type:T}, {type:"null"}]` | Optional T field | Nullable pattern |
| `anyOf: [{type:A}, {type:B}]` | JSON editor fallback | Non-trivial union |

### Constraint Mapping

| Schema Constraint | Form Behavior |
|---|---|
| `required` (top-level array) | Mark field as required, prevent empty submit |
| `default` | Pre-fill field value |
| `description` | Help text / tooltip |
| `title` | Field label |
| `minimum` / `maximum` | Number input min/max attributes |
| `minLength` / `maxLength` | Text input constraints |
| `pattern` | Regex validation on input |

---

## 5. Existing Schema Utilities

### Backend: flatten_schema() (llm_pipeline/llm/schema.py)

Inlines all `$ref` pointers by resolving from `$defs`, removes `$defs` and `examples`. Already production-tested for LLM prompt formatting. Could be reused to pre-flatten schemas before serving to frontend.

### Backend: PipelineIntrospector._get_schema()

Calls `model_json_schema()` for Pydantic BaseModel subclasses, returns `{"type": ClassName}` for non-Pydantic types, returns None for None. Used for `instructions_schema` and `context_schema` per step.

---

## 6. LLMResultMixin (Instructions) Schema Shape

The existing `instructions_schema` exposed per-step uses `LLMResultMixin` subclasses. These always include inherited fields:

```json
{
  "properties": {
    "confidence_score": {
      "default": 0.95,
      "description": "Confidence in this analysis (0-1)",
      "maximum": 1.0, "minimum": 0.0,
      "title": "Confidence Score", "type": "number"
    },
    "notes": {
      "anyOf": [{"type":"string"}, {"type":"null"}],
      "default": null,
      "description": "General observations, reasoning, or additional context",
      "title": "Notes"
    },
    // ... subclass-specific fields
  },
  "required": ["widget_count", "category"],  // only subclass fields without defaults
  "title": "WidgetDetectionInstructions",
  "type": "object"
}
```

Note: `confidence_score` and `notes` always have defaults so they're never in `required`.

---

## 7. Gaps and Dependencies

### Missing for Task 38

1. **PipelineInputData class** (task 43) -- the base class for pipeline input schemas
2. **input_schema field on PipelineMetadata** -- neither the backend response model nor the introspector include it
3. **PipelineConfig.INPUT_DATA** -- the ClassVar linking a pipeline to its input schema
4. **Introspection update** -- PipelineIntrospector needs to extract INPUT_DATA schema
5. **API update** -- GET /api/pipelines/{name} needs to return input_schema
6. **TypeScript type update** -- PipelineMetadata interface needs input_schema field

### What CAN Be Built Without Task 43

- InputForm component structure and FormField components (schema -> form rendering logic)
- JSON editor fallback component
- $ref resolution / schema flattening utility (frontend-side)
- Form submission and validation logic
- All of the above coded against the EXPECTED schema shape (a standard JSON Schema object)

---

## 8. POST /api/runs -- Current Input Support

`TriggerRunRequest` currently only accepts `pipeline_name: str`. No `input_data` field. Task 38 or a related task would need to add:

```python
class TriggerRunRequest(BaseModel):
    pipeline_name: str
    input_data: Optional[dict] = None  # validated against PipelineInputData schema
```

And the frontend `TriggerRunRequest` TypeScript type would need updating:

```typescript
export interface TriggerRunRequest {
  pipeline_name: string
  input_data?: Record<string, unknown>
}
```

---

## 9. Recommended Approach (pending CEO input)

Given task 43 is pending, the InputForm can be built against the standard JSON Schema contract that Pydantic v2 always produces. The component needs:

1. Accept a `schema: Record<string, unknown> | null` prop
2. If null -> render JSON editor fallback
3. If present -> iterate `schema.properties`, check `schema.required`, render FormField per property
4. FormField resolves type from property schema (handling `$ref` via $defs lookup or pre-flattened schema)
5. Form state managed via React state, validated on submit, passed as `input_data` to POST /api/runs

The schema shape is deterministic from Pydantic v2 -- it won't change regardless of whether it comes from PipelineInputData or any other BaseModel subclass.
