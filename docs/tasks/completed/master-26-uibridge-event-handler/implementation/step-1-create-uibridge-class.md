# IMPLEMENTATION - STEP 1: CREATE UIBRIDGE CLASS
**Status:** completed

## Summary
Created `llm_pipeline/ui/bridge.py` with `UIBridge` class -- a thin sync adapter implementing `PipelineEventEmitter` protocol that delegates to `ConnectionManager.broadcast_to_run()`.

## Files
**Created:** `llm_pipeline/ui/bridge.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/bridge.py`
New file implementing UIBridge with:
- `__init__(run_id, manager=None)` -- stores run_id, lazy-imports singleton if manager is None, inits `_completed = False`
- `emit(event)` -- calls `broadcast_to_run(run_id, event.to_dict())`, auto-detects terminal events and calls `complete()`
- `complete()` -- idempotent guard, calls `signal_run_complete(run_id)` at most once
- `__repr__` -- returns `UIBridge(run_id=...)`
- `__slots__` for memory efficiency
- Module docstring documenting sync delegation, spec deviation, threading model
- `__all__ = ["UIBridge"]`

```python
# Key implementation pattern
def emit(self, event: PipelineEvent) -> None:
    self._manager.broadcast_to_run(self.run_id, event.to_dict())
    if isinstance(event, (PipelineCompleted, PipelineError)):
        self.complete()

def complete(self) -> None:
    if not self._completed:
        self._completed = True
        self._manager.signal_run_complete(self.run_id)
```

## Decisions
### Lazy import for singleton
**Choice:** Import `manager` singleton inside `__init__` body, not at module level
**Rationale:** Avoids circular import (bridge.py -> routes/websocket.py -> potentially back). TYPE_CHECKING guard used for ConnectionManager type hint.

### `from __future__ import annotations`
**Choice:** Use PEP 604 union syntax (`ConnectionManager | None`) with future annotations
**Rationale:** Consistent with codebase style; defers annotation evaluation so TYPE_CHECKING import works for type hints without runtime import.

### `__slots__`
**Choice:** Added `__slots__ = ("run_id", "_manager", "_completed")`
**Rationale:** Matches CompositeEmitter pattern in emitter.py; memory-efficient for potentially many UIBridge instances.

## Verification
[x] `isinstance(UIBridge(...), PipelineEventEmitter)` returns True (runtime_checkable Protocol)
[x] `repr(UIBridge(run_id='test'))` returns `UIBridge(run_id='test')`
[x] Module imports cleanly without circular import errors
[x] Full test suite passes (683 passed; 1 pre-existing failure in test_events_router_prefix unrelated to this change)
[x] `UIBridge` exported in `__all__`
