# Research: Python Protocol & Thread Safety for PipelineEventEmitter

## 1. typing.Protocol Best Practices (Python 3.11+)

### 1.1 Structural Subtyping Fundamentals

`typing.Protocol` enables structural subtyping (static duck typing). Any class matching the Protocol's method signatures is considered compatible without explicit inheritance.

```python
from typing import Protocol

class PipelineEventEmitter(Protocol):
    def emit(self, event: PipelineEvent) -> None: ...

# This works without inheriting PipelineEventEmitter:
class MyHandler:
    def emit(self, event: PipelineEvent) -> None:
        print(event)
```

Key behaviors (CPython 3.11+):
- Static type checkers (mypy, pyright) validate structural conformance at call sites
- No runtime overhead unless `@runtime_checkable` is used
- Protocol methods use `...` (Ellipsis) as body, not `pass`
- Protocol classes should NOT define `__init__` (they describe interface, not construction)

### 1.2 @runtime_checkable Decision

**Recommendation: Use `@runtime_checkable`.**

Rationale:
- Existing codebase precedent: `VariableResolver` in `llm_pipeline/prompts/variables.py` uses `@runtime_checkable`
- Enables `isinstance(obj, PipelineEventEmitter)` checks useful for:
  - CompositeEmitter constructor validation (defensive, optional)
  - Debugging/introspection
  - Downstream task 7 (PipelineConfig could validate the parameter)
- Performance: Single `hasattr` check per method. Negligible for single-method Protocol.

Limitations of `@runtime_checkable`:
- Only checks method **existence**, not signatures
- Cannot verify parameter types or return type at runtime
- `isinstance` may return True for objects that would fail static type checking
- These limitations are acceptable for a single-method Protocol

### 1.3 Codebase Pattern Consistency

| Interface Type | Usage in Codebase | Pattern |
|---|---|---|
| `Protocol` | `VariableResolver` (prompts/variables.py) | `@runtime_checkable`, single method, duck-typing |
| `ABC` | `LLMProvider` (llm/provider.py) | Required explicit subclassing, multiple methods |
| `ABC` | `PipelineStrategy` (strategy.py) | Required explicit subclassing, `__init_subclass__` |
| `ABC` | `PipelineConfig` (pipeline.py) | Required explicit subclassing, complex lifecycle |

**Pattern rule**: Protocol for simple duck-typed interfaces (1-2 methods, no state). ABC for complex hierarchies requiring explicit opt-in and shared implementation.

PipelineEventEmitter fits Protocol: single method, stateless interface, duck-typing desired.

## 2. Thread Safety Patterns

### 2.1 threading.Lock vs RLock

**Recommendation: `threading.Lock`.**

| Feature | Lock | RLock |
|---|---|---|
| Re-entrant | No (deadlocks) | Yes |
| Performance | Faster | ~10% slower |
| Debugging | Deadlock = immediate signal of design error | Silent re-entry can mask bugs |
| Use case | Non-recursive critical sections | Recursive/nested locking |

For CompositeEmitter:
- `emit()` iterates handlers sequentially, each handler call is isolated
- If a handler calls `emit()` on the same CompositeEmitter, that's a circular design error
- Lock makes this fail-fast (deadlock = bug signal)
- RLock would silently allow infinite recursion
- No legitimate re-entry scenario exists

### 2.2 What Needs Protection

CompositeEmitter thread safety scope:

1. **Handler tuple is immutable after construction** -- stored as `tuple`, no add/remove. No lock needed for reads.
2. **Concurrent `emit()` calls** -- multiple threads calling `emit()` simultaneously. Each iterates the same tuple. Since tuple is immutable and each handler call is independent, **no lock needed for the iteration itself**.
3. **Handler internal state** -- each handler's own thread safety is its responsibility (e.g., InMemoryEventHandler in task 6 uses its own Lock).

**Revised recommendation**: CompositeEmitter does NOT need a Lock if:
- Handler list is stored as immutable tuple at construction
- No mutable shared state in CompositeEmitter itself
- Each handler manages its own thread safety

However, if future requirements add dynamic handler registration (add/remove at runtime), a Lock would be needed. Two design options:

**Option A: No Lock (immutable handlers) -- RECOMMENDED**
```python
class CompositeEmitter:
    def __init__(self, handlers: Iterable[PipelineEventEmitter]) -> None:
        self._handlers: tuple[PipelineEventEmitter, ...] = tuple(handlers)

    def emit(self, event: PipelineEvent) -> None:
        for handler in self._handlers:
            try:
                handler.emit(event)
            except Exception:
                logger.exception("Handler %r failed for %s", handler, event.event_type)
```

