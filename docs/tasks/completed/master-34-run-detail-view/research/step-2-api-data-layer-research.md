# Step 2: API & Data Layer Research

## Backend API Endpoints

### Runs API (`llm_pipeline/ui/routes/runs.py`)

| Method | Path | Response Model | Description |
|--------|------|---------------|-------------|
| GET | `/api/runs` | `RunListResponse` | Paginated run list, filters: pipeline_name, status, started_after, started_before, offset, limit |
| GET | `/api/runs/{run_id}` | `RunDetail` | Single run with embedded `steps: StepSummary[]` ordered by step_number |
| POST | `/api/runs` | `TriggerRunResponse` (202) | Trigger background pipeline run |
| GET | `/api/runs/{run_id}/context` | `ContextEvolutionResponse` | Per-step context snapshots ordered by step_number |

### Steps API (`llm_pipeline/ui/routes/steps.py`)

| Method | Path | Response Model | Description |
|--------|------|---------------|-------------|
| GET | `/api/runs/{run_id}/steps` | `StepListResponse` | Step list with model info, ordered by step_number |
| GET | `/api/runs/{run_id}/steps/{step_number}` | `StepDetail` | Full step data including result_data, context_snapshot, prompt keys |

### Events API (`llm_pipeline/ui/routes/events.py`)

| Method | Path | Response Model | Description |
|--------|------|---------------|-------------|
| GET | `/api/runs/{run_id}/events` | `EventListResponse` | Paginated events, filter: event_type, offset, limit |

### WebSocket (`llm_pipeline/ui/routes/websocket.py`)

| Path | Protocol | Description |
|------|----------|-------------|
| `/ws/runs/{run_id}` | WS | Live event stream (running runs) or batch replay (terminal runs) |

### Pipelines API (`llm_pipeline/ui/routes/pipelines.py`)

| Method | Path | Response Model | Description |
|--------|------|---------------|-------------|
| GET | `/api/pipelines` | `PipelineListResponse` | List registered pipelines with introspection metadata |
| GET | `/api/pipelines/{name}` | `PipelineMetadata` | Full introspection: strategies, steps, schemas |

---

## Database Models (SQLModel)

### PipelineRun (`llm_pipeline/state.py`)
Table: `pipeline_runs`

| Field | Type | Notes |
|-------|------|-------|
| id | int (PK) | Auto-increment |
| run_id | str(36) | UUID, unique |
| pipeline_name | str(100) | snake_case |
| status | str(20) | "running" / "completed" / "failed" |
| started_at | datetime | UTC, default now |
| completed_at | datetime? | Null while running |
| step_count | int? | Unique step classes executed |
| total_time_ms | int? | Total run duration |

Indexes: `(pipeline_name, started_at)`, `(status)`

### PipelineStepState (`llm_pipeline/state.py`)
Table: `pipeline_step_states`

| Field | Type | Notes |
|-------|------|-------|
| id | int (PK) | Auto-increment |
| pipeline_name | str(100) | |
| run_id | str(36) | FK-like to PipelineRun.run_id (no formal FK) |
| step_name | str(100) | e.g. "table_type_detection" |
| step_number | int | 1-based execution order |
| input_hash | str(64) | For cache invalidation |
| result_data | JSON dict | Step's result (serialized) |
| context_snapshot | JSON dict | Full pipeline context at this point |
| prompt_system_key | str(200)? | System prompt key used |
| prompt_user_key | str(200)? | User prompt key used |
| prompt_version | str(20)? | Prompt version for cache invalidation |
| model | str(50)? | LLM model name |
| created_at | datetime | UTC |
| execution_time_ms | int? | Step duration |

Indexes: `(run_id, step_number)`, `(pipeline_name, step_name, input_hash)`

**Key detail**: PipelineStepState is written ONLY after a step completes. There is no "in-progress" step state in the DB. For live runs, in-progress step info comes exclusively from WebSocket events.

### PipelineRunInstance (`llm_pipeline/state.py`)
Table: `pipeline_run_instances`

| Field | Type | Notes |
|-------|------|-------|
| id | int (PK) | |
| run_id | str(36) | |
| model_type | str(100) | e.g. "Rate", "Lane" |
| model_id | int | FK to created instance |
| created_at | datetime | |

Not directly used by Run Detail View UI.

### PipelineEventRecord (`llm_pipeline/events/models.py`)
Table: `pipeline_events`

