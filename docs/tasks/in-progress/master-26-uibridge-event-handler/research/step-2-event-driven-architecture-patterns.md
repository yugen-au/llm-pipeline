# Step 2: Event-Driven Architecture Patterns

## Research Scope

Event emitter/handler patterns, queue-based event forwarding, graceful completion signaling, error propagation across sync/async boundaries, and backpressure handling -- all in context of UIBridge bridging sync `pipeline.execute()` to async WebSocket clients.

---

## 1. Existing Architecture Analysis

### Event System (Task 6)

```
PipelineEventEmitter (Protocol, @runtime_checkable)
  -> emit(event: PipelineEvent) -> None  [sync]

CompositeEmitter
  -> wraps list[PipelineEventEmitter]
  -> dispatches sequentially with per-handler error isolation
  -> handler exceptions logged, never propagated to caller

Concrete handlers:
  - LoggingEventHandler: logs via Python logger, category-based levels
  - InMemoryEventHandler: thread-safe list (threading.Lock), query methods
  - SQLiteEventHandler: session-per-emit, PipelineEventRecord table
```

All handlers are sync. `emit()` is synchronous throughout.

### WebSocket Infrastructure (Task 25)

```
ConnectionManager (class, module-level singleton)
  _connections: dict[str, list[WebSocket]]     -- per-run client tracking
  _queues: dict[str, list[thread_queue.Queue]] -- per-CLIENT queue fan-out

  connect(run_id, ws) -> thread_queue.Queue    -- registers client, returns its queue
  disconnect(run_id, ws, queue) -> None        -- unregisters, cleans empty keys
  broadcast_to_run(run_id, event_data) -> None -- put_nowait into all client queues [SYNC]
  signal_run_complete(run_id) -> None          -- put_nowait(None) sentinel [SYNC]
```

Key implementation detail: Uses `queue.Queue` (stdlib threading), NOT `asyncio.Queue`. The VALIDATED_RESEARCH from task 25 references `asyncio.Queue` but the **actual shipped implementation** uses `import queue as thread_queue` and `thread_queue.Queue`. This is a critical finding that changes UIBridge design.

### Pipeline Execution

```python
# runs.py trigger_run()
def run_pipeline() -> None:
    pipeline = factory(run_id=run_id, engine=engine)
    pipeline.execute()  # fully synchronous
    pipeline.save()

background_tasks.add_task(run_pipeline)  # runs in threadpool
```

Pipeline accepts `event_emitter: Optional[PipelineEventEmitter]` at construction. Calls `self._emit(event)` which delegates to `self._event_emitter.emit(event)` if set. All events are `PipelineEvent` frozen dataclasses with `to_dict()` serialization.

### Async Bridge in WebSocket Handler

```python
async def _stream_events(websocket, queue, run_id):
    while True:
        event = await asyncio.to_thread(queue.get, True, HEARTBEAT_INTERVAL_S)
        if event is None:  # sentinel
            await websocket.send_json({"type": "stream_complete", "run_id": run_id})
            break
        await websocket.send_json(event)
```

The sync-to-async bridge is handled by `asyncio.to_thread()` wrapping `queue.get()`. The WebSocket handler awaits the blocking `queue.get()` without blocking the event loop.

---

## 2. Applicable Architecture Patterns

### 2.1 Observer Pattern (Current)

The existing event system implements the classic Observer pattern:

- **Subject**: `PipelineConfig` (calls `self._emit()` at lifecycle points)
- **Observer interface**: `PipelineEventEmitter` Protocol (single `emit()` method)
- **Concrete observers**: `LoggingEventHandler`, `InMemoryEventHandler`, `SQLiteEventHandler`
- **Dispatcher**: `CompositeEmitter` (multi-observer with error isolation)

UIBridge is another concrete observer. It implements `PipelineEventEmitter` and translates `emit()` calls into WebSocket-bound operations.

**Fit**: Perfect. UIBridge slots into the existing observer chain via `CompositeEmitter([UIBridge, LoggingEventHandler, SQLiteEventHandler])`.

### 2.2 Mediator Pattern (ConnectionManager)

