# PLANNING

## Summary

Write `tests/ui/test_integration.py` covering the 5 genuine cross-component integration gaps identified in validated research. Tests exercise POST /api/runs triggering a real UIBridge -> WS live stream flow (GAP 1, CRITICAL), the trigger-run error-handling DB update path (GAP 3), combined query filters (GAP 6), CORS response headers (GAP 7), and WebSocket mid-stream disconnect cleanup (GAP 5). All tests use the proven `_make_app()` + StaticPool pattern from `tests/ui/conftest.py`. No source changes required.

## Plugin & Agents

**Plugin:** backend-development
**Subagents:** python-development
**Skills:** none

## Phases

1. **Implementation**: Write `tests/ui/test_integration.py` with all test classes and a fake pipeline factory helper for E2E trigger+WS tests.

## Architecture Decisions

### Test Location
**Choice:** `tests/ui/test_integration.py`
**Rationale:** CEO decision. Follows existing `tests/ui/` convention. Imports conftest fixtures (already scoped to that directory). Keeps new cross-component tests separate from the per-route files.
**Alternatives:** `tests/test_ui_backend.py` (task 54 spec, stale), adding to existing per-route files (mixes unit and integration concerns)

### App Factory Pattern
**Choice:** `_make_app()` from `tests/ui/conftest.py` (private helper, not a pytest fixture)
**Rationale:** CEO decision. Proven StaticPool thread-safe in-memory SQLite pattern. `create_app(":memory:")` does not use StaticPool so threadpool workers get separate empty DBs -- makes seeded-data tests unreliable for trigger flow tests.
**Alternatives:** Extend `create_app()` to accept pre-built engine (requires source change, out of scope)