**Option B: Lock (mutable handlers)**
```python
class CompositeEmitter:
    def __init__(self, handlers: Iterable[PipelineEventEmitter]) -> None:
        self._handlers: list[PipelineEventEmitter] = list(handlers)
        self._lock = threading.Lock()

    def emit(self, event: PipelineEvent) -> None:
        with self._lock:
            handlers = list(self._handlers)  # snapshot under lock
        for handler in handlers:
            try:
                handler.emit(event)
            except Exception:
                logger.exception(...)

    def add_handler(self, handler: PipelineEventEmitter) -> None:
        with self._lock:
            self._handlers.append(handler)
```

**Decision**: Option A is sufficient for task spec. Task spec says "accepts list of PipelineEventEmitter instances" at construction with no mention of dynamic modification. Task 7 sets emitter at PipelineConfig construction time. Store as tuple for true immutability.

If the task spec or downstream tasks explicitly require thread-safe mutable handler registration, use Option B.

### 2.3 Thread Safety for Downstream Handlers (Task 6 Context)

Each handler manages its own concurrency:
- `LoggingEventHandler`: Python logging is thread-safe by default (Handler.emit uses Lock internally)
- `InMemoryEventHandler`: Needs `threading.Lock` to protect its internal list (task 6 spec explicitly says this)
- `SQLiteEventHandler`: SQLAlchemy Session is not thread-safe; handler should create session-per-emit or use scoped_session

## 3. Error Isolation in Handler Dispatch

### 3.1 Pattern

Standard observer pattern error isolation: catch `Exception` per handler, log, continue.

```python
def emit(self, event: PipelineEvent) -> None:
    for handler in self._handlers:
        try:
            handler.emit(event)
        except Exception:
            logger.exception(
                "Event handler %r raised while processing %s",
                handler,
                event.event_type,
            )
```

Key decisions:
- Catch `Exception`, NOT `BaseException` -- let `KeyboardInterrupt`, `SystemExit` propagate
- Use `logger.exception()` which automatically includes traceback at ERROR level
- Log handler repr and event_type for debugging context
- Do NOT re-raise or collect exceptions -- fire-and-forget semantics
- Follows codebase logging pattern: `logger = logging.getLogger(__name__)`

### 3.2 Alternative: Exception Callback

For advanced use cases, CompositeEmitter could accept an error callback:
```python
ErrorCallback = Callable[[PipelineEventEmitter, PipelineEvent, Exception], None]
```

**Not recommended for task 2** -- adds complexity. Logging is sufficient per spec. Can be added later.

## 4. Duck-Typing Compatibility

### 4.1 Protocol Enables True Duck Typing

With `Protocol`, ANY object with `emit(event: PipelineEvent) -> None` is compatible:

```python
# Lambda-based handler (for testing)
class LambdaEmitter:
    def __init__(self, fn):
        self._fn = fn
    def emit(self, event):
        self._fn(event)

# Existing class with emit method (coincidental match)
class SomeExistingLogger:
    def emit(self, event):
        ...  # structurally compatible

# CompositeEmitter accepts all of these
composite = CompositeEmitter([LambdaEmitter(print), SomeExistingLogger()])
```

### 4.2 Type Checker Behavior

- mypy: Validates structural conformance. Flags if `emit` signature doesn't match.
- pyright: Same structural checking.
- Neither requires explicit `class MyHandler(PipelineEventEmitter)` inheritance.
- Explicit Protocol inheritance IS allowed but not required:
  ```python
  class MyHandler(PipelineEventEmitter):  # optional, for documentation
      def emit(self, event: PipelineEvent) -> None: ...
  ```

## 5. Protocol + PipelineEvent (Dataclass) Interaction

### 5.1 No Pydantic Involvement

`PipelineEvent` is a stdlib `@dataclass(frozen=True, slots=True)`, NOT a Pydantic model. The Protocol method signature simply uses it as a type annotation:

```python
class PipelineEventEmitter(Protocol):
    def emit(self, event: PipelineEvent) -> None: ...
```

This is a plain Python type annotation. No Pydantic validation, no schema generation, no serialization happens in the Protocol itself.

### 5.2 Frozen Dataclass as Parameter

Since PipelineEvent is frozen:
- Handlers cannot modify events (immutability guarantee)
- Safe to pass same event instance to multiple handlers
- No defensive copying needed in CompositeEmitter
- Thread-safe reads (frozen = no writes after construction)

### 5.3 PipelineConfig Uses Pydantic

Downstream task 7 adds `event_emitter: Optional[PipelineEventEmitter] = None` to PipelineConfig.__init__(). PipelineConfig is an ABC (not Pydantic), so this is a plain Python parameter. No Pydantic type adapter or schema generation needed.

## 6. Codebase Consistency Guidelines

### 6.1 File Structure

Target file: `llm_pipeline/events/emitter.py` (per task spec)

