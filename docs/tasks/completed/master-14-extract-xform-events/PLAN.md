# PLANNING

## Summary
Add event emissions for ExtractionStarting, ExtractionCompleted, ExtractionError in step.py extract_data() method, and TransformationStarting, TransformationCompleted events in pipeline.py at both cached (L576-580) and fresh (L652-656) transformation sites. Extend event types with execution_time_ms field for ExtractionCompleted and cached field for transformation events.

## Plugin & Agents
**Plugin:** python-development
**Subagents:** python-pro, test-automator
**Skills:** none

## Phases
1. Implementation - Add event type fields and emit events in extraction/transformation code paths
2. Testing - Verify all 5 event types emit with correct field values

## Architecture Decisions

### Decision 1: Type Modifications Before Event Emissions
**Choice:** Modify types.py first to add execution_time_ms to ExtractionCompleted and cached:bool to TransformationStarting/TransformationCompleted
**Rationale:** Events cannot be emitted until event types have required fields. Adding fields first prevents import errors and makes subsequent steps independent
**Alternatives:** Modify types inline with event emissions (creates complex step dependencies)

### Decision 2: Double-Emit ExtractionError and PipelineError
**Choice:** ExtractionError emits in step.py then re-raises exception; outer PipelineError handler in pipeline.py still fires
**Rationale:** CEO decision from validation. ExtractionError has extraction-specific detail (extraction_class, error_type, validation_errors), PipelineError has full traceback. Complementary signals for different consumer needs
**Alternatives:** Suppress PipelineError for extraction failures (rejected - loses traceback detail)

### Decision 3: Both Cached and Fresh Transformation Paths Emit Events
**Choice:** Both cached (L576-580) and fresh (L652-656) transformation blocks emit TransformationStarting/Completed with cached=True/False respectively
**Rationale:** CEO decision from validation. Consumers may need visibility into cached transformations (performance monitoring, cache effectiveness). Distinguishing flag enables filtering without duplicate logic
**Alternatives:** Fresh-only emissions (rejected - loses cache path visibility)

### Decision 4: Timing Capture for ExtractionCompleted
**Choice:** Add execution_time_ms field to ExtractionCompleted, capture timing around extraction.extract() + flush
**Rationale:** CEO approved scope expansion. Matches existing pattern in TransformationCompleted (L479), enables extraction performance monitoring
**Alternatives:** No timing (rejected - asymmetry with transformation events)

### Decision 5: Reuse Existing Test Infrastructure
**Choice:** Use ExtractionPipeline from conftest.py for extraction event tests; create minimal TransformationPipeline + test fixtures for transformation event tests
**Rationale:** ExtractionPipeline with ItemDetectionStep + ItemExtraction already exists (L280 conftest.py). No transformation test infrastructure exists. Create only what's needed
**Alternatives:** Full transformation test suite in conftest (over-engineering for this task)

## Implementation Steps

### Step 1: Extend Event Type Definitions
**Agent:** python-development:python-pro
**Skills:** none
**Context7 Docs:** /python/dataclasses
**Group:** A

1. Add `execution_time_ms: float` field to ExtractionCompleted class in llm_pipeline/events/types.py (L496-504)
2. Add `cached: bool` field to TransformationStarting class in llm_pipeline/events/types.py (L464-470)
3. Add `cached: bool` field to TransformationCompleted class in llm_pipeline/events/types.py (L473-480)

### Step 2: Emit Extraction Events in step.py
**Agent:** python-development:python-pro
**Skills:** none
**Context7 Docs:** /python/datetime
**Group:** B

