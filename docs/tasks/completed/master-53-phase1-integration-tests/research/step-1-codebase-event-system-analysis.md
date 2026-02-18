# Step 1: Codebase Event System Analysis

## 1. Event Type Hierarchy

### Base Classes

```
PipelineEvent (frozen dataclass, slots=True)
  fields: run_id (str), pipeline_name (str), timestamp (datetime, default=utc_now), event_type (str, init=False)
  class vars: _EVENT_REGISTRY (ClassVar dict)
  methods: __init_subclass__ (auto-register), __post_init__ (set event_type), to_dict(), to_json(), resolve_event()

StepScopedEvent(PipelineEvent) -- intermediate base, _skip_registry=True
  fields: step_name (str | None = None)
```

### All 28 Concrete Event Types (9 Categories)

#### Pipeline Lifecycle (CATEGORY_PIPELINE_LIFECYCLE)
| Event | Base | Extra Fields |
|---|---|---|
| PipelineStarted | PipelineEvent | (none) |
| PipelineCompleted | PipelineEvent (kw_only) | execution_time_ms: float, steps_executed: int |
| PipelineError | StepScopedEvent (kw_only) | error_type: str, error_message: str, traceback: str\|None |

#### Step Lifecycle (CATEGORY_STEP_LIFECYCLE)
| Event | Base | Extra Fields |
|---|---|---|
| StepSelecting | StepScopedEvent (kw_only) | step_index: int, strategy_count: int |
| StepSelected | StepScopedEvent (kw_only) | step_number: int, strategy_name: str |
| StepSkipped | StepScopedEvent (kw_only) | step_number: int, reason: str |
| StepStarted | StepScopedEvent (kw_only) | step_number: int, system_key: str\|None, user_key: str\|None |
| StepCompleted | StepScopedEvent (kw_only) | step_number: int, execution_time_ms: float |

#### Cache (CATEGORY_CACHE)
| Event | Base | Extra Fields |
|---|---|---|
| CacheLookup | StepScopedEvent (kw_only) | input_hash: str |
| CacheHit | StepScopedEvent (kw_only) | input_hash: str, cached_at: datetime |
| CacheMiss | StepScopedEvent (kw_only) | input_hash: str |
| CacheReconstruction | StepScopedEvent (kw_only) | model_count: int, instance_count: int |

#### LLM Call (CATEGORY_LLM_CALL)
| Event | Base | Extra Fields |
|---|---|---|
| LLMCallPrepared | StepScopedEvent (kw_only) | call_count: int, system_key: str\|None, user_key: str\|None |
| LLMCallStarting | StepScopedEvent (kw_only) | call_index: int, rendered_system_prompt: str, rendered_user_prompt: str |
| LLMCallCompleted | StepScopedEvent (kw_only) | call_index: int, raw_response: str\|None, parsed_result: dict\|None, model_name: str\|None, attempt_count: int, validation_errors: list[str] |
| LLMCallRetry | StepScopedEvent (kw_only) | attempt: int, max_retries: int, error_type: str, error_message: str |
| LLMCallFailed | StepScopedEvent (kw_only) | max_retries: int, last_error: str |
| LLMCallRateLimited | StepScopedEvent (kw_only) | attempt: int, wait_seconds: float, backoff_type: str |

#### Consensus (CATEGORY_CONSENSUS)
| Event | Base | Extra Fields |
|---|---|---|
| ConsensusStarted | StepScopedEvent (kw_only) | threshold: int, max_calls: int |
| ConsensusAttempt | StepScopedEvent (kw_only) | attempt: int, group_count: int |
| ConsensusReached | StepScopedEvent (kw_only) | attempt: int, threshold: int |
| ConsensusFailed | StepScopedEvent (kw_only) | max_calls: int, largest_group_size: int |

