# Research: Codebase Architecture for PipelineInputData

## 1. Current Module Layout

### context.py (37 lines)
- `PipelineContext(BaseModel)` -- minimal base with `pass` body
- Pattern: subclasses declare typed fields (e.g., `TableTypeDetectionContext`)
- Single import: `from pydantic import BaseModel`
- PipelineInputData fits here naturally -- same module, same pattern

### pipeline.py (1150 lines)
- `PipelineConfig(ABC)` -- abstract orchestrator
- ClassVar pattern: `REGISTRY: ClassVar[Type[...]] = None`, `STRATEGIES: ClassVar[Type[...]] = None`
- `__init_subclass__` handles `registry=` and `strategies=` keyword params with naming validation
- `execute()` at L424-817, signature: `(data, initial_context, use_cache, consensus_polling)`
- `_validate_and_merge_context()` validates PipelineContext instances from steps
- StepKeyDict helper for flexible key lookup

### __init__.py (78 lines)
- 36 exports in `__all__`
- Groups: Core, Strategy, Data handling, State, Events, Types, DB, Session, Introspection
- PipelineContext already exported

### pyproject.toml
- `pydantic>=2.0` confirmed
- Python 3.11+

---

## 2. Existing ClassVar Patterns

| ClassVar | Module | Required? | Set via | Naming enforced? |
|---|---|---|---|---|
| `REGISTRY` | pipeline.py | Yes (validated in `__init__`) | `__init_subclass__(registry=)` | Yes: `{Prefix}Registry` |
| `STRATEGIES` | pipeline.py | Yes (validated in `__init__`) | `__init_subclass__(strategies=)` | Yes: `{Prefix}Strategies` |
| `MODEL` | extraction.py | Yes (concrete only) | `__init_subclass__(model=)` | No |
| `INPUT_TYPE` / `OUTPUT_TYPE` | transformation.py | Yes (concrete only) | `__init_subclass__(input_type=, output_type=)` | No |
| `MODELS` | registry.py | Yes (concrete only) | `__init_subclass__(models=)` | No |
| `STRATEGIES` | strategy.py | Yes (concrete only) | `__init_subclass__(strategies=)` | No |

Key distinction: All current ClassVars are **required** for concrete subclasses. INPUT_DATA is **optional** (pipelines may or may not support UI-initiated runs). Therefore plain ClassVar override is correct -- no `__init_subclass__` keyword param needed.

---

## 3. execute() Flow Analysis

```
L424  def execute(self, data, initial_context, use_cache, consensus_polling):
L432    if initial_context is None: initial_context = {}
L439    provider validation
L444    strategies validation
L464    self._context = initial_context.copy()
L465    self.data = {"raw": data, "sanitized": self.sanitize(data)}
L466    self.extractions = {}
L468    start_time = ...
L471-478  PipelineRun record creation + flush
L480-484  PipelineStarted event
L486-771  Step loop
L781-786  PipelineRun completion
L799-817  Exception handler
```

**Input validation insertion point**: Between L444 (strategies validation) and L464 (context initialization). Before PipelineRun record creation -- if validation fails, no run should be created.

---

## 4. UI Integration Points (Already Prepared)

### ui/routes/pipelines.py
- `PipelineListItem.has_input_schema: bool = False` -- L26
- `PipelineMetadata.pipeline_input_schema: Optional[Any] = None` -- L62
- `list_pipelines()` currently derives `has_input_schema` from step instruction schemas (L98-102) -- should be updated to check `INPUT_DATA`
- `get_pipeline()` returns `PipelineMetadata(**metadata)` -- needs `input_data_schema` from introspector

### ui/routes/runs.py
- `TriggerRunRequest.input_data: Optional[Dict[str, Any]] = None` -- L63
- `trigger_run()` at L184-247 passes `input_data` to factory and `initial_context`:
  ```python
  pipeline = factory(run_id=..., engine=..., event_emitter=..., input_data=body.input_data or {})
  pipeline.execute(data=None, initial_context=body.input_data or {})
  ```

### introspection.py
- `_get_schema(cls)` already handles `BaseModel -> model_json_schema()` (L82-95)
- `get_metadata()` returns dict with `pipeline_name`, `registry_models`, `strategies`, `execution_order`
- Needs: `input_data_schema` key added from `getattr(pipeline_cls, "INPUT_DATA", None)`

---

## 5. Integration Map: What Changes Where

| File | Change | Type |
|---|---|---|
| `context.py` | Add `PipelineInputData(BaseModel): pass` | New class |
| `pipeline.py` | Add `INPUT_DATA: ClassVar[Optional[Type["PipelineInputData"]]] = None` to PipelineConfig | ClassVar |
| `pipeline.py` | Add input validation block in `execute()` before L464 | Validation logic |
| `introspection.py` | Add `input_data_schema` to `get_metadata()` output | Schema extraction |
| `pipelines.py` (UI) | Update `has_input_schema` to check `INPUT_DATA`, populate `pipeline_input_schema` | Route fix |
| `__init__.py` | Add `PipelineInputData` to imports and `__all__` | Export |

---

## 6. Validation Strategy in execute()

Proposed insertion (pseudocode):

```python
# After strategies validation, before context init
input_data_cls = self.__class__.INPUT_DATA
if input_data_cls is not None and initial_context:
    try:
        validated = input_data_cls.model_validate(initial_context)
        # Use validated dict as initial_context
        initial_context = validated.model_dump()
    except ValidationError as e:
        raise ValueError(f"Pipeline input validation failed:\n{e}") from e
```

Considerations:
- Validates initial_context dict against INPUT_DATA schema
- Replaces initial_context with validated+coerced dict (Pydantic handles defaults, type coercion)
- Fails fast before PipelineRun creation
- ValidationError wrapping provides clean error chain

---

## 7. Naming Convention Assessment

Following existing patterns:
- Class: `PipelineInputData` (consistent with `PipelineContext`, `PipelineConfig`, `PipelineExtraction`)
- ClassVar: `INPUT_DATA` (UPPER_SNAKE, consistent with `REGISTRY`, `STRATEGIES`, `MODEL`)
- File location: `context.py` (logically grouped with PipelineContext -- both are "input shape" declarations)

---

## 8. Dependencies and Import Order

### context.py (updated)
```python
from pydantic import BaseModel

class PipelineContext(BaseModel): ...
class PipelineInputData(BaseModel): ...
```

### pipeline.py (updated imports)
```python
# Already imports from typing: ClassVar, Type, Optional
# TYPE_CHECKING block already imports from context -- add PipelineInputData
if TYPE_CHECKING:
    from llm_pipeline.context import PipelineInputData
```

Runtime import in execute() for validation:
```python
from pydantic import ValidationError  # already available (pydantic is a dep)
```

No new dependencies needed. Pydantic v2 is already a project dependency.

---

## 9. Test Patterns Observed

- `test_introspection.py`: Tests class-level metadata extraction without DB/LLM
- Defines minimal pipeline domain classes (WidgetPipeline pattern)
- Uses `PipelineIntrospector._cache.clear()` fixture
- Test groups: top-level metadata, strategies, steps, extractions, execution order, caching, broken strategies, transformations

For PipelineInputData tests:
- Subclassing test (schema generation from subclass)
- JSON schema output test (model_json_schema())
- Validation of valid/invalid dicts (model_validate())
- INPUT_DATA ClassVar introspection
- Execute() validation integration (requires DB fixture from test_pipeline.py patterns)
