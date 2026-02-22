# API Surface Research - Task 31 TanStack Query Hooks

## 1. Backend Framework & Architecture

- **Framework**: FastAPI
- **App factory**: `llm_pipeline/ui/app.py` -> `create_app()`
- **DB**: SQLite via SQLModel/SQLAlchemy 2.0, engine on `app.state.engine`
- **Session**: ReadOnlySession wrapper (prevents writes from API layer)
- **Dependency injection**: `DBSession = Annotated[ReadOnlySession, Depends(get_db)]` in `llm_pipeline/ui/deps.py`
- **All route handlers are sync** (SQLite is sync; FastAPI wraps in threadpool)

### Route Mounting

```
app.include_router(runs_router, prefix="/api")       # -> /api/runs
app.include_router(steps_router, prefix="/api")       # -> /api/runs/{run_id}/steps
app.include_router(events_router, prefix="/api")      # -> /api/runs/{run_id}/events
app.include_router(prompts_router, prefix="/api")     # -> /api/prompts (EMPTY)
app.include_router(pipelines_router, prefix="/api")   # -> /api/pipelines (EMPTY)
app.include_router(ws_router)                         # -> /ws/runs/{run_id} (no /api prefix)
```

### Vite Proxy (dev)

```
/api  -> http://localhost:{apiPort}  (default 8642)
/ws   -> ws://localhost:{apiPort}    (ws: true)
```

---

## 2. Implemented REST Endpoints

### 2.1 Runs (`llm_pipeline/ui/routes/runs.py`)

**Router prefix**: `/runs` (mounted at `/api` -> `/api/runs`)

#### GET /api/runs

Paginated list with optional filters.

**Query params** (RunListParams):
| Param | Type | Default | Constraints |
|---|---|---|---|
| pipeline_name | string? | null | exact match |
| status | string? | null | exact match |
| started_after | datetime? | null | >= filter |
| started_before | datetime? | null | <= filter |
| offset | int | 0 | ge=0 |
| limit | int | 50 | ge=1, le=200 |

**Response** (RunListResponse):
```typescript
{
  items: RunListItem[]
  total: number
  offset: number
  limit: number
}
```

**RunListItem**:
```typescript
{
  run_id: string
  pipeline_name: string
  status: string          // "running" | "completed" | "failed"
  started_at: string      // ISO datetime
  completed_at?: string   // ISO datetime, nullable
  step_count?: number     // nullable
  total_time_ms?: number  // nullable
}
```

#### GET /api/runs/{run_id}

Single run detail with step summaries.

**Path params**: `run_id: string`

**Response** (RunDetail):
```typescript
{
  run_id: string
  pipeline_name: string
  status: string
  started_at: string
  completed_at?: string
  step_count?: number
  total_time_ms?: number
  steps: StepSummary[]
}
```

**StepSummary** (embedded):
```typescript
{
  step_name: string
  step_number: number
  execution_time_ms?: number
  created_at: string
}
```

**Errors**: 404 if run not found.

#### POST /api/runs

Trigger a pipeline run in background. Returns 202.

**Request** (TriggerRunRequest):
```typescript
{
  pipeline_name: string
}
```

**Response** (TriggerRunResponse):
```typescript
{
  run_id: string
  status: string          // "accepted"
}
```

**Errors**: 404 if pipeline_name not in registry.

**Notes**: Uses `BackgroundTasks`. Pipeline factory from `app.state.pipeline_registry`. On failure, sets run status to "failed".

#### GET /api/runs/{run_id}/context

Context snapshot evolution per step.

**Path params**: `run_id: string`

**Response** (ContextEvolutionResponse):
```typescript
{
  run_id: string
  snapshots: ContextSnapshot[]
}
```

**ContextSnapshot**:
```typescript
{
  step_name: string
  step_number: number
  context_snapshot: Record<string, unknown>
}
```

**Errors**: 404 if run not found.

---

### 2.2 Steps (`llm_pipeline/ui/routes/steps.py`)

**Router prefix**: `/runs/{run_id}/steps` (mounted at `/api` -> `/api/runs/{run_id}/steps`)

#### GET /api/runs/{run_id}/steps

List steps for a run, ordered by step_number.

**Path params**: `run_id: string`

**Response** (StepListResponse):
```typescript
{
  items: StepListItem[]
}
```

**StepListItem**:
```typescript
{
  step_name: string
  step_number: number
  execution_time_ms?: number
  model?: string
  created_at: string
}
```

**Errors**: 404 if run not found.

#### GET /api/runs/{run_id}/steps/{step_number}

Full detail for a single step.

**Path params**: `run_id: string`, `step_number: number`

**Response** (StepDetail):
```typescript
{
  step_name: string
  step_number: number
  pipeline_name: string
  run_id: string
  input_hash: string
  result_data: Record<string, unknown>
  context_snapshot: Record<string, unknown>
  prompt_system_key?: string
  prompt_user_key?: string
  prompt_version?: string
  model?: string
  execution_time_ms?: number
  created_at: string
}
```

**Errors**: 404 if run or step not found.

---

