# Step 2: Event System Architecture Research

## Event Type Hierarchy

```
PipelineEvent (base, frozen dataclass, slots=True)
  run_id: str
  pipeline_name: str
  timestamp: datetime (default_factory=utc_now)
  event_type: str (init=False, derived from class name via __init_subclass__)

  StepScopedEvent (intermediate base, _skip_registry=True)
    step_name: str | None = None

    CacheLookup (kw_only=True, CATEGORY_CACHE)
      input_hash: str

    CacheHit (kw_only=True, CATEGORY_CACHE)
      input_hash: str
      cached_at: datetime

    CacheMiss (kw_only=True, CATEGORY_CACHE)
      input_hash: str

    CacheReconstruction (kw_only=True, CATEGORY_CACHE)
      model_count: int
      instance_count: int
```

All four cache event types already exist in `llm_pipeline/events/types.py` (lines 266-302). No new type definitions needed for task 10.

## Auto-Registration Mechanism

- `__init_subclass__` on PipelineEvent derives event_type from class name (CamelCase -> snake_case via `_derive_event_type`)
- Stores in module-level `_EVENT_REGISTRY` dict: `{"cache_lookup": CacheLookup, ...}`
- `__post_init__` sets `event_type` on each instance via `object.__setattr__` (bypasses frozen)
- Classes with `_skip_registry = True` (StepScopedEvent) or leading underscore skip registration

## Serialization

- `to_dict()` converts datetimes to ISO strings
- `to_json()` wraps `to_dict()` in `json.dumps`
- `resolve_event()` handles deserialization; `dt_fields = ("timestamp", "cached_at")` already includes CacheHit's cached_at field

## Emitter Architecture

### PipelineEventEmitter Protocol (emitter.py)
- `@runtime_checkable Protocol` with single `emit(event: PipelineEvent) -> None` method
- Any object with conforming `emit()` duck-types as emitter

### CompositeEmitter (emitter.py)
- Wraps list of handlers as immutable tuple
- Sequential dispatch with per-handler error isolation (try/except per handler, logs exceptions)

### Pipeline._emit() Pattern (pipeline.py L212-219)
```python
def _emit(self, event: "PipelineEvent") -> None:
    if self._event_emitter is not None:
        self._event_emitter.emit(event)
```

### Double-Guard Pattern (zero overhead)
All emission sites in pipeline.py use:
```python
if self._event_emitter:
    self._emit(EventType(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
        step_name=step.step_name,
        ...domain fields...
    ))
```
The outer `if self._event_emitter:` avoids event construction cost when no emitter is configured. `self._emit()` also checks internally but the outer guard prevents even constructing the dataclass.

## Handler Implementations (handlers.py)

| Handler | Purpose | Thread-safe |
|---------|---------|-------------|
| LoggingEventHandler | Log via Python logging, category-based levels | N/A (logging is thread-safe) |
| InMemoryEventHandler | List store for UI/testing, `get_events()` / `get_events_by_type()` | Yes (threading.Lock) |
| SQLiteEventHandler | Persist to `pipeline_events` table via PipelineEventRecord | Session-per-emit |

### Log Level Map (relevant to cache)
```python
CATEGORY_CACHE: logging.DEBUG  # implementation detail level
```

## Existing Event Categories & Emission Locations

| Category | Events | Emitted From |
|----------|--------|-------------|
| pipeline_lifecycle | PipelineStarted, PipelineCompleted, PipelineError | pipeline.py execute() |
| step_lifecycle | StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted | pipeline.py execute() step loop |
| llm_call | LLMCallPrepared | pipeline.py execute() (after prepare_calls) |
| llm_call | LLMCallStarting, LLMCallCompleted | executor.py execute_llm_step() |
| cache | CacheLookup, CacheHit, CacheMiss, CacheReconstruction | **NOT YET EMITTED** (task 10) |

## Task 11 LLM Call Events Implementation (Reference Pattern)

