# Step 2: Backend & WebSocket Research for Live Execution View (Task 37)

## 1. Existing Backend Architecture

### 1.1 FastAPI App Factory (`llm_pipeline/ui/app.py`)

- `create_app()` builds FastAPI instance with CORS, DB engine, and route modules
- `app.state.engine` -- SQLAlchemy engine (SQLite)
- `app.state.pipeline_registry` -- `dict[str, Callable]` mapping pipeline names to factory callables
- `app.state.introspection_registry` -- `dict[str, Type[PipelineConfig]]` for class-level introspection
- Route mounting:
  - `/api` prefix: runs, steps, events, prompts, pipelines routers
  - No prefix: websocket router (mounts at `/ws/runs/{run_id}`)

### 1.2 Route Modules (`llm_pipeline/ui/routes/`)

| File | Prefix | Endpoints |
|---|---|---|
| `runs.py` | `/api/runs` | GET (list), GET `/{run_id}` (detail), POST (trigger), GET `/{run_id}/context` |
| `steps.py` | `/api/runs/{run_id}/steps` | GET (list), GET `/{step_number}` (detail) |
| `events.py` | `/api/runs/{run_id}/events` | GET (list with event_type/step_name filters) |
| `pipelines.py` | `/api/pipelines` | GET (list), GET `/{name}` (detail), GET `/{name}/steps/{step_name}/prompts` |
| `prompts.py` | `/api/prompts` | GET (list), GET `/{prompt_key}` (detail) |
| `websocket.py` | `/ws` | WS `/ws/runs/{run_id}` |

### 1.3 Dependency Injection (`llm_pipeline/ui/deps.py`)

- `DBSession` = `Annotated[ReadOnlySession, Depends(get_db)]`
- All API routes use read-only sessions from `app.state.engine`
- Write operations (trigger_run) use direct Session instances

---

## 2. WebSocket Infrastructure

### 2.1 ConnectionManager (`llm_pipeline/ui/routes/websocket.py`)

- **Singleton**: module-level `manager = ConnectionManager()`
- **Fan-out pattern**: Per-client `threading.Queue` (sync, thread-safe)
- Key methods (all sync -- callable from pipeline threads):
  - `connect(run_id, ws) -> Queue` -- register client, return dedicated queue
  - `disconnect(run_id, ws, queue)` -- unregister client
  - `broadcast_to_run(run_id, event_data)` -- fan-out dict to all client queues via `put_nowait()`
  - `signal_run_complete(run_id)` -- send `None` sentinel to all queues

### 2.2 WebSocket Endpoint (`/ws/runs/{run_id}`)

Three behaviors based on run state:
1. **Unknown run_id**: Send `{"type":"error","detail":"Run not found"}`, close with 4004
2. **Completed/failed runs**: Batch replay all persisted `PipelineEventRecord` rows, send `{"type":"replay_complete","run_status":...,"event_count":...}`, close with 1000
3. **Running runs**: Register with ConnectionManager, stream live events from queue, send heartbeat every 30s on inactivity, ends with `{"type":"stream_complete","run_id":...}`

### 2.3 WebSocket Message Types (Server -> Client)

| type | Description | Fields |
|---|---|---|
| `heartbeat` | Keep-alive on 30s inactivity | `timestamp` |
| `stream_complete` | Live run finished | `run_id` |
| `replay_complete` | Historical replay done | `run_status`, `event_count` |
| `error` | Server error (pre-close) | `detail` |
| _(no type field)_ | Raw pipeline event | `event_type`, `run_id`, `pipeline_name`, `timestamp`, `step_name?`, ... |

### 2.4 UIBridge (`llm_pipeline/ui/bridge.py`)

- Sync adapter implementing `PipelineEventEmitter` protocol
- `emit(event)` -> `manager.broadcast_to_run(run_id, event.to_dict())`
- Auto-detects terminal events (`PipelineCompleted`, `PipelineError`) -> calls `complete()`
- `complete()` -> `manager.signal_run_complete(run_id)` (idempotent via `_completed` flag)
- Created per-run in `trigger_run()` and passed as `event_emitter` to pipeline factory

