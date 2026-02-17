# Task 14 Research: Event System for Extraction/Transformation Events

## Event Infrastructure Overview

### Event Type Hierarchy
- `PipelineEvent` (base, frozen dataclass with slots) - fields: run_id, pipeline_name, timestamp, event_type (derived)
- `StepScopedEvent(PipelineEvent)` - adds: step_name (str | None), has `_skip_registry = True`
- All concrete events inherit from StepScopedEvent or PipelineEvent

### Auto-Registration
- `__init_subclass__` on PipelineEvent auto-registers subclasses in `_EVENT_REGISTRY`
- `_derive_event_type()` converts CamelCase to snake_case (e.g. ExtractionStarting -> extraction_starting)
- `__post_init__` sets event_type via `object.__setattr__` (bypasses frozen)

### Emitter Architecture
- `PipelineEventEmitter` - runtime_checkable Protocol with `emit(event) -> None`
- `CompositeEmitter` - dispatches to multiple handlers, isolates per-handler errors
- Pipeline stores emitter as `self._event_emitter` (Optional), `_emit()` guards with None check
- Handlers: LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler

### Event Dataclass Pattern
All events use: `@dataclass(frozen=True, slots=True, kw_only=True)` with `EVENT_CATEGORY: ClassVar[str]`.

## Existing Event Types (Already Defined)

The following extraction/transformation event types **already exist** in `llm_pipeline/events/types.py`:

### Extraction Events (lines 487-522)
```python
@dataclass(frozen=True, slots=True, kw_only=True)
class ExtractionStarting(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_EXTRACTION
    extraction_class: str
    model_class: str

@dataclass(frozen=True, slots=True, kw_only=True)
class ExtractionCompleted(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_EXTRACTION
    extraction_class: str
    model_class: str
    instance_count: int

@dataclass(frozen=True, slots=True, kw_only=True)
class ExtractionError(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_EXTRACTION
    extraction_class: str
    error_type: str
    error_message: str
    validation_errors: list[str] = field(default_factory=list)
```

### Transformation Events (lines 465-482)
```python
@dataclass(frozen=True, slots=True, kw_only=True)
class TransformationStarting(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_TRANSFORMATION
    transformation_class: str

@dataclass(frozen=True, slots=True, kw_only=True)
class TransformationCompleted(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_TRANSFORMATION
    data_key: str
    execution_time_ms: float
```

### Export Status
All 5 events already exported in both `events/types.py` `__all__` and `events/__init__.py` `__all__`. Category constants `CATEGORY_EXTRACTION` and `CATEGORY_TRANSFORMATION` also defined.

## Emission Sites - Where to Add Code

### 1. Extraction Events in `step.py` extract_data() (lines 315-332)

Current code:
```python
def extract_data(self, instructions: List[Any]) -> None:
    extraction_classes = getattr(self, '_extractions', [])
    for extraction_class in extraction_classes:
        extraction = extraction_class(self.pipeline)
        self.pipeline._current_extraction = extraction_class
        try:
            instances = extraction.extract(instructions)
            self.store_extractions(extraction.MODEL, instances)
            for instance in instances:
                self.pipeline._real_session.add(instance)
            self.pipeline._real_session.flush()
        finally:
            self.pipeline._current_extraction = None
```

Changes needed:
- **ExtractionStarting**: Emit after `self.pipeline._current_extraction = extraction_class` (before try block)
- **ExtractionCompleted**: Emit after `self.pipeline._real_session.flush()` (inside try, after flush)
- **ExtractionError**: Add `except Exception as e:` block before `finally:`, emit then re-raise
- Access pattern: `self.pipeline._emit(ExtractionStarting(...))` guarded by `if self.pipeline._event_emitter:`
- Field values: `extraction_class=extraction_class.__name__`, `model_class=extraction.MODEL.__name__`, `step_name=self.step_name`

### 2. Transformation Events in `pipeline.py` (TWO sites)

#### Site A: Cached path (lines 576-580)
```python
if hasattr(step, "_transformation") and step._transformation:
    transformation = step._transformation(self)
    current_data = self.get_data("current")
    transformed_data = transformation.transform(current_data, instructions)
    self.set_data(transformed_data, step_name=step.step_name)
```

#### Site B: Fresh execution path (lines 652-656)
```python
if hasattr(step, "_transformation") and step._transformation:
    transformation = step._transformation(self)
    current_data = self.get_data("current")
    transformed_data = transformation.transform(current_data, instructions)
    self.set_data(transformed_data, step_name=step.step_name)
```

Changes needed (both sites):
- **TransformationStarting**: Emit before `transformation.transform()` call
- **TransformationCompleted**: Emit after `self.set_data()` call with timing
- Need `datetime.now(timezone.utc)` before transform for timing
- Field values: `transformation_class=step._transformation.__name__`, `data_key=step.step_name`
- Guard: `if self._event_emitter:`

## Emission Pattern (from consensus events)

```python
# In pipeline.py:
if self._event_emitter:
    self._emit(EventClass(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
        step_name=current_step_name,
        # event-specific fields...
    ))

# In step.py (accessing through pipeline):
if self.pipeline._event_emitter:
    self.pipeline._emit(EventClass(
        run_id=self.pipeline.run_id,
        pipeline_name=self.pipeline.pipeline_name,
        step_name=self.step_name,
        # event-specific fields...
    ))
```

## Imports Needed

### step.py
```python
from llm_pipeline.events.types import ExtractionStarting, ExtractionCompleted, ExtractionError
```

### pipeline.py (additional imports)
```python
from llm_pipeline.events.types import TransformationStarting, TransformationCompleted
```

## Test Infrastructure

- Tests in `tests/events/` folder
- `conftest.py` has: MockProvider, test domain models (SimpleInstructions, Item, ItemExtraction, etc.)
- ExtractionPipeline with ItemDetectionStep + ItemExtraction already exists in conftest
- InMemoryEventHandler captures events as dicts via `.get_events()`
- Test pattern: run pipeline, get events, filter by event_type, assert fields/ordering
- Extraction tests need ExtractionPipeline; transformation tests need a pipeline with a transformation step (not yet in conftest)

## Key Observations

1. **No code changes to event types** - all 5 event dataclasses already defined
2. **step.py needs error handling** - extract_data() has try/finally but no except; ExtractionError requires adding except block
3. **Two transformation sites** - identical code in cached vs fresh paths, both need events
4. **Handler log levels** - CATEGORY_EXTRACTION and CATEGORY_TRANSFORMATION both at DEBUG level in DEFAULT_LEVEL_MAP (handlers.py line 44-45)
5. **Zero-overhead pattern** - all emission guarded by `if _event_emitter:` check
