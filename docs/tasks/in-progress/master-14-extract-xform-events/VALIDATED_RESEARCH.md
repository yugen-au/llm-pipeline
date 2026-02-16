# Research Summary

## Executive Summary

Validated both research files against actual source code (events/types.py, step.py, pipeline.py, extraction.py, transformation.py, handlers.py, tests/events/conftest.py). All findings confirmed accurate. 5 event types already defined with correct fields and exports. Insertion points in step.py extract_data() (L315-332) and pipeline.py transformation blocks (L576-580, L652-656) verified. One deviation from task description found and resolved (ExtractionError lacks model_class field). Test infrastructure partially exists -- extraction pipeline ready, transformation pipeline needs creation.

## Domain Findings

### Event Type Definitions
**Source:** research/step-1-event-system-research.md, research/step-2-extractiontransform-code-research.md

- All 5 event types confirmed in events/types.py with correct line numbers:
  - ExtractionStarting (L487-494): extraction_class:str, model_class:str
  - ExtractionCompleted (L497-505): extraction_class:str, model_class:str, instance_count:int
  - ExtractionError (L508-522): extraction_class:str, error_type:str, error_message:str, validation_errors:list[str]
  - TransformationStarting (L465-471): transformation_class:str
  - TransformationCompleted (L474-481): data_key:str, execution_time_ms:float
- All inherit from StepScopedEvent (step_name:str|None, run_id:str, pipeline_name:str, timestamp:datetime)
- All use @dataclass(frozen=True, slots=True, kw_only=True) pattern
- Exported in both types.py __all__ (L588-593) and events/__init__.py (L65-71)
- Category constants CATEGORY_EXTRACTION (L34) and CATEGORY_TRANSFORMATION (L33) confirmed
- Both categories mapped to DEBUG log level in handlers.py DEFAULT_LEVEL_MAP (L43-44)

### Extraction Code Path (step.py)
**Source:** research/step-2-extractiontransform-code-research.md

- extract_data() at L315-332 confirmed exact match with research
- try/finally structure with NO except block confirmed -- adding except block required
- Insertion points validated:
  - ExtractionStarting: after L324 (_current_extraction set), before try block
  - ExtractionCompleted: after L330 (flush), inside try
  - ExtractionError: new except block between try and finally, re-raise to preserve behavior
- Field sources confirmed available at each insertion point:
  - extraction_class.__name__ (loop variable, str)
  - extraction.MODEL.__name__ (ClassVar on PipelineExtraction subclass, str)
  - self.step_name (property L246-256)
  - self.pipeline.run_id (L198), self.pipeline.pipeline_name (property L234-243)
  - len(instances) for instance_count (return value from extraction.extract())
- step.py currently has ZERO event imports -- first file to emit events outside pipeline.py
- extract_data() called from 2 sites in pipeline.py (L596 partial cache fallback, L658 fresh path); both automatically covered since events emit from within extract_data()

### Transformation Code Path (pipeline.py)
**Source:** research/step-2-extractiontransform-code-research.md

- Two identical transformation blocks confirmed:
  - Cached path: L576-580
  - Fresh path: L652-656
- Both blocks structurally identical (hasattr check, instantiate, get_data, transform, set_data)
- Insertion points validated:
  - TransformationStarting: after transformation instantiation, before transform() call
  - TransformationCompleted: after set_data(), with timing delta
- Timing pattern: datetime.now(timezone.utc) delta in ms, matches established pattern (L544, L660)
- execution_time_ms includes get_data() call (negligible dict lookup) -- acceptable
- No TransformationError type exists (out of scope) -- errors propagate to PipelineError

### Emission Pattern
**Source:** research/step-1-event-system-research.md

- Guard pattern `if self._event_emitter:` confirmed as zero-overhead convention
- pipeline._emit() (L214-221) has internal None guard but external guard avoids object construction
- step.py access via `self.pipeline._emit()` with `self.pipeline._event_emitter` guard
- All event constructors use keyword args (kw_only=True on all event types)
- CompositeEmitter isolates per-handler errors (emitter.py L58-67)

