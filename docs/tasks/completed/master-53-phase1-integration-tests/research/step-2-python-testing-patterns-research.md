# Step 2: Python Testing Patterns Research

## 1. Existing Test Infrastructure Summary

### Project Setup
- pytest >= 7.0 with pytest-cov >= 4.0 (in `[project.optional-dependencies].dev`)
- `pyproject.toml`: `testpaths = ["tests"]`, `pythonpath = ["."]`
- No root-level conftest.py; all event fixtures in `tests/events/conftest.py`
- No `__init__.py` in `tests/events/` (flat conftest import)

### Current Test Coverage (10 files, ~200+ tests)

| File | What It Covers |
|---|---|
| `conftest.py` | MockProvider, 5 step types, 5 pipeline configs, 3 fixtures |
| `test_handlers.py` | LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler, PipelineEventRecord, Protocol conformance, DEFAULT_LEVEL_MAP |
| `test_pipeline_lifecycle_events.py` | PipelineStarted, PipelineCompleted, PipelineError, no-emitter |
| `test_step_lifecycle_events.py` | StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted, ordering |
| `test_llm_call_events.py` | LLMCallPrepared, LLMCallStarting, LLMCallCompleted, pairing, error path |
| `test_cache_events.py` | CacheLookup, CacheMiss, CacheHit, CacheReconstruction, two-run pattern |
| `test_retry_ratelimit_events.py` | LLMCallRetry, LLMCallFailed, LLMCallRateLimited (GeminiProvider-level mocking) |
| `test_consensus_events.py` | ConsensusStarted, ConsensusAttempt, ConsensusReached, ConsensusFailed |
| `test_extraction_events.py` | ExtractionStarting, ExtractionCompleted, ExtractionError |
| `test_transformation_events.py` | TransformationStarting, TransformationCompleted, fresh/cached paths |
| `test_ctx_state_events.py` | InstructionsStored, InstructionsLogged, ContextUpdated, StateSaved |

### Also: `tests/test_emitter.py`
- PipelineEventEmitter Protocol conformance (4 tests)
- CompositeEmitter instantiation (4 tests)
- CompositeEmitter emit dispatch (3 tests)
- CompositeEmitter error isolation (3 tests)
- CompositeEmitter thread safety (2 tests)
- CompositeEmitter repr/slots (4 tests)

### Correction to Step 1 Gap Analysis
Step 1 section 7 incorrectly listed "CompositeEmitter -- NO dedicated tests at all" as Gap 1. `tests/test_emitter.py` exists with 20 tests covering error isolation, thread safety, protocol conformance, and dispatch ordering. This gap is already addressed.


## 2. Pytest Fixture Patterns for Event System Testing

### 2.1. Layered Conftest Pattern (Already Used)
```
tests/
  events/
    conftest.py        # Shared: MockProvider, steps, strategies, pipelines, fixtures
    test_*.py          # Per-category test modules
```

The project correctly uses a single conftest.py for all event tests. Each test module imports from conftest directly (flat import path via `pythonpath = ["."]` in pytest config).

### 2.2. Factory Fixtures for Parametrized Event Creation

**Current gap**: No factory fixture for creating arbitrary events with defaults.

**Recommended pattern**:
```python
@pytest.fixture
def event_factory():
    """Factory fixture for creating events with sane defaults."""
    def _create(event_cls, **overrides):
        defaults = {
            "run_id": "test-run",
            "pipeline_name": "test_pipeline",
        }
        if issubclass(event_cls, StepScopedEvent):
            defaults["step_name"] = "test_step"
        defaults.update(overrides)
        return event_cls(**defaults)
    return _create
```

Useful for:
- Parametrized tests over all 28 event types
- `resolve_event()` round-trip tests
- Serialization tests

### 2.3. Fixture Composition for Pipeline Setup

**Current pattern** (effective, no change needed):
```python
@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:", echo=False)
    SQLModel.metadata.create_all(eng)
    return eng

@pytest.fixture
def seeded_session(engine):
    # Seed prompts, return session
    ...

@pytest.fixture
def in_memory_handler():
    return InMemoryEventHandler()
```

