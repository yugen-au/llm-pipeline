# Step 2: Backend API Integration Research

## Overview

Research into how the Python backend (FastAPI) exposes pipeline data that frontend Zustand stores will interact with. The backend API is fully implemented with well-defined Pydantic response models, and the frontend already has a complete TanStack Query layer mirroring all endpoints. Zustand stores only need to hold **UI-ephemeral state** -- all server state is handled by TanStack Query.

---

## Backend API Endpoint Map

All REST routes mount under `/api` prefix. WebSocket mounts without prefix.

### Runs (`llm_pipeline/ui/routes/runs.py`)

| Method | Path | Response Model | Pagination | Filters |
|--------|------|---------------|------------|---------|
| GET | `/api/runs` | `RunListResponse` | offset/limit (default 50, max 200) | pipeline_name, status, started_after, started_before |
| GET | `/api/runs/{run_id}` | `RunDetail` | -- | -- |
| POST | `/api/runs` | `TriggerRunResponse` (202) | -- | -- |
| GET | `/api/runs/{run_id}/context` | `ContextEvolutionResponse` | -- | -- |

### Steps (`llm_pipeline/ui/routes/steps.py`)

| Method | Path | Response Model | Pagination | Filters |
|--------|------|---------------|------------|---------|
| GET | `/api/runs/{run_id}/steps` | `StepListResponse` | -- | -- |
| GET | `/api/runs/{run_id}/steps/{step_number}` | `StepDetail` | -- | -- |

### Events (`llm_pipeline/ui/routes/events.py`)

| Method | Path | Response Model | Pagination | Filters |
|--------|------|---------------|------------|---------|
| GET | `/api/runs/{run_id}/events` | `EventListResponse` | offset/limit (default 100, max 500) | event_type |

### Prompts (`llm_pipeline/ui/routes/prompts.py`)

| Method | Path | Response Model | Pagination | Filters |
|--------|------|---------------|------------|---------|
| GET | `/api/prompts` | `PromptListResponse` | offset/limit (default 50, max 200) | category, step_name, prompt_type, is_active (default True) |
| GET | `/api/prompts/{prompt_key}` | `PromptDetailResponse` | -- | -- |

### Pipelines (`llm_pipeline/ui/routes/pipelines.py`)

| Method | Path | Response Model | Pagination | Filters |
|--------|------|---------------|------------|---------|
| GET | `/api/pipelines` | `PipelineListResponse` | -- | -- |
| GET | `/api/pipelines/{name}` | `PipelineMetadata` | -- | -- |

### WebSocket (`llm_pipeline/ui/routes/websocket.py`)

| Path | Protocol | Behavior |
|------|----------|----------|
| `/ws/runs/{run_id}` | WS | Live streaming for running runs, batch replay for completed/failed, 4004 close for unknown |

---

## Backend Pydantic Response Shapes

All response models are plain Pydantic BaseModel (NOT SQLModel). Defined in each route module.

### Run Models

```python
class RunListItem(BaseModel):
    run_id: str
    pipeline_name: str
    status: str           # "running" | "completed" | "failed"
    started_at: datetime
    completed_at: Optional[datetime] = None
    step_count: Optional[int] = None
    total_time_ms: Optional[int] = None

class RunListResponse(BaseModel):
    items: List[RunListItem]
    total: int
    offset: int
    limit: int

class RunDetail(BaseModel):
    run_id: str
    pipeline_name: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    step_count: Optional[int] = None
    total_time_ms: Optional[int] = None
    steps: List[StepSummary]
```

### Run Query Params (filter shape for Zustand filters store)

```python
class RunListParams(BaseModel):
    pipeline_name: Optional[str] = None
    status: Optional[str] = None
    started_after: Optional[datetime] = None
    started_before: Optional[datetime] = None
    offset: int = Query(default=0, ge=0)
    limit: int = Query(default=50, ge=1, le=200)
```

### Step Models

```python
class StepListItem(BaseModel):
    step_name: str
    step_number: int
    execution_time_ms: Optional[int] = None
    model: Optional[str] = None
    created_at: datetime

class StepDetail(BaseModel):
    step_name: str
    step_number: int
    pipeline_name: str
    run_id: str
    input_hash: str
    result_data: dict
    context_snapshot: dict
    prompt_system_key: Optional[str] = None
    prompt_user_key: Optional[str] = None
    prompt_version: Optional[str] = None
    model: Optional[str] = None
    execution_time_ms: Optional[int] = None
    created_at: datetime
```

### Pipeline Models (static config, no DB)

```python
class PipelineListItem(BaseModel):
    name: str
    strategy_count: Optional[int] = None
    step_count: Optional[int] = None
    has_input_schema: bool = False
    registry_model_count: Optional[int] = None
    error: Optional[str] = None

class PipelineMetadata(BaseModel):
    pipeline_name: str
    registry_models: List[str] = []
    strategies: List[StrategyMetadata] = []
    execution_order: List[str] = []
```

### Prompt Models

```python
class PromptItem(BaseModel):
    id: int
    prompt_key: str
    prompt_name: str
    prompt_type: str     # "system" | "user"
    category: Optional[str]
    step_name: Optional[str]
    content: str
    required_variables: Optional[List[str]]
    description: Optional[str]
    version: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]
```

---

## SQLModel Database Tables (data source for API)

Three tables power the API:

1. **`pipeline_runs`** (`PipelineRun`): run_id, pipeline_name, status, started_at, completed_at, step_count, total_time_ms
2. **`pipeline_step_states`** (`PipelineStepState`): pipeline_name, run_id, step_name, step_number, input_hash, result_data (JSON), context_snapshot (JSON), prompt keys, model, execution_time_ms
3. **`pipeline_events`** (`PipelineEventRecord`): run_id, event_type, pipeline_name, timestamp, event_data (JSON)
4. **`prompts`** (`Prompt`): prompt_key, prompt_name, prompt_type, category, step_name, content, required_variables (JSON)

Pipelines data comes from in-memory introspection (`PipelineIntrospector`) against registered pipeline classes, not from the database.

---

## Existing Frontend State Architecture

### TanStack Query Layer (complete)

Located in `llm_pipeline/ui/frontend/src/api/`:

| File | Hooks | Endpoint |
|------|-------|----------|
| `runs.ts` | `useRuns`, `useRun`, `useCreateRun`, `useRunContext` | /api/runs, /api/runs/{id}, /api/runs/{id}/context |
| `steps.ts` | `useSteps`, `useStep` | /api/runs/{id}/steps |
| `events.ts` | `useEvents` | /api/runs/{id}/events |
| `prompts.ts` | `usePrompts` | /api/prompts |
| `pipelines.ts` | `usePipelines`, `usePipeline` | /api/pipelines |
| `websocket.ts` | `useWebSocket` | /ws/runs/{id} |

Key patterns:
- `apiClient` wrapper prepends `/api`, throws typed `ApiError`
- Dynamic `staleTime`: terminal runs (completed/failed) get `Infinity`, active runs get 5s with 3s polling
- `query-keys.ts` enables hierarchical cache invalidation
- `types.ts` mirrors ALL backend Pydantic models as TypeScript interfaces

### Existing Zustand Store

Only one store exists: `stores/websocket.ts` (`useWsStore`) -- holds WS connection status, error, reconnect count. No persist middleware.

---

## Zustand Store Design Implications

### Server State vs UI State Boundary

**Server state (TanStack Query -- already done):**
- Run list data, run detail, steps, events, prompts, pipelines
- Caching, refetching, polling, cache invalidation
- WebSocket event streaming -> query cache integration

**UI-only state (Zustand stores -- task 32 scope):**
- `ui.ts`: sidebar collapsed, theme, selected step ID, step detail panel open
- `filters.ts`: run list filter values that feed into `useRuns(filters)`

### Filters Store <-> API Contract

The filters store shape should align with `RunListParams` from the backend:

```typescript
// Zustand store fields -> backend query params
interface FiltersState {
  pipelineName: string | null    // -> ?pipeline_name=...
  status: string | null          // -> ?status=...
  startedAfter: string | null    // -> ?started_after=... (ISO datetime)
  startedBefore: string | null   // -> ?started_before=... (ISO datetime)
  // offset/limit are pagination, may live here or separate
}
```

Pipeline name dropdown options come from `usePipelines()` -> `data.pipelines[].name`.
Status dropdown options: `'running' | 'completed' | 'failed'` (from `PipelineRun.status`).

### UI Store

Per task 32 spec, uses `zustand/persist` with `localStorage` key `'llm-pipeline-ui'`:

```typescript
interface UIState {
  sidebarCollapsed: boolean      // consumed by task 41 (Sidebar)
  theme: 'dark' | 'light'       // persisted across sessions
  selectedStepId: string | null  // step selection for detail panel
  stepDetailOpen: boolean        // step detail panel visibility
}
```

### Data Flow

```
User interacts with FilterBar
  -> Zustand filters store updates
    -> useRuns(filters) re-queries with new params
      -> GET /api/runs?pipeline_name=...&status=...
        -> RunListResponse flows into TanStack Query cache
          -> Components re-render with filtered data
```

---

## Minor Type Discrepancy

`PipelineListItem` in backend has `strategy_count: Optional[int]` and `step_count: Optional[int]`, but the frontend `types.ts` types them as `number` (non-optional). Also missing `registry_model_count` and `error` fields. This is noted but not relevant to Zustand stores -- it's a types.ts concern for a future task.

---

## Pagination Pattern

Backend uses offset/limit on three endpoints:
- `/api/runs`: default 50, max 200
- `/api/runs/{id}/events`: default 100, max 500
- `/api/prompts`: default 50, max 200

Response always includes `total`, `offset`, `limit` for client-side pagination UI. The filters store may include offset/limit or a separate pagination concern could exist. Task 33 (Run List View) references `<Pagination total={data?.total} />` which reads from TanStack Query cache, suggesting offset/limit could be part of the filters store passed to `useRuns()`.

---

## WebSocket Integration (already complete)

The `useWebSocket` hook in `api/websocket.ts` already:
- Imports `useWsStore` from `stores/websocket.ts`
- Appends pipeline events to TanStack Query event cache
- Invalidates step queries on step-scoped events
- Handles reconnection with exponential backoff
- No additional Zustand store work needed for WebSocket

---

## Conclusion

The backend API is fully defined with clean Pydantic response models. The frontend TanStack Query layer already mirrors all endpoints with typed hooks. Task 32's Zustand stores are purely UI-ephemeral state that feeds filter params into existing query hooks. No API gaps or ambiguities exist. The filters store shape maps directly to `RunListParams` backend query params.
