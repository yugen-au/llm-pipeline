# Research Step 2: Python Testing Patterns for Backend Integration Tests

## 1. Existing Test Infrastructure

### pytest Configuration (pyproject.toml)
- `testpaths = ["tests"]`, `pythonpath = ["."]`
- Test deps in `[project.optional-dependencies].dev`: pytest>=7.0, pytest-cov>=4.0, httpx>=0.24, fastapi>=0.115.0
- No pytest-asyncio or anyio -- not needed since TestClient handles async transparently

### Test Directory Structure
```
tests/
  __init__.py
  test_ui.py                    # app factory, deps, route stubs, pyproject validation (~30 tests)
  test_init_pipeline_db.py      # DB init tests
  test_pipeline_run_tracking.py
  test_introspection.py
  events/
    conftest.py                 # MockProvider, test pipelines, engine/session fixtures
    test_handlers.py, test_pipeline_lifecycle_events.py, ...
  ui/
    __init__.py
    conftest.py                 # app_client, seeded_app_client fixtures
    test_runs.py                # 21 tests: TestListRuns, TestGetRun, TestTriggerRun
    test_steps.py               # 14 tests: TestListSteps, TestGetStep, TestContextEvolution
    test_events.py              # 12 tests: TestListEvents
    test_websocket.py           # 6 tests: TestBatchReplay, TestNotFound, TestLiveStream, TestHeartbeat
    test_bridge.py              # ~20 tests: UIBridge unit tests
    test_cli.py                 # ~20 tests: CLI command tests
    test_wal.py                 # 4 tests: WAL mode verification
```

## 2. FastAPI TestClient Patterns (Established in Codebase)

### REST API Testing
All endpoints are **sync `def`** (not async). TestClient wraps them in a threadpool automatically.

```python
# Pattern: fixture-based client injection
class TestListRuns:
    def test_empty_returns_200(self, app_client):
        resp = app_client.get("/api/runs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []

    def test_pagination(self, seeded_app_client):
        page1 = seeded_app_client.get("/api/runs", params={"limit": 2, "offset": 0}).json()
        assert len(page1["items"]) == 2
```

Key conventions:
- `starlette.testclient.TestClient` (not `fastapi.testclient` -- both work, project uses starlette)
- `resp.status_code` and `resp.json()` for assertions
- `params={}` kwarg for query parameters
- `json={}` kwarg for POST request bodies
- No `await` needed -- all synchronous

### WebSocket Testing
```python
# Pattern: websocket_connect context manager
class TestBatchReplay:
    def test_batch_replay_completed_run(self, seeded_app_client):
        with seeded_app_client.websocket_connect(f"/ws/runs/{RUN_COMPLETED}") as ws:
            events = []
            while True:
                msg = ws.receive_json()
                if msg.get("type") == "replay_complete":
                    break
                events.append(msg)
        assert len(events) == 4
```

Key conventions:
- `client.websocket_connect(path)` as context manager
- `ws.receive_json()`, `ws.send_json()` for message exchange
- Module-level `manager` singleton requires cleanup between tests via autouse fixture
- `_wait_for_connection()` helper for timing-sensitive live stream tests
- `manager.broadcast_to_run()` and `manager.signal_run_complete()` called directly in tests

### WebSocket Manager Cleanup Pattern
```python
from llm_pipeline.ui.routes.websocket import manager

@pytest.fixture(autouse=True)
def _clean_manager():
    manager._connections.clear()
    manager._queues.clear()
    yield
    manager._connections.clear()
    manager._queues.clear()
```

## 3. Database Fixture Patterns

### In-Memory SQLite with StaticPool (Critical Pattern)
```python
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine
from llm_pipeline.db import init_pipeline_db

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
init_pipeline_db(engine)
```

Why StaticPool:
- All connections share the **same** in-memory database
- Without StaticPool, each connection gets a separate empty DB
- `check_same_thread=False` required because FastAPI runs sync endpoints in threadpool workers
- This pattern is used in `tests/ui/conftest.py::_make_app()`

### Two-Tier Fixture Strategy
1. **`app_client`** -- empty DB, for testing empty-state and validation behavior
2. **`seeded_app_client`** -- pre-populated with 3 runs, 3 steps, 4 events

Seeding pattern uses direct SQLModel Session:
```python
with Session(engine) as session:
    run1 = PipelineRun(run_id="aaaaaaaa-...-001", pipeline_name="alpha_pipeline", ...)
    session.add(run1)
    session.commit()
```

### _make_app() vs create_app()
- `_make_app()` in conftest.py builds the app manually with StaticPool engine -- used for most tests
- `create_app(db_path=":memory:")` uses the standard factory -- used in TestTriggerRun and test_ui.py
- Difference: `_make_app()` guarantees thread-safe shared DB; `create_app(":memory:")` may not use StaticPool

## 4. Test Organization Conventions

### Class-Based Grouping
Tests grouped by endpoint/feature using classes:
- `TestListRuns`, `TestGetRun`, `TestTriggerRun` (in test_runs.py)
- `TestListSteps`, `TestGetStep`, `TestContextEvolution` (in test_steps.py)
- `TestBatchReplay`, `TestNotFound`, `TestLiveStream`, `TestHeartbeat` (in test_websocket.py)

