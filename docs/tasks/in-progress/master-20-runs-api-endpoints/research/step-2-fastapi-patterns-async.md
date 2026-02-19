# Step 2: FastAPI Patterns & Async Research

## 1. Pagination Pattern: Offset/Limit

### Recommendation: Offset/Limit for v1

Offset/limit is the correct choice for this use case. Cursor-based pagination is better suited for infinite-scroll UIs or real-time feeds with frequent inserts; neither applies here. With proper indexing (see step-3 research), offset/limit handles 10k+ runs well within the <200ms target.

### Query Parameter Model Pattern

FastAPI supports Pydantic models as query parameter containers via `Query()`. This is cleaner than individual parameters when there are 4+ filters.

```python
from datetime import datetime
from typing import Annotated, Optional
from fastapi import Query
from pydantic import BaseModel, Field

class RunListParams(BaseModel):
    """Query parameters for GET /runs."""
    model_config = {"extra": "forbid"}

    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, gt=0, le=100)
    pipeline_name: Optional[str] = None
    status: Optional[str] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None

# Usage in endpoint:
@router.get("/runs")
def list_runs(
    db: DBSession,
    params: Annotated[RunListParams, Query()],
): ...
```

**Note on `extra="forbid"`:** Rejects unknown query params with 422, preventing typos like `?pipline_name=...` from silently returning unfiltered results.

**Alternative (individual params):** Simpler, but less structured:
```python
@router.get("/runs")
def list_runs(
    db: DBSession,
    offset: int = 0,
    limit: int = Query(default=50, le=100),
    pipeline_name: Optional[str] = None,
    created_after: Optional[datetime] = None,
    created_before: Optional[datetime] = None,
): ...
```

Both patterns work. The Pydantic model approach is recommended for consistency and reuse (e.g., the model can be imported in tests).

---

## 2. Sync vs Async Endpoints

### Key Insight: The Codebase is Entirely Sync

- `PipelineConfig.execute()` is sync
- `SQLModel.Session` is sync
- `ReadOnlySession` wraps sync `Session`
- `init_pipeline_db()` uses sync `create_engine()`
- No async SQLAlchemy engine or async session anywhere in the codebase

### Recommendation: Use `def` (Not `async def`) for DB-Reading Endpoints

FastAPI handles `def` endpoints by running them in a threadpool automatically (via `anyio.to_thread.run_sync`). This means:

- `def` endpoints with sync DB calls: FastAPI runs them in threadpool, non-blocking to the event loop
- `async def` endpoints with sync DB calls: **BLOCKS the event loop** (wrong)
- `async def` endpoints with `await asyncio.to_thread(sync_call)`: Works but adds boilerplate for zero benefit

**Correct pattern for GET endpoints:**
```python
from llm_pipeline.ui.deps import DBSession

@router.get("/runs")
def list_runs(db: DBSession):
    # sync DB calls here - FastAPI auto-runs in threadpool
    results = db.exec(select(PipelineStepState).where(...))
    return results
```

**Do NOT do this:**
```python
@router.get("/runs")
async def list_runs(db: DBSession):
    # WRONG: sync DB call inside async def blocks the event loop
    results = db.exec(select(PipelineStepState).where(...))
    return results
```

### When to Use `async def`

Only if the endpoint body uses `await` (e.g., calling httpx, aiofiles, or `asyncio.to_thread`). For the Runs API, only the POST /runs trigger endpoint needs this pattern.

---

## 3. Response Model Patterns with SQLModel + Pydantic v2

### Pattern: Separate Read Models (No `table=True`)

SQLModel models with `table=True` carry SQLAlchemy metadata that shouldn't leak into API responses. Create plain SQLModel (or Pydantic BaseModel) classes for response serialization.

### Run List Item (Slim)

```python
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel

class RunListItem(SQLModel):
    """Slim run representation for list endpoint. No JSON blobs."""
    run_id: str
    pipeline_name: str
    status: str  # "running", "completed", "failed"
    started_at: datetime
    completed_at: Optional[datetime] = None
    step_count: int = 0
    total_time_ms: Optional[int] = None
```

### Paginated Response (Generic Wrapper)

```python
from typing import Generic, TypeVar, Sequence
from pydantic import BaseModel

T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper."""
    items: Sequence[T]
    total: int
    offset: int
    limit: int
```

Usage: `response_model=PaginatedResponse[RunListItem]`

