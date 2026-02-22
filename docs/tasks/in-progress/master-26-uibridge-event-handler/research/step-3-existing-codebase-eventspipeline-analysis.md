# Step 3: Existing Codebase Events/Pipeline Analysis

## 1. Event System Architecture (Task 6 - Complete)

### PipelineEventEmitter Protocol
- **File**: `llm_pipeline/events/emitter.py`
- `@runtime_checkable` Protocol with single method: `emit(self, event: PipelineEvent) -> None`
- UIBridge MUST implement this `emit()` method to satisfy the protocol
- `isinstance(obj, PipelineEventEmitter)` works at runtime

### CompositeEmitter
- **File**: `llm_pipeline/events/emitter.py`
- Wraps `list[PipelineEventEmitter]` as immutable tuple
- Dispatches `emit()` to all handlers sequentially
- Per-handler error isolation via try/except (logs exception, continues to next)
- UIBridge would be one handler in a CompositeEmitter alongside LoggingEventHandler, SQLiteEventHandler

### PipelineEvent Base
- **File**: `llm_pipeline/events/types.py`
- Frozen dataclass (`frozen=True, slots=True`)
- Required init fields: `run_id: str`, `pipeline_name: str`
- Auto-derived fields: `timestamp` (default_factory=utc_now), `event_type` (derived from class name via __init_subclass__)
- Serialization: `to_dict() -> dict[str, Any]` (converts datetimes to ISO strings), `to_json() -> str`
- 30+ concrete event types across 9 categories (pipeline_lifecycle, step_lifecycle, cache, llm_call, consensus, instructions_context, transformation, extraction, state)
- Auto-registry via `__init_subclass__` populating `_EVENT_REGISTRY`

### StepScopedEvent
- Intermediate base extending PipelineEvent
- Adds `step_name: str | None = None`
- Most events (StepStarted, LLMCallStarting, etc.) extend this

### Existing Handlers
- **File**: `llm_pipeline/events/handlers.py`
- `LoggingEventHandler`: logs via Python logging with category-based log levels
- `InMemoryEventHandler`: thread-safe list with `threading.Lock`, stores `event.to_dict()`
- `SQLiteEventHandler`: persists `PipelineEventRecord` rows to DB (session-per-emit)
- ALL handlers are SYNCHRONOUS - no async anywhere in event system

### PipelineEventRecord (DB Model)
- **File**: `llm_pipeline/events/models.py`
- SQLModel table: `pipeline_events`
- Columns: `id`, `run_id`, `event_type`, `pipeline_name`, `timestamp`, `event_data` (JSON)
- Indexes: composite `(run_id, event_type)`, standalone `event_type`

## 2. Pipeline Execution Model

### PipelineConfig.__init__
- **File**: `llm_pipeline/pipeline.py`
- Accepts `event_emitter: Optional[PipelineEventEmitter] = None`
- Stores as `self._event_emitter`
- `_emit(event)` method: forwards to emitter if not None

### execute() Method - FULLY SYNCHRONOUS
- **Signature**: `execute(self, data, initial_context, use_cache=False, consensus_polling=None) -> PipelineConfig`
- **No async anywhere** - entire execution is blocking/synchronous
- Creates `PipelineRun` DB record (status="running")
- Iterates through steps: strategy selection -> step execution -> cache/LLM -> extraction -> transformation
- Events emitted at every lifecycle point via `self._emit()`:
  - `PipelineStarted` at start
  - `StepSelecting`, `StepSelected`, `StepSkipped`, `StepStarted`, `StepCompleted` per step
  - `CacheLookup`, `CacheHit`, `CacheMiss`, `CacheReconstruction` for caching
  - `LLMCallPrepared`, `InstructionsStored`, `InstructionsLogged` for LLM flow
  - `TransformationStarting`, `TransformationCompleted` for data transforms
  - `StateSaved` after step state persistence
  - `PipelineCompleted` on success, `PipelineError` on failure
- Event emitter also forwarded to `execute_llm_step()` which emits `LLMCallStarting`, `LLMCallCompleted`

### execute_llm_step()
- **File**: `llm_pipeline/llm/executor.py`
- Receives `event_emitter`, `run_id`, `pipeline_name`, `step_name`, `call_index` as optional kwargs
- Emits `LLMCallStarting` before provider call
- Emits `LLMCallCompleted` after (with raw_response, parsed_result, validation_errors)

## 3. WebSocket Infrastructure (Task 25 - Complete)

### ConnectionManager
- **File**: `llm_pipeline/ui/routes/websocket.py`
- Module-level singleton: `manager = ConnectionManager()`
- Uses `threading.Queue` (stdlib `queue.Queue`), NOT `asyncio.Queue`
- Per-client queue fan-out pattern

#### Public API (all SYNC):
```python
def connect(self, run_id: str, ws: WebSocket) -> thread_queue.Queue
def disconnect(self, run_id: str, ws: WebSocket, queue: Optional[thread_queue.Queue]) -> None
def broadcast_to_run(self, run_id: str, event_data: dict) -> None  # put_nowait to all client queues
def signal_run_complete(self, run_id: str) -> None  # put_nowait(None) sentinel to all client queues
```