---

## 3. Pipeline Execution Model

### 3.1 PipelineConfig.execute() (`llm_pipeline/pipeline.py`)

**Signature**: `execute(self, data, initial_context, use_cache=False, consensus_polling=None)`

**Required positional params**: `data` (Any) and `initial_context` (dict)

**Execution flow**:
1. Creates `PipelineRun` row (status="running")
2. Emits `PipelineStarted`
3. Iterates steps: StepSelecting -> StepSelected -> StepStarted -> (cache or LLM) -> StepCompleted
4. On success: updates PipelineRun to "completed", emits `PipelineCompleted`
5. On failure: updates PipelineRun to "failed", emits `PipelineError`

**Event emitter integration**: `_emit()` checks `self._event_emitter is not None` before forwarding

### 3.2 Run Trigger Flow (`POST /api/runs`)

```
TriggerRunRequest(pipeline_name)
  -> lookup factory in app.state.pipeline_registry
  -> generate run_id (uuid4)
  -> background task:
       bridge = UIBridge(run_id)
       pipeline = factory(run_id=run_id, engine=engine, event_emitter=bridge)
       pipeline.execute()  # <-- MISSING data + initial_context args
       pipeline.save()
     finally:
       bridge.complete()
  -> return TriggerRunResponse(run_id, status="accepted")
```

**CRITICAL GAP**: `trigger_run()` calls `pipeline.execute()` with NO arguments, but `execute()` requires `data` and `initial_context` as positional params. This will fail at runtime for any real pipeline. The factory callable must be providing these at construction time, OR this endpoint is incomplete.

### 3.3 Factory Callable Signature

Documented as: `(run_id: str, engine: Engine, event_emitter: PipelineEventEmitter | None) -> pipeline`

The returned object must expose `.execute()` and `.save()`. If the factory wraps execute() to bind data/context, the current pattern works. Otherwise, the endpoint needs `input_data` and `initial_context` fields on TriggerRunRequest.

---

## 4. State Models

### 4.1 PipelineRun (`llm_pipeline/state.py`)

| Column | Type | Notes |
|---|---|---|
| `id` | int (PK) | auto-increment |
| `run_id` | str(36), unique | UUID |
| `pipeline_name` | str(100) | snake_case |
| `status` | str(20) | "running" / "completed" / "failed" |
| `started_at` | datetime | UTC |
| `completed_at` | datetime? | UTC, null until done |
| `step_count` | int? | unique step classes executed |
| `total_time_ms` | int? | total execution time |

### 4.2 PipelineStepState (`llm_pipeline/state.py`)

| Column | Type | Notes |
|---|---|---|
| `id` | int (PK) | auto-increment |
| `pipeline_name` | str(100) | |
| `run_id` | str(36) | |
| `step_name` | str(100) | |
| `step_number` | int | execution order |
| `input_hash` | str(64) | for cache invalidation |
| `result_data` | JSON | step's serialized result |
| `context_snapshot` | JSON | context at this step |
| `prompt_system_key` | str(200)? | |
| `prompt_user_key` | str(200)? | |
| `prompt_version` | str(20)? | |
| `model` | str(50)? | LLM model used |
| `created_at` | datetime | UTC |
| `execution_time_ms` | int? | |

### 4.3 PipelineEventRecord (`llm_pipeline/events/models.py`)

| Column | Type | Notes |
|---|---|---|
| `id` | int (PK) | |
| `run_id` | str(36) | |
| `event_type` | str(100) | e.g. "pipeline_started" |
| `pipeline_name` | str(100) | |
| `step_name` | str(100)? | null for pipeline-level events |
| `timestamp` | datetime | UTC |
| `event_data` | JSON | full serialized event |

---

## 5. Event System

### 5.1 Event Types (31 concrete types in `llm_pipeline/events/types.py`)