This generates correct OpenAPI schema with typed items array.

### Run Detail (Full, with Steps)

```python
class StepSummary(SQLModel):
    """Step info included in run detail response."""
    step_number: int
    step_name: str
    execution_time_ms: Optional[int] = None
    model: Optional[str] = None
    created_at: datetime

class RunDetail(SQLModel):
    """Full run detail with step summaries."""
    run_id: str
    pipeline_name: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    step_count: int
    total_time_ms: Optional[int] = None
    steps: list[StepSummary] = []
```

### Construction Pattern (Mapping DB Rows to Response Models)

For aggregated query results (not ORM instances), use dict unpacking or manual construction:

```python
# From PipelineRun ORM instance (if Option C table exists):
RunListItem.model_validate(run_row)

# From raw Row result (GROUP BY query):
RunListItem(
    run_id=row.run_id,
    pipeline_name=row.pipeline_name,
    status="completed",  # derived
    started_at=row.started_at,
    completed_at=row.completed_at,
    step_count=row.step_count,
    total_time_ms=row.total_time_ms,
)
```

---

## 4. POST /runs: Triggering Async Pipeline Execution

### The Problem

`PipelineConfig.execute()` is sync and long-running (seconds to minutes for LLM calls). The API must return immediately with a run_id while execution proceeds in the background.

### Pattern A: BackgroundTasks (Recommended for v1)

FastAPI's `BackgroundTasks` runs functions after the response is sent. Handles both sync and async callables.

```python
from fastapi import BackgroundTasks, HTTPException
from pydantic import BaseModel

class RunCreateRequest(BaseModel):
    pipeline_name: str
    data: dict  # raw input data
    initial_context: dict = {}
    use_cache: bool = False

class RunCreateResponse(BaseModel):
    run_id: str
    status: str = "running"

def _execute_pipeline(pipeline_name: str, data: dict, context: dict, use_cache: bool):
    """Sync function that runs in background."""
    # Resolve pipeline class from name, instantiate, execute
    # This is a sync call - BackgroundTasks handles it via run_in_executor
    pipeline = resolve_pipeline(pipeline_name)
    pipeline.execute(data, context, use_cache=use_cache)

@router.post("/runs", status_code=202, response_model=RunCreateResponse)
def trigger_run(
    request: RunCreateRequest,
    background_tasks: BackgroundTasks,
):
    run_id = str(uuid.uuid4())
    # Create initial run record (needs writable session)
    # ...
    background_tasks.add_task(
        _execute_pipeline,
        request.pipeline_name,
        request.data,
        request.initial_context,
        request.use_cache,
    )
    return RunCreateResponse(run_id=run_id, status="running")
```

**Key details:**
- Returns **202 Accepted** (not 201 Created) since execution is deferred
- `BackgroundTasks` runs sync functions via `run_in_executor` automatically
- No need for `asyncio.to_thread` wrapper -- BackgroundTasks handles it
- The sync endpoint (`def`, not `async def`) is fine here since the endpoint itself does minimal work

### Pattern B: asyncio.create_task + asyncio.to_thread

More control than BackgroundTasks. Useful if you need to track the task or cancel it.

```python
import asyncio

@router.post("/runs", status_code=202)
async def trigger_run(request: RunCreateRequest):
    run_id = str(uuid.uuid4())

    async def run_in_background():
        await asyncio.to_thread(
            _execute_pipeline,
            request.pipeline_name,
            request.data,
            request.initial_context,
            request.use_cache,
        )

    asyncio.create_task(run_in_background())
    return RunCreateResponse(run_id=run_id, status="running")
```

**Tradeoffs:**
- `async def` required (uses `await`)
- Task survives beyond request lifecycle
- Task reference can be stored for cancellation
- More complex error handling (exceptions in fire-and-forget tasks are silent)

### Recommendation

**BackgroundTasks for v1.** Simpler, built into FastAPI, sufficient for the use case. If task cancellation or progress tracking via task handles is needed later, switch to Pattern B or a proper task queue (Celery, etc.).

### Writable Session for POST /runs

The current `get_db()` dependency yields `ReadOnlySession`. The POST endpoint needs to write (create run record, update status on completion). Options:

```python
# Option 1: Separate writable dependency
def get_write_db(request: Request) -> Generator[Session, None, None]:
    engine = request.app.state.engine
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()

WriteDBSession = Annotated[Session, Depends(get_write_db)]
```

