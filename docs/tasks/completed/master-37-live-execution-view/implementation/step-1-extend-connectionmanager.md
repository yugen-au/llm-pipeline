# IMPLEMENTATION - STEP 1: EXTEND CONNECTIONMANAGER
**Status:** completed

## Summary
Added global subscriber support to the existing ConnectionManager singleton: `_global_queues` list, `connect_global()`, `disconnect_global()`, and `broadcast_global()` methods. All sync and thread-safe via `put_nowait`, matching existing per-run pattern.

## Files
**Created:** none
**Modified:** `llm_pipeline/ui/routes/websocket.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/websocket.py`
Added `_global_queues` field to `__init__` and three new methods to `ConnectionManager`.

```python
# Before (ConnectionManager.__init__)
def __init__(self) -> None:
    self._connections: dict[str, list[WebSocket]] = defaultdict(list)
    self._queues: dict[str, list[thread_queue.Queue]] = defaultdict(list)

# After
def __init__(self) -> None:
    self._connections: dict[str, list[WebSocket]] = defaultdict(list)
    self._queues: dict[str, list[thread_queue.Queue]] = defaultdict(list)
    self._global_queues: list[thread_queue.Queue] = []
```

```python
# New methods added after signal_run_complete:

def connect_global(self, ws: WebSocket) -> thread_queue.Queue:
    """Register a global subscriber, return its dedicated event queue."""
    queue: thread_queue.Queue = thread_queue.Queue()
    self._global_queues.append(queue)
    return queue

def disconnect_global(self, queue: thread_queue.Queue) -> None:
    """Unregister a global subscriber. Safe if not present."""
    try:
        self._global_queues.remove(queue)
    except ValueError:
        pass

def broadcast_global(self, event_data: dict) -> None:
    """Fan-out an event dict to every global subscriber. Sync, thread-safe."""
    for q in self._global_queues:
        q.put_nowait(event_data)
```

## Decisions
### disconnect_global uses try/except vs conditional check
**Choice:** `try: remove() except ValueError: pass` instead of `if queue in list: remove()`
**Rationale:** EAFP is more Pythonic and avoids TOCTOU race between check and remove. Matches the safety guarantee in the method contract.

### Flat list vs dict for global queues
**Choice:** `list[thread_queue.Queue]` (flat list, no keying)
**Rationale:** Global subscribers have no run_id to key by. Plan explicitly calls for flat list parallel to existing `_queues` dict but simpler.

## Verification
[x] `python -c "from llm_pipeline.ui.routes.websocket import manager"` -- imports clean
[x] All 3 new methods present on singleton: `connect_global`, `disconnect_global`, `broadcast_global`
[x] `_global_queues` initialized as empty list
[x] 16/16 existing websocket tests pass (no regressions)
[x] Pre-existing failure (`test_events_router_prefix`) unrelated to this change

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] Thread safety of `_global_queues` list iteration during concurrent mutation in `broadcast_global`
[x] Same issue in pre-existing `broadcast_to_run` and `signal_run_complete`

### Changes Made
#### File: `llm_pipeline/ui/routes/websocket.py`
Snapshot list before iteration in all three broadcast/signal methods to prevent IndexError or skipped items from concurrent connect/disconnect mutations.

```python
# Before (broadcast_to_run)
for q in self._queues.get(run_id, []):

# After
for q in list(self._queues.get(run_id, [])):
```

```python
# Before (signal_run_complete)
for q in self._queues.get(run_id, []):

# After
for q in list(self._queues.get(run_id, [])):
```

```python
# Before (broadcast_global)
for q in self._global_queues:

# After
for q in list(self._global_queues):
```

### Verification
[x] 16/16 websocket tests pass
[x] `list()` snapshot is O(n) but n is tiny (number of connected WS clients per run)
