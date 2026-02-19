# Research Step 2: API Architecture & Route Structuring

## 1. Data Model Analysis

### 1.1 PipelineStepState (`pipeline_step_states`)

Location: `llm_pipeline/state.py`

| Column | Type | Notes |
|--------|------|-------|
| id | int (PK) | auto-increment |
| pipeline_name | str(100) | snake_case, e.g. `rate_card_parser` |
| run_id | str(36) | UUID, indexed |
| step_name | str(100) | e.g. `table_type_detection` |
| step_number | int | execution order (1,2,3...) |
| input_hash | str(64) | SHA256 prefix for cache invalidation |
| result_data | JSON | serialized step result (list of instruction dicts) |
| context_snapshot | JSON | context at step completion |
| prompt_system_key | str(200) | nullable |
| prompt_user_key | str(200) | nullable |
| prompt_version | str(20) | nullable, for cache invalidation |
| model | str(50) | LLM model name, nullable |
| created_at | datetime | UTC |
| execution_time_ms | int | nullable |

Indexes:
- `ix_pipeline_step_states_run` (run_id, step_number) - fetch steps for a run
- `ix_pipeline_step_states_cache` (pipeline_name, step_name, input_hash) - cache lookups

### 1.2 PipelineRunInstance (`pipeline_run_instances`)

Location: `llm_pipeline/state.py`

| Column | Type | Notes |
|--------|------|-------|
| id | int (PK) | auto-increment |
| run_id | str(36) | UUID, indexed |
| model_type | str(100) | e.g. `Rate`, `Lane` |
| model_id | int | FK to created instance |
| created_at | datetime | UTC |

Indexes:
- `ix_pipeline_run_instances_run` (run_id)
- `ix_pipeline_run_instances_model` (model_type, model_id)

### 1.3 PipelineEventRecord (`pipeline_events`)

Location: `llm_pipeline/events/models.py`

| Column | Type | Notes |
|--------|------|-------|
| id | int (PK) | auto-increment |
| run_id | str(36) | UUID |
| event_type | str(100) | e.g. `pipeline_started`, `step_completed` |
| pipeline_name | str(100) | snake_case |
| timestamp | datetime | UTC |
| event_data | JSON | full serialized event payload |

Indexes:
- `ix_pipeline_events_run_event` (run_id, event_type)
- `ix_pipeline_events_type` (event_type)

### 1.4 Prompt (`prompts`)

Location: `llm_pipeline/db/prompt.py`

| Column | Type | Notes |
|--------|------|-------|
| id | int (PK) | auto-increment |
| prompt_key | str(100) | indexed, e.g. `table_type_detection` |
| prompt_name | str(200) | human-readable |
| prompt_type | str(50) | `system` or `user` |
| category | str(50) | nullable |
| step_name | str(50) | nullable |
| content | str | template text with `{variable}` placeholders |
| required_variables | JSON | nullable, auto-extracted from content |
| description | str | nullable |
| version | str(20) | default `1.0` |
| is_active | bool | default True |
| created_at | datetime | UTC |
| updated_at | datetime | UTC |
| created_by | str(100) | nullable |

Constraints:
- UNIQUE(prompt_key, prompt_type) via `uq_prompts_key_type`
- Index on (category, step_name), (is_active)

### 1.5 Key Insight: No Dedicated Runs Table

There is NO `pipeline_runs` table. A "run" is an implicit concept identified by `run_id` (UUID) appearing across:
- `pipeline_step_states.run_id`
- `pipeline_run_instances.run_id`
- `pipeline_events.run_id`

To list runs, the API must aggregate from `pipeline_step_states` (GROUP BY run_id) or `pipeline_events` (filter for `pipeline_started`/`pipeline_completed` event types). Task 20 confirms this approach: "Query pipeline_step_states grouped by run_id."

---

## 2. Pipeline Execution State Tracking

### 2.1 How State is Tracked

`PipelineConfig.execute()` in `pipeline.py` orchestrates:

1. Generates `run_id = uuid4()` at pipeline init
2. For each step: saves `PipelineStepState` row via `_save_step_state()` (writes to `_real_session`, not the ReadOnlySession)
3. For each extracted model: saves `PipelineRunInstance` linking run_id -> model_type + model_id
4. Events emitted via `_emit()` -> `PipelineEventEmitter` protocol -> handlers (LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler)
5. `SQLiteEventHandler` persists events to `pipeline_events` table

### 2.2 Database Initialization

