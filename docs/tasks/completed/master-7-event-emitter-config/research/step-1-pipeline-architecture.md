# Research Step 1: PipelineConfig Architecture

## PipelineConfig Class Overview

**File:** `llm_pipeline/pipeline.py` (line 73)
**Base:** `ABC` (not Pydantic)
**Exported via:** `llm_pipeline/__init__.py`

### Class-level Attributes (ClassVar)
```python
REGISTRY: ClassVar[Type["PipelineDatabaseRegistry"]] = None
STRATEGIES: ClassVar[Type["PipelineStrategies"]] = None
```

Set via `__init_subclass__` metaclass hook (line 96) using class definition kwargs:
```python
class MyPipeline(PipelineConfig, registry=MyRegistry, strategies=MyStrategies):
    pass
```

### __init__ Signature (lines 127-134)
```python
def __init__(
    self,
    strategies: Optional[List["PipelineStrategy"]] = None,
    session: Optional[Session] = None,
    engine: Optional[Engine] = None,
    provider: Optional["LLMProvider"] = None,
    variable_resolver: Optional["VariableResolver"] = None,
):
```

All parameters are Optional with None defaults. Every caller uses keyword arguments exclusively.

### Instance Attributes Set in __init__
| Attribute | Type | Line | Pattern |
|---|---|---|---|
| `self._provider` | Optional[LLMProvider] | 148 | Private, DI |
| `self._variable_resolver` | Optional[VariableResolver] | 149 | Private, DI |
| `self._strategies` | List[PipelineStrategy] | 163 | Private |
| `self._instructions` | StepKeyDict | 166 | Private |
| `self._context` | Dict[str, Any] | 167 | Private |
| `self.data` | StepKeyDict | 170 | Public |
| `self.extractions` | Dict[...] | 171 | Public |
| `self._step_order` | Dict[Type, int] | 174 | Private, execution tracking |
| `self._model_extraction_step` | Dict | 175 | Private |
| `self._step_data_transformations` | Dict | 176 | Private |
| `self._executed_steps` | set | 177 | Private |
| `self._current_step` | Optional[Type] | 178 | Private |
| `self._current_extraction` | Optional[Type] | 179 | Private |
| `self.run_id` | str | 185 | Public |
| `self._owns_session` | bool | 189/196 | Private |
| `self._real_session` | Session | 190/197 | Private |
| `self.session` | ReadOnlySession | 199 | Public |

**DI params pattern:** `self._provider` and `self._variable_resolver` are stored immediately at lines 148-149 before any validation. The new `self._event_emitter` should follow the same pattern.

### TYPE_CHECKING Import Pattern (lines 35-40)
```python
if TYPE_CHECKING:
    from llm_pipeline.strategy import PipelineStrategy, PipelineStrategies
    from llm_pipeline.registry import PipelineDatabaseRegistry
    from llm_pipeline.state import PipelineStepState
    from llm_pipeline.llm.provider import LLMProvider
    from llm_pipeline.prompts.variables import VariableResolver
```
Type annotations in `__init__` use string form: `"LLMProvider"`, `"VariableResolver"`.

## PipelineEventEmitter (Upstream Task 2 - Done)

**File:** `llm_pipeline/events/emitter.py`
**Type:** `@runtime_checkable Protocol` with single `emit(event: PipelineEvent) -> None` method
**Import path:** `from llm_pipeline.events.emitter import PipelineEventEmitter`
**Also available via:** `from llm_pipeline.events import PipelineEventEmitter`

No deviations from task 2 plan. CompositeEmitter also available at same paths.

### PipelineEvent Base (events/types.py)
- `@dataclass(frozen=True, slots=True)` with auto-registration via `__init_subclass__`
- Fields: `run_id: str`, `pipeline_name: str`, `timestamp: datetime`
- Has `to_dict()` / `to_json()` serialization
- Subclasses include all lifecycle, step, cache, LLM call, consensus, transformation, extraction, state events

## All PipelineConfig Instantiation Sites

### In tests/test_pipeline.py (only instantiation file)
All use keyword arguments:
```python
TestPipeline(session=..., provider=MockProvider())          # line 310
TestPipeline(provider=MockProvider())                        # line 326
TestPipeline(session=session, provider=MockProvider())       # line 332
TestPipeline(engine=engine, provider=MockProvider())         # line 337
TestPipeline(session=session, provider=None)                 # line 342
TestPipeline(session=seeded_session, provider=provider)      # lines 357, 389, 408
```

No positional argument usage anywhere. Adding `event_emitter=None` default is fully backwards-compatible.

## Implementation Plan (Task 7 Spec)

### 1. Import (TYPE_CHECKING guard)
Add to the existing TYPE_CHECKING block at line 35:
```python
from llm_pipeline.events.emitter import PipelineEventEmitter
```

### 2. __init__ Parameter
Add after `variable_resolver` (last current param, line 133):
```python
event_emitter: Optional["PipelineEventEmitter"] = None,
```

### 3. Storage
At line 149 (after `self._variable_resolver`):
```python
self._event_emitter = event_emitter
```

### 4. Helper Method
Add `_emit` method (protected, single underscore, matches codebase convention):
```python
def _emit(self, event: "PipelineEvent") -> None:
    if self._event_emitter is not None:
        self._event_emitter.emit(event)
```

Placement: After `__init__` and before `instructions` property (between lines 199 and 201).

### 5. Zero Overhead
- When `event_emitter is None`: `_emit()` is a single `is not None` check, returns immediately
- Event objects must NOT be constructed before calling `_emit()` -- callers (task 8) should construct inside an `if self._event_emitter:` guard
- The `_emit()` helper is for convenience when event is already constructed

### 6. Docstring Update
Add to `__init__` Args docstring:
```
event_emitter: Optional PipelineEventEmitter for receiving pipeline events.
    None means no events emitted (zero overhead).
```

## Downstream Context (Task 8 - OUT OF SCOPE)

Task 8 will use `self._event_emitter` and `self._emit()` to emit PipelineStarted, PipelineCompleted, PipelineError in `execute()`. Task 7 only provides the plumbing; task 8 does the wiring.

## PipelineEvent Import for _emit Type Hint

The `_emit` method type-hints its parameter as `PipelineEvent`. This import also goes under TYPE_CHECKING:
```python
from llm_pipeline.events.types import PipelineEvent
```