Tests compose these manually:
```python
def test_something(self, seeded_session, in_memory_handler):
    pipeline = SuccessPipeline(
        session=seeded_session,
        provider=MockProvider(responses=[...]),
        event_emitter=in_memory_handler,
    )
```

### 2.4. Helper Functions Per Module

**Current pattern** (effective):
```python
def _run_success_pipeline(seeded_session, handler):
    """Module-level helper, not a fixture."""
    provider = MockProvider(responses=[...])
    pipeline = SuccessPipeline(
        session=seeded_session, provider=provider, event_emitter=handler,
    )
    pipeline.execute(data="test data", initial_context={})
    return pipeline, handler.get_events()
```

This avoids fixture-bloat and keeps setup visible at call site.


## 3. Testing Composite/Multi-Handler Event Dispatch

### 3.1. Error Isolation Pattern (Already in test_emitter.py)

```python
class TestCompositeEmitterErrorIsolation:
    def test_failing_handler_does_not_block_others(self):
        h1 = Mock()
        h2 = Mock()
        h2.emit.side_effect = RuntimeError("boom")
        h3 = Mock()

        emitter = CompositeEmitter(handlers=[h1, h2, h3])
        emitter.emit(event)

        h1.emit.assert_called_once_with(event)
        h2.emit.assert_called_once_with(event)
        h3.emit.assert_called_once_with(event)
```

**Key technique**: Mock with `side_effect` on middle handler, verify all 3 called.

### 3.2. Logger Verification Pattern

```python
@patch("llm_pipeline.events.emitter.logger")
def test_logger_exception_called(self, mock_logger):
    h1 = Mock()
    h1.emit.side_effect = ValueError("test error")
    emitter = CompositeEmitter(handlers=[h1])
    emitter.emit(event)
    mock_logger.exception.assert_called_once()
```

### 3.3. Dispatch Order Pattern

```python
def test_handlers_called_in_order(self):
    call_order = []
    h1 = Mock(side_effect=lambda e: call_order.append(1))
    h1.emit = h1
    # ...
    emitter = CompositeEmitter(handlers=[h1, h2, h3])
    emitter.emit(event)
    assert call_order == [1, 2, 3]
```


## 4. Thread Safety Testing Patterns

### 4.1. Concurrent Emit with Barrier (Already Used)

```python
def test_concurrent_emit(self, in_memory_handler):
    num_threads = 10
    events_per_thread = 20

    def _worker():
        for i in range(events_per_thread):
            event = PipelineStarted(run_id=f"run-{threading.current_thread().ident}-{i}", ...)
            in_memory_handler.emit(event)

    threads = [threading.Thread(target=_worker) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(in_memory_handler.get_events()) == num_threads * events_per_thread
```

### 4.2. Threading.Lock Counter Pattern

```python
counts = [0, 0]
lock = threading.Lock()

class _CountingHandler:
    def __init__(self, idx):
        self._idx = idx
    def emit(self, event):
        with lock:
            counts[self._idx] += 1

h1, h2 = _CountingHandler(0), _CountingHandler(1)
emitter = CompositeEmitter(handlers=[h1, h2])
# ... spawn threads, join ...
assert counts[0] == total_expected
assert counts[1] == total_expected
```

### 4.3. Recommendations for Additional Thread Safety Tests

- Concurrent `emit()` + `get_events()` on InMemoryEventHandler (read during write)
- Concurrent `emit()` + `clear()` on InMemoryEventHandler (clear during write)
- These would verify Lock correctness under mixed read/write contention


## 5. Mocking Strategies for LLM Providers

### 5.1. MockProvider (Application-Level Mock)

```python
class MockProvider(LLMProvider):
    def __init__(self, responses=None, should_fail=False):
        self._responses = responses or []
        self._call_count = 0
        self._should_fail = should_fail

    def call_structured(self, prompt, system_instruction, result_class, **kwargs):
        if self._should_fail:
            raise ValueError("Mock provider failure")
        if self._call_count < len(self._responses):
            response = self._responses[self._call_count]
            self._call_count += 1
            return LLMCallResult.success(
                parsed=response, raw_response="mock response",
                model_name="mock-model", attempt_count=1,
            )
        return LLMCallResult(parsed=None, raw_response="", ...)
```