### 6.2 Module Docstring

Follow existing pattern (types.py has detailed module docstring):
```python
"""Pipeline event emitter protocol and composite handler.

PipelineEventEmitter defines the structural interface for event handlers.
CompositeEmitter dispatches events to multiple handlers with error isolation.
"""
```

### 6.3 Imports

Follow codebase patterns:
- `from typing import Protocol, runtime_checkable` (matches variables.py)
- `import logging` + `logger = logging.getLogger(__name__)` (matches all modules)
- `from llm_pipeline.events.types import PipelineEvent` (local import for type reference)

### 6.4 `__all__` Export

Every module in codebase defines `__all__`. Follow same:
```python
__all__ = ["PipelineEventEmitter", "CompositeEmitter"]
```

### 6.5 Docstring Style

Codebase uses Google-style docstrings (see provider.py, strategy.py). Follow same for Protocol and CompositeEmitter.

### 6.6 No `from __future__ import annotations`

Not needed for Protocol (unlike frozen+slots dataclass `__init_subclass__` which breaks). But also not harmful. Follow the decision from task 1: types.py omits it due to slots issue. emitter.py has no slots, so either works. For consistency with types.py in same package, omit it.

## 7. Implementation Skeleton

```python
"""Pipeline event emitter protocol and composite handler.

PipelineEventEmitter defines the structural interface for event handlers.
CompositeEmitter dispatches events to multiple handlers with error isolation.
"""
import logging
from typing import Iterable, Protocol, runtime_checkable

from llm_pipeline.events.types import PipelineEvent

logger = logging.getLogger(__name__)


@runtime_checkable
class PipelineEventEmitter(Protocol):
    """Structural interface for pipeline event handlers.

    Any object with a compatible ``emit`` method satisfies this protocol
    without explicit inheritance (duck typing).

    Example:
        class MyHandler:
            def emit(self, event: PipelineEvent) -> None:
                print(event.event_type)

        emitter: PipelineEventEmitter = MyHandler()  # valid
    """

    def emit(self, event: PipelineEvent) -> None:
        """Handle a pipeline event.

        Args:
            event: Immutable pipeline event instance.
        """
        ...


class CompositeEmitter:
    """Dispatches events to multiple handlers with error isolation.

    Handlers are stored as an immutable tuple at construction time.
    Each handler's ``emit`` is called sequentially; exceptions in one
    handler do not prevent subsequent handlers from receiving the event.

    Thread-safe for concurrent ``emit`` calls (handler tuple is immutable).

    Args:
        handlers: Iterable of objects satisfying PipelineEventEmitter protocol.
    """

    __slots__ = ("_handlers",)

    def __init__(self, handlers: Iterable[PipelineEventEmitter]) -> None:
        self._handlers: tuple[PipelineEventEmitter, ...] = tuple(handlers)

    def emit(self, event: PipelineEvent) -> None:
        """Dispatch event to all handlers, isolating per-handler errors.

        Args:
            event: Immutable pipeline event instance.
        """
        for handler in self._handlers:
            try:
                handler.emit(event)
            except Exception:
                logger.exception(
                    "Event handler %r failed for %s",
                    handler,
                    event.event_type,
                )

    @property
    def handlers(self) -> tuple[PipelineEventEmitter, ...]:
        """Read-only access to registered handlers."""
        return self._handlers


__all__ = ["PipelineEventEmitter", "CompositeEmitter"]
```

## 8. Testing Strategy Pointers

For implementation phase (not in scope for research):
- Mock handlers with `emit` method, verify all called
- Error isolation: one mock raises, verify others still called
- Thread safety: concurrent `emit` from multiple threads, verify no crashes
- Duck typing: class without explicit Protocol inheritance still works
- `isinstance` check works with `@runtime_checkable`
- Empty handler list: CompositeEmitter([]) does nothing
- Composite nesting: CompositeEmitter([CompositeEmitter([h1]), h2]) works

## 9. Upstream Task 1 Deviations (Context)

Task 1 completed with several deviations from PLAN.md (documented in SUMMARY.md):
- LLMCallResult fields differ from PLAN (follows PRD PS-2 instead)
- Event field names follow task spec over PLAN.md
- `from __future__ import annotations` omitted from types.py due to slots+`__init_subclass__` issue
- Private symbols removed from `__all__`
- InstructionsLogged added `logged_keys` field; ExtractionError added `error_type` and `validation_errors`

None of these deviations affect task 2 implementation. PipelineEvent base class and its interface are stable.

## 10. Out of Scope (Downstream Tasks)

- Task 6: Concrete handler implementations (LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler)
- Task 7: Adding event_emitter parameter to PipelineConfig
- Task 18: Full package exports in `__init__.py`