### One File Per Route Module
- `test_runs.py` -> `routes/runs.py`
- `test_steps.py` -> `routes/steps.py`
- `test_events.py` -> `routes/events.py`
- `test_websocket.py` -> `routes/websocket.py`

### Module-Level Constants
```python
RUN_1 = "aaaaaaaa-0000-0000-0000-000000000001"
RUN_2 = "aaaaaaaa-0000-0000-0000-000000000002"
RUN_3 = "aaaaaaaa-0000-0000-0000-000000000003"
NONEXISTENT = "ffffffff-0000-0000-0000-000000000099"
```

### No Parametrization Used
Current tests use individual test methods rather than `@pytest.mark.parametrize`. This is a stylistic choice -- each test is explicit and self-documenting.

## 5. Async Test Patterns

**Not needed.** The codebase does not use pytest-asyncio. Key reasons:
- All REST endpoints are sync `def` (FastAPI auto-wraps in threadpool)
- WebSocket endpoint is `async def` but TestClient handles this transparently
- SQLite operations are synchronous
- WebSocket module uses `asyncio.to_thread()` for DB queries internally, but this is abstracted from tests

## 6. Coverage Analysis -- Existing Tests vs Task 54 Scope

### Endpoints With Full Test Coverage
| Endpoint | Method | Test File | Test Count |
|----------|--------|-----------|------------|
| `/api/runs` | GET | test_runs.py::TestListRuns | 10 |
| `/api/runs` | POST | test_runs.py::TestTriggerRun | 5 |
| `/api/runs/{run_id}` | GET | test_runs.py::TestGetRun | 6 |
| `/api/runs/{run_id}/context` | GET | test_steps.py::TestContextEvolution | 5 |
| `/api/runs/{run_id}/steps` | GET | test_steps.py::TestListSteps | 5 |
| `/api/runs/{run_id}/steps/{n}` | GET | test_steps.py::TestGetStep | 4 |
| `/api/runs/{run_id}/events` | GET | test_events.py::TestListEvents | 12 |
| `/ws/runs/{run_id}` | WS | test_websocket.py | 6 |

### Empty Router Stubs (No Endpoints to Test)
- `/api/prompts` -- router exists but has no endpoint handlers
- `/api/pipelines` -- router exists but has no endpoint handlers

### Coverage Observations
All implemented REST and WebSocket endpoints have existing integration tests. Tests cover:
- Happy path responses
- Pagination (offset/limit)
- Filtering (pipeline_name, status, started_after/before, event_type)
- 404 for nonexistent resources
- 422 for invalid query params
- Response schema field presence
- Ordering guarantees (desc by started_at, asc by step_number/timestamp)
- Background task execution (TestTriggerRun)
- WebSocket batch replay, live streaming, multiple clients, heartbeat, error handling

### Potential Gap Areas (Minor)
1. No parametrized tests for combined filter queries (e.g., pipeline_name + status together)
2. No test for POST /api/runs with invalid JSON body (missing pipeline_name field)
3. No concurrent WebSocket connection stress test (deferred to Task 56 per downstream scope)
4. No test for WebSocket disconnect during live stream (exception path covered by except WebSocketDisconnect)

## 7. Recommended Patterns for Any New Tests

### For New REST Endpoint Tests
Follow existing convention -- add to the appropriate existing test file:
```python
# In tests/ui/test_runs.py
class TestListRuns:
    # ... existing tests ...

    def test_combined_filters_pipeline_and_status(self, seeded_app_client):
        resp = seeded_app_client.get(
            "/api/runs",
            params={"pipeline_name": "alpha_pipeline", "status": "completed"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
```

### For New WebSocket Tests
```python
# In tests/ui/test_websocket.py
class TestDisconnectDuringStream:
    def test_client_disconnect_mid_stream(self, seeded_app_client):
        # WebSocketDisconnect is swallowed by the handler
        with seeded_app_client.websocket_connect(f"/ws/runs/{RUN_RUNNING}") as ws:
            _wait_for_connection(RUN_RUNNING, count=1)
            manager.broadcast_to_run(RUN_RUNNING, {"event_type": "test"})
            ws.receive_json()  # consume the event
            # closing early triggers disconnect
```

### Fixture Reuse
Always use `app_client` for empty-state tests and `seeded_app_client` for populated-state tests. If new seed data is needed, extend `seeded_app_client` or create a specialized fixture in the specific test file.

## 8. Key Dependencies and Imports

```python
# Test infrastructure
import pytest
from starlette.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session

# Application
from llm_pipeline.db import init_pipeline_db
from llm_pipeline.ui.app import create_app
from llm_pipeline.state import PipelineRun, PipelineStepState
from llm_pipeline.events.models import PipelineEventRecord
from llm_pipeline.ui.routes.websocket import manager
```

## 9. Summary

The existing test suite at `tests/ui/` provides comprehensive integration test coverage for all implemented Phase 2 backend endpoints. The established patterns are:
- **Sync TestClient** for both REST and WebSocket (no async test framework needed)
- **StaticPool in-memory SQLite** for thread-safe DB testing
- **Two-tier fixtures** (empty vs seeded) in `tests/ui/conftest.py`
- **Class-based organization** grouped by endpoint, one file per route module
- **Direct assertions** without parametrization (explicit, self-documenting style)

Task 54's spec suggests creating `tests/test_ui_backend.py` but existing tests in `tests/ui/` already cover all endpoints. Implementation phase should determine whether to add gap tests to existing files or consolidate.
