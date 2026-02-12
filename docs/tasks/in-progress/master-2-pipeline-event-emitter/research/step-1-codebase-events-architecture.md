# Research Step 1: Codebase & Events Architecture

## Upstream Task (Task 1) Status

Task 1 (PipelineEvent base + event types) is **done**. All artifacts are in place.

### Key Deliverables from Task 1
- `llm_pipeline/events/types.py`: 31 concrete event dataclasses, PipelineEvent + StepScopedEvent bases, auto-registration via `__init_subclass__`, `_EVENT_REGISTRY`
- `llm_pipeline/llm/result.py`: LLMCallResult frozen+slots dataclass
- `llm_pipeline/events/__init__.py`: Re-exports all events, LLMCallResult, category constants, `resolve_event` helper

### Deviations from Plan (Task 1)
- LLMCallResult fields differ from PLAN.md (follows PRD PS-2 instead)
- Several event field names differ from PLAN.md (follows task spec)
- No `from __future__ import annotations` in types.py due to slots+`__init_subclass__` CPython edge case
- Private symbols removed from `__all__`

No deviations affect Task 2 design.

## Existing Protocol Pattern

**File:** `llm_pipeline/prompts/variables.py`

```python
from typing import Optional, Protocol, Type, runtime_checkable
from pydantic import BaseModel

@runtime_checkable
class VariableResolver(Protocol):
    def resolve(self, prompt_key: str, prompt_type: str) -> Optional[Type[BaseModel]]:
        ...
```

Pattern characteristics:
- `@runtime_checkable` decorator (enables isinstance() checks)
- Single-method protocol
- Docstring with usage example showing duck-typing
- Module-level `__all__` export
- No ABC, no metaclass

**Recommendation:** Follow same pattern for PipelineEventEmitter. Use `@runtime_checkable`.

## Event System Architecture

### PipelineEvent Base (`events/types.py`)

```
PipelineEvent (frozen=True, slots=True)
  fields: run_id, pipeline_name, timestamp, event_type (init=False, derived)
  methods: to_dict(), to_json(), resolve_event() classmethod
  class var: _EVENT_REGISTRY (dict[str, type[PipelineEvent]])
  |
  +-- StepScopedEvent (_skip_registry=True)
        field: step_name: str | None = None
        |
        +-- 28 concrete events (step lifecycle, cache, LLM, consensus, etc.)
  |
  +-- 3 pipeline-level events (PipelineStarted, PipelineCompleted, PipelineError)
```

### Key Design Points for Emitter
- Events are **frozen dataclasses** - no mutation concern when passing to multiple handlers
- Events carry `event_type: str` (derived from class name, snake_case) and `EVENT_CATEGORY: ClassVar[str]`
- The `emit(event: PipelineEvent)` signature is type-safe since all concrete events inherit PipelineEvent

## Logging Pattern

All modules use:
```python
import logging
logger = logging.getLogger(__name__)
```

Files using this: pipeline.py, step.py, executor.py, rate_limiter.py, validation.py, loader.py, gemini.py, db/__init__.py

CompositeEmitter should follow this same pattern for error logging.

## Threading Status

**No existing threading in codebase.** No imports of `threading`, `Lock`, `RLock`, or thread-related modules anywhere.

RateLimiter (`llm_pipeline/llm/rate_limiter.py`) uses plain list without locks - not thread-safe.

CompositeEmitter will be the **first thread-safe component** in the codebase.

**Thread-safety design:**
- Use `threading.Lock` to protect handler list access
- Store handlers as `tuple` (immutable) to enable lock-free iteration after snapshot
- Lock only held during tuple copy, not during handler.emit() calls
- This prevents a handler's long-running emit() from blocking other threads

## Error Handling Patterns

| Module | Pattern |
|--------|---------|
| pipeline.py | try/except with logger.info/error, continues execution |
| executor.py | try/except, returns failure objects (create_failure) |
| LLMProvider | Returns None on failure |
| step.py extract_data | try/finally for cleanup |

CompositeEmitter error isolation should: catch Exception (not BaseException), log at `logger.error` level with exc_info, continue to next handler. Consistent with codebase pattern of "catch, log, continue."

## Export Structure

### Current events/__init__.py exports
- All 31 event types + PipelineEvent + StepScopedEvent
- LLMCallResult
- 9 category constants
- resolve_event helper
- `_EVENT_REGISTRY` and `_derive_event_type` imported but NOT in `__all__`

### Required additions for Task 2
- `PipelineEventEmitter` (Protocol)
- `CompositeEmitter` (concrete class)
- Both added to events/__init__.py `__all__`

### Package __init__.py (`llm_pipeline/__init__.py`)
- Does NOT currently import from events/
- Task 18 (downstream, out of scope) handles package-level exports

## File Placement

Target file: `llm_pipeline/events/emitter.py`

Imports needed:
```python
from __future__ import annotations  # safe here, no slots+__init_subclass__ issue
import logging
import threading
from typing import Protocol, runtime_checkable
from llm_pipeline.events.types import PipelineEvent
```

## Downstream Tasks (OUT OF SCOPE)

- **Task 6** (pending): Implements LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler - these consume the Protocol
- **Task 7** (pending): Adds `event_emitter: Optional[PipelineEventEmitter] = None` to PipelineConfig.__init__() with `_emit()` helper
- **Task 18** (pending): Package-level exports in llm_pipeline/__init__.py

## Implementation Blueprint

### PipelineEventEmitter Protocol
```python
@runtime_checkable
class PipelineEventEmitter(Protocol):
    def emit(self, event: PipelineEvent) -> None: ...
```

### CompositeEmitter
- Constructor: `__init__(self, handlers: Iterable[PipelineEventEmitter])`
- Store as `tuple` (immutable snapshot)
- `emit()`: acquire lock, copy tuple ref, release lock, iterate and call each handler with try/except
- Thread safety via `threading.Lock`
- Error isolation: catch Exception per handler, log with `logger.error(..., exc_info=True)`
- `handlers` property: returns tuple (read-only access)

### No `from __future__ import annotations` Issue
Unlike `events/types.py`, the emitter module has no `slots=True` + `__init_subclass__` interaction. Safe to use future annotations if desired, but not required since all types are runtime-available.