`llm_pipeline/db/__init__.py`:
- `init_pipeline_db(engine=None)` - creates tables, stores engine in module-level `_engine`
- `get_engine()` - returns `_engine`, lazy-inits if needed
- `get_session()` - returns `Session(get_engine())`
- Default DB path: `LLM_PIPELINE_DB` env var or `.llm_pipeline/pipeline.db`

### 2.3 ReadOnlySession Pattern

`llm_pipeline/session/readonly.py`:
- Wraps `sqlmodel.Session`
- Allows: `query()`, `exec()`, `get()`, `execute()`, `scalar()`, `scalars()`
- Blocks: `add()`, `delete()`, `flush()`, `commit()`, `merge()`, `refresh()`, `expire()`, `expunge()`
- All UI routes should use ReadOnlySession since they are read-only consumers

---

## 3. Route Module Organization

### 3.1 Package Structure

```
llm_pipeline/ui/
    __init__.py          # import guard (FastAPI dependency check)
    app.py               # create_app() factory
    deps.py              # shared FastAPI dependencies (get_db, get_engine)
    routes/
        __init__.py      # empty or route registry
        runs.py          # pipeline run endpoints
        steps.py         # pipeline step state endpoints
        events.py        # pipeline event endpoints
        prompts.py       # prompt template endpoints
        pipelines.py     # pipeline introspection endpoints (stub for task 23)
        websocket.py     # WebSocket real-time event streaming
```

### 3.2 Router Registration Pattern

Each route module defines an `APIRouter` with appropriate prefix and tags:

```python
# runs.py
router = APIRouter(prefix="/runs", tags=["runs"])

# steps.py
router = APIRouter(prefix="/runs/{run_id}/steps", tags=["steps"])

# events.py
router = APIRouter(prefix="/events", tags=["events"])

# prompts.py
router = APIRouter(prefix="/prompts", tags=["prompts"])

# pipelines.py
router = APIRouter(prefix="/pipelines", tags=["pipelines"])

# websocket.py
router = APIRouter(tags=["websocket"])
```

App factory registers all routers under `/api` prefix:
```python
app.include_router(runs.router, prefix="/api")
app.include_router(steps.router, prefix="/api")
# ...etc
# websocket.router has NO /api prefix (WS at /ws/...)
app.include_router(websocket.router)
```

---

## 4. Endpoint Catalog

### 4.1 Runs Route (`runs.py`)

| Method | Path | Description | Query Params |
|--------|------|-------------|--------------|
| GET | `/api/runs` | List pipeline runs | `pipeline_name`, `from_date`, `to_date`, `page`, `page_size` |
| GET | `/api/runs/{run_id}` | Get run detail with step summary | - |

**Data source**: Aggregate from `pipeline_step_states` GROUP BY run_id. Optionally join `pipeline_events` for PipelineStarted/PipelineCompleted to get total execution time.

**Run summary fields** (derived):
- `run_id`: from step_states
- `pipeline_name`: from step_states
- `started_at`: MIN(created_at) from step_states or PipelineStarted event timestamp
- `completed_at`: MAX(created_at) from step_states or PipelineCompleted event timestamp
- `step_count`: COUNT(DISTINCT step_number)
- `total_time_ms`: SUM(execution_time_ms) or from PipelineCompleted.execution_time_ms event
- `status`: derived from presence of PipelineCompleted vs PipelineError events

### 4.2 Steps Route (`steps.py`)

| Method | Path | Description | Query Params |
|--------|------|-------------|--------------|
| GET | `/api/runs/{run_id}/steps` | List steps for run | - |
| GET | `/api/runs/{run_id}/steps/{step_number}` | Step detail | - |

**Data source**: `pipeline_step_states` WHERE run_id, ordered by step_number.

**Step detail fields**:
- All PipelineStepState columns
- `result_data`: JSON (LLM instruction results)
- `context_snapshot`: JSON (pipeline context at step completion)

### 4.3 Events Route (`events.py`)

| Method | Path | Description | Query Params |
|--------|------|-------------|--------------|
| GET | `/api/events` | List events (global) | `run_id`, `event_type`, `pipeline_name`, `page`, `page_size` |
| GET | `/api/runs/{run_id}/events` | Events for a run | `event_type` |

**Data source**: `pipeline_events` table.