#### Instructions & Context (CATEGORY_INSTRUCTIONS_CONTEXT)
| Event | Base | Extra Fields |
|---|---|---|
| InstructionsStored | StepScopedEvent (kw_only) | instruction_count: int |
| InstructionsLogged | StepScopedEvent (kw_only) | logged_keys: list[str] |
| ContextUpdated | StepScopedEvent (kw_only) | new_keys: list[str], context_snapshot: dict[str, Any] |

#### Transformation (CATEGORY_TRANSFORMATION)
| Event | Base | Extra Fields |
|---|---|---|
| TransformationStarting | StepScopedEvent (kw_only) | transformation_class: str, cached: bool |
| TransformationCompleted | StepScopedEvent (kw_only) | data_key: str, execution_time_ms: float, cached: bool |

#### Extraction (CATEGORY_EXTRACTION)
| Event | Base | Extra Fields |
|---|---|---|
| ExtractionStarting | StepScopedEvent (kw_only) | extraction_class: str, model_class: str |
| ExtractionCompleted | StepScopedEvent (kw_only) | extraction_class: str, model_class: str, instance_count: int, execution_time_ms: float |
| ExtractionError | StepScopedEvent (kw_only) | extraction_class: str, error_type: str, error_message: str, validation_errors: list[str] |

#### State (CATEGORY_STATE)
| Event | Base | Extra Fields |
|---|---|---|
| StateSaved | StepScopedEvent (kw_only) | step_number: int, input_hash: str, execution_time_ms: float |

### Auto-Registration Mechanism

- `__init_subclass__` on PipelineEvent auto-registers each subclass in `_EVENT_REGISTRY`
- Skips classes starting with `_` or having `_skip_registry = True` (StepScopedEvent)
- `_derive_event_type()` converts CamelCase to snake_case (e.g., LLMCallStarting -> llm_call_starting)
- `__post_init__` sets the derived `event_type` via `object.__setattr__` (bypasses frozen)
- `resolve_event(event_type, data)` reconstructs events from serialized data


## 2. Event Handlers

### PipelineEventEmitter Protocol (emitter.py)
```python
@runtime_checkable
class PipelineEventEmitter(Protocol):
    def emit(self, event: PipelineEvent) -> None: ...
```
- Duck-typed protocol; any object with `emit(event) -> None` qualifies
- `isinstance()` checks work at runtime

### LoggingEventHandler (handlers.py)
- Logs events via Python `logging` with category-based levels
- Uses `DEFAULT_LEVEL_MAP`: lifecycle/consensus/LLM at INFO, details at DEBUG
- Supports custom logger and custom level_map
- No internal error handling (relies on CompositeEmitter)

### InMemoryEventHandler (handlers.py)
- Thread-safe via `threading.Lock` on `_events` list
- Stores events as dicts (via `event.to_dict()`)
- Query methods: `get_events(run_id=None)`, `get_events_by_type(event_type, run_id=None)`
- Returns shallow copies from `get_events()` to prevent caller mutation
- `clear()` empties the store

### SQLiteEventHandler (handlers.py)
- Persists events as `PipelineEventRecord` rows
- Session-per-emit pattern (new Session per emit, closed in finally)
- Table creation idempotent on init
- No internal error handling (relies on CompositeEmitter)

### PipelineEventRecord (models.py)
- SQLModel table: `pipeline_events`
- Fields: id, run_id, event_type, pipeline_name, timestamp, event_data (JSON)
- Indexes: `ix_pipeline_events_run_event` (run_id, event_type), `ix_pipeline_events_type` (event_type)
- Intentionally duplicates run_id/event_type/timestamp in columns AND in event_data JSON


## 3. CompositeEmitter (emitter.py)

```python
class CompositeEmitter:
    __slots__ = ("_handlers",)

    def __init__(self, handlers: list[PipelineEventEmitter]) -> None:
        self._handlers: tuple[PipelineEventEmitter, ...] = tuple(handlers)

    def emit(self, event: PipelineEvent) -> None:
        for handler in self._handlers:
            try:
                handler.emit(event)
            except Exception:
                logger.exception("Handler %r failed for event %s", handler, event.event_type)
```