**Categories:**
- `pipeline_lifecycle`: PipelineStarted, PipelineCompleted, PipelineError
- `step_lifecycle`: StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted
- `cache`: CacheLookup, CacheHit, CacheMiss, CacheReconstruction
- `llm_call`: LLMCallPrepared, LLMCallStarting, LLMCallCompleted, LLMCallRetry, LLMCallFailed, LLMCallRateLimited
- `consensus`: ConsensusStarted, ConsensusAttempt, ConsensusReached, ConsensusFailed
- `instructions_context`: InstructionsStored, InstructionsLogged, ContextUpdated
- `transformation`: TransformationStarting, TransformationCompleted
- `extraction`: ExtractionStarting, ExtractionCompleted, ExtractionError
- `state`: StateSaved

### 5.2 Event Handlers (`llm_pipeline/events/handlers.py`)

- `LoggingEventHandler` -- category-based log levels
- `InMemoryEventHandler` -- thread-safe in-memory store (testing/UI)
- `SQLiteEventHandler` -- persists to `pipeline_events` table (session-per-emit)

### 5.3 Event Flow: Pipeline -> WebSocket Client

```
PipelineConfig._emit(event)
  -> CompositeEmitter.emit(event) [dispatches to all handlers]
    -> SQLiteEventHandler.emit(event) [persists to DB]
    -> UIBridge.emit(event) [WebSocket forwarding]
      -> ConnectionManager.broadcast_to_run(run_id, event.to_dict())
        -> queue.put_nowait(event_data) [per-client Queue]
          -> websocket_endpoint._stream_events() polls queue
            -> websocket.send_json(event_data) [to client]
```

---

## 6. Frontend Integration (from Task 31)

### 6.1 Existing Hooks

- `useWebSocket(runId)` -- connects to `/ws/runs/{runId}`, handles replay/live/error, appends events to TanStack Query cache
- `useCreateRun()` -- mutation calling `POST /api/runs`, invalidates run queries on success
- `usePipelines()` -- fetches `GET /api/pipelines`
- `usePipeline(name)` -- fetches `GET /api/pipelines/{name}`
- `useRuns(filters)` / `useRun(runId)` -- run list and detail queries

### 6.2 Zustand Stores

- `useWsStore` -- WebSocket connection status (idle/connecting/connected/replaying/closed/error)
- `useUIStore` -- sidebar, theme, step detail panel state

### 6.3 TypeScript Types (`src/api/types.ts`)

- `TriggerRunRequest` has only `pipeline_name` (matches backend)
- `WsMessage` discriminated union with 5 variants (heartbeat, stream_complete, replay_complete, error, pipeline_event)
- All backend response models mirrored in TS interfaces

---

## 7. Gaps & Decisions Needed for Task 37

### 7.1 TriggerRunRequest Missing input_data

**Current**: `TriggerRunRequest { pipeline_name: str }`
**Needed**: `input_data: dict` and/or `initial_context: dict` fields

The `trigger_run()` endpoint calls `pipeline.execute()` without passing `data` or `initial_context`. For Live Execution to send user input to a pipeline, the backend request model must be extended.

**Question**: Is extending TriggerRunRequest with `input_data` in scope for task 37, or should task 37 only build the view structure and defer input handling to task 38?

### 7.2 Python-Initiated Run Auto-Detection

Task 37 says: "Support both Python-initiated (auto-detect via WebSocket) and UI-initiated runs."

Current WebSocket requires a known `run_id`. When a pipeline is started from Python (not through the UI), the frontend has no way to discover the new run_id in real-time.

**Options**:
a) Poll `GET /api/runs?status=running` periodically (simple, ~3s delay)
b) New WebSocket `/ws/runs` (no run_id) that broadcasts run creation notifications
c) SSE endpoint for run-creation events

**Question**: Which auto-detection mechanism should be used?

### 7.3 Factory execute() Argument Binding

The pipeline_registry factory signature creates a pipeline object, but `trigger_run()` calls `pipeline.execute()` with no arguments. Either:
a) Factories are expected to return objects where execute() is pre-bound with data/context
b) The endpoint is incomplete and needs data/context pass-through

**Question**: Is the current factory pattern intentionally pre-binding execute() args, or does trigger_run need to forward input_data to execute()?