### 2.3 Events (`llm_pipeline/ui/routes/events.py`)

**Router prefix**: `/runs/{run_id}/events` (mounted at `/api` -> `/api/runs/{run_id}/events`)

#### GET /api/runs/{run_id}/events

Paginated list of events for a run with optional event_type filter.

**Path params**: `run_id: string`

**Query params** (EventListParams):
| Param | Type | Default | Constraints |
|---|---|---|---|
| event_type | string? | null | exact match |
| offset | int | 0 | ge=0 |
| limit | int | 100 | ge=1, le=500 |

**Response** (EventListResponse):
```typescript
{
  items: EventItem[]
  total: number
  offset: number
  limit: number
}
```

**EventItem**:
```typescript
{
  event_type: string
  pipeline_name: string
  run_id: string
  timestamp: string       // ISO datetime
  event_data: Record<string, unknown>
}
```

**Errors**: 404 if run not found.

---

## 3. WebSocket Endpoint (`llm_pipeline/ui/routes/websocket.py`)

### WS /ws/runs/{run_id}

Real-time pipeline event streaming. No /api prefix.

**Path params**: `run_id: string`

**Connection behavior**:
1. **Unknown run_id**: sends `{"type": "error", "detail": "Run not found"}`, closes with code 4004
2. **Completed/failed run**: replays all persisted events as JSON, then sends `{"type": "replay_complete", "run_status": string, "event_count": number}`, closes with 1000
3. **Running run**: live stream via ConnectionManager queue fan-out

**Live stream messages**:
- Event dicts from pipeline execution (same shape as PipelineEvent.to_dict())
- Heartbeat on inactivity: `{"type": "heartbeat", "timestamp": string}`
- Stream end: `{"type": "stream_complete", "run_id": string}`

**ConnectionManager** (module-level singleton `manager`):
- `connect(run_id, ws)` -> thread_queue.Queue
- `disconnect(run_id, ws, queue)`
- `broadcast_to_run(run_id, event_data)` -- sync, called from pipeline code
- `signal_run_complete(run_id)` -- sync, sends None sentinel

**Heartbeat interval**: 30 seconds

---

## 4. Stub/Empty Endpoints

### 4.1 Prompts (`llm_pipeline/ui/routes/prompts.py`)

**Router**: `APIRouter(prefix="/prompts", tags=["prompts"])` -- **no endpoints defined**

The Prompt DB model exists at `llm_pipeline/db/prompt.py`:
```typescript
// Prompt model fields (for future endpoint design)
{
  id: number
  prompt_key: string       // max 100
  prompt_name: string      // max 200
  prompt_type: string      // "system" | "user", max 50
  category?: string        // max 50
  step_name?: string       // max 50
  content: string
  required_variables?: string[]  // JSON column
  description?: string
  version: string          // default "1.0", max 20
  is_active: boolean       // default true
  created_at: string
  updated_at: string
  created_by?: string      // max 100
}
```

### 4.2 Pipelines (`llm_pipeline/ui/routes/pipelines.py`)

**Router**: `APIRouter(prefix="/pipelines", tags=["pipelines"])` -- **no endpoints defined**

`PipelineIntrospector` exists at `llm_pipeline/introspection.py` with `get_metadata()` returning:
```typescript
// PipelineIntrospector.get_metadata() return shape
{
  pipeline_name: string
  registry_models: string[]
  strategies: Array<{
    name: string
    display_name: string
    class_name: string
    steps: Array<{
      step_name: string
      class_name: string
      system_key: string
      user_key: string
      instructions_class?: string
      instructions_schema?: Record<string, unknown>  // JSON Schema
      context_class?: string
      context_schema?: Record<string, unknown>       // JSON Schema
      extractions: Array<{
        class_name: string
        model_class?: string
        methods: string[]
      }>
      transformation?: {
        class_name: string
        input_type?: string
        input_schema?: Record<string, unknown>
        output_type?: string
        output_schema?: Record<string, unknown>
      }
      action_after?: string
    }>
    error?: string  // present if strategy instantiation failed
  }>
  execution_order: string[]
}
```

The `introspection_registry` is passed to `create_app()` and stored on `app.state.introspection_registry` (Dict[str, Type[PipelineConfig]]).

---

## 5. Database Models (SQLModel)

### PipelineRun (`llm_pipeline/state.py`)
Table: `pipeline_runs`
| Column | Type | Notes |
|---|---|---|
| id | int? | PK, auto |
| run_id | str(36) | unique |
| pipeline_name | str(100) | |
| status | str(20) | default "running" |
| started_at | datetime | default utc_now |
| completed_at | datetime? | |
| step_count | int? | |
| total_time_ms | int? | |

### PipelineStepState (`llm_pipeline/state.py`)
Table: `pipeline_step_states`
| Column | Type | Notes |
|---|---|---|
| id | int? | PK, auto |
| pipeline_name | str(100) | |
| run_id | str(36) | |
| step_name | str(100) | |
| step_number | int | |
| input_hash | str(64) | |
| result_data | dict (JSON) | |
| context_snapshot | dict (JSON) | |
| prompt_system_key | str(200)? | |
| prompt_user_key | str(200)? | |
| prompt_version | str(20)? | |
| model | str(50)? | |
| created_at | datetime | default utc_now |
| execution_time_ms | int? | |