### Key Behaviors
- Handlers stored as immutable tuple at construction
- Sequential dispatch (not parallel)
- Per-handler error isolation: catches `Exception`, logs via `logger.exception`, continues to next handler
- Does NOT re-raise exceptions from handlers
- Does NOT itself implement PipelineEventEmitter protocol (no `emit` method signature match, but structurally compatible)


## 4. PipelineConfig Event Integration

### _emit() Pattern
```python
def _emit(self, event: PipelineEvent) -> None:
    if self._event_emitter is not None:
        self._event_emitter.emit(event)
```
- Guard check at call site: `if self._event_emitter:` before constructing event
- Zero overhead when `event_emitter=None` (no event objects created)

### Constructor
- `event_emitter: Optional[PipelineEventEmitter] = None` parameter
- Stored as `self._event_emitter`

### Event Emission Points in execute()

**Pipeline Level:**
1. `PipelineStarted` -- before step loop
2. `PipelineCompleted` -- after step loop (success only)
3. `PipelineError` -- in except block (includes step_name if available, traceback)

**Step Selection (per step_index):**
4. `StepSelecting` -- before strategy iteration (step_name=None, step_index, strategy_count)
5. `StepSelected` -- after step chosen (step_name, step_number, strategy_name)
6. `StepSkipped` -- if should_skip() returns True (reason="should_skip returned True")
7. `StepStarted` -- before step execution (step_number, system_key, user_key)
8. `StepCompleted` -- after step execution (step_number, execution_time_ms)

**Cache Path (when use_cache=True):**
9. `CacheLookup` -- before _find_cached_state (input_hash)
10. `CacheHit` -- when cached_state found (input_hash, cached_at)
11. `CacheMiss` -- when no cached_state (input_hash)
12. `CacheReconstruction` -- after reconstruction from cache (model_count, instance_count)

**LLM Call Path (fresh, non-consensus):**
13. `LLMCallPrepared` -- after prepare_calls() (call_count, system_key, user_key)
14. `InstructionsStored` -- after instructions collected (instruction_count)
15. `ContextUpdated` -- inside _validate_and_merge_context (new_keys, context_snapshot)
16. `InstructionsLogged` -- after log_instructions() (logged_keys=[step.step_name])
17. `StateSaved` -- inside _save_step_state (step_number, input_hash, execution_time_ms)

**Transformation Path (both fresh and cached):**
18. `TransformationStarting` -- before transform() (transformation_class, cached)
19. `TransformationCompleted` -- after transform() (data_key, execution_time_ms, cached)

### Event Emission Points in execute_llm_step() (executor.py)
20. `LLMCallStarting` -- before provider.call_structured (rendered prompts)
21. `LLMCallCompleted` -- after provider.call_structured (success or error path)

### Event Emission Points in GeminiProvider.call_structured()
22. `LLMCallRetry` -- on non-last-attempt failure (empty_response, json_decode_error, validation_error, array_validation_error, pydantic_validation_error, exception)
23. `LLMCallFailed` -- after all retries exhausted
24. `LLMCallRateLimited` -- on 429 errors (api_suggested or exponential backoff_type)

### Event Emission Points in LLMStep.extract_data() (step.py)
25. `ExtractionStarting` -- before extraction.extract() or extraction.default()
26. `ExtractionCompleted` -- after extraction + flush
27. `ExtractionError` -- on extraction failure (includes validation_errors for ValidationError)

### Consensus Path (_execute_with_consensus)
28. `ConsensusStarted` -- before consensus loop
29. `ConsensusAttempt` -- after each attempt (attempt, group_count)
30. `ConsensusReached` -- when group hits threshold
31. `ConsensusFailed` -- after exhausting max_calls


## 5. Execution Lifecycle Event Order