**Use for**: Pipeline integration tests where you need controlled LLM responses without touching retry logic.

### 5.2. Gemini API-Level Mocking (Low-Level Mock)

```python
@patch('google.generativeai.GenerativeModel')
def test_retry_events(self, mock_model_class):
    provider = GeminiProvider(api_key="test_key")
    handler = InMemoryEventHandler()

    _setup_model_mocks(mock_model_class, [
        _create_mock_response(""),       # empty -> retry
        _create_mock_response("{bad}"),   # JSON error -> retry
        _create_mock_response('{"count": 1, "notes": "ok"}'),  # success
    ])

    result = provider.call_structured(
        prompt="test", system_instruction="test",
        result_class=SimpleSchema, max_retries=3,
        event_emitter=handler, step_name="test_step",
        run_id="run_001", pipeline_name="test_pipeline",
    )
```

**Use for**: Testing retry/ratelimit events (LLMCallRetry, LLMCallFailed, LLMCallRateLimited).

### 5.3. When to Use Which

| Scenario | Mock Level |
|---|---|
| Pipeline lifecycle events | MockProvider (conftest) |
| Step lifecycle events | MockProvider |
| Cache events | MockProvider |
| LLM call events (Prepared, Starting, Completed) | MockProvider |
| Retry/ratelimit events | @patch GenerativeModel |
| Consensus events | MockProvider |
| Extraction/transformation events | MockProvider |
| Context/state events | MockProvider |


## 6. Pytest Parametrize Patterns for Event Types

### 6.1. Registry Completeness Test

```python
import pytest
from llm_pipeline.events.types import _EVENT_REGISTRY

ALL_EVENT_TYPES = list(_EVENT_REGISTRY.keys())

@pytest.mark.parametrize("event_type", ALL_EVENT_TYPES)
def test_event_type_in_registry(event_type):
    """Every event type has a registered class."""
    assert event_type in _EVENT_REGISTRY
    assert _EVENT_REGISTRY[event_type] is not None
```

### 6.2. Serialization Round-Trip

```python
# Build (event_type, kwargs) pairs for all 28 types
EVENT_FIXTURES = [
    ("pipeline_started", {"run_id": "r1", "pipeline_name": "p1"}),
    ("pipeline_completed", {"run_id": "r1", "pipeline_name": "p1",
                            "execution_time_ms": 100.0, "steps_executed": 2}),
    # ... all 28 ...
]

@pytest.mark.parametrize("event_type,kwargs", EVENT_FIXTURES, ids=[e[0] for e in EVENT_FIXTURES])
def test_serialization_round_trip(event_type, kwargs):
    """to_dict() -> resolve_event() produces equivalent event."""
    cls = _EVENT_REGISTRY[event_type]
    original = cls(**kwargs)
    serialized = original.to_dict()
    restored = PipelineEvent.resolve_event(event_type, serialized)
    assert restored.event_type == original.event_type
    assert restored.run_id == original.run_id
```

### 6.3. Category Verification

```python
EXPECTED_CATEGORIES = {
    "PipelineStarted": CATEGORY_PIPELINE_LIFECYCLE,
    "PipelineCompleted": CATEGORY_PIPELINE_LIFECYCLE,
    # ... all 28 ...
}

@pytest.mark.parametrize("class_name,expected_category", EXPECTED_CATEGORIES.items())
def test_event_category(class_name, expected_category):
    """Each event class has correct EVENT_CATEGORY."""
    cls = _EVENT_REGISTRY[_derive_event_type(class_name)]
    assert cls.EVENT_CATEGORY == expected_category
```

### 6.4. Derive Event Type Conversion

```python
CAMEL_TO_SNAKE = [
    ("PipelineStarted", "pipeline_started"),
    ("LLMCallStarting", "llm_call_starting"),
    ("CacheHit", "cache_hit"),
    # etc.
]

@pytest.mark.parametrize("camel,snake", CAMEL_TO_SNAKE)
def test_derive_event_type(camel, snake):
    assert _derive_event_type(camel) == snake
```


## 7. Integration Test Organization

