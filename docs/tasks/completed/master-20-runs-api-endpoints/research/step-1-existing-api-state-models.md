# Step 1: Existing API State Models & FastAPI Architecture

## Models

### PipelineStepState (table: `pipeline_step_states`)
**File:** `llm_pipeline/state.py`

| Column | Type | Notes |
| --- | --- | --- |
| id | int (PK) | auto-increment |
| pipeline_name | str(100) | snake_case, e.g. `rate_card_parser` |
| run_id | str(36) | UUID, indexed |
| step_name | str(100) | e.g. `table_type_detection` |
| step_number | int | execution order (1, 2, 3...) |
| input_hash | str(64) | cache invalidation |
| result_data | JSON | step result (serialized dict) |
| context_snapshot | JSON | context at this point (serialized dict) |
| prompt_system_key | str(200), optional | |
| prompt_user_key | str(200), optional | |
| prompt_version | str(20), optional | |
| model | str(50), optional | LLM model name |
| created_at | datetime | UTC, default=now |
| execution_time_ms | int, optional | |

**Indexes:**
- `ix_pipeline_step_states_run`: (run_id, step_number) -- covers single-run step listing
- `ix_pipeline_step_states_cache`: (pipeline_name, step_name, input_hash) -- covers cache lookups

**Key observation:** No `status` field. No `completed_at` field. `created_at` marks when the row was inserted (i.e., step completion).

### PipelineRunInstance (table: `pipeline_run_instances`)
**File:** `llm_pipeline/state.py`

| Column | Type | Notes |
| --- | --- | --- |
| id | int (PK) | auto-increment |
| run_id | str(36) | UUID, indexed |
| model_type | str(100) | class name, e.g. `Rate` |
| model_id | int | FK to created instance |
| created_at | datetime | UTC, default=now |

**Indexes:**
- `ix_pipeline_run_instances_run`: (run_id)
- `ix_pipeline_run_instances_model`: (model_type, model_id)

**Purpose:** Links created DB instances back to pipeline runs. NOT a "runs" table -- it's a polymorphic join table for traceability.

### PipelineEventRecord (table: `pipeline_events`)
**File:** `llm_pipeline/events/models.py`

| Column | Type | Notes |
| --- | --- | --- |
| id | int (PK) | auto-increment |
| run_id | str(36) | |
| event_type | str(100) | e.g. `pipeline_started`, `pipeline_completed` |
| pipeline_name | str(100) | snake_case |
| timestamp | datetime | UTC |
| event_data | JSON | full event payload |

**Indexes:**
- `ix_pipeline_events_run_event`: (run_id, event_type)
- `ix_pipeline_events_type`: (event_type)

**Key observation:** This table has `pipeline_name` + `timestamp` per event. The `pipeline_started` event could serve as a "runs index" -- one row per run with the pipeline_name and start time already denormalized.

### Prompt (table: `prompts`)
**File:** `llm_pipeline/db/prompt.py`

Not directly relevant to runs API, but exists in the same DB.

## No Dedicated Runs Table

A "run" is an implicit concept. `run_id` (UUID) appears across 3 tables:
- `pipeline_step_states` -- step-level audit data
- `pipeline_run_instances` -- created DB instances
- `pipeline_events` -- event stream

To list runs, we must aggregate from one of these tables.

## FastAPI App Factory (Task 19)

### create_app() -- `llm_pipeline/ui/app.py`
- Accepts `db_path: Optional[str]` and `cors_origins: Optional[list]`
- Stores engine on `app.state.engine` via `init_pipeline_db()`
- CORS: `allow_origins=["*"]`, `allow_credentials=False`
- Lazy imports routers inside function body (avoids circular imports)
- Mounts all 6 routers with `prefix="/api"` (except websocket)

### Router Registration Pattern
```python
app.include_router(runs_router, prefix="/api")    # runs.py has prefix="/runs"   -> /api/runs
app.include_router(steps_router, prefix="/api")    # steps.py has prefix="/runs/{run_id}/steps" -> /api/runs/{run_id}/steps
app.include_router(events_router, prefix="/api")   # events.py has prefix="/events" -> /api/events
```

