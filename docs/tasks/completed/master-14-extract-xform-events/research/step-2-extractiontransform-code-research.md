# Step 2: Extraction/Transform Code Research

## Executive Summary

Mapped all extraction and transformation code paths for event emission insertion. 5 event types already defined in events/types.py. Extraction events go in step.py extract_data() (3 emission points per extraction class). Transformation events go in pipeline.py execute() at 2 identical blocks (cached path L576-580, fresh path L652-656). No ambiguities found.

## Extraction Code Path

### Source: llm_pipeline/step.py extract_data() (L315-332)

```python
def extract_data(self, instructions: List[Any]) -> None:
    extraction_classes = getattr(self, '_extractions', [])
    for extraction_class in extraction_classes:                    # L322
        extraction = extraction_class(self.pipeline)               # L323
        self.pipeline._current_extraction = extraction_class       # L324
        try:
            instances = extraction.extract(instructions)           # L326
            self.store_extractions(extraction.MODEL, instances)    # L327
            for instance in instances:                             # L328
                self.pipeline._real_session.add(instance)          # L329
            self.pipeline._real_session.flush()                    # L330
        finally:
            self.pipeline._current_extraction = None               # L332
```

### Insertion Points

| Event | Location | Guard Pattern |
|-------|----------|---------------|
| ExtractionStarting | After L324 (pipeline._current_extraction set), before L326 (extract call) | `if self.pipeline._event_emitter:` |
| ExtractionCompleted | After L330 (flush), before finally block | `if self.pipeline._event_emitter:` |
| ExtractionError | New except block between try and finally | `if self.pipeline._event_emitter:` |

### Required Code Change: Add except block

Current: try/finally (no except). Need try/except/finally:

```python
try:
    instances = extraction.extract(instructions)
    self.store_extractions(extraction.MODEL, instances)
    for instance in instances:
        self.pipeline._real_session.add(instance)
    self.pipeline._real_session.flush()
    # ExtractionCompleted here
except Exception as e:
    # ExtractionError here
    raise  # re-raise preserves existing behavior
finally:
    self.pipeline._current_extraction = None
```

### Data Available at Each Point

| Event | Field | Source |
|-------|-------|--------|
| ExtractionStarting.step_name | `self.step_name` | LLMStep.step_name property (L246-256) |
| ExtractionStarting.extraction_class | `extraction_class.__name__` | Loop variable (L322) |
| ExtractionStarting.model_class | `extraction_class.MODEL.__name__` | ClassVar on PipelineExtraction subclass |
| ExtractionStarting.run_id | `self.pipeline.run_id` | Set at pipeline init (L198) |
| ExtractionStarting.pipeline_name | `self.pipeline.pipeline_name` | PipelineConfig property (L234-243) |
| ExtractionCompleted.instance_count | `len(instances)` | Return value from extraction.extract() |
| ExtractionError.error_type | `type(e).__name__` | Caught exception |
| ExtractionError.error_message | `str(e)` | Caught exception |
| ExtractionError.validation_errors | Extract from Pydantic ValidationError if applicable | Optional enrichment |

### Import Requirement

step.py currently imports NO event types. Add direct import (following pipeline.py pattern):

```python
from llm_pipeline.events.types import (
    ExtractionStarting, ExtractionCompleted, ExtractionError,
)
```

### Callers of extract_data()

extract_data is called from pipeline.py execute() in TWO places:
1. **Partial cache fallback** (L596): `step.extract_data(instructions)` -- when CacheReconstruction finds 0 instances
2. **Fresh path** (L658): `step.extract_data(instructions)` -- normal execution

Both paths will benefit from extraction events. Cache reconstruction path uses `_reconstruct_extractions_from_cache` which already emits CacheReconstruction events.

## Transformation Code Path

### Source: llm_pipeline/pipeline.py execute() -- TWO identical blocks

**Cached path (L576-580):**
```python
if hasattr(step, "_transformation") and step._transformation:
    transformation = step._transformation(self)
    current_data = self.get_data("current")
    transformed_data = transformation.transform(current_data, instructions)
    self.set_data(transformed_data, step_name=step.step_name)
```

**Fresh path (L652-656):**
```python
if hasattr(step, "_transformation") and step._transformation:
    transformation = step._transformation(self)
    current_data = self.get_data("current")
    transformed_data = transformation.transform(current_data, instructions)
    self.set_data(transformed_data, step_name=step.step_name)
```

### Insertion Points (same pattern for BOTH blocks)

| Event | Location | Guard Pattern |
|-------|----------|---------------|
| TransformationStarting | After transformation instantiation, before transform() call | `if self._event_emitter:` |
| TransformationCompleted | After set_data(), with timing | `if self._event_emitter:` |

### Data Available at Each Point

