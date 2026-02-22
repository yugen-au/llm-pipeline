# Step 1: Async/Sync Bridging Patterns for UIBridge

## Objective
Research Python async/sync bridging patterns for a UIBridge component that bridges synchronous pipeline execution (runs in threads) to async WebSocket broadcasting.

## Current Architecture Summary

### Pipeline Execution (Sync)
- `PipelineConfig.execute()` is fully synchronous
- Calls `self._emit(event)` which delegates to `PipelineEventEmitter.emit(event)`
- `PipelineEventEmitter` is a `Protocol` with sync signature: `emit(event: PipelineEvent) -> None`
- `CompositeEmitter` dispatches to multiple handlers sequentially with error isolation
- Pipeline runs triggered via `POST /api/runs` use `BackgroundTasks.add_task(run_pipeline)` -- Starlette runs this in its thread pool

### WebSocket Infrastructure (Task 25 -- Implemented)
- `ConnectionManager` singleton in `llm_pipeline/ui/routes/websocket.py`
- Uses **stdlib `queue.Queue`** (NOT `asyncio.Queue`) for per-client fan-out
- `broadcast_to_run(run_id, event_data)` -- sync, uses `put_nowait()`, thread-safe
- `signal_run_complete(run_id)` -- sync, sends `None` sentinel via `put_nowait()`
- `_stream_events()` consumes via `asyncio.to_thread(queue.get, True, timeout)` -- non-blocking on event loop
- Completed/failed runs: batch replay from persisted `PipelineEventRecord` rows

### Key Upstream Recommendation (Task 25 SUMMARY)
> "Task 26 should import manager from llm_pipeline.ui.routes.websocket and call these [broadcast_to_run, signal_run_complete] via asyncio.run_coroutine_threadsafe() or directly from the event loop thread (both are safe since the methods are sync put_nowait calls)."

Since `broadcast_to_run` and `signal_run_complete` are already sync and thread-safe, `asyncio.run_coroutine_threadsafe()` is unnecessary for calling them.

---

## Bridging Patterns Evaluated

### Pattern 1: asyncio.run_coroutine_threadsafe() + asyncio.Queue

**How it works:**
```python
class UIBridge(PipelineEventEmitter):
    def __init__(self, run_id: str, loop: asyncio.AbstractEventLoop):
        self.run_id = run_id
        self._loop = loop
        self._queue = asyncio.Queue()

    def emit(self, event: PipelineEvent) -> None:
        asyncio.run_coroutine_threadsafe(
            self._queue.put(event.to_dict()), self._loop
        )

    def complete(self):
        asyncio.run_coroutine_threadsafe(
            self._queue.put(None), self._loop
        )
```

**Mechanics:**
- `asyncio.run_coroutine_threadsafe(coro, loop)` schedules a coroutine on a running event loop from any thread
- Returns `concurrent.futures.Future` for optional result retrieval
- Thread-safe by design (uses `loop.call_soon_threadsafe` internally)
- Requires a reference to the running asyncio event loop

**Pros:**
- Standard Python pattern for sync-to-async bridging
- Well-documented in Python stdlib
- Provides backpressure via asyncio.Queue if consumer is slow

**Cons:**
- `asyncio.Queue` is NOT thread-safe natively; requires `run_coroutine_threadsafe()` wrapper for every put()
- Each `put()` schedules a coroutine on the event loop -- overhead per event
- Requires obtaining and passing the event loop reference
- **Conflicts with existing ConnectionManager architecture**: WebSocket endpoint already consumes from per-client `queue.Queue` instances, not from a UIBridge-owned `asyncio.Queue`
- Would require rewriting or bypassing ConnectionManager fan-out logic

**Verdict:** Not recommended for this codebase. The existing WebSocket infrastructure already solves thread-safe event delivery using stdlib queues.

### Pattern 2: stdlib queue.Queue with asyncio.to_thread() Consumer

**How it works:**
```python
# Producer (sync thread):
q = queue.Queue()
q.put_nowait(event_data)

# Consumer (async handler):
event = await asyncio.to_thread(q.get, True, timeout)
```

