# Research: Python Event Handler Patterns for Task 6

## 1. Thread-Safe Collection Patterns (InMemoryEventHandler)

### 1.1 Pattern: threading.Lock + list

Standard Python pattern for protecting mutable shared state across threads.

```python
import threading
from llm_pipeline.events.types import PipelineEvent

class InMemoryEventHandler:
    __slots__ = ("_events", "_lock")

    def __init__(self) -> None:
        self._events: list[PipelineEvent] = []
        self._lock = threading.Lock()

    def emit(self, event: PipelineEvent) -> None:
        with self._lock:
            self._events.append(event)

    def get_events(self, run_id: str | None = None) -> list[PipelineEvent]:
        with self._lock:
            if run_id is None:
                return list(self._events)  # copy
            return [e for e in self._events if e.run_id == run_id]

    def get_events_by_type(self, event_type: str) -> list[PipelineEvent]:
        with self._lock:
            return [e for e in self._events if e.event_type == event_type]

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
```

### 1.2 Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Lock type | `threading.Lock` (not RLock) | No re-entrant scenarios. emit() never calls another Lock-protected method. Deadlock = bug signal. |
| Data structure | `list` (not deque) | Need filtering by run_id/event_type via list comprehension. No FIFO eviction required by spec. |
| Lock granularity | Single Lock for all ops | Simple, correct. All mutations and reads go through same lock. |
| Return values | New list copies | Never expose internal `_events` reference. Comprehension/list() creates copy. |
| `__slots__` | Yes | Matches CompositeEmitter pattern. Memory efficient. |

### 1.3 Why Not RLock

From task 2 research (already validated):
- Lock: deadlocks on re-entry = immediate design error signal
- RLock: silently allows re-entry, can mask bugs
- No legitimate re-entry scenario: emit() is leaf-level, query methods don't call emit()

### 1.4 CPython GIL Note

While `list.append()` is atomic under CPython's GIL, we must NOT rely on this:
- GIL is an implementation detail, not a language guarantee
- Free-threaded Python (PEP 703, Python 3.13+) removes GIL
- Explicit Lock is the portable, correct approach
- `get_events()` filtering is NOT atomic even under GIL (iterates + copies)

### 1.5 Memory Bounds

Task spec says "stores events in thread-safe list" with no bounds mention. Recommendation:

- Default: unbounded (matches UI/testing use case from spec)
- Optional: `max_events: int | None = None` constructor param for production use
- If max_events set, FIFO eviction via `self._events = self._events[-max_events:]` after append
- This is an enhancement, not required by spec. Document that `clear()` exists for manual management.

Decision: Start unbounded per spec. Add max_events only if CEO requests it.

## 2. Python Logging Best Practices (LoggingEventHandler)

### 2.1 Thread Safety

Python's `logging.Handler.emit()` internally uses a Lock. LoggingEventHandler needs NO additional threading protection. This is documented in the Python logging cookbook.

### 2.2 Configurable Log Levels per Category

Pattern: dict mapping EVENT_CATEGORY constants -> logging level integers.

```python
import logging
from llm_pipeline.events.types import (
    CATEGORY_PIPELINE_LIFECYCLE, CATEGORY_STEP_LIFECYCLE,
    CATEGORY_CACHE, CATEGORY_LLM_CALL, CATEGORY_CONSENSUS,
    CATEGORY_INSTRUCTIONS_CONTEXT, CATEGORY_TRANSFORMATION,
    CATEGORY_EXTRACTION, CATEGORY_STATE,
)

DEFAULT_LEVEL_MAP: dict[str, int] = {
    CATEGORY_PIPELINE_LIFECYCLE: logging.INFO,
    CATEGORY_STEP_LIFECYCLE: logging.INFO,
    CATEGORY_CACHE: logging.DEBUG,
    CATEGORY_LLM_CALL: logging.DEBUG,
    CATEGORY_CONSENSUS: logging.INFO,
    CATEGORY_INSTRUCTIONS_CONTEXT: logging.DEBUG,
    CATEGORY_TRANSFORMATION: logging.DEBUG,
    CATEGORY_EXTRACTION: logging.DEBUG,
    CATEGORY_STATE: logging.DEBUG,
}
```

Constructor accepts optional override dict that merges with defaults:

```python
class LoggingEventHandler:
    def __init__(self, level_map: dict[str, int] | None = None) -> None:
        self._level_map = {**DEFAULT_LEVEL_MAP, **(level_map or {})}
```

### 2.3 Logger Naming

Use module-level `logger = logging.getLogger(__name__)` which resolves to `llm_pipeline.events.handlers`. Matches codebase pattern (every module uses `__name__`).

Alternative: `logging.getLogger("llm_pipeline.events")` for package-level grouping. But `__name__` is simpler and consistent.