`ConnectionManager` acts as a mediator between event producers (UIBridge) and consumers (WebSocket clients):

- Decouples producers from consumers -- UIBridge doesn't know about individual WebSocket connections
- Handles per-client fan-out internally
- Manages connection lifecycle (connect/disconnect/cleanup)

UIBridge talks only to the mediator, never directly to WebSocket instances. This separation is already in place.

### 2.3 Producer-Consumer with Fan-Out

```
Pipeline Thread                    Event Loop Thread
  |                                   |
  pipeline.execute()                  |
  -> emitter.emit(event)              |
  -> UIBridge.emit(event)             |
  -> event.to_dict()                  |
  -> manager.broadcast_to_run()       |
  -> queue.put_nowait(event_dict)  ---+-> queue.get() [via asyncio.to_thread]
                                      |-> websocket.send_json(event_dict)
                                      |
                                      +-> queue.get() [client 2]
                                      |-> websocket.send_json(event_dict)
```

Single producer (UIBridge) -> N consumers (WebSocket clients). `ConnectionManager.broadcast_to_run()` replicates each event into N per-client queues. Each WebSocket handler independently reads from its own queue.

### 2.4 Adapter Pattern (UIBridge)

UIBridge is a structural adapter:

- **Source interface**: `PipelineEventEmitter.emit(event: PipelineEvent)` -- receives typed event objects
- **Target interface**: `ConnectionManager.broadcast_to_run(run_id, event_dict)` -- expects serialized dicts
- **Adaptation**: `event.to_dict()` serialization + `run_id` scoping

This is the thinnest possible bridge: serialize and forward. No queueing, no async machinery, no threading complexity.

---

## 3. Completion Signaling (Sentinel Pattern)

### Current Implementation

`ConnectionManager.signal_run_complete(run_id)` sends `None` sentinel to all client queues. `_stream_events()` checks for `None` and sends `{"type": "stream_complete", "run_id": run_id}` control message before exiting the loop.

### UIBridge Completion Strategy

Two approaches considered:

**Option A: Explicit `complete()` method (task spec)**
```python
class UIBridge:
    def complete(self):
        manager.signal_run_complete(self.run_id)
```
Caller must remember to invoke. Risk of orphaned connections if caller forgets (e.g., exception path not handled).

**Option B: Auto-detect terminal events**
```python
class UIBridge:
    def emit(self, event):
        event_dict = event.to_dict()
        self._manager.broadcast_to_run(self.run_id, event_dict)
        if isinstance(event, (PipelineCompleted, PipelineError)):
            self._manager.signal_run_complete(self.run_id)
```
Automatically signals on terminal events. Can't forget. But couples UIBridge to specific event types.

**Option C: Both (recommended)**
```python
class UIBridge:
    def __init__(self, run_id, manager, auto_complete=True):
        self._auto_complete = auto_complete
        self._completed = False

    def emit(self, event):
        event_dict = event.to_dict()
        self._manager.broadcast_to_run(self.run_id, event_dict)
        if self._auto_complete and isinstance(event, (PipelineCompleted, PipelineError)):
            self._signal_complete()

    def complete(self):
        self._signal_complete()

    def _signal_complete(self):
        if not self._completed:
            self._completed = True
            self._manager.signal_run_complete(self.run_id)
```
Auto-detect by default, explicit override available, idempotent guard prevents double-signaling.