| Field | Type | Notes |
|-------|------|-------|
| id | int (PK) | |
| run_id | str(36) | |
| event_type | str(100) | e.g. "pipeline_started" |
| pipeline_name | str(100) | |
| timestamp | datetime | UTC |
| event_data | JSON dict | Full serialized event payload |

Indexes: `(run_id, event_type)`, `(event_type)`

**Key detail**: `event_data` contains the full event dict (including step_name for StepScopedEvent subtypes). The top-level columns (run_id, event_type, pipeline_name, timestamp) are intentionally duplicated for query efficiency.

---

## Pydantic Response Shapes

### RunDetail (GET /api/runs/{run_id})
```json
{
  "run_id": "uuid-string",
  "pipeline_name": "rate_card_parser",
  "status": "completed",
  "started_at": "2026-02-24T10:00:00Z",
  "completed_at": "2026-02-24T10:01:30Z",
  "step_count": 5,
  "total_time_ms": 90000,
  "steps": [
    {
      "step_name": "table_type_detection",
      "step_number": 1,
      "execution_time_ms": 1500,
      "created_at": "2026-02-24T10:00:01Z"
    }
  ]
}
```

### StepDetail (GET /api/runs/{run_id}/steps/{step_number})
```json
{
  "step_name": "table_type_detection",
  "step_number": 1,
  "pipeline_name": "rate_card_parser",
  "run_id": "uuid-string",
  "input_hash": "sha256-hash",
  "result_data": { "...step result JSON..." },
  "context_snapshot": { "table_type": "lane_based", "...other context..." },
  "prompt_system_key": "table_type_detection_system_v1",
  "prompt_user_key": "table_type_detection_user_v1",
  "prompt_version": "1.0",
  "model": "gemini-2.0-flash",
  "execution_time_ms": 1500,
  "created_at": "2026-02-24T10:00:01Z"
}
```

### ContextEvolutionResponse (GET /api/runs/{run_id}/context)
```json
{
  "run_id": "uuid-string",
  "snapshots": [
    {
      "step_name": "table_type_detection",
      "step_number": 1,
      "context_snapshot": { "table_type": "lane_based" }
    },
    {
      "step_name": "semantic_mapping",
      "step_number": 2,
      "context_snapshot": { "table_type": "lane_based", "lane_count": 42 }
    }
  ]
}
```

### EventListResponse (GET /api/runs/{run_id}/events)
```json
{
  "items": [
    {
      "event_type": "llm_call_starting",
      "pipeline_name": "rate_card_parser",
      "run_id": "uuid-string",
      "timestamp": "2026-02-24T10:00:01Z",
      "event_data": {
        "event_type": "llm_call_starting",
        "run_id": "...",
        "pipeline_name": "...",
        "step_name": "table_type_detection",
        "call_index": 0,
        "rendered_system_prompt": "You are...",
        "rendered_user_prompt": "Analyze this...",
        "timestamp": "..."
      }
    }
  ],
  "total": 25,
  "offset": 0,
  "limit": 100
}
```

---

## Event Type Catalog

27 event types across 9 categories. All inherit from PipelineEvent (base: run_id, pipeline_name, timestamp, event_type). Step-scoped events add `step_name: str | None`.

### Pipeline Lifecycle
| Event Type | Key Fields | Notes |
|------------|-----------|-------|
| `pipeline_started` | (base only) | Run begins |
| `pipeline_completed` | execution_time_ms, steps_executed | Run success |
| `pipeline_error` | error_type, error_message, traceback?, step_name? | Run failure |

### Step Lifecycle
| Event Type | Key Fields | Notes |
|------------|-----------|-------|
| `step_selecting` | step_index, strategy_count | Before step chosen |
| `step_selected` | step_number, strategy_name, step_name | Step chosen |
| `step_skipped` | step_number, reason, step_name | Step skipped |
| `step_started` | step_number, system_key?, user_key?, step_name | Execution begins |
| `step_completed` | step_number, execution_time_ms, step_name | Execution ends |

### LLM Call
| Event Type | Key Fields | Notes |
|------------|-----------|-------|
| `llm_call_prepared` | call_count, system_key?, user_key?, step_name | Calls prepared |
| `llm_call_starting` | call_index, rendered_system_prompt, rendered_user_prompt, step_name | **Has rendered prompts** |
| `llm_call_completed` | call_index, raw_response, parsed_result, model_name, attempt_count, validation_errors[], step_name | **Has LLM response** |
| `llm_call_retry` | attempt, max_retries, error_type, error_message, step_name | Retry event |
| `llm_call_failed` | max_retries, last_error, step_name | All retries exhausted |
| `llm_call_rate_limited` | attempt, wait_seconds, backoff_type, step_name | Rate limit hit |