### Successful 2-Step Pipeline (no cache, no consensus)
```
PipelineStarted
  StepSelecting(step_index=0)
  StepSelected(step_name, step_number=1, strategy_name)
  StepStarted(step_number=1, system_key, user_key)
    LLMCallPrepared(call_count, system_key, user_key)
    LLMCallStarting(call_index=0, rendered prompts)
    LLMCallCompleted(call_index=0, raw_response, parsed_result, model_name, attempt_count)
    InstructionsStored(instruction_count)
    ContextUpdated(new_keys, context_snapshot)
    TransformationStarting(if step has transformation, cached=False)
    TransformationCompleted(if step has transformation, cached=False)
    ExtractionStarting(if step has extractions)
    ExtractionCompleted(if step has extractions)
    StateSaved(step_number, input_hash, execution_time_ms)
    InstructionsLogged(logged_keys)
  StepCompleted(step_number=1, execution_time_ms)
  StepSelecting(step_index=1)
  StepSelected(step_name, step_number=2, strategy_name)
  StepStarted(step_number=2, ...)
    ... (same inner pattern)
  StepCompleted(step_number=2, ...)
PipelineCompleted(execution_time_ms, steps_executed)
```

### Cached Path (use_cache=True, cache hit)
```
  StepStarted(...)
    CacheLookup(input_hash)
    CacheHit(input_hash, cached_at)
    InstructionsStored(instruction_count)
    ContextUpdated(new_keys, context_snapshot)
    TransformationStarting(cached=True)
    TransformationCompleted(cached=True)
    InstructionsLogged(logged_keys)
    CacheReconstruction(model_count, instance_count)  -- only if step has extractions
  StepCompleted(...)
```

### Error Path
```
PipelineStarted
  StepSelecting(...)
  StepSelected(...)
  StepStarted(...)
    LLMCallPrepared(...)
    LLMCallStarting(...)
    LLMCallCompleted(raw_response=None, parsed_result=None, validation_errors=[...])
  PipelineError(error_type, error_message, traceback, step_name)
  -- NO PipelineCompleted
  -- NO StepCompleted
```


## 6. Thread Safety Analysis

### InMemoryEventHandler
- `threading.Lock` protects `_events` list in `emit()`, `get_events()`, `clear()`
- `get_events()` returns shallow copy outside lock
- Thread-safe for concurrent emit/read

### CompositeEmitter
- `_handlers` stored as immutable tuple (no mutation possible)
- `emit()` iterates tuple sequentially -- no lock needed for handler list
- Each handler's `emit()` is called synchronously
- If handler.emit() is thread-safe, CompositeEmitter is thread-safe
- No thread safety issues in CompositeEmitter itself

### SQLiteEventHandler
- Session-per-emit pattern -- each emit creates/closes its own Session
- SQLite in WAL mode handles concurrent writes (but single-writer at a time)
- No shared state between emits


## 7. Existing Test Coverage

### tests/events/ (10 files)

| File | Coverage |
|---|---|
| conftest.py | MockProvider, test domain models, steps, strategies, pipelines, fixtures |
| test_handlers.py | LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler, PipelineEventRecord, Protocol, DEFAULT_LEVEL_MAP, thread safety |
| test_pipeline_lifecycle_events.py | PipelineStarted, PipelineCompleted, PipelineError, no-emitter |
| test_step_lifecycle_events.py | StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted, ordering |
| test_llm_call_events.py | LLMCallPrepared, LLMCallStarting, LLMCallCompleted, pairing, error path, zero overhead |
| test_cache_events.py | CacheLookup, CacheMiss, CacheHit, CacheReconstruction, two-run, ordering |
| test_retry_ratelimit_events.py | LLMCallRetry, LLMCallFailed, LLMCallRateLimited via GeminiProvider mocking |
| test_consensus_events.py | ConsensusStarted, ConsensusAttempt, ConsensusReached, ConsensusFailed, ordering |
| test_extraction_events.py | ExtractionStarting, ExtractionCompleted, ExtractionError |
| test_transformation_events.py | TransformationStarting, TransformationCompleted, fresh/cached |
| test_ctx_state_events.py | InstructionsStored, InstructionsLogged, ContextUpdated, StateSaved, fresh/cached |

### Gaps Identified