### 7.1. Current Structure (1 File Per Category)
```
tests/events/
  conftest.py                          # shared fixtures
  test_pipeline_lifecycle_events.py    # 3 test classes
  test_step_lifecycle_events.py        # 7 test classes
  test_llm_call_events.py             # 7 test classes
  test_cache_events.py                 # 12 test classes
  test_retry_ratelimit_events.py       # 10 test classes
  test_consensus_events.py             # 6 test classes
  test_extraction_events.py            # 6 test classes
  test_transformation_events.py        # 8 test classes
  test_ctx_state_events.py             # 9 test classes
```

### 7.2. Recommended Additions

```
tests/events/
  test_event_types.py                  # NEW: registry, serialization, derive_event_type, frozen, categories
  test_end_to_end_event_flow.py        # NEW: full pipeline event ordering across all categories
```

### 7.3. Test Class Naming Convention (Already Used)

Pattern: `Test<EventType><Scenario>`
```python
class TestPipelineLifecycleSuccess: ...
class TestPipelineLifecycleError: ...
class TestStepLifecycleOrdering: ...
class TestConsensusReachedPath: ...
class TestConsensusFailedPath: ...
```

### 7.4. Helper Function Convention

Module-level helpers starting with `_`:
```python
def _run_success_pipeline(seeded_session, handler): ...
def _run_pipeline_with_cache(seeded_session, handler): ...
def _consensus_events(events): ...
def _extraction_events(events): ...
```

### 7.5. Filter Helper Convention

Each module defines category-specific event filter:
```python
def _consensus_events(events):
    target_types = {"consensus_started", "consensus_attempt", "consensus_reached", "consensus_failed"}
    return [e for e in events if e["event_type"] in target_types]
```


## 8. Coverage Strategies for >90% on Events Package

### 8.1. Coverage Command

```bash
pytest tests/events/ tests/test_emitter.py --cov=llm_pipeline/events --cov-report=term-missing --cov-branch -v
```

### 8.2. What's Already Covered

- `types.py`: All 28 concrete event dataclass definitions (instantiated in tests)
- `emitter.py`: CompositeEmitter + PipelineEventEmitter protocol (20 tests)
- `handlers.py`: All 3 handlers + PipelineEventRecord (31 tests)
- `models.py`: PipelineEventRecord (tested via handlers tests)
- `__init__.py`: Re-exports only, covered transitively

### 8.3. What Needs Coverage for >90%

| Module | Uncovered Code | Recommended Tests |
|---|---|---|
| `types.py` | `_derive_event_type()` function | Parametrized CamelCase->snake_case tests |
| `types.py` | `_EVENT_REGISTRY` population logic | Verify all 28 types registered |
| `types.py` | `PipelineEvent.__init_subclass__` skip paths | Test `_skip_registry=True`, `_`-prefixed class |
| `types.py` | `resolve_event()` round-trip | Parametrized serialize/deserialize for all types |
| `types.py` | `resolve_event()` error path | Test with unknown event_type -> ValueError |
| `types.py` | `to_dict()` datetime conversion | Verify timestamp -> ISO string |
| `types.py` | `to_json()` output | Verify valid JSON string |
| `types.py` | Frozen dataclass immutability | Verify `object.__setattr__` raises FrozenInstanceError |
| `types.py` | `StepScopedEvent._skip_registry` | Verify StepScopedEvent NOT in registry |

### 8.4. Estimated Coverage Impact

| Area | Before | After |
|---|---|---|
| `types.py` | ~70% (event classes instantiated, but utilities untested) | ~95% |
| `emitter.py` | ~95% (thorough test_emitter.py) | ~98% |
| `handlers.py` | ~95% (thorough test_handlers.py) | ~97% |
| `models.py` | ~90% (tested via handler tests) | ~95% |
| `__init__.py` | ~100% (re-exports) | ~100% |
| **Overall events package** | **~85%** | **>93%** |


## 9. Specific Test Patterns for Missing Coverage

### 9.1. Event Registry Tests

