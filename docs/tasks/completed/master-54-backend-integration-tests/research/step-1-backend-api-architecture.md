# Research Step 1: Backend API Architecture

## 1. API Surface Area

### Active REST Endpoints (all prefixed /api)

| # | Method | Path | Router | Response Model | Key Params |
|---|--------|------|--------|----------------|------------|
| 1 | GET | /api/runs | runs | RunListResponse | pipeline_name, status, started_after, started_before, offset (0), limit (50, max 200) |
| 2 | GET | /api/runs/{run_id} | runs | RunDetail | - |
| 3 | POST | /api/runs | runs | TriggerRunResponse (202) | body: TriggerRunRequest {pipeline_name} |
| 4 | GET | /api/runs/{run_id}/context | runs | ContextEvolutionResponse | - |
| 5 | GET | /api/runs/{run_id}/steps | steps | StepListResponse | - |
| 6 | GET | /api/runs/{run_id}/steps/{step_number} | steps | StepDetail | - |
| 7 | GET | /api/runs/{run_id}/events | events | EventListResponse | event_type, offset (0), limit (100, max 500) |

### WebSocket Endpoint (no /api prefix)

| # | Protocol | Path | Behavior |
|---|----------|------|----------|
| 8 | WS | /ws/runs/{run_id} | completed/failed: batch replay then close(1000); running: live stream via queue fan-out; unknown: error + close(4004) |

### Empty Stub Routers (no endpoints)

| Router | Prefix | Status |
|--------|--------|--------|
| prompts | /api/prompts | Stub only |
| pipelines | /api/pipelines | Stub only |

## 2. Response Models

### Runs
- **RunListResponse**: items (RunListItem[]), total, offset, limit
- **RunListItem**: run_id, pipeline_name, status, started_at, completed_at?, step_count?, total_time_ms?
- **RunDetail**: extends RunListItem + steps (StepSummary[])
- **StepSummary**: step_name, step_number, execution_time_ms?, created_at
- **TriggerRunRequest**: pipeline_name (body)
- **TriggerRunResponse**: run_id, status ("accepted")
- **ContextEvolutionResponse**: run_id, snapshots (ContextSnapshot[])
- **ContextSnapshot**: step_name, step_number, context_snapshot (dict)

### Steps
- **StepListResponse**: items (StepListItem[])
- **StepListItem**: step_name, step_number, execution_time_ms?, model?, created_at
- **StepDetail**: full fields including pipeline_name, run_id, input_hash, result_data (dict), context_snapshot (dict), prompt_system_key?, prompt_user_key?, prompt_version?, model?, execution_time_ms?, created_at

### Events
- **EventListResponse**: items (EventItem[]), total, offset, limit
- **EventItem**: event_type, pipeline_name, run_id, timestamp, event_data (dict)

### WebSocket Messages
- Live event: arbitrary dict (event.to_dict() from PipelineEvent subclasses)
- Heartbeat: `{"type": "heartbeat", "timestamp": "<iso>"}`
- Stream complete: `{"type": "stream_complete", "run_id": "<id>"}`
- Replay complete: `{"type": "replay_complete", "run_status": "<status>", "event_count": <n>}`
- Error: `{"type": "error", "detail": "<msg>"}`

## 3. Database Models Used by API

| Model | Table | Key Fields |
|-------|-------|------------|
| PipelineRun | pipeline_runs | run_id (unique), pipeline_name, status, started_at, completed_at, step_count, total_time_ms |
| PipelineStepState | pipeline_step_states | run_id, pipeline_name, step_name, step_number, input_hash, result_data (JSON), context_snapshot (JSON), prompt_*, model, execution_time_ms, created_at |
| PipelineEventRecord | pipeline_events | run_id, event_type, pipeline_name, timestamp, event_data (JSON) |

## 4. Key Architecture Patterns