Decision: `__name__` (= `llm_pipeline.events.handlers`).

### 2.4 Log Message Format

Structured but human-readable. Include essential context fields:

```python
def emit(self, event: PipelineEvent) -> None:
    category = getattr(type(event), "EVENT_CATEGORY", "unknown")
    level = self._level_map.get(category, logging.DEBUG)
    logger.log(
        level,
        "[%s] %s run=%s pipeline=%s",
        category,
        event.event_type,
        event.run_id[:8],
        event.pipeline_name,
    )
```

Key format decisions:
- `run_id[:8]` truncation: UUIDs are 36 chars, first 8 is sufficient for log readability
- Use `%s` format (lazy evaluation) not f-strings per Python logging best practice
- Category in brackets for grep/filter friendliness
- Don't log full event.to_dict() at default level (too verbose); could add at TRACE/DEBUG-5

### 2.5 Supplementing Existing Logging

Task spec: "Supplements existing logger.info calls, doesn't replace."

Existing pipeline.py uses `logger = logging.getLogger(__name__)` (= `llm_pipeline.pipeline`). LoggingEventHandler uses `llm_pipeline.events.handlers`. Different logger namespaces = no conflict. Both fire independently.

### 2.6 Structured Logging Compatibility

For users with JSON formatters (structlog, python-json-logger), include event data in `extra`:

```python
logger.log(level, msg, extra={"event_data": event.to_dict()})
```

Default formatter ignores `extra` fields, so no impact on basic usage. JSON formatters pick it up automatically. Safe to include always.

Decision: Include `extra={"event_data": event.to_dict()}` for structured logging compatibility.

### 2.7 EVENT_CATEGORY Access

PipelineEvent base class does NOT define EVENT_CATEGORY. Only concrete subclasses do (as ClassVar). Safe access pattern:

```python
category = getattr(type(event), "EVENT_CATEGORY", "unknown")
```

This handles any event (including hypothetical future events without category).

## 3. Protocol Class Patterns (Python 3.11+ with Pydantic v2)

### 3.1 Structural Conformance (No Inheritance)

PipelineEventEmitter is a `@runtime_checkable Protocol` with single method `emit(event: PipelineEvent) -> None`.

Handler classes should NOT explicitly inherit PipelineEventEmitter. They structurally conform by implementing `emit()`. This is the Protocol's purpose: duck typing.

From task 2 research: "Protocol inheritance is optional, for documentation." First-party handlers in the same package don't need it for discoverability.

Verification: `isinstance(handler, PipelineEventEmitter)` returns True for any object with `emit` attribute (runtime_checkable only checks attribute existence, not signatures).

### 3.2 No Pydantic Involvement

PipelineEvent is a stdlib `@dataclass(frozen=True, slots=True)`, NOT a Pydantic BaseModel. Handlers receive plain dataclass instances. No Pydantic validation, serialization, or schema generation in the handler layer.

PipelineConfig.__init__ accepts `event_emitter: Optional[PipelineEventEmitter] = None` as plain Python parameter (PipelineConfig is ABC, not Pydantic). No type adapter needed.

### 3.3 Frozen Dataclass Implications

Since PipelineEvent is frozen:
- Handlers cannot modify events (immutability guarantee)
- Same event instance safely passed to multiple handlers via CompositeEmitter
- No defensive copying needed
- Thread-safe reads (no writes after construction)

### 3.4 __repr__ Convention

Codebase CompositeEmitter defines `__repr__`. Handlers should too for debugging:

```python
def __repr__(self) -> str:
    return f"LoggingEventHandler(levels={len(self._level_map)})"
```

## 4. Event Filtering/Querying Patterns

### 4.1 Query Methods (InMemoryEventHandler)

Task spec defines two query methods:
- `get_events(run_id: str)` - filter by run_id
- `get_events_by_type(event_type: str)` - filter by event_type string

### 4.2 Implementation Pattern

Lock-protected list comprehension returning new list:

```python
def get_events(self, run_id: str | None = None) -> list[PipelineEvent]:
    with self._lock:
        if run_id is None:
            return list(self._events)
        return [e for e in self._events if e.run_id == run_id]

def get_events_by_type(self, event_type: str) -> list[PipelineEvent]:
    with self._lock:
        return [e for e in self._events if e.event_type == event_type]
```

### 4.3 Design Notes

- `get_events()` with `run_id=None` returns ALL events (useful for testing assertions)
- `get_events_by_type()` uses `event_type` string (snake_case, e.g. "pipeline_started") matching `event.event_type` field
- Both return copies: caller can mutate returned list without affecting handler state
- Lock held during iteration: brief for typical event counts (tens to hundreds in a pipeline run)
- No indexing optimization needed: linear scan is O(n) where n is total events. Pipeline runs produce ~50-200 events. Negligible.