1. Import event types at module level in llm_pipeline/step.py: ExtractionStarting, ExtractionCompleted, ExtractionError from llm_pipeline.events.types
2. Import datetime, timezone from datetime module
3. In extract_data() method (L314-331), add ExtractionStarting emission after L323 (_current_extraction set), before try block: `if self.pipeline._event_emitter: self.pipeline._emit(ExtractionStarting(extraction_class=extraction_class.__name__, model_class=extraction.MODEL.__name__, step_name=self.step_name, run_id=self.pipeline.run_id, pipeline_name=self.pipeline.pipeline_name, timestamp=datetime.now(timezone.utc)))`
4. Capture start time before extraction.extract() call: `extract_start = datetime.now(timezone.utc)`
5. Add ExtractionCompleted emission after L329 (flush), inside try block: `if self.pipeline._event_emitter: self.pipeline._emit(ExtractionCompleted(extraction_class=extraction_class.__name__, model_class=extraction.MODEL.__name__, instance_count=len(instances), execution_time_ms=(datetime.now(timezone.utc) - extract_start).total_seconds() * 1000, step_name=self.step_name, run_id=self.pipeline.run_id, pipeline_name=self.pipeline.pipeline_name, timestamp=datetime.now(timezone.utc)))`
6. Add except block between try and finally to catch exceptions, emit ExtractionError, then re-raise: `except Exception as e: if self.pipeline._event_emitter: validation_errors = e.errors() if isinstance(e, ValidationError) else []; self.pipeline._emit(ExtractionError(extraction_class=extraction_class.__name__, error_type=type(e).__name__, error_message=str(e), validation_errors=validation_errors, step_name=self.step_name, run_id=self.pipeline.run_id, pipeline_name=self.pipeline.pipeline_name, timestamp=datetime.now(timezone.utc))); raise`

### Step 3: Emit Transformation Events in pipeline.py (Cached Path)
**Agent:** python-development:python-pro
**Skills:** none
**Context7 Docs:** /python/datetime
**Group:** B

1. Import datetime, timezone at module level in llm_pipeline/pipeline.py if not already imported (check L1-50)
2. Import TransformationStarting, TransformationCompleted from llm_pipeline.events.types at module level
3. In cached transformation block (L576-580), add TransformationStarting emission after L577 (transformation instantiation), before transform() call: `if self._event_emitter: self._emit(TransformationStarting(transformation_class=step._transformation.__name__, cached=True, step_name=step.step_name, run_id=self.run_id, pipeline_name=self.pipeline_name, timestamp=datetime.now(timezone.utc)))`
4. Capture start time before transformation.transform() call: `transform_start = datetime.now(timezone.utc)`
5. Add TransformationCompleted emission after L580 (set_data()), with timing: `if self._event_emitter: self._emit(TransformationCompleted(data_key=step.step_name, execution_time_ms=(datetime.now(timezone.utc) - transform_start).total_seconds() * 1000, cached=True, step_name=step.step_name, run_id=self.run_id, pipeline_name=self.pipeline_name, timestamp=datetime.now(timezone.utc)))`

### Step 4: Emit Transformation Events in pipeline.py (Fresh Path)
**Agent:** python-development:python-pro
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. In fresh transformation block (L652-656), add TransformationStarting emission after L653 (transformation instantiation), before transform() call: `if self._event_emitter: self._emit(TransformationStarting(transformation_class=step._transformation.__name__, cached=False, step_name=step.step_name, run_id=self.run_id, pipeline_name=self.pipeline_name, timestamp=datetime.now(timezone.utc)))`
2. Capture start time before transformation.transform() call: `transform_start = datetime.now(timezone.utc)`
3. Add TransformationCompleted emission after L656 (set_data()), with timing: `if self._event_emitter: self._emit(TransformationCompleted(data_key=step.step_name, execution_time_ms=(datetime.now(timezone.utc) - transform_start).total_seconds() * 1000, cached=False, step_name=step.step_name, run_id=self.run_id, pipeline_name=self.pipeline_name, timestamp=datetime.now(timezone.utc)))`

### Step 5: Create Transformation Test Infrastructure
**Agent:** python-development:test-automator
**Skills:** none
**Context7 Docs:** /pytest/pytest, /python/pydantic
**Group:** C

1. Create PipelineTransformation subclass in tests/events/conftest.py: TransformDataTransformation with transform() method that modifies input dict (e.g., adds transformed_key)
2. Create step definition TransformationStep with default_transformation=TransformDataTransformation
3. Create TransformationStrategy with single TransformationStep
4. Create TransformationStrategies registry with TransformationStrategy
5. Create TransformationPipeline(PipelineConfig) with registry=ExtractionRegistry (reuse for simplicity), strategies=TransformationStrategies
6. Add pytest fixture transformation_pipeline that instantiates TransformationPipeline with seeded_session and InMemoryEventHandler