```python
class TestEventRegistry:
    def test_all_28_event_types_registered(self):
        """_EVENT_REGISTRY contains exactly 28 entries."""
        assert len(_EVENT_REGISTRY) == 28

    def test_step_scoped_event_not_in_registry(self):
        """StepScopedEvent has _skip_registry=True, should NOT be registered."""
        assert "step_scoped_event" not in _EVENT_REGISTRY

    def test_pipeline_event_base_not_in_registry(self):
        """PipelineEvent base class should NOT be in registry (no derived type)."""
        assert "pipeline_event" not in _EVENT_REGISTRY
```

### 9.2. Frozen Immutability Tests

```python
class TestEventImmutability:
    def test_frozen_prevents_field_reassignment(self):
        """Frozen dataclass raises FrozenInstanceError on field assignment."""
        event = PipelineStarted(run_id="r1", pipeline_name="p1")
        with pytest.raises(AttributeError):  # FrozenInstanceError is subclass of AttributeError
            event.run_id = "changed"

    def test_frozen_prevents_new_attribute(self):
        """Frozen dataclass + slots prevents adding new attributes."""
        event = PipelineStarted(run_id="r1", pipeline_name="p1")
        with pytest.raises(AttributeError):
            event.new_attr = "nope"
```

### 9.3. Serialization Tests

```python
class TestEventSerialization:
    def test_to_dict_contains_all_fields(self):
        event = PipelineCompleted(run_id="r1", pipeline_name="p1",
                                  execution_time_ms=100.0, steps_executed=2)
        d = event.to_dict()
        assert d["run_id"] == "r1"
        assert d["event_type"] == "pipeline_completed"
        assert d["execution_time_ms"] == 100.0
        assert isinstance(d["timestamp"], str)  # datetime -> ISO string

    def test_to_json_returns_valid_json(self):
        import json
        event = PipelineStarted(run_id="r1", pipeline_name="p1")
        j = event.to_json()
        parsed = json.loads(j)
        assert parsed["run_id"] == "r1"

    def test_resolve_event_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown event_type"):
            PipelineEvent.resolve_event("nonexistent_event", {})
```

### 9.4. End-to-End Event Flow Test

```python
class TestFullPipelineEventFlow:
    def test_successful_pipeline_full_event_sequence(self, seeded_session, in_memory_handler):
        """Verify complete event ordering for 2-step successful pipeline."""
        provider = MockProvider(responses=[
            {"count": 1, "notes": "first"},
            {"count": 2, "notes": "second"},
        ])
        pipeline = SuccessPipeline(
            session=seeded_session, provider=provider, event_emitter=in_memory_handler,
        )
        pipeline.execute(data="test data", initial_context={})

        events = in_memory_handler.get_events()
        types = [e["event_type"] for e in events]

        # First event must be pipeline_started, last must be pipeline_completed
        assert types[0] == "pipeline_started"
        assert types[-1] == "pipeline_completed"

        # All events share same run_id
        run_ids = {e["run_id"] for e in events}
        assert len(run_ids) == 1

        # Step 1 sequence
        # (verify ordering within step 1 events)
```


## 10. Summary of Recommendations

### New Test Files to Create

1. **`tests/events/test_event_types.py`** -- Unit tests for event type system mechanics
   - `_derive_event_type()` parametrized (all 28 class names)
   - `_EVENT_REGISTRY` completeness (28 entries, no bases)
   - `resolve_event()` round-trip (parametrized over all 28 types)
   - `resolve_event()` error path (unknown event_type)
   - `to_dict()` / `to_json()` serialization
   - Frozen dataclass immutability
   - EVENT_CATEGORY on all concrete types
   - StepScopedEvent skip registry

2. **`tests/events/test_end_to_end_event_flow.py`** -- Cross-cutting integration tests
   - Full event sequence for successful 2-step pipeline
   - Full event sequence for error pipeline
   - Full event sequence for cached pipeline
   - run_id consistency across all events
   - timestamp monotonicity

### No Changes Needed To

- Existing conftest.py (well-structured)
- Existing test files (comprehensive for their categories)
- test_emitter.py (CompositeEmitter already well-tested)

### Coverage Target

With the 2 new test files above, estimated coverage for `llm_pipeline/events/` goes from ~85% to >93%.