### 4.4 Not Adding (Out of Scope)

- `get_events_by_category()` - not in task spec
- Iterator/generator patterns - not needed for small collections
- Async query methods - pipeline is sync
- Predicate-based filtering (`get_events(filter=lambda e: ...)`) - YAGNI

## 5. Error Handling in Event Handlers

### 5.1 Architecture: Two Layers of Protection

**Layer 1: CompositeEmitter (existing, from task 2)**
```python
# Already implemented in emitter.py
for handler in self._handlers:
    try:
        handler.emit(event)
    except Exception:
        logger.exception("Handler %r failed for event %s", handler, event.event_type)
```

Catches `Exception` (not `BaseException`), logs traceback, continues to next handler. This ensures a failing handler NEVER crashes the pipeline.

**Layer 2: Handler internal (task 6)**
Handlers should NOT add their own try/except around the entire emit(). Let exceptions propagate to CompositeEmitter's catch. Reasons:
- Avoids double-logging of the same error
- CompositeEmitter's isolation is the canonical error boundary
- Handlers swallowing errors silently makes debugging harder

### 5.2 Per-Handler Error Scenarios

| Handler | Failure Mode | Strategy |
|---|---|---|
| LoggingEventHandler | Logger misconfigured, to_dict() fails | Propagate to CompositeEmitter |
| InMemoryEventHandler | Lock acquisition timeout (theoretical) | Propagate to CompositeEmitter |
| SQLiteEventHandler | DB write failure (disk full, schema mismatch, connection lost) | Propagate to CompositeEmitter |

### 5.3 Internal Defensive Checks

Handlers MAY include lightweight defensive checks that DON'T use try/except:

```python
# LoggingEventHandler - safe category lookup with fallback
category = getattr(type(event), "EVENT_CATEGORY", "unknown")
level = self._level_map.get(category, logging.DEBUG)
```

These handle edge cases (unknown category, missing attribute) without exceptions.

### 5.4 Handler Shouldn't Crash Pipeline - Summary

The guarantee "handlers shouldn't crash the pipeline" is fulfilled by:
1. CompositeEmitter catches all handler exceptions
2. PipelineConfig._emit() only calls emitter if configured (None check)
3. Handlers don't need internal catch-all - that would mask bugs

## 6. Implementation Skeleton (All Three Handlers)

### 6.1 File: `llm_pipeline/events/handlers.py`