### Fake Pipeline Factory for E2E Test
**Choice:** Module-level lambda/class in test file that emits `PipelineStarted` + `PipelineCompleted` via UIBridge and creates a `PipelineRun` row directly using the passed engine.
**Rationale:** GAP 1 requires a real UIBridge emission path. Existing TestTriggerRun tests pass a no-op factory; the E2E test needs an emitting factory. The factory signature `(run_id, engine, event_emitter=None, **kw)` matches the pattern established in test_runs.py since task 26.
**Alternatives:** Mock UIBridge (doesn't test the actual WS fan-out path -- defeats the purpose of GAP 1)

### GAP 2 Exclusion
**Choice:** Do not write create_app() factory integration tests.
**Rationale:** CEO decision. 52 existing tests (TestTriggerRun + test_ui.py) already exercise create_app(). StaticPool threading concern makes seeded-data + create_app() tests unreliable without source changes.
**Alternatives:** none

### GAP 4 Exclusion
**Choice:** Do not add a separate GAP 4 test class.
**Rationale:** GAP 4 (UIBridge WS wiring verification) is fully subsumed by GAP 1. The E2E test in TestE2ETriggerWebSocket directly verifies UIBridge.emit() reaches WS clients.
**Alternatives:** none

## Implementation Steps

### Step 1: Write tests/ui/test_integration.py
**Agent:** backend-development:python-development
**Skills:** none
**Context7 Docs:** /websites/fastapi_tiangolo, /pytest-dev/pytest
**Group:** A

1. Add module-level imports: `pytest`, `time`, `threading`, `starlette.testclient.TestClient`, `sqlmodel.Session`, `llm_pipeline.ui.routes.websocket.manager`, `llm_pipeline.events.types.{PipelineStarted, PipelineCompleted, PipelineError}`, `llm_pipeline.state.PipelineRun`, conftest `_make_app` (imported directly, not as fixture).

2. Add module-level constants matching conftest seed data:
   ```
   RUN_COMPLETED = "aaaaaaaa-0000-0000-0000-000000000001"
   RUN_FAILED    = "aaaaaaaa-0000-0000-0000-000000000002"
   RUN_RUNNING   = "aaaaaaaa-0000-0000-0000-000000000003"
   ```

3. Add `autouse` fixture `_clean_manager` (same pattern as test_websocket.py) to reset the ConnectionManager singleton between tests.

4. Add `_wait_for_connection(run_id, count, timeout)` helper (same pattern as test_websocket.py).

5. Add `_make_emitting_pipeline_factory()` helper that returns a factory callable.
   - Factory signature: `(run_id, engine, event_emitter=None, **kw) -> fake_pipeline`
   - Fake pipeline `.execute()`: emits `PipelineStarted` then `PipelineCompleted(execution_time_ms=10.0, steps_executed=0)` via `event_emitter` if provided; inserts a `PipelineRun(run_id=run_id, pipeline_name=..., status="running", started_at=utc_now())` row into engine before emitting.
   - Fake pipeline `.save()`: updates the `PipelineRun.status = "completed"` and sets `completed_at`.
   - Note: `PipelineCompleted` auto-triggers `UIBridge.complete()` via `emit()`, which sends the None sentinel; `trigger_run` `finally` block calls `bridge.complete()` again (idempotent).

6. Add `_make_failing_pipeline_factory()` helper.
   - Factory signature: `(run_id, engine, event_emitter=None, **kw) -> fake_pipeline`
   - Fake pipeline `.execute()`: inserts `PipelineRun` with status="running", then raises `RuntimeError("forced failure")`.
   - `.save()`: not called (exception in execute stops execution).
   - The `trigger_run` except block in runs.py:216-231 catches this and sets `status="failed"` + `completed_at` in DB.

7. Write `class TestE2ETriggerWebSocket` (covers GAP 1 + GAP 4):
   - `test_trigger_then_ws_receives_events`: POST /api/runs with `emitting_pipeline` in registry, connect WS before execute completes (use `_wait_for_connection` pattern with threading), collect messages until `stream_complete`, assert `pipeline_started` and `pipeline_completed` event_types appear.
   - `test_trigger_ws_stream_complete_sent_on_finish`: same flow, assert final message is `{"type": "stream_complete", "run_id": <id>}`.
   - Implementation note: TestClient is synchronous. The trigger POST returns 202 (background task enqueued). The WS must be connected concurrently with the background task running. Pattern: open WS in a thread OR connect WS immediately after POST and use `_wait_for_connection` before pipeline executes. Use `app_client` fixture with the emitting factory registered on `app.state.pipeline_registry`.

8. Write `class TestTriggerRunErrorHandling` (covers GAP 3):
   - Fixture: create app via `_make_app()`, register `_make_failing_pipeline_factory()` in `app.state.pipeline_registry`, wrap with `TestClient`.
   - `test_trigger_failing_pipeline_sets_status_failed`: POST /api/runs, sleep briefly to let background task complete, GET /api/runs/{run_id}, assert `status == "failed"`.
   - `test_trigger_failing_pipeline_sets_completed_at`: same setup, assert `completed_at` is not None.
   - Use `time.sleep(0.1)` after POST to allow background task completion (same approach as existing test_runs.py TestTriggerRun).

9. Write `class TestCombinedFilters` (covers GAP 6):
   - Use `seeded_app_client` fixture (imported from conftest, available via pytest fixture injection).
   - `test_runs_filter_pipeline_name_and_status`: GET /api/runs with `pipeline_name=alpha_pipeline&status=completed`, assert total==1, result is RUN_1.
   - `test_runs_filter_pipeline_name_and_status_no_match`: GET /api/runs with `pipeline_name=beta_pipeline&status=completed`, assert total==0.
   - `test_runs_filter_pipeline_name_and_started_after`: combine pipeline_name + started_after to isolate RUN_3 (running, started ~100s ago).
   - `test_events_filter_event_type_with_pagination`: GET /api/runs/{RUN_1}/events with `event_type=step_started&limit=1&offset=0`, assert exactly 1 item, event_type matches.

10. Write `class TestCORSHeaders` (covers GAP 7):
    - Use `app_client` fixture.
    - `test_cors_allows_any_origin`: GET /api/runs with `Origin: http://localhost:5173` header, assert response has `Access-Control-Allow-Origin: *`.
    - `test_cors_preflight_options_request`: OPTIONS /api/runs with `Origin`, `Access-Control-Request-Method: GET`, assert 200 (or 204), assert `Access-Control-Allow-Origin` present in response.

11. Write `class TestWebSocketDisconnect` (covers GAP 5):
    - Use `seeded_app_client` fixture.
    - `test_disconnect_mid_stream_cleans_up`: connect to `RUN_RUNNING` (live stream path), `_wait_for_connection` confirms registration, assert `manager._queues[RUN_RUNNING]` has 1 entry, exit the `websocket_connect` context manager early (triggers disconnect), assert `RUN_RUNNING` no longer in `manager._queues` (cleanup ran).

12. Verify no accidental dependency on Task 56 scope: no performance/load tests, no concurrent connection stress.

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Background task timing in E2E test: WS must connect before pipeline emits events | High | Use `_wait_for_connection` to spin until WS is registered; run WS collection in a separate thread while POST triggers the background task. Alternatively: `TestClient(raise_server_exceptions=True)` with thread-based WS open before POST returns, joining after. |
| `PipelineCompleted` auto-calls `bridge.complete()` via `emit()` then `finally` calls it again | Low | UIBridge.complete() is idempotent (guarded by `_completed` flag). No action needed. |
| ConnectionManager singleton state leaks between tests | Medium | `_clean_manager` autouse fixture (identical to test_websocket.py) clears `_connections` and `_queues` before and after each test. |
| Task 54 spec code patterns are stale (wrong API params, wrong TestClient import) | Medium | VALIDATED_RESEARCH.md documents all discrepancies. Implementation uses `starlette.testclient.TestClient`, `offset`/`limit` params, `items` response key, `**kw` in factories. |
| Pre-existing test failure in test_ui.py::TestRoutersIncluded::test_events_router_prefix | Low | Out of scope. Do not touch. New tests in test_integration.py are independent. |

## Success Criteria

- [ ] `tests/ui/test_integration.py` created with 5 test classes: TestE2ETriggerWebSocket, TestTriggerRunErrorHandling, TestCombinedFilters, TestCORSHeaders, TestWebSocketDisconnect
- [ ] All new tests pass with `pytest tests/ui/test_integration.py`
- [ ] Full suite passes with `pytest` (excluding pre-existing failure in test_ui.py::TestRoutersIncluded::test_events_router_prefix which is out of scope)
- [ ] GAP 1 covered: E2E POST /api/runs -> WS receives pipeline_started and pipeline_completed events -> stream_complete
- [ ] GAP 3 covered: trigger failing pipeline -> DB status="failed" + completed_at set
- [ ] GAP 5 covered: WS disconnect mid-stream -> ConnectionManager cleaned up
- [ ] GAP 6 covered: combined pipeline_name + status filters return correct results
- [ ] GAP 7 covered: actual CORS response headers present in HTTP responses
- [ ] No new test dependencies added (all imports already in dev deps)
- [ ] No changes to any source file under llm_pipeline/

## Phase Recommendation

**Risk Level:** medium
**Reasoning:** The E2E trigger+WS test (GAP 1) requires coordinating a background task with a concurrent WS connection -- timing-sensitive. The approach (thread-based WS open + _wait_for_connection spin) is established in the codebase but the E2E combination is novel. Other test classes are straightforward. The pre-existing test failure is unrelated but adds test suite noise.
**Suggested Exclusions:** review