**This is exactly what ConnectionManager already implements.** The UIBridge just needs to call into it.

**Pros:**
- `queue.Queue` is inherently thread-safe (uses internal `threading.Lock`)
- `put_nowait()` is non-blocking and safe from any thread
- `asyncio.to_thread()` (Python 3.9+) dispatches blocking `get()` to threadpool, keeping event loop free
- No event loop reference needed by producer
- Already battle-tested in this codebase (task 25)

**Cons:**
- No native backpressure (unbounded queue unless maxsize set)
- `asyncio.to_thread()` consumes a thread from the default executor for each blocking get

**Verdict:** Already implemented by ConnectionManager. UIBridge should delegate to it.

### Pattern 3: ConnectionManager Delegation (Recommended)

**How it works:**
```python
class UIBridge(PipelineEventEmitter):
    def __init__(self, run_id: str, manager: ConnectionManager):
        self.run_id = run_id
        self._manager = manager

    def emit(self, event: PipelineEvent) -> None:
        self._manager.broadcast_to_run(self.run_id, event.to_dict())

    def complete(self) -> None:
        self._manager.signal_run_complete(self.run_id)
```

**Pros:**
- Zero additional threading or asyncio complexity
- Reuses existing, tested infrastructure
- `broadcast_to_run` is sync, thread-safe (`put_nowait` on each client queue)
- No event loop reference needed
- Consistent with task 25's explicit recommendation
- Fan-out to multiple WS clients handled by ConnectionManager
- Clean separation: UIBridge = emitter adapter, ConnectionManager = delivery infrastructure

**Cons:**
- Tight coupling to ConnectionManager import (can be mitigated with Protocol/interface)
- Events emitted before any WS client connects are silently dropped (acceptable -- completed runs use batch replay from persisted events)

**Verdict:** Recommended approach. Simplest, safest, consistent with existing architecture.

### Pattern 4: janus Library (Dual-Interface Queue)

**How it works:**
```python
import janus
q = janus.Queue()
# Sync side:
q.sync_q.put_nowait(data)
# Async side:
data = await q.async_q.get()
```

**Pros:**
- Single queue with both sync and async interfaces
- Proper backpressure support
- Clean API

**Cons:**
- External dependency (not in stdlib)
- Redundant with existing ConnectionManager pattern
- Would bypass existing per-client fan-out architecture

**Verdict:** Not recommended. Adds dependency for no benefit over existing infrastructure.

### Pattern 5: Callback-Based Bridge

**How it works:**
```python
class UIBridge(PipelineEventEmitter):
    def __init__(self, run_id: str, on_event: Callable[[str, dict], None]):
        self.run_id = run_id
        self._on_event = on_event

    def emit(self, event: PipelineEvent) -> None:
        self._on_event(self.run_id, event.to_dict())
```

**Pros:**
- Maximum flexibility -- caller provides delivery mechanism
- Easy to test (inject mock callback)
- No coupling to ConnectionManager

**Cons:**
- Pushes thread-safety responsibility to callback provider
- Less explicit about architectural intent
- Over-abstracted for current needs

**Verdict:** Viable but unnecessary abstraction given the clear ConnectionManager integration path.

---

## Thread Safety Analysis

### Pipeline Execution Thread Model
1. `POST /api/runs` creates a `BackgroundTasks` task
2. Starlette runs it via `anyio.to_thread.run_sync()` in default thread pool
3. Pipeline `.execute()` runs synchronously in that thread
4. `UIBridge.emit()` called from that thread

### ConnectionManager Thread Safety
- Internal state (`_connections`, `_queues`) is a `defaultdict(list)` -- not locked
- `broadcast_to_run()` iterates `self._queues.get(run_id, [])` and calls `q.put_nowait()`
- `queue.Queue.put_nowait()` is thread-safe (uses internal lock)
- `connect()` and `disconnect()` modify the dict from async handlers (event loop thread)
- `broadcast_to_run()` only reads the dict (gets list reference) then writes to queues