### WebSocket Endpoint
- Route: `GET /ws/runs/{run_id}` (WebSocket upgrade)
- Completed/failed runs: batch replay from `PipelineEventRecord` DB, then `replay_complete` message, close
- Running runs: live stream via manager queue fan-out
- `_stream_events()` bridges sync Queue to async via `asyncio.to_thread(queue.get, True, timeout)`
- Heartbeat every 30s on inactivity
- `stream_complete` message on None sentinel

### Task 25 SUMMARY Recommendation for Task 26
> "Task 26 should import `manager` from `llm_pipeline.ui.routes.websocket` and call these via `asyncio.run_coroutine_threadsafe()` or directly from the event loop thread (both are safe since the methods are sync `put_nowait` calls)."

## 4. UI App & Run Triggering

### create_app()
- **File**: `llm_pipeline/ui/app.py`
- FastAPI factory: creates engine, registers all route modules
- `app.state.engine` holds the SQLAlchemy engine
- `app.state.pipeline_registry` maps pipeline names to factory callables

### trigger_run (POST /api/runs)
- **File**: `llm_pipeline/ui/routes/runs.py`
- Gets factory from `app.state.pipeline_registry`
- Creates `run_id = str(uuid.uuid4())`
- Runs `factory(run_id=run_id, engine=engine)` then `.execute()` then `.save()` via `BackgroundTasks`
- **Currently does NOT wire up event_emitter** - no UIBridge, no manager integration
- Error handling: catches exceptions, updates PipelineRun.status to "failed"

## 5. Critical Deviation: Task Spec vs Actual Infrastructure

### Task 26 Spec Prescribes
```python
class UIBridge(PipelineEventEmitter):
    def __init__(self, run_id: str, loop: asyncio.AbstractEventLoop = None):
        self._loop = loop or asyncio.get_event_loop()
        self._queue = asyncio.Queue()

    def emit(self, event: PipelineEvent) -> None:
        asyncio.run_coroutine_threadsafe(
            self._queue.put(event.to_dict()), self._loop
        )

    @property
    def queue(self) -> asyncio.Queue:
        return self._queue
```

### What Task 25 Actually Built
- `ConnectionManager` uses `threading.Queue` (not `asyncio.Queue`)
- `broadcast_to_run()` is fully SYNC (uses `put_nowait()`)
- WebSocket endpoint bridges sync->async via `asyncio.to_thread(queue.get)`
- No asyncio event loop reference needed

### Implication
The task spec's `asyncio.Queue` + `asyncio.run_coroutine_threadsafe` approach is architecturally mismatched with the actual ConnectionManager infrastructure. A simpler sync-only approach would work:

```python
class UIBridge:
    def __init__(self, run_id: str):
        self.run_id = run_id

    def emit(self, event: PipelineEvent) -> None:
        manager.broadcast_to_run(self.run_id, event.to_dict())

    def complete(self) -> None:
        manager.signal_run_complete(self.run_id)
```

This directly delegates to the existing ConnectionManager which handles fan-out. No asyncio.Queue, no event loop reference, no thread-safety concerns (manager's broadcast_to_run is already safe via put_nowait on threading.Queue).

## 6. Interfaces UIBridge Must Implement

### Required
- `emit(self, event: PipelineEvent) -> None` - satisfies PipelineEventEmitter protocol
- Must pass `isinstance(bridge, PipelineEventEmitter)` check

### Expected by Consumers
- Constructor accepting at minimum `run_id: str`
- `complete()` method to signal end of run (sends sentinel to WebSocket clients)
- Compatible with CompositeEmitter (UIBridge as one of multiple handlers)

### Event Data Format
- `event.to_dict()` produces the dict that goes to WebSocket clients
- Dict contains: `event_type`, `run_id`, `pipeline_name`, `timestamp` (ISO string), plus event-specific fields
- WebSocket endpoint sends this dict via `websocket.send_json(event_data)`

## 7. Execution Flow for UIBridge Integration

```
POST /api/runs
  -> trigger_run()
    -> BackgroundTasks thread pool
      -> factory(run_id, engine) creates pipeline with UIBridge as event_emitter
      -> pipeline.execute() (SYNC, in thread pool)
        -> self._emit(event) at each lifecycle point
          -> UIBridge.emit(event) (SYNC)
            -> manager.broadcast_to_run(run_id, event.to_dict()) (SYNC, put_nowait)
              -> threading.Queue per connected WebSocket client
      -> UIBridge.complete() (SYNC)
        -> manager.signal_run_complete(run_id) (SYNC, put_nowait None)

Meanwhile, in async event loop:
  WebSocket endpoint
    -> _stream_events()
      -> asyncio.to_thread(queue.get) reads from threading.Queue
      -> websocket.send_json(event_data) sends to client
```

## 8. Open Questions for CEO

1. **Sync-only vs asyncio.Queue approach**: Task spec prescribes `asyncio.Queue` + `asyncio.run_coroutine_threadsafe`, but ConnectionManager (task 25) uses `threading.Queue` with sync `broadcast_to_run()`. Should UIBridge use the simpler sync-direct approach (calling `manager.broadcast_to_run()` directly), or follow the spec's asyncio pattern (which would bypass ConnectionManager and duplicate fan-out logic)?

2. **Wiring scope**: Should task 26 also modify `trigger_run()` in `runs.py` to create UIBridge + CompositeEmitter and pass as event_emitter to the pipeline factory? Or is wiring a separate task?