1. **CompositeEmitter** -- NO dedicated tests at all
   - Error isolation (failing handler doesn't block others)
   - Multi-handler dispatch order
   - Thread safety under concurrent emit
   - Protocol conformance check
   - Repr

2. **Event Type System Mechanics** -- NOT tested
   - `_derive_event_type()` CamelCase->snake_case conversion
   - `_EVENT_REGISTRY` population (all 28 types registered)
   - `resolve_event()` round-trip (serialize -> deserialize)
   - `to_dict()` / `to_json()` serialization
   - Frozen dataclass immutability (cannot reassign fields)
   - EVENT_CATEGORY ClassVar on all concrete types
   - StepScopedEvent._skip_registry prevents registry entry

3. **Cross-Cutting** -- NOT tested
   - Full end-to-end event flow validation (all events from a complex pipeline run in exact order)
   - Event immutability after emission (frozen dataclass guarantee)
   - CompositeEmitter + InMemoryEventHandler + SQLiteEventHandler together


## 8. Key Implementation Details for Test Writing

### Pipeline Name Derivation
- Class name `SuccessPipeline` -> pipeline_name `"success"` (strip "Pipeline" suffix, snake_case)

### Step Name Derivation
- Class name `SimpleStep` -> step_name `"simple"` (strip "Step" suffix, snake_case)
- Class name `ItemDetectionStep` -> step_name `"item_detection"`

### Strategy Name Derivation
- Class name `SuccessStrategy` -> strategy.name `"success"` (strip "Strategy" suffix, snake_case)

### Input Hash
- SHA256 of JSON-serialized prepare_calls() output, truncated to 16 hex chars
- Identical steps produce identical hashes -> cache hit on step 2 if same as step 1

### steps_executed in PipelineCompleted
- Counts unique step CLASSES (set), not instances
- 2 SimpleStep instances = 1 unique step class = `steps_executed=1`

### Event Emitter Injection into LLM Executor
- When `self._event_emitter` is set, pipeline injects `event_emitter`, `run_id`, `pipeline_name`, `step_name`, `call_index` into `call_kwargs`
- When `self._event_emitter` is None, these keys are NOT added to `call_kwargs`

### GeminiProvider Event Params
- `call_structured()` accepts `event_emitter`, `step_name`, `run_id`, `pipeline_name` as kwargs
- Retry/ratelimit events emitted directly via `event_emitter.emit()` inside retry loop
- LLMCallRetry only emitted when `attempt < max_retries - 1` (not on last attempt)
- LLMCallFailed emitted after loop exhaustion

### Extraction Event Emission
- Events emitted in `LLMStep.extract_data()` (step.py), not pipeline.py
- Uses `self.pipeline._emit()` and `self.pipeline._event_emitter` guard


## 9. Test Infrastructure (conftest.py)

### Available Fixtures
- `engine` -- in-memory SQLite engine with all tables
- `seeded_session` -- Session with Prompt records for all test steps (simple, failing, skippable, item_detection, transformation)
- `in_memory_handler` -- fresh InMemoryEventHandler

### Available Test Domain
- MockProvider (configurable responses, should_fail flag)
- SimpleStep, FailingStep, SkippableStep, ItemDetectionStep, TransformationStep
- SuccessPipeline (2 SimpleSteps), FailurePipeline, SkipPipeline, ExtractionPipeline, TransformationPipeline
- Item (SQLModel table), ItemExtraction, TransformationTransformation


## 10. Dependencies & Scope

### Upstream (done)
- Task 15: Emit InstructionsStored, InstructionsLogged, ContextUpdated, StateSaved -- VERIFIED IMPLEMENTED
- Task 16: Populate PipelineStepState.model field from LLMCallResult.model_name -- VERIFIED IMPLEMENTED

### Downstream (out of scope)
- Task 57: Documentation and Examples -- depends on task 53 completion

### What Tests Should Cover (per task 53 description + testStrategy)
- All event types tested (28 types)
- Error isolation in CompositeEmitter
- Handler thread safety
- Target >90% coverage for events package