### Task Description Deviation
**Source:** research/step-2-extractiontransform-code-research.md

- Task 14 description example passes model_class to ExtractionError, but ExtractionError type has NO model_class field
- Resolution: follow types.py as source of truth (types were defined with intentional field choices)
- Line number shifts from task description (L322 -> L315, L493 -> L576, L536 -> L652) caused by Tasks 8-13 adding code; use current lines

### Test Infrastructure
**Source:** research/step-1-event-system-research.md, tests/events/conftest.py

- ExtractionPipeline with ItemDetectionStep + ItemExtraction exists in conftest (L280)
- MockProvider, InMemoryEventHandler, seeded prompts all available
- Test pattern established: run pipeline -> get_events() -> filter by event_type -> assert fields
- GAP: No transformation step/pipeline in conftest -- needs creation for transformation event tests
  - Requires: PipelineTransformation subclass, step with default_transformation, strategy, pipeline

## Q&A History

| # | Question | Answer | Impact |
| --- | --- | --- | --- |
| 1 | ExtractionError emits then re-raises. The outer PipelineError handler (L699) catches all exceptions with full traceback. Should extraction errors produce BOTH ExtractionError + PipelineError events (double-emit), or should ExtractionError suppress PipelineError for extraction failures? | PENDING | Determines whether except block re-raises or handles differently |
| 2 | Transformation blocks exist in both cached path (L576-580) and fresh path (L652-656). Cached path re-transforms data that was already transformed when cache was built. Should both paths emit TransformationStarting/Completed events, or only the fresh path? If both, should the events distinguish cached vs fresh context? | PENDING | Affects whether we add events to 1 or 2 code sites, and whether events need additional context |
| 3 | ExtractionCompleted has no execution_time_ms field, but TransformationCompleted does. This asymmetry is baked into the existing type definitions. Should we add execution_time_ms to ExtractionCompleted (scope creep, requires type modification), or implement strictly per existing types? | PENDING | Scope decision: modify types.py or not |

## Assumptions Validated

- [x] All 5 event types already defined in events/types.py (no type changes needed)
- [x] ExtractionError intentionally omits model_class field (types.py is source of truth)
- [x] step.py extract_data() structure matches research (L315-332, try/finally, no except)
- [x] Two identical transformation blocks at L576-580 and L652-656 in pipeline.py
- [x] Guard pattern `if self._event_emitter:` is correct zero-overhead convention
- [x] step.py emits events via `self.pipeline._emit()` (first event emissions from step.py)
- [x] extract_data() called from both cache-fallback and fresh paths (events cover both automatically)
- [x] Transformation test infrastructure (step + pipeline) does not exist in conftest yet
- [x] ExtractionStarting placement outside try block is safe (finally still executes on propagated exceptions)
- [x] Import pattern: module-level imports, not TYPE_CHECKING (matches pipeline.py convention)
- [x] Timing pattern: float via (datetime.now(timezone.utc) - start).total_seconds() * 1000

## Open Items

- Pydantic ValidationError enrichment for ExtractionError.validation_errors: implementation can do isinstance check for ValidationError and extract .errors() details, or pass empty list for non-validation exceptions. Decide during implementation.

## Recommendations for Planning

1. Start with step.py extraction events (single file, 3 event types) before pipeline.py transformation events (2 sites, 2 event types)
2. Add except block to extract_data() try/finally -- restructure to try/except/finally with re-raise
3. Create transformation test infrastructure in conftest (PipelineTransformation subclass, step, strategy, pipeline) before writing transformation event tests
4. Use ExtractionPipeline from existing conftest for extraction event tests (no new infrastructure needed)
5. Import from llm_pipeline.events.types directly (not through events/__init__.py) matching pipeline.py L35-41 pattern
6. Both transformation sites need identical event emission code -- consider whether a helper is warranted (likely not, given existing duplication pattern in codebase)