### Cache
| Event Type | Key Fields | Notes |
|------------|-----------|-------|
| `cache_lookup` | input_hash, step_name | Cache check initiated |
| `cache_hit` | input_hash, cached_at, step_name | Cache match found |
| `cache_miss` | input_hash, step_name | No cache match |
| `cache_reconstruction` | model_count, instance_count, step_name | Models rebuilt from DB |

### Consensus
| Event Type | Key Fields | Notes |
|------------|-----------|-------|
| `consensus_started` | threshold, max_calls, step_name | Voting begins |
| `consensus_attempt` | attempt, group_count, step_name | Vote attempt |
| `consensus_reached` | attempt, threshold, step_name | Agreement reached |
| `consensus_failed` | max_calls, largest_group_size, step_name | No agreement |

### Instructions & Context
| Event Type | Key Fields | Notes |
|------------|-----------|-------|
| `instructions_stored` | instruction_count, step_name | Instructions saved |
| `instructions_logged` | logged_keys[], step_name | Keys logged |
| `context_updated` | new_keys[], context_snapshot, step_name | **Has context diff data** |

### Transformation
| Event Type | Key Fields | Notes |
|------------|-----------|-------|
| `transformation_starting` | transformation_class, cached, step_name | Transform begins |
| `transformation_completed` | data_key, execution_time_ms, cached, step_name | Transform ends |

### Extraction
| Event Type | Key Fields | Notes |
|------------|-----------|-------|
| `extraction_starting` | extraction_class, model_class, step_name | Extract begins |
| `extraction_completed` | extraction_class, model_class, instance_count, execution_time_ms, step_name | Extract ends |
| `extraction_error` | extraction_class, error_type, error_message, validation_errors[], step_name | Extract failed |

### State
| Event Type | Key Fields | Notes |
|------------|-----------|-------|
| `state_saved` | step_number, input_hash, execution_time_ms, step_name | State persisted |

---

## Frontend Hook -> API Mapping

| Hook | API Endpoint | Return Type | Caching Behavior |
|------|-------------|-------------|-----------------|
| `useRun(runId)` | GET /api/runs/{run_id} | `RunDetail` | Terminal: Infinity stale; Active: 5s stale, 3s poll |
| `useRuns(filters)` | GET /api/runs | `RunListResponse` | Global 30s staleTime |
| `useCreateRun()` | POST /api/runs | `TriggerRunResponse` | Mutation, invalidates runs.all |
| `useRunContext(runId, status?)` | GET /api/runs/{run_id}/context | `ContextEvolutionResponse` | Terminal: Infinity; Active: 30s |
| `useSteps(runId, runStatus?)` | GET /api/runs/{run_id}/steps | `StepListResponse` | Terminal: Infinity; Active: 5s stale, 3s poll |
| `useStep(runId, stepNumber, runStatus?)` | GET /api/runs/{run_id}/steps/{step_number} | `StepDetail` | Terminal: Infinity; Active: 30s |
| `useEvents(runId, filters, runStatus?)` | GET /api/runs/{run_id}/events | `EventListResponse` | Terminal: Infinity; Active: 5s stale, 3s poll |

### Query Key Hierarchy
```
['runs']                              -> invalidates everything
['runs', filters]                     -> run list
['runs', runId]                       -> single run detail
['runs', runId, 'context']            -> context evolution
['runs', runId, 'steps']              -> step list
['runs', runId, 'steps', stepNumber]  -> single step detail
['runs', runId, 'events', filters]    -> event list
```

---

## TypeScript Types (frontend/src/api/types.ts)

All interfaces mirror backend Pydantic models. Key types for Run Detail View:

- `RunDetail`: run metadata + `steps: StepSummary[]`
- `StepSummary`: step_name, step_number, execution_time_ms, created_at (embedded in RunDetail)
- `StepListItem`: step_name, step_number, execution_time_ms, **model**, created_at (from /steps endpoint)
- `StepDetail`: full step data including result_data, context_snapshot, all prompt keys, model
- `ContextSnapshot`: step_name, step_number, context_snapshot (Record<string, unknown>)
- `ContextEvolutionResponse`: run_id, snapshots[]
- `EventItem`: event_type, pipeline_name, run_id, timestamp, event_data (Record<string, unknown>)
- `RunStatus`: 'running' | 'completed' | 'failed'