### App Factory
- `create_app(db_path, cors_origins, pipeline_registry, introspection_registry)` in `llm_pipeline/ui/app.py`
- Engine stored on `app.state.engine`
- Pipeline registry stored on `app.state.pipeline_registry`
- Routers mounted: 5 under `/api` prefix, 1 WebSocket without prefix

### Dependency Injection
- `DBSession` = `Annotated[ReadOnlySession, Depends(get_db)]`
- `get_db()` creates `Session(engine)` from `request.app.state.engine`, wraps in `ReadOnlySession`
- All REST endpoints use sync `def` (FastAPI threadpool wraps automatically)

### WebSocket Architecture
- `ConnectionManager` singleton in `websocket.py` module level
- Per-client `threading.Queue` for fan-out (NOT asyncio.Queue)
- `UIBridge` (in `bridge.py`) calls `manager.broadcast_to_run()` and `manager.signal_run_complete()` synchronously
- `_stream_events()` uses `asyncio.to_thread(queue.get, ...)` to bridge sync queue to async WS
- Heartbeat on inactivity (30s default, monkeypatchable)

### Trigger Run Flow
1. POST /api/runs -> validates pipeline_name in registry -> generates UUID
2. Background task: creates UIBridge -> calls factory(run_id, engine, event_emitter=bridge) -> pipeline.execute() + pipeline.save()
3. On exception: updates PipelineRun.status = "failed" in DB
4. Finally block: bridge.complete() (sends None sentinel to all WS clients)

## 5. Existing Test Coverage

### Test Files and Counts

| File | Tests | Scope |
|------|-------|-------|
| tests/ui/conftest.py | (fixtures) | _make_app, app_client, seeded_app_client |
| tests/ui/test_runs.py | 19 | GET/POST /api/runs, trigger run |
| tests/ui/test_steps.py | 10 | GET steps + context evolution |
| tests/ui/test_events.py | 12 | GET events with filters/pagination |
| tests/ui/test_websocket.py | 6 | WS batch replay, live stream, heartbeat, not-found |
| tests/ui/test_bridge.py | 27 | UIBridge unit tests (emit, complete, DI, repr, protocol) |
| tests/ui/test_cli.py | 27 | CLI entry point (prod/dev mode, cleanup, import guard) |
| tests/ui/test_wal.py | 4 | WAL mode verification |
| tests/test_ui.py | 23 | App factory, deps, router structure, pyproject.toml |
| **Total** | **~128** | |

### Test Infrastructure Patterns

**conftest.py _make_app():**
```python
# Uses StaticPool + check_same_thread=False for true in-memory shared DB
engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
init_pipeline_db(engine)
app = FastAPI(...)
app.state.engine = engine
# Manually includes all routers (does NOT use create_app factory)
```

**Seeded data (seeded_app_client):**
- 3 PipelineRun: completed (run1), failed (run2), running (run3)
- 3 PipelineStepState: 2 for run1, 1 for run2
- 4 PipelineEventRecord: all for run1 (started, step_started, step_completed, pipeline_completed)

**WebSocket test helper:**
```python
def _wait_for_connection(run_id, count=1, timeout=2.0):
    # Spins until manager._queues has expected connections
```

**Trigger run tests:**
- Use `create_app(db_path=":memory:", pipeline_registry={...})` directly
- Factory lambdas accept `**kw` for forward-compat with event_emitter kwarg

## 6. Gap Analysis - What Integration Tests Are Missing

### GAP 1: End-to-End Pipeline Trigger + WebSocket Live Events (CRITICAL)
No test exercises: POST /api/runs -> WS /ws/runs/{run_id} receives events -> verify DB state.
Task 26 SUMMARY.md recommendation #2 explicitly calls this out.
Needs: a fake pipeline factory that emits real PipelineEvent instances through UIBridge.

### GAP 2: create_app() Factory Integration (MEDIUM)
All conftest fixtures use `_make_app()` which manually constructs the app. No test verifies `create_app()` itself produces a working app with TestClient.
Needs: test that uses `create_app(db_path=":memory:")` -> TestClient -> exercises endpoints.