**Recommendation**: Option C. Auto-detection is safer (can't forget), idempotent guard handles edge cases, `auto_complete=False` available for advanced use.

---

## 4. Error Propagation Across Sync/Async Boundary

### Error Events (Already Handled)

`PipelineError` event carries `error_type`, `error_message`, and `traceback` fields. UIBridge forwards this like any other event -- WebSocket clients receive the full error detail as JSON.

### UIBridge.emit() Failures

If `broadcast_to_run()` raises (unlikely with `put_nowait` on unbounded queues), `CompositeEmitter` catches the exception and logs it. Pipeline execution continues. This error isolation is already built into the existing architecture.

### Pipeline Crash Without Terminal Event

If `pipeline.execute()` crashes before emitting `PipelineCompleted` or `PipelineError` (e.g., segfault, OOM), no sentinel is sent. WebSocket clients hang until heartbeat timeout.

**Mitigation**: The `trigger_run()` function should call `manager.signal_run_complete(run_id)` in a `finally` block, regardless of how the pipeline exits. This is an integration concern (not UIBridge's responsibility) but should be documented.

```python
# In runs.py trigger_run()
def run_pipeline():
    try:
        pipeline = factory(run_id=run_id, engine=engine)
        pipeline.execute()
        pipeline.save()
    except Exception:
        logger.exception(...)
    finally:
        manager.signal_run_complete(run_id)  # always signal
```

---

## 5. Backpressure Handling

### Current Queue Behavior

`thread_queue.Queue()` is unbounded by default (`maxsize=0`). `put_nowait()` never blocks and never raises `queue.Full`.

### Event Volume Assessment

Pipeline events per run: typically 10-50, maximum ~200 for complex multi-step pipelines with consensus. Each serialized event is ~200-500 bytes JSON. Total buffered data per run: <100KB.

Memory per 100 concurrent connections watching same run: 100 queues x 200 events x 500 bytes = ~10MB worst case. Acceptable.

### Backpressure Not Needed

Producers (pipeline threads) are never blocked by slow consumers. Each consumer reads independently from its own queue. If a consumer disconnects, `disconnect()` removes its queue. Abandoned queues accumulate events until cleanup.

If future scale requires it, options:
1. **Bounded queues + drop-oldest**: `maxsize=N` with custom put logic that drops oldest event when full
2. **Event batching**: Accumulate N events before broadcasting to reduce per-event overhead
3. **Consumer timeout**: Disconnect clients whose queues exceed size threshold

None of these are needed at current scale (NFR-003: 100+ connections, <100 events per run).

---

## 6. Critical Deviation: Task Spec vs Actual Codebase

### Task 26 Spec Proposes

```python
class UIBridge(PipelineEventEmitter):
    def __init__(self, run_id, loop=None):
        self._loop = loop or asyncio.get_event_loop()
        self._queue = asyncio.Queue()

    def emit(self, event):
        asyncio.run_coroutine_threadsafe(
            self._queue.put(event.to_dict()),
            self._loop
        )

    @property
    def queue(self):
        return self._queue
```

### Why This Is Wrong for the Actual Codebase

1. **ConnectionManager uses `thread_queue.Queue`, not `asyncio.Queue`**: The task spec assumed `asyncio.Queue` per-run. Task 25 implemented per-client `thread_queue.Queue` instead. `asyncio.run_coroutine_threadsafe()` is unnecessary because `put_nowait()` on `thread_queue.Queue` is inherently thread-safe.

2. **UIBridge doesn't need its own queue**: ConnectionManager already manages per-client queues with fan-out. UIBridge adding its own queue creates redundant buffering and requires someone to consume from UIBridge's queue and forward to ConnectionManager -- pointless indirection.

3. **Event loop reference is unnecessary**: Since `broadcast_to_run()` and `signal_run_complete()` are sync methods using `put_nowait()`, they can be called from any thread without event loop interaction.

### Correct Approach

```python
class UIBridge:
    def __init__(self, run_id, manager):
        self.run_id = run_id
        self._manager = manager

    def emit(self, event):
        self._manager.broadcast_to_run(self.run_id, event.to_dict())
```

No asyncio. No event loop. No internal queue. The bridge is a thin adapter: serialize event, forward to ConnectionManager.

---

## 7. Thread Safety Analysis

### Call Path

```
Thread: BackgroundTasks threadpool worker
  pipeline.execute()
    -> self._event_emitter.emit(event)    # could be CompositeEmitter
      -> UIBridge.emit(event)
        -> event.to_dict()                 # PipelineEvent is frozen dataclass, safe
        -> manager.broadcast_to_run(...)
          -> queue.put_nowait(event_dict)   # thread_queue.Queue is thread-safe
```

### Safety Guarantees

- `PipelineEvent.to_dict()`: Creates new dict via `dataclasses.asdict()`. No shared mutable state. Thread-safe.
- `thread_queue.Queue.put_nowait()`: Documented as thread-safe. Uses internal `threading.Lock`.
- `ConnectionManager._queues` dict: Accessed by both pipeline thread (`broadcast_to_run`) and event loop thread (`connect`/`disconnect`). `defaultdict` is NOT thread-safe for concurrent mutation. However, `broadcast_to_run` only reads `_queues.get(run_id, [])` -- it doesn't add/remove keys. `connect`/`disconnect` mutate the dict but always run on the event loop thread (called from async WebSocket handlers).

**Potential race**: If `connect()` adds a new queue list for `run_id` while `broadcast_to_run()` is iterating the old empty list, the new client misses events emitted during registration. This is the same race condition documented in task 25 SUMMARY ("client connects while run transitions"). Acceptable per CEO decision.

### No Additional Locking Needed in UIBridge

UIBridge has no mutable instance state (except `_completed` flag for idempotent completion). The `_completed` flag can use a simple boolean since `emit()` is called sequentially from `CompositeEmitter` (single pipeline thread). If called from multiple threads, an `threading.Event` or `threading.Lock` guard would be needed. Current architecture: single pipeline thread, so boolean is sufficient.

---

## 8. Integration Points

### UIBridge Construction

UIBridge needs:
- `run_id: str` -- scopes events to a pipeline run
- `manager: ConnectionManager` -- the WebSocket connection mediator

Constructor should accept `manager` via dependency injection for testability, with an optional default to the module-level singleton:

```python
from llm_pipeline.ui.routes.websocket import manager as default_manager

class UIBridge:
    def __init__(self, run_id, manager=None):
        self.run_id = run_id
        self._manager = manager or default_manager
```

### CompositeEmitter Composition

UIBridge composes with other handlers via CompositeEmitter:

```python
bridge = UIBridge(run_id=run_id, manager=manager)
logging_handler = LoggingEventHandler()
sqlite_handler = SQLiteEventHandler(engine=engine)
emitter = CompositeEmitter(handlers=[bridge, logging_handler, sqlite_handler])
pipeline = SomePipeline(event_emitter=emitter, ...)
```

UIBridge is order-independent in the handler list. CompositeEmitter isolates failures.

### trigger_run Modification (Adjacent Work)

Current `trigger_run()` creates pipeline via factory but doesn't wire UIBridge. Integration requires:

1. Import `manager` from `websocket` module
2. Create `UIBridge(run_id, manager)` before factory call
3. Pass UIBridge (or CompositeEmitter wrapping it) to factory
4. Call `manager.signal_run_complete(run_id)` in `finally` block as safety net

This modification is NOT part of task 26 (which creates the bridge class only) but is documented here as context for downstream work.

---

## 9. File Placement

Task spec: `llm_pipeline/ui/bridge.py`

This placement is correct:
- `ui/` package: UIBridge is UI-layer infrastructure
- `bridge.py`: Clear module name indicating bridging purpose
- Separate from `routes/websocket.py`: UIBridge is not a route; it's consumed by route handlers and pipeline factories

---

## 10. Recommendations Summary

| Decision | Recommendation | Rationale |
|----------|---------------|-----------|
| Internal queue in UIBridge | No | ConnectionManager already handles per-client fan-out via thread_queue.Queue |
| asyncio.Queue / run_coroutine_threadsafe | No | ConnectionManager uses thread_queue.Queue; broadcast_to_run is sync |
| Event loop reference | Not needed | All ConnectionManager methods are sync (put_nowait) |
| Completion signaling | Auto-detect + explicit fallback | Can't forget; idempotent; configurable via auto_complete flag |
| ConnectionManager dependency | DI with singleton default | Testable; convenient for production use |
| Error propagation | Forward PipelineError as normal event | Error detail preserved in event payload; no special channel |
| Backpressure | Unbounded queues | <200 events/run, <100KB total; bounded queues add complexity for no benefit |
| Thread safety | Inherited from thread_queue.Queue | No additional locking needed in UIBridge |
| Persistence | Separate concern (SQLiteEventHandler) | UIBridge only bridges to WebSocket; CompositeEmitter composes both |