```python
"""Concrete PipelineEventEmitter implementations.

Three handlers for different use cases:
- LoggingEventHandler: Python logging with configurable levels per category
- InMemoryEventHandler: Thread-safe in-memory storage with query methods
- SQLiteEventHandler: Persistent storage to pipeline_events table
"""
import logging
import threading

from llm_pipeline.events.types import (
    PipelineEvent,
    CATEGORY_PIPELINE_LIFECYCLE,
    CATEGORY_STEP_LIFECYCLE,
    CATEGORY_CACHE,
    CATEGORY_LLM_CALL,
    CATEGORY_CONSENSUS,
    CATEGORY_INSTRUCTIONS_CONTEXT,
    CATEGORY_TRANSFORMATION,
    CATEGORY_EXTRACTION,
    CATEGORY_STATE,
)

logger = logging.getLogger(__name__)

# -- Default log level mapping ------------------------------------------------

DEFAULT_LEVEL_MAP: dict[str, int] = {
    CATEGORY_PIPELINE_LIFECYCLE: logging.INFO,
    CATEGORY_STEP_LIFECYCLE: logging.INFO,
    CATEGORY_CACHE: logging.DEBUG,
    CATEGORY_LLM_CALL: logging.DEBUG,
    CATEGORY_CONSENSUS: logging.INFO,
    CATEGORY_INSTRUCTIONS_CONTEXT: logging.DEBUG,
    CATEGORY_TRANSFORMATION: logging.DEBUG,
    CATEGORY_EXTRACTION: logging.DEBUG,
    CATEGORY_STATE: logging.DEBUG,
}


# -- LoggingEventHandler ------------------------------------------------------

class LoggingEventHandler:
    """Emit pipeline events to Python logging with per-category log levels.

    Supplements (does not replace) existing logger.info calls in pipeline.py.
    Thread-safe: Python logging.Handler.emit() uses internal Lock.

    Args:
        level_map: Optional dict mapping EVENT_CATEGORY -> logging level.
            Merges with DEFAULT_LEVEL_MAP (overrides take precedence).
        logger_name: Optional logger name override (default: module __name__).
    """

    __slots__ = ("_level_map", "_logger")

    def __init__(
        self,
        level_map: dict[str, int] | None = None,
        logger_name: str | None = None,
    ) -> None:
        self._level_map = {**DEFAULT_LEVEL_MAP, **(level_map or {})}
        self._logger = logging.getLogger(logger_name or __name__)

    def emit(self, event: PipelineEvent) -> None:
        category = getattr(type(event), "EVENT_CATEGORY", "unknown")
        level = self._level_map.get(category, logging.DEBUG)
        self._logger.log(
            level,
            "[%s] %s run=%s pipeline=%s",
            category,
            event.event_type,
            event.run_id[:8],
            event.pipeline_name,
            extra={"event_data": event.to_dict()},
        )

    def __repr__(self) -> str:
        return f"LoggingEventHandler(levels={len(self._level_map)})"


# -- InMemoryEventHandler -----------------------------------------------------

class InMemoryEventHandler:
    """Store pipeline events in thread-safe list with query methods.

    Intended for UI consumers and testing. Events stored in insertion order.

    Thread-safe: all mutations and reads protected by threading.Lock.
    Query methods return copies (never expose internal list).

    Args:
        (none - stateless construction)
    """

    __slots__ = ("_events", "_lock")

    def __init__(self) -> None:
        self._events: list[PipelineEvent] = []
        self._lock = threading.Lock()

    def emit(self, event: PipelineEvent) -> None:
        with self._lock:
            self._events.append(event)

    def get_events(self, run_id: str | None = None) -> list[PipelineEvent]:
        """Return events, optionally filtered by run_id.

        Returns new list (safe to mutate without affecting handler state).
        """
        with self._lock:
            if run_id is None:
                return list(self._events)
            return [e for e in self._events if e.run_id == run_id]

    def get_events_by_type(self, event_type: str) -> list[PipelineEvent]:
        """Return events matching event_type string (e.g. 'pipeline_started')."""
        with self._lock:
            return [e for e in self._events if e.event_type == event_type]

    def clear(self) -> None:
        """Remove all stored events."""
        with self._lock:
            self._events.clear()

    def __repr__(self) -> str:
        with self._lock:
            return f"InMemoryEventHandler(events={len(self._events)})"

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)


# -- SQLiteEventHandler -------------------------------------------------------
# (Implementation details deferred to step-3 database schema research)
# Key patterns from this step:
# - No internal try/except: let CompositeEmitter handle errors
# - emit() serializes event via to_dict()/to_json()
# - Query methods mirror InMemoryEventHandler interface
# - Uses existing SQLAlchemy/SQLModel infrastructure


__all__ = [
    "DEFAULT_LEVEL_MAP",
    "LoggingEventHandler",
    "InMemoryEventHandler",
]
```

### 6.2 Exports Update

`llm_pipeline/events/__init__.py` should add handler imports (task 18 scope, noted here for awareness).

## 7. Codebase Consistency Checklist

| Aspect | Pattern | Source |
|---|---|---|
| Module docstring | Multi-line, describes purpose | types.py, emitter.py |
| Logger | `logger = logging.getLogger(__name__)` | All modules |
| `__all__` | Explicit list at module bottom | All modules |
| `__slots__` | Used on handler classes | CompositeEmitter precedent |
| `__repr__` | Defined on all classes | CompositeEmitter precedent |
| Type hints | Full annotations, `str | None` union syntax | Python 3.11+ style, types.py |
| Docstrings | Google-style | provider.py, strategy.py |
| No `from __future__ import annotations` | Omit for consistency with events package | types.py rationale (slots issue) |
| Error handling | Propagate to CompositeEmitter | emitter.py error isolation |

## 8. Upstream Deviations Check

### Task 1 (PipelineEvent types) - Status: done
- EVENT_CATEGORY is ClassVar on concrete subclasses, not on PipelineEvent base
- to_dict() and to_json() available for serialization
- No deviations affecting task 6

### Task 2 (PipelineEventEmitter + CompositeEmitter) - Status: done
- Protocol is @runtime_checkable with single emit() method
- CompositeEmitter uses immutable tuple, error isolation via try/except
- PipelineConfig already has _emit() helper and event_emitter param
- No deviations affecting task 6

## 9. Downstream Scope Boundaries

### Task 8 (Emit Pipeline Lifecycle Events) - OUT OF SCOPE
Modifies pipeline.py execute() to emit PipelineStarted/Completed/Error. Depends on task 6 handlers existing.

### Task 18 (Export Event System in Package __init__) - OUT OF SCOPE
Updates llm_pipeline/__init__.py exports. Will import handlers once implemented.

### Task 26 (UIBridge Event Handler) - OUT OF SCOPE
Async bridge handler. Different pattern (asyncio queue). Depends on task 6 for handler precedent.