**Race condition surface:** If `broadcast_to_run()` (background thread) reads `_queues[run_id]` while `disconnect()` (event loop thread) removes a queue from the list, the iteration could see a stale list. However, Python's GIL ensures list iteration over a snapshot is safe (list operations are atomic at the bytecode level for simple get/append/remove). The existing implementation in task 25 accepted this as sufficient.

### UIBridge Thread Safety with Delegation
- `UIBridge.emit()` -> `manager.broadcast_to_run(run_id, event_data)` -> `queue.Queue.put_nowait()`
- Thread-safe: `put_nowait()` acquires internal lock
- `event.to_dict()` produces a new dict each call (no shared mutable state)
- `PipelineEvent` dataclasses are frozen -- immutable after creation

**Conclusion:** Delegation to ConnectionManager provides thread safety without additional synchronization in UIBridge.

---

## Event Loop Reference Considerations

### When Needed
- Only if using `asyncio.run_coroutine_threadsafe()` (Pattern 1)
- Must be the loop currently running in the main thread

### How to Obtain in FastAPI
```python
# From async context (handler creating UIBridge):
loop = asyncio.get_running_loop()

# From sync context (NOT reliable):
loop = asyncio.get_event_loop()  # deprecated warning in 3.12+
```

### With Recommended Pattern (Pattern 3)
- NOT needed. ConnectionManager delegation is fully synchronous.
- Eliminates entire class of "wrong event loop" bugs.

---

## Integration Pattern (How UIBridge Fits)

### Pipeline Factory in trigger_run()
```python
def run_pipeline() -> None:
    from llm_pipeline.ui.routes.websocket import manager

    bridge = UIBridge(run_id=run_id, manager=manager)
    sqlite_handler = SQLiteEventHandler(engine)
    emitter = CompositeEmitter(handlers=[bridge, sqlite_handler])

    pipeline = factory(run_id=run_id, engine=engine, event_emitter=emitter)
    try:
        pipeline.execute()
        pipeline.save()
    finally:
        bridge.complete()
```

### Event Flow
```
Pipeline.execute() [background thread]
    -> self._emit(event)
    -> CompositeEmitter.emit(event)
        -> UIBridge.emit(event)
            -> manager.broadcast_to_run(run_id, event.to_dict())
                -> queue.Queue.put_nowait(event_data) [per client]
        -> SQLiteEventHandler.emit(event)
            -> DB persist

WebSocket handler [event loop thread]
    -> _stream_events()
        -> asyncio.to_thread(queue.get, ...)
        -> await websocket.send_json(event_data)
```

### Lifecycle
1. Client connects to `/ws/runs/{run_id}` -- ConnectionManager registers per-client queue
2. Pipeline triggers in background thread with UIBridge + SQLiteEventHandler
3. UIBridge.emit() -> manager.broadcast_to_run() -> per-client queues
4. WS handler consumes from its queue, sends to client
5. Pipeline completes -> UIBridge.complete() -> manager.signal_run_complete()
6. WS handler receives None sentinel, sends `stream_complete`, closes
7. Late-connecting clients see "completed" status, get batch replay from DB

---

## Task Spec Deviation Analysis

The task 26 spec proposes `asyncio.Queue` + `run_coroutine_threadsafe()`. The actual task 25 implementation uses `queue.Queue` + sync `broadcast_to_run()`. The spec was written before task 25 was implemented.

**Recommendation:** Follow the actual infrastructure (Pattern 3: ConnectionManager delegation). Document the deviation. The spec's intent (thread-safe bridging) is fully satisfied by the simpler approach.

---

## Summary of Recommendations

| Aspect | Recommendation |
|--------|---------------|
| Bridging pattern | ConnectionManager delegation (Pattern 3) |
| asyncio.Queue | Not needed; ConnectionManager uses stdlib queue |
| run_coroutine_threadsafe | Not needed; broadcast_to_run is already sync+threadsafe |
| Event loop reference | Not needed with delegation pattern |
| Thread safety | Provided by queue.Queue.put_nowait() internally |
| Persistence | CompositeEmitter composes UIBridge + SQLiteEventHandler |
| File location | `llm_pipeline/ui/bridge.py` per task spec |
| External dependencies | None (all stdlib + existing codebase) |