---

## UI State (frontend/src/stores/ui.ts)

Zustand store with step detail panel state:
- `selectedStepId: number | null` - currently selected step number
- `stepDetailOpen: boolean` - slide-over visibility
- `selectStep(stepId)` - opens panel, sets selected step
- `closeStepDetail()` - closes panel, clears selection

Persists sidebar + theme to localStorage. Step detail state is ephemeral (not persisted).

---

## Data Mapping: Task 34 Components -> API

### RunMeta (header)
**Source**: `useRun(runId)` -> `RunDetail`
**Fields**: pipeline_name, status, started_at, completed_at, step_count, total_time_ms, run_id

### StepTimeline
**Source**: `useRun(runId).steps` provides StepSummary[] (name, number, timing, created_at). `useSteps(runId)` provides StepListItem[] which adds `model` field.
**Recommendation**: Use `useSteps(runId, run.status)` for the timeline since it includes model info. StepSummary in RunDetail is redundant but useful for initial render before steps query resolves.
**Step status derivation**: All steps in DB are implicitly "completed" (written post-execution). For active runs, WS events (StepStarted without StepCompleted) indicate "running" state. Steps not yet in DB are "pending."

### ContextEvolution
**Source**: `useRunContext(runId, run.status)` -> `ContextEvolutionResponse.snapshots[]`
**Fields per snapshot**: step_name, step_number, context_snapshot (JSON dict)
**Diff**: Frontend computes diff between `snapshots[i-1].context_snapshot` and `snapshots[i].context_snapshot`. First step shows full context as "added."

### StepDetailPanel (trigger only - implementation is task 35)
**Trigger**: `useUIStore.selectStep(stepNumber)` on step click in timeline
**Data sources for task 35**: useStep(runId, stepNumber) + useEvents(runId, {event_type: specific_type})

---

## Identified Gaps (Non-Blocking)

### 1. Events API lacks step_name filter
**Current**: Events endpoint filters by event_type only, not step_name.
**Impact**: StepDetailPanel (task 35) must fetch all events for a run and filter client-side by `event_data.step_name`. Manageable for typical pipeline sizes (5-15 steps, ~50-100 events total).
**Future optimization**: Add `step_name` query param to GET /runs/{run_id}/events.

### 2. No explicit step status field
**Current**: PipelineStepState has no status column. Steps are only recorded after completion.
**Derivation strategy**:
  - **Terminal runs**: All steps in DB are "completed". Steps referenced in StepSkipped events are "skipped".
  - **Active runs**: Steps with StepStarted but no StepCompleted WS event are "running". Steps not yet started are "pending".
  - **Failed runs**: Last step may be incomplete (check PipelineError event for which step failed).

### 3. Rendered prompts not in StepDetail
**Current**: PipelineStepState stores prompt_system_key and prompt_user_key (template keys), not rendered prompt text.
**Location**: Rendered prompts exist only in LLMCallStarting events (rendered_system_prompt, rendered_user_prompt fields in event_data).
**Impact**: Prompts tab in StepDetailPanel (task 35) must query events, not step state.

### 4. StepSummary vs StepListItem redundancy
RunDetail embeds StepSummary[] (name, number, timing, created_at). StepListResponse has StepListItem[] which adds `model`. Both are available and consistent -- use StepListItem from useSteps for richer data.

---

## Domain Model Classes (non-DB, for pipeline execution)

### PipelineContext (`llm_pipeline/context.py`)
Base Pydantic model for step context contributions. Steps define subclasses (e.g. `TableTypeDetectionContext(PipelineContext)`). Context is serialized to JSON and stored in `PipelineStepState.context_snapshot`.

### PipelineExtraction (`llm_pipeline/extraction.py`)
ABC for converting LLM results to DB models. Uses class params (`model=SomeModel`). Has smart method routing (default, strategy-specific, auto-detect single method). Validates instances before DB insertion.

### PipelineTransformation (`llm_pipeline/transformation.py`)
ABC for data structure changes (unpivoting, normalizing). Uses class params (`input_type=DataFrame, output_type=DataFrame`). Type validation on input/output. Smart method routing similar to extractions.

These classes are not directly queried by the UI, but their metadata is available via the Pipelines introspection API (GET /api/pipelines/{name}).