### Route Stub Pattern (all route files follow this)
```python
from fastapi import APIRouter
router = APIRouter(prefix="/runs", tags=["runs"])
```

No endpoints defined yet -- just router declarations.

## Dependency Injection -- `llm_pipeline/ui/deps.py`

```python
def get_db(request: Request) -> Generator[ReadOnlySession, None, None]:
    engine = request.app.state.engine
    session = Session(engine)
    try:
        yield ReadOnlySession(session)
    finally:
        session.close()

DBSession = Annotated[ReadOnlySession, Depends(get_db)]
```

**Usage pattern for endpoints:**
```python
from llm_pipeline.ui.deps import DBSession

@router.get("/runs")
async def list_runs(db: DBSession):
    results = db.exec(select(PipelineStepState).where(...))
```

## ReadOnlySession -- `llm_pipeline/session/readonly.py`

Wraps `sqlmodel.Session`. Allows: `query`, `exec`, `get`, `execute`, `scalar`, `scalars`. Blocks: `add`, `add_all`, `delete`, `flush`, `commit`, `merge`, `refresh`, `expire*`, `expunge*`.

No `close()` method -- deps.py closes the underlying session directly.

**Implication for task 20:** All GET endpoints use `DBSession` (ReadOnlySession). Any write endpoint (POST /runs) cannot use this dependency -- needs a separate write session dependency or a different approach.

## Database Init -- `llm_pipeline/db/__init__.py`

- `init_pipeline_db(engine=None)` -- creates tables, sets module-level `_engine`
- `get_engine()` -- returns `_engine`, initializes if needed
- `get_session()` -- returns `Session(get_engine())`
- Default DB: `LLM_PIPELINE_DB` env var or `.llm_pipeline/pipeline.db`
- Creates 4 tables: pipeline_step_states, pipeline_run_instances, prompts, pipeline_events

## pyproject.toml Dependencies

**Core:** pydantic>=2.0, sqlmodel>=0.0.14, sqlalchemy>=2.0, pyyaml>=6.0
**UI optional:** fastapi>=0.100, uvicorn[standard]>=0.20
**Dev:** pytest, pytest-cov, google-generativeai, fastapi, uvicorn

**Note from task 19 summary:** `httpx` should be added to dev deps for FastAPI TestClient endpoint integration tests.

## Index Gap Analysis for Runs API

Current indexes on `pipeline_step_states`:
- (run_id, step_number) -- good for single-run step listing
- (pipeline_name, step_name, input_hash) -- cache lookups, not useful for run listing

**Missing for run listing:**
- No index on (pipeline_name) alone for filtered run listing
- No index on created_at for date range queries
- No covering index for the aggregate "list all runs" query pattern

**pipeline_events** indexes:
- (run_id, event_type) -- good for "get events for run"
- (event_type) -- good for "all pipeline_started events" query

## Task 19 Deviations (from SUMMARY.md)

1. Lazy router imports inside create_app() body (not module-level) -- intentional
2. Test file named `tests/test_ui.py` not `tests/test_ui_app.py` -- minor
3. fastapi + uvicorn added to dev deps (not in original plan) -- needed for CI

No deviations affect task 20 approach.

## Downstream Task 21 (OUT OF SCOPE)

Task 21: Steps and Events API endpoints. Depends on task 20. Covers:
- GET /runs/{run_id}/steps
- GET /runs/{run_id}/steps/{step_number}
- GET /runs/{run_id}/context
- GET /runs/{run_id}/events

These are NOT in scope for task 20. Task 20 covers only:
- GET /runs (list, paginated, filtered)
- GET /runs/{run_id} (detail with step summary)
- POST /runs (trigger execution -- SCOPE QUESTION, see below)

## Unresolved Questions

See response status block -- 3 questions require CEO input before proceeding.