```python
# Option 2: Use db.get_session() directly in the background function
# (not via FastAPI DI since background tasks outlive the request)
from llm_pipeline.db import get_session

def _execute_pipeline(...):
    session = get_session()
    try:
        # create/update run records
        ...
    finally:
        session.close()
```

Option 2 is recommended for the background execution function since the session lifecycle must span the entire pipeline execution, not be tied to the request.

---

## 5. Error Handling Patterns

### 404: Run Not Found

```python
from fastapi import HTTPException

@router.get("/runs/{run_id}")
def get_run(run_id: str, db: DBSession):
    steps = db.exec(
        select(PipelineStepState)
        .where(PipelineStepState.run_id == run_id)
        .order_by(PipelineStepState.step_number)
    ).all()

    if not steps:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    return build_run_detail(run_id, steps)
```

If PipelineRun table exists (Option C from step-3 research):
```python
@router.get("/runs/{run_id}")
def get_run(run_id: str, db: DBSession):
    run = db.exec(
        select(PipelineRun).where(PipelineRun.run_id == run_id)
    ).first()

    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    steps = db.exec(
        select(PipelineStepState)
        .where(PipelineStepState.run_id == run_id)
        .order_by(PipelineStepState.step_number)
    ).all()

    return RunDetail(
        **run.model_dump(),
        steps=[StepSummary.model_validate(s) for s in steps],
    )
```

### Validation Errors (422)

Handled automatically by FastAPI + Pydantic. The `RunListParams` model with `extra="forbid"` and field constraints (`ge=0`, `le=100`) produces standard 422 responses. No custom code needed.

### Pipeline Not Found (POST /runs)

```python
@router.post("/runs", status_code=202)
def trigger_run(request: RunCreateRequest, background_tasks: BackgroundTasks):
    pipeline_class = PIPELINE_REGISTRY.get(request.pipeline_name)
    if not pipeline_class:
        raise HTTPException(
            status_code=404,
            detail=f"Pipeline '{request.pipeline_name}' not found"
        )
    # ...
```

### Custom Error Response Model (Optional)

```python
class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None

@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(detail=exc.detail).model_dump(),
    )
```

This is optional -- FastAPI's default error responses are fine for v1.

---

## 6. Complete Endpoint Skeleton

Putting all patterns together for the runs router:

```python
"""Pipeline runs route module."""
import uuid
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from llm_pipeline.state import PipelineStepState
from llm_pipeline.ui.deps import DBSession

router = APIRouter(prefix="/runs", tags=["runs"])


# --- Request/Response Models ---

class RunListParams(BaseModel):
    model_config = {"extra": "forbid"}
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, gt=0, le=100)
    pipeline_name: Optional[str] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None


class RunListItem(BaseModel):
    run_id: str
    pipeline_name: str
    step_count: int
    total_time_ms: int
    started_at: datetime
    completed_at: datetime


class PaginatedRuns(BaseModel):
    items: list[RunListItem]
    total: int
    offset: int
    limit: int


class RunCreateRequest(BaseModel):
    pipeline_name: str
    data: dict
    initial_context: dict = {}
    use_cache: bool = False


class RunCreateResponse(BaseModel):
    run_id: str
    status: str = "running"


# --- Endpoints ---

@router.get("", response_model=PaginatedRuns)
def list_runs(
    db: DBSession,
    params: Annotated[RunListParams, Query()],
):
    """List pipeline runs with pagination and optional filters."""
    # Build base aggregation query (GROUP BY fallback)
    # or direct select (if PipelineRun table exists)
    base = (
        select(
            PipelineStepState.run_id,
            PipelineStepState.pipeline_name,
            func.count(PipelineStepState.id).label("step_count"),
            func.coalesce(
                func.sum(PipelineStepState.execution_time_ms), 0
            ).label("total_time_ms"),
            func.min(PipelineStepState.created_at).label("started_at"),
            func.max(PipelineStepState.created_at).label("completed_at"),
        )
        .group_by(
            PipelineStepState.run_id,
            PipelineStepState.pipeline_name,
        )
    )

    if params.pipeline_name:
        base = base.where(
            PipelineStepState.pipeline_name == params.pipeline_name
        )
    if params.created_after:
        base = base.having(
            func.min(PipelineStepState.created_at) >= params.created_after
        )
    if params.created_before:
        base = base.having(
            func.min(PipelineStepState.created_at) <= params.created_before
        )

    subq = base.subquery()
    total = db.scalar(select(func.count()).select_from(subq))

    rows = db.execute(
        select(subq)
        .order_by(subq.c.started_at.desc())
        .offset(params.offset)
        .limit(params.limit)
    ).all()

    items = [
        RunListItem(
            run_id=r.run_id,
            pipeline_name=r.pipeline_name,
            step_count=r.step_count,
            total_time_ms=r.total_time_ms,
            started_at=r.started_at,
            completed_at=r.completed_at,
        )
        for r in rows
    ]

    return PaginatedRuns(
        items=items,
        total=total or 0,
        offset=params.offset,
        limit=params.limit,
    )


@router.get("/{run_id}")
def get_run(run_id: str, db: DBSession):
    """Get detailed run info with step summaries."""
    steps = db.exec(
        select(PipelineStepState)
        .where(PipelineStepState.run_id == run_id)
        .order_by(PipelineStepState.step_number)
    ).all()

    if not steps:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    return {
        "run_id": run_id,
        "pipeline_name": steps[0].pipeline_name,
        "step_count": len(steps),
        "total_time_ms": sum(s.execution_time_ms or 0 for s in steps),
        "started_at": steps[0].created_at,
        "completed_at": steps[-1].created_at,
        "steps": [
            {
                "step_number": s.step_number,
                "step_name": s.step_name,
                "execution_time_ms": s.execution_time_ms,
                "model": s.model,
                "created_at": s.created_at,
            }
            for s in steps
        ],
    }


@router.post("", status_code=202, response_model=RunCreateResponse)
def trigger_run(
    request: RunCreateRequest,
    background_tasks: BackgroundTasks,
):
    """Trigger async pipeline execution. Returns run_id immediately."""
    run_id = str(uuid.uuid4())
    # NOTE: actual implementation depends on architecture decisions
    # (pipeline registry, writable session, etc.)
    background_tasks.add_task(
        _execute_pipeline_background,
        run_id,
        request.pipeline_name,
        request.data,
        request.initial_context,
        request.use_cache,
    )
    return RunCreateResponse(run_id=run_id, status="running")


def _execute_pipeline_background(
    run_id: str,
    pipeline_name: str,
    data: dict,
    initial_context: dict,
    use_cache: bool,
):
    """Sync pipeline execution in background thread."""
    # Implementation depends on pipeline registry pattern
    # BackgroundTasks auto-runs sync functions via run_in_executor
    pass
```

---

## 7. Key Decisions Summary

| Decision | Recommendation | Rationale |
|----------|---------------|-----------|
| Pagination | Offset/limit | Simple, sufficient for 10k runs, cursor-based is premature |
| Endpoint style | `def` (sync) for GET | FastAPI auto-threadpools sync endpoints; avoids event loop blocking |
| Endpoint style | `def` (sync) for POST | BackgroundTasks handles sync callables via run_in_executor |
| Query params | Pydantic model with `Query()` | Clean, reusable, validates + documents automatically |
| Response models | Separate non-table SQLModel/BaseModel | Don't leak ORM metadata; slim list vs full detail |
| Background exec | BackgroundTasks | Built-in, simple; upgrade to task queue if cancellation needed |
| Error handling | HTTPException(404) + auto 422 | Standard FastAPI patterns, no custom handler needed for v1 |
| Writable session | Direct `get_session()` in background fn | Session lifecycle must span execution, not tied to request DI |

## 8. Architecture Questions (Need CEO Input)

These are identified by step-1 and step-3 research as well, listed here for completeness:

1. **Run listing source:** No dedicated runs table exists. Step-3 recommends creating `PipelineRun` table (Option C). Without it, listing requires GROUP BY aggregation on `pipeline_step_states` which may not meet <200ms at scale. The endpoint skeleton above uses the GROUP BY fallback but the PipelineRun table would simplify everything.

2. **POST /runs pipeline resolution:** `PipelineConfig` is abstract. How should the API resolve `pipeline_name` string to a concrete pipeline class? Options:
   - a) Global registry dict populated by pipeline subclasses at import time
   - b) Pipeline name passed to a factory function that imports the right module
   - c) POST /runs is view-only in v1 (defer trigger capability)

3. **POST /runs writable session:** Current `get_db()` yields `ReadOnlySession`. The POST endpoint and background execution function need write access. Recommendation: use `llm_pipeline.db.get_session()` directly in the background function (not via FastAPI DI).