| Event | Field | Source |
|-------|-------|--------|
| TransformationStarting.step_name | `step.step_name` | LLMStep.step_name property |
| TransformationStarting.transformation_class | `step._transformation.__name__` | Class reference on step instance (strategy.py:133) |
| TransformationStarting.run_id | `self.run_id` | Pipeline instance |
| TransformationStarting.pipeline_name | `self.pipeline_name` | Pipeline property |
| TransformationCompleted.data_key | `step.step_name` | Same key used in set_data() |
| TransformationCompleted.execution_time_ms | Calculated delta | Need to capture start time before transform() |

### Timing Capture

Need `datetime.now(timezone.utc)` before transform() call and delta calculation after set_data():

```python
if hasattr(step, "_transformation") and step._transformation:
    transformation = step._transformation(self)
    if self._event_emitter:
        self._emit(TransformationStarting(...))
    xform_start = datetime.now(timezone.utc)
    current_data = self.get_data("current")
    transformed_data = transformation.transform(current_data, instructions)
    self.set_data(transformed_data, step_name=step.step_name)
    if self._event_emitter:
        xform_ms = (datetime.now(timezone.utc) - xform_start).total_seconds() * 1000
        self._emit(TransformationCompleted(...))
```

### Import Requirement

pipeline.py already imports event types at L35-41. Need to add TransformationStarting and TransformationCompleted to existing import block.

## Event Type Definitions (Already Exist)

All 5 types defined in llm_pipeline/events/types.py:

### ExtractionStarting (L487-494)
- Category: CATEGORY_EXTRACTION
- Fields: extraction_class: str, model_class: str
- Base: StepScopedEvent (step_name, run_id, pipeline_name, timestamp)

### ExtractionCompleted (L497-505)
- Category: CATEGORY_EXTRACTION
- Fields: extraction_class: str, model_class: str, instance_count: int
- Base: StepScopedEvent

### ExtractionError (L508-522)
- Category: CATEGORY_EXTRACTION
- Fields: extraction_class: str, error_type: str, error_message: str, validation_errors: list[str]
- Base: StepScopedEvent
- Note: NO model_class field (differs from task description which mentions it)

### TransformationStarting (L465-471)
- Category: CATEGORY_TRANSFORMATION
- Fields: transformation_class: str
- Base: StepScopedEvent

### TransformationCompleted (L474-481)
- Category: CATEGORY_TRANSFORMATION
- Fields: data_key: str, execution_time_ms: float
- Base: StepScopedEvent

## PipelineExtraction Class Structure

Source: llm_pipeline/extraction.py

- `MODEL: ClassVar[Type[SQLModel]]` -- set via `__init_subclass__(cls, model=None)`
- `__init__(self, pipeline)` -- validates MODEL in pipeline REGISTRY
- `extract(self, results)` -- auto-detects extraction method (default > strategy-match > single-method)
- `_validate_instances(self, instances)` -- validates instances before return
- `_validate_instance(self, instance, index)` -- checks NaN, NULL, FK constraints
- Naming convention enforced: must end with 'Extraction'

## PipelineTransformation Class Structure

Source: llm_pipeline/transformation.py

- `INPUT_TYPE: ClassVar[Type]` -- set via `__init_subclass__(cls, input_type=None, output_type=None)`
- `OUTPUT_TYPE: ClassVar[Type]` -- same
- `__init__(self, pipeline)` -- stores pipeline reference
- `transform(self, data, instructions)` -- auto-detects method (default > single-method > passthrough)
- `_validate_input(self, data)` / `_validate_output(self, data)` -- type checks
- No MODEL attribute (unlike extraction)

## Upstream Task 9 Patterns (Established Conventions)

From task 9 (completed):
1. Guard pattern: `if self._event_emitter:` before every emit call
2. Import at module level (not TYPE_CHECKING)
3. All event constructors use keyword args (kw_only=True)
4. run_id and pipeline_name always passed from pipeline instance
5. step_name from step.step_name property
6. Zero-overhead: no object instantiation when emitter is None
7. Timing as float via `(datetime.now(timezone.utc) - start).total_seconds() * 1000`

## Scope Boundaries

IN SCOPE:
- ExtractionStarting, ExtractionCompleted, ExtractionError in step.py extract_data()
- TransformationStarting, TransformationCompleted in pipeline.py (both cached and fresh paths)

OUT OF SCOPE:
- InstructionsStored, ContextUpdated, StateSaved (Task 15)
- CacheReconstruction events (already implemented in Task 10)
- Transformation error events (no TransformationError type defined)

## Deviation from Task Description

Task description references "line ~322" for extraction and "lines 493-497 and 536-540" for transformation. Actual current lines:
- Extraction: L315-332 (close match)
- Transformation cached path: L576-580 (shifted ~83 lines from task description)
- Transformation fresh path: L652-656 (shifted ~116 lines from task description)

Line shifts caused by Tasks 8, 9, 10, 11, 13 adding event emissions. Not a real issue -- use current lines.

Task description mentions `model_class` in ExtractionError emit example, but ExtractionError type definition has no model_class field. Follow types.py as source of truth.