**Event categories** (from `events/types.py`):
- `pipeline_lifecycle`: PipelineStarted, PipelineCompleted, PipelineError
- `step_lifecycle`: StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted
- `cache`: CacheLookup, CacheHit, CacheMiss, CacheReconstruction
- `llm_call`: LLMCallPrepared, LLMCallStarting, LLMCallCompleted, LLMCallRetry, LLMCallFailed, LLMCallRateLimited
- `consensus`: ConsensusStarted, ConsensusAttempt, ConsensusReached, ConsensusFailed
- `instructions_context`: InstructionsStored, InstructionsLogged, ContextUpdated
- `transformation`: TransformationStarting, TransformationCompleted
- `extraction`: ExtractionStarting, ExtractionCompleted, ExtractionError
- `state`: StateSaved

### 4.4 Prompts Route (`prompts.py`)

| Method | Path | Description | Query Params |
|--------|------|-------------|--------------|
| GET | `/api/prompts` | List prompts | `prompt_type`, `category`, `step_name`, `is_active` |
| GET | `/api/prompts/{prompt_key}` | Prompt detail with variables | - |

**Data source**: `prompts` table.

**Variable extraction**: Reuse `extract_variables_from_content()` from `llm_pipeline/prompts/loader.py` (regex: `{variable_name}` pattern).

### 4.5 Pipelines Route (`pipelines.py`) - STUB

| Method | Path | Description | Notes |
|--------|------|-------------|-------|
| GET | `/api/pipelines` | List registered pipelines | Stub for task 23 |
| GET | `/api/pipelines/{name}` | Pipeline introspection | Stub for task 23 |

Task 23 (PipelineIntrospector) will implement the actual logic. Route module just needs router definition.

### 4.6 WebSocket Route (`websocket.py`)

| Protocol | Path | Description |
|----------|------|-------------|
| WS | `/ws/runs/{run_id}/events` | Stream events for a run in real-time |

See section 6 for WebSocket patterns.

---

## 5. Database Session Injection Pattern

### 5.1 App Factory DB Configuration

```python
# app.py
def create_app(db_path: str = None) -> FastAPI:
    app = FastAPI(...)

    # Create engine from db_path
    if db_path:
        engine = create_engine(f"sqlite:///{db_path}", echo=False)
    else:
        engine = create_engine(f"sqlite:///{get_default_db_path()}", echo=False)

    app.state.engine = engine
    # ... register routers, middleware
    return app
```

### 5.2 Dependency Injection

```python
# deps.py
from typing import Annotated, Generator
from fastapi import Depends, Request
from sqlmodel import Session
from llm_pipeline.session import ReadOnlySession

def get_engine(request: Request):
    return request.app.state.engine

def get_db(request: Request) -> Generator[ReadOnlySession, None, None]:
    engine = request.app.state.engine
    session = Session(engine)
    try:
        yield ReadOnlySession(session)
    finally:
        session.close()

# Type alias for route injection
DBSession = Annotated[ReadOnlySession, Depends(get_db)]
```

### 5.3 Usage in Routes

```python
# runs.py
from llm_pipeline.ui.deps import DBSession

@router.get("/runs")
async def list_runs(db: DBSession, pipeline_name: str = None):
    # db is ReadOnlySession - can query but not write
    ...
```

### 5.4 Why ReadOnlySession for UI

- UI backend is a read-only dashboard consumer
- Existing ReadOnlySession allows: `exec()`, `scalars()`, `get()`, `execute()`
- Blocks all writes, preventing accidental data corruption
- Same pattern already used by pipeline steps during execution
- POST /runs (task 20) would need writable session - that route can bypass ReadOnlySession

---

## 6. WebSocket Patterns for Real-Time Updates

### 6.1 Approach A: DB Polling (Simple, Works Today)

Poll `pipeline_events` table for new rows since last check:

```python
@router.websocket("/ws/runs/{run_id}/events")
async def ws_events(websocket: WebSocket, run_id: str):
    await websocket.accept()
    last_id = 0
    while True:
        # Query for new events since last_id
        new_events = session.exec(
            select(PipelineEventRecord)
            .where(PipelineEventRecord.run_id == run_id)
            .where(PipelineEventRecord.id > last_id)
            .order_by(PipelineEventRecord.id)
        ).all()
        for event in new_events:
            await websocket.send_json(event.event_data)
            last_id = event.id
        await asyncio.sleep(0.5)  # polling interval
```

**Pros**: Works with existing SQLiteEventHandler, no additional infrastructure.
**Cons**: Polling latency (0.5s), DB load for active connections, SQLite WAL mode needed for concurrent reads.

### 6.2 Approach B: In-Process Event Bridge (Low Latency)

Bridge `InMemoryEventHandler` to connected WebSocket clients:

```python
# Event bridge: pipeline events -> WebSocket clients
class WebSocketEventBridge:
    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = {}  # run_id -> queues

    def subscribe(self, run_id: str) -> asyncio.Queue:
        queue = asyncio.Queue()
        self._subscribers.setdefault(run_id, []).append(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue):
        if run_id in self._subscribers:
            self._subscribers[run_id].remove(queue)

    def emit(self, event: PipelineEvent) -> None:
        """PipelineEventEmitter protocol - called by CompositeEmitter."""
        for queue in self._subscribers.get(event.run_id, []):
            queue.put_nowait(event.to_dict())
```

**Pros**: Zero latency, no DB polling overhead.
**Cons**: Only works if pipeline runs in same process as FastAPI, events lost if client disconnects during delivery.

### 6.3 Recommendation

Use Approach A (DB polling) as default, with Approach B as enhancement when pipeline runs in-process. The `create_app()` factory could accept an optional `event_bridge` parameter.

---

## 7. Response Schema Suggestions

### 7.1 Pagination Envelope

```python
class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int  # ceil(total / page_size)
```

### 7.2 Run Summary Response

```python
class RunSummary(BaseModel):
    run_id: str
    pipeline_name: str
    started_at: datetime | None
    completed_at: datetime | None
    status: str  # "running", "completed", "error"
    step_count: int
    total_time_ms: int | None
```

### 7.3 Step Detail Response

```python
class StepDetail(BaseModel):
    id: int
    pipeline_name: str
    run_id: str
    step_name: str
    step_number: int
    input_hash: str
    result_data: dict | list
    context_snapshot: dict
    prompt_system_key: str | None
    prompt_user_key: str | None
    prompt_version: str | None
    model: str | None
    created_at: datetime
    execution_time_ms: int | None
```

### 7.4 Event Response

```python
class EventResponse(BaseModel):
    id: int
    run_id: str
    event_type: str
    pipeline_name: str
    timestamp: datetime
    event_data: dict
```

### 7.5 Prompt Response

```python
class PromptResponse(BaseModel):
    id: int
    prompt_key: str
    prompt_name: str
    prompt_type: str
    category: str | None
    step_name: str | None
    content: str
    required_variables: list[str] | None
    version: str
    is_active: bool
```

---

## 8. CORS Configuration

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # dev mode - all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

For production, `allow_origins` should be restricted. Could parameterize in `create_app(cors_origins=None)`.

---

## 9. Import Guard Pattern

```python
# llm_pipeline/ui/__init__.py
try:
    from fastapi import FastAPI  # noqa: F401
except ImportError:
    raise ImportError(
        "FastAPI not installed. Install with: pip install llm-pipeline[ui]"
    )
```

pyproject.toml addition:
```toml
[project.optional-dependencies]
ui = ["fastapi>=0.100.0", "uvicorn[standard]>=0.20.0"]
```

---

## 10. Scope Boundaries

### In Scope (Task 19)
- `llm_pipeline/ui/` package creation
- `__init__.py` with import guard
- `app.py` with `create_app()` factory
- `deps.py` with shared dependencies
- `routes/` directory with stub route modules (router definitions only)
- CORS middleware
- pyproject.toml `[ui]` optional dependency

### Out of Scope (Downstream Tasks)
- Task 20: Implement runs endpoint logic (querying, pagination, filtering)
- Task 22: Implement prompts endpoint logic
- Task 23: Pipeline introspection service
- Task 27: CLI entry point (`llm-pipeline ui` command)

---

## 11. Relationship Map

```
pipeline_step_states.run_id ----+
pipeline_run_instances.run_id --+---> implicit "run" concept (no dedicated table)
pipeline_events.run_id ---------+

prompts (global, no run_id) -- referenced by step_states via prompt_system_key/prompt_user_key
```

Event type hierarchy:
```
PipelineEvent (base)
  +-- PipelineStarted, PipelineCompleted
  +-- StepScopedEvent (intermediate, has step_name)
        +-- PipelineError (may lack step_name)
        +-- StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted
        +-- CacheLookup, CacheHit, CacheMiss, CacheReconstruction
        +-- LLMCallPrepared, LLMCallStarting, LLMCallCompleted, LLMCallRetry, LLMCallFailed, LLMCallRateLimited
        +-- ConsensusStarted, ConsensusAttempt, ConsensusReached, ConsensusFailed
        +-- InstructionsStored, InstructionsLogged, ContextUpdated
        +-- TransformationStarting, TransformationCompleted
        +-- ExtractionStarting, ExtractionCompleted, ExtractionError
        +-- StateSaved
```