### GAP 3: Trigger Run Error Handling DB Update (MEDIUM)
`trigger_run()` has a try/except that updates PipelineRun.status="failed" on exception. No test verifies this DB update path.
Needs: factory that raises during execute() -> verify run status in DB.

### GAP 4: Trigger Run UIBridge Wiring Verification (MEDIUM)
Current trigger tests use mocked pipelines but never verify that UIBridge.emit() actually reaches WebSocket clients during a triggered run.
Covered by GAP 1 if addressed.

### GAP 5: WebSocket Disconnect During Live Stream (LOW)
No test verifies cleanup when a client disconnects mid-stream.
ConnectionManager.disconnect() is tested implicitly but not the full WS disconnect lifecycle.

### GAP 6: Combined Filter Tests (LOW)
No test uses multiple filters simultaneously (e.g., pipeline_name + status on /api/runs).

### GAP 7: CORS Response Headers (LOW)
Only middleware config is tested, not actual response headers in HTTP responses.

## 7. Recommended Test Structure

### File: `tests/ui/test_integration.py`
Follows existing convention (tests/ui/ directory). Contains only genuinely new integration tests that exercise cross-component flows not covered by existing unit/endpoint tests.

### Proposed Test Classes:

```
class TestCreateAppIntegration:
    # Verify create_app() produces working app with all endpoints
    test_create_app_runs_endpoint_works
    test_create_app_steps_endpoint_works
    test_create_app_events_endpoint_works
    test_create_app_websocket_works
    test_create_app_with_pipeline_registry
    test_create_app_with_introspection_registry

class TestTriggerRunIntegration:
    # Trigger pipeline and verify full lifecycle
    test_trigger_creates_pipeline_run_in_db
    test_trigger_failing_pipeline_sets_status_failed
    test_trigger_failing_pipeline_sets_completed_at
    test_trigger_pipeline_emits_events_via_uibridge
    test_trigger_calls_bridge_complete_in_finally

class TestWebSocketIntegration:
    # End-to-end: trigger + WS live events
    test_trigger_run_events_received_on_websocket
    test_trigger_run_websocket_stream_complete_on_finish
    test_trigger_run_websocket_receives_error_event_on_failure
    test_websocket_disconnect_cleanup

class TestCombinedFilters:
    # Multiple filter params together
    test_runs_filter_pipeline_name_and_status
    test_runs_filter_pipeline_name_and_started_after
    test_events_filter_event_type_with_pagination

class TestCORSHeaders:
    # Verify actual response headers
    test_cors_allows_any_origin
    test_cors_preflight_options_request
```

## 8. Test Dependencies Required

Already in dev dependencies (pyproject.toml):
- pytest
- fastapi (TestClient from starlette)
- httpx (already listed in dev deps)
- sqlalchemy (StaticPool for in-memory shared DB)
- sqlmodel

No new dependencies needed.

## 9. Known Issues

### Pre-existing test failure
`tests/test_ui.py::TestRoutersIncluded::test_events_router_prefix` asserts `prefix == "/events"` but actual router prefix is `/runs/{run_id}/events`. Introduced by task 28, unrelated to task 54. OUT OF SCOPE.

## 10. Out of Scope

- Task 56 (Performance Benchmarking) - downstream, depends on this task
- Task 57 (Documentation) - downstream, depends on this task
- Empty stub routers (prompts, pipelines) - no endpoints to test
- Frontend integration tests
- Load testing / concurrent connection tests (task 56 scope)

## 11. Upstream Context

### Task 26 (UIBridge Event Handler) - DONE
- Created `llm_pipeline/ui/bridge.py` with UIBridge class
- Wired UIBridge into trigger_run() in runs.py
- Deviation: uses sync delegation (threading.Queue.put_nowait) not asyncio.Queue
- Recommendation: integration test for full WS fan-out path (this is what task 54 addresses)