### PipelineEventRecord (`llm_pipeline/events/models.py`)
Table: `pipeline_events`
| Column | Type | Notes |
|---|---|---|
| id | int? | PK, auto |
| run_id | str(36) | |
| event_type | str(100) | |
| pipeline_name | str(100) | |
| timestamp | datetime | default utc_now |
| event_data | dict (JSON) | full serialized event |

### PipelineRunInstance (`llm_pipeline/state.py`)
Table: `pipeline_run_instances`
| Column | Type | Notes |
|---|---|---|
| id | int? | PK, auto |
| run_id | str(36) | |
| model_type | str(100) | |
| model_id | int | |
| created_at | datetime | default utc_now |

### Prompt (`llm_pipeline/db/prompt.py`)
Table: `prompts`
| Column | Type | Notes |
|---|---|---|
| id | int? | PK, auto |
| prompt_key | str(100) | indexed |
| prompt_name | str(200) | |
| prompt_type | str(50) | "system"/"user" |
| category | str(50)? | |
| step_name | str(50)? | |
| content | str | |
| required_variables | list[str]? | JSON column |
| description | str? | |
| version | str(20) | default "1.0" |
| is_active | bool | default true |
| created_at | datetime | |
| updated_at | datetime | |
| created_by | str(100)? | |

---

## 6. Event Types (for WebSocket Messages)

All events extend `PipelineEvent` base. Categories and types:

**pipeline_lifecycle**: pipeline_started, pipeline_completed, pipeline_error
**step_lifecycle**: step_selecting, step_selected, step_skipped, step_started, step_completed
**cache**: cache_lookup, cache_hit, cache_miss, cache_reconstruction
**llm_call**: llm_call_prepared, llm_call_starting, llm_call_completed, llm_call_retry, llm_call_failed, llm_call_rate_limited
**consensus**: consensus_started, consensus_attempt, consensus_reached, consensus_failed
**instructions_context**: instructions_stored, instructions_logged, context_updated
**transformation**: transformation_starting, transformation_completed
**extraction**: extraction_starting, extraction_completed, extraction_error
**state**: state_saved

Base event fields (all events): `run_id`, `pipeline_name`, `timestamp`, `event_type`
Step-scoped events add: `step_name` (nullable)

---

## 7. Existing Frontend State

### Already installed (package.json)
- @tanstack/react-query ^5.90.21
- @tanstack/react-query-devtools ^5.91.3 (dev)
- @tanstack/react-router ^1.161.3
- @tanstack/router-plugin ^1.161.3 (dev)
- @tanstack/zod-adapter ^1.161.3
- zod ^4.3.6
- zustand ^5.0.11

### QueryClient (`src/queryClient.ts`)
```typescript
new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
})
```

### Existing routes (task 30, all placeholder UI)
- `/` - index with Zod search params (page, status)
- `/runs/$runId` - run detail with search params (tab)
- `/live` - live execution
- `/prompts` - prompt browser
- `/pipelines` - pipeline structure

### No existing API client code
- `src/api/` directory does not exist
- No TypeScript types for API responses
- No fetch wrappers or API utilities

---

## 8. Gaps & Ambiguities

### GAP 1: Prompts API has no endpoints
The `/api/prompts` router is empty. The Prompt DB model exists. Downstream task 39 (Prompt Browser) needs `usePrompts` hook. Task 31 spec lists `prompts.ts` as a deliverable.

### GAP 2: Pipelines API has no endpoints
The `/api/pipelines` router is empty. PipelineIntrospector exists but no REST routes expose it. Downstream tasks 37, 40 need `usePipelines`/`usePipeline` hooks. Task 31 spec lists `pipelines.ts` as a deliverable.

### GAP 3: TriggerRunRequest lacks input_data
Current `TriggerRunRequest` only has `pipeline_name`. Task 37 (Live Execution) expects passing `input_data` when triggering. This may need extending.

---

## 9. Hook-to-Endpoint Mapping (Proposed)

| Hook | Endpoint | Status |
|---|---|---|
| useRuns(filters) | GET /api/runs | EXISTS |
| useRun(runId) | GET /api/runs/{run_id} | EXISTS |
| useCreateRun() | POST /api/runs | EXISTS |
| useRunContext(runId) | GET /api/runs/{run_id}/context | EXISTS |
| useSteps(runId) | GET /api/runs/{run_id}/steps | EXISTS |
| useStep(runId, stepNumber) | GET /api/runs/{run_id}/steps/{step_number} | EXISTS |
| useEvents(runId, filters) | GET /api/runs/{run_id}/events | EXISTS |
| useWebSocket(runId) | WS /ws/runs/{run_id} | EXISTS |
| usePrompts(filters) | GET /api/prompts | MISSING |
| usePipelines() | GET /api/pipelines | MISSING |
| usePipeline(name) | GET /api/pipelines/{name} | MISSING |