Task 11 used a hybrid approach:
- **LLMCallPrepared**: Emitted from pipeline.py after `prepare_calls()` (pipeline has call_count info)
- **LLMCallStarting/Completed**: Emitted from executor.py (executor has rendered prompts and raw response)
- Event context (event_emitter, run_id, pipeline_name, step_name, call_index) injected into `call_kwargs` dict from pipeline to executor
- All guarded by `if self._event_emitter:` (pipeline) or `if event_emitter:` (executor)
- Exception path: LLMCallCompleted emitted before re-raise with raw_response=None, parsed_result=None

For task 10: All cache events emit from pipeline.py only (no cross-module injection needed). Simpler than task 11.

## Emission Points for Cache Events (pipeline.py)

### CacheLookup (L546-547)
```
L543: input_hash = self._hash_step_inputs(step, step_num)
L546: if use_cache:
  >>> EMIT CacheLookup(step_name=step.step_name, input_hash=input_hash)
L547:     cached_state = self._find_cached_state(step, input_hash)
```
Naturally inside `if use_cache:` block. Only fires when caching is enabled.

### CacheHit (L549)
```
L549: if cached_state:
  >>> EMIT CacheHit(step_name=step.step_name, input_hash=input_hash, cached_at=cached_state.created_at)
L550:     logger.info(f"  [CACHED] Using result from ...")
```

### CacheMiss (L572-574)
```
L572: else:  # no cached_state
L573:     if use_cache:
  >>> EMIT CacheMiss(step_name=step.step_name, input_hash=input_hash)
L574:         logger.info("  [FRESH] No cache found, running fresh")
```
Only inside `if use_cache:` to avoid emitting CacheMiss when caching is disabled entirely.

### CacheReconstruction (L760, _reconstruct_extractions_from_cache)
```
Method already computes: total (int), len(extraction_classes) (int)
After L792 (return total):
  >>> EMIT CacheReconstruction(step_name=step_def.step_class.__name__, model_count=len(extraction_classes), instance_count=total)
```
Note: step_def.step_class.__name__ is used for step_name since this method receives step_def not step instance. Need to verify what convention to use -- could derive snake_case step_name from step_class.__name__ the same way StepKeyDict does it, or pass step.step_name from the caller.

## Field Availability at Each Emission Point

| Event | Field | Source | Available |
|-------|-------|--------|-----------|
| CacheLookup | input_hash | local var L543 | Yes |
| CacheHit | input_hash | local var L543 | Yes |
| CacheHit | cached_at | cached_state.created_at | Yes |
| CacheMiss | input_hash | local var L543 | Yes |
| CacheReconstruction | model_count | len(extraction_classes) L765 | Yes |
| CacheReconstruction | instance_count | total L770 | Yes |
| All | run_id | self.run_id | Yes |
| All | pipeline_name | self.pipeline_name | Yes |
| All | step_name | step.step_name (or derived from step_def) | Yes |

## CacheReconstruction step_name

`_reconstruct_extractions_from_cache(self, cached_state, step_def)` receives `step_def` (a step definition object). The step_name can be derived from `step_def.step_class` using the same snake_case conversion as `StepKeyDict._normalize_key()`. However, the caller (execute() method at L566) has `step.step_name` available, so it may be cleaner to pass step_name as an additional parameter, or emit CacheReconstruction from the caller after the method returns.

**Recommendation**: Emit CacheReconstruction from the caller in execute() after `_reconstruct_extractions_from_cache()` returns, since the caller has both `step.step_name` and the return value `reconstructed_count`, and can compute `model_count` from `len(step_def.extractions)`. This keeps emission in execute() consistent with all other event emissions and avoids modifying _reconstruct_extractions_from_cache's signature.

## Test Patterns (from test_step_lifecycle_events.py)

- Tests use `InMemoryEventHandler` fixture (`in_memory_handler`)
- Pipeline constructed with `event_emitter=in_memory_handler`
- After execution: `events = in_memory_handler.get_events()`
- Filter by event_type: `[e for e in events if e["event_type"] == "cache_lookup"]`
- Assert field values directly on serialized dict
- Test classes per event type + ordering test class + no-emitter test class
- MockProvider returns predefined responses
- Shared fixtures in conftest.py (engine, seeded_session, in_memory_handler)