### Step 6: Test Extraction Event Emissions
**Agent:** python-development:test-automator
**Skills:** none
**Context7 Docs:** /pytest/pytest
**Group:** D

1. Create tests/events/test_extraction_events.py
2. Test ExtractionStarting: run ExtractionPipeline, filter events by ExtractionStarting, assert extraction_class="ItemExtraction", model_class="Item", step_name="item_detection", timestamp present
3. Test ExtractionCompleted: run ExtractionPipeline, filter events by ExtractionCompleted, assert extraction_class="ItemExtraction", model_class="Item", instance_count > 0, execution_time_ms > 0, step_name="item_detection"
4. Test ExtractionError: create extraction that raises ValidationError, run pipeline with error handler suppressing PipelineError, filter events by ExtractionError, assert extraction_class present, error_type="ValidationError", error_message present, validation_errors list populated

### Step 7: Test Transformation Event Emissions
**Agent:** python-development:test-automator
**Skills:** none
**Context7 Docs:** /pytest/pytest
**Group:** D

1. Create tests/events/test_transformation_events.py
2. Test TransformationStarting (fresh path): run TransformationPipeline with empty cache, filter events by TransformationStarting, assert transformation_class="TransformDataTransformation", cached=False, step_name present
3. Test TransformationCompleted (fresh path): run TransformationPipeline with empty cache, filter events by TransformationCompleted, assert data_key equals step_name, execution_time_ms > 0, cached=False
4. Test TransformationStarting (cached path): run TransformationPipeline twice (first fresh, second cached), filter events from second run by TransformationStarting, assert cached=True
5. Test TransformationCompleted (cached path): run TransformationPipeline twice (first fresh, second cached), filter events from second run by TransformationCompleted, assert cached=True, execution_time_ms > 0

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| ExtractionError except block breaks existing error propagation | High | Re-raise exception after event emission; verify PipelineError still fires in tests |
| Timing capture overhead in hot path (extract_data called per extraction class) | Low | datetime.now() overhead negligible (microseconds); guard pattern already used throughout codebase |
| Transformation event duplication in cached/fresh paths | Low | Accept duplication (matches existing codebase pattern per research); both sites need identical code except cached flag |
| ValidationError enrichment for ExtractionError.validation_errors may fail for non-Pydantic exceptions | Low | Use isinstance check, default to empty list for non-ValidationError exceptions |
| Transformation test infrastructure incomplete in conftest | Medium | Create minimal infrastructure in Step 5 before tests; verify fresh and cached paths both exercise transformation logic |

## Success Criteria

- [ ] ExtractionCompleted has execution_time_ms field in types.py
- [ ] TransformationStarting and TransformationCompleted have cached field in types.py
- [ ] ExtractionStarting emits before extraction.extract() in step.py
- [ ] ExtractionCompleted emits after flush with timing in step.py
- [ ] ExtractionError emits in except block then re-raises in step.py
- [ ] TransformationStarting emits before transform() in both cached and fresh paths in pipeline.py
- [ ] TransformationCompleted emits after set_data() with timing in both cached and fresh paths in pipeline.py
- [ ] Cached path transformations have cached=True, fresh path has cached=False
- [ ] All 5 event types have passing tests verifying field values
- [ ] ExtractionError test verifies validation_errors populated for ValidationError
- [ ] Transformation tests verify both cached and fresh code paths

## Phase Recommendation

**Risk Level:** low
**Reasoning:** Straightforward event emissions following established patterns from Task 13. Type modifications are additive (no breaking changes). Extraction events isolated to step.py, transformation events isolated to pipeline.py. Test infrastructure creation is minimal (reuse ExtractionPipeline, add simple TransformationPipeline). No architectural decisions or integration complexity.
**Suggested Exclusions:** testing, review
