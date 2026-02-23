# Research Summary

## Executive Summary

Validated Step 1 (API architecture) and Step 2 (testing patterns) against codebase. Core tension resolved: both are partially correct. Step 2's "comprehensive coverage" is accurate for endpoint-level testing (all 7 REST + 1 WS endpoint have happy/error path tests). Step 1's 7 gaps are about cross-component integration flows, not endpoint coverage. After codebase validation, 5 of 7 gaps are genuine, 1 is overstated, 1 is subsumed. Both documents have significant test count inaccuracies (actual total: 180, Step 1 claims ~128). Task 54 spec details contain stale/incorrect code patterns.

Two architectural questions resolved by CEO -- all decisions locked in, ready for planning.

## Domain Findings

### Test Count Discrepancies
**Source:** step-1, step-2, pytest --collect-only

Neither document accurately counts existing tests. Validated counts:

| File | Step 1 | Step 2 | Actual |
|------|--------|--------|--------|
| test_runs.py | 19 | 21 | **23** |
| test_steps.py | 10 | 14 | **14** |
| test_events.py | 12 | 12 | **13** |
| test_websocket.py | 6 | 6 | **6** |
| test_bridge.py | 27 | ~20 | **27** |
| test_cli.py | 27 | ~20 | **46** |
| test_wal.py | 4 | 4 | **4** |
| test_ui.py | 23 | ~30 | **47** |
| **Total** | **~128** | **n/a** | **180** |

Impact: doesn't change gap analysis but Step 1's "~128" substantially undercounts (actual 40% higher). Scoping decisions based on that number would be off.

### Coverage Gap Validation
**Source:** step-1 section 6, step-2 section 6, codebase verification

| Gap | Step 1 Claim | Validated | Priority |
|-----|-------------|-----------|----------|
| GAP 1: E2E trigger+WS | CRITICAL, no test | **Confirmed genuine** - no test exercises POST /api/runs -> WS receives events -> DB state verified. Task 26 SUMMARY.md recommendation #2 explicitly calls for this. | CRITICAL |
| GAP 2: create_app() factory | MEDIUM, not tested | **Overstated** - TestTriggerRun (5 tests) already uses create_app(). test_ui.py (47 tests) validates config. Narrow gap: no create_app() + seeded-data + endpoint query test. Blocked by StaticPool issue (see below). | LOW |
| GAP 3: Trigger error DB update | MEDIUM, untested | **Confirmed genuine** - runs.py:216-231 except block sets status="failed" and completed_at. No test verifies this DB write. | MEDIUM |
| GAP 4: UIBridge WS wiring | MEDIUM | **Subsumed by GAP 1** - Step 1 acknowledges this. | n/a |
| GAP 5: WS disconnect mid-stream | LOW | **Confirmed genuine** - websocket.py:141 `except WebSocketDisconnect: pass` + finally cleanup untested in integration. | LOW |
| GAP 6: Combined filters | LOW | **Confirmed genuine** - no test combines pipeline_name+status on /api/runs. | LOW |
| GAP 7: CORS response headers | LOW | **Confirmed genuine** - test_ui.py checks middleware kwargs only, not actual HTTP response headers. | LOW |

### Hidden Assumption: StaticPool Threading Issue
**Source:** step-2 section 3, app.py source code

Step 2 correctly notes `_make_app()` uses StaticPool for thread-safe shared in-memory DB. But both documents understate a critical implication:

`create_app(db_path=":memory:")` at app.py:59 uses `create_engine(f"sqlite:///{db_path}")` **without** StaticPool. This means each threadpool worker gets a separate empty in-memory database. Existing TestTriggerRun tests work only because they check the HTTP response (status 202, run_id format) and don't query seeded data cross-thread.

**Impact on Task 54:** New integration tests that need seeded data + create_app() (e.g., GAP 1 E2E test) cannot use `create_app(":memory:")` directly. They must either:
- (a) Continue using `_make_app()` pattern from conftest.py (proven, safe)
- (b) Extend `create_app()` to accept a pre-built engine parameter
- (c) Use file-based SQLite in tmp_path

### Task 54 Spec Staleness
**Source:** taskmaster task 54 details

The code in Task 54's details field has multiple inaccuracies vs actual codebase:
- Uses `from fastapi.testclient import TestClient` -- codebase uses `from starlette.testclient import TestClient`
- Uses `?page=1&page_size=10` -- actual API uses `?offset=0&limit=50`
- Uses `response.json()['runs']` -- actual response key is `items`
- Missing `**kw` in factory lambdas (required since task 26)

These are rough sketches, not copy-pasteable code. Planning phase must use actual API signatures from Step 1.

### Context Evolution Test Location
**Source:** step-1, step-2, codebase

Minor inconsistency: context evolution endpoint lives in `runs.py` (router prefix `/runs`) but tests are in `test_steps.py::TestContextEvolution`. Both research docs reference this without flagging the mismatch. Not blocking, but worth noting for organizational consistency in new tests.

### Pre-existing Test Failure (Out of Scope)
**Source:** step-1 section 9, pytest verification

`tests/test_ui.py::TestRoutersIncluded::test_events_router_prefix` fails. Asserts prefix=="/events" but actual prefix is "/runs/{run_id}/events". Introduced by task 28, confirmed by running pytest. Step 1 correctly marks this OUT OF SCOPE. Task 26 SUMMARY.md also documents it with the originating commit.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Where should new integration tests go? `tests/test_ui_backend.py` (task 54 spec) or `tests/ui/test_integration.py` (step 1)? | **`tests/ui/test_integration.py`** -- follow existing tests/ui/ convention | Locks file location. New tests import from conftest.py fixtures already in tests/ui/. No new conftest needed. |
| Should new tests use `_make_app()` or extend `create_app()` to accept pre-built engine? | **Use `_make_app()` from conftest** -- proven pattern, no source changes | No modifications to app.py. GAP 2 (create_app factory integration) downgraded to NOT PLANNED -- existing 52 tests already cover create_app() config and trigger flow. StaticPool threading concern becomes moot since _make_app() already handles it. |

## Assumptions Validated
- [x] All 7 REST endpoints + 1 WS endpoint have individual test coverage (Step 2 claim confirmed)
- [x] 5 of 7 gaps from Step 1 are genuine coverage holes (cross-component, not endpoint-level)
- [x] GAP 2 (create_app factory) is overstated -- already partially tested
- [x] StaticPool is required for thread-safe in-memory SQLite testing (Step 2 section 3)
- [x] create_app(":memory:") does NOT use StaticPool (app.py:59, verified)
- [x] No async test framework needed -- TestClient handles async transparently (Step 2 section 5)
- [x] Pre-existing test failure is real and out of scope (task 28 origin, verified)
- [x] Task 26 SUMMARY.md explicitly recommends E2E integration test (recommendation #2)
- [x] UIBridge uses sync delegation (threading.Queue.put_nowait), not asyncio (bridge.py, verified)
- [x] Factory lambdas in test_runs.py already accept **kw since task 26

## Open Items
- Task 54 spec code samples are inaccurate -- planning must reference actual API signatures from Step 1

## Recommendations for Planning
1. **File:** `tests/ui/test_integration.py` (CEO decision, follows convention)
2. **Fixtures:** Use `_make_app()` from existing conftest.py (CEO decision, proven StaticPool pattern)
3. **Primary deliverable:** GAP 1 (E2E trigger+WS) -- only CRITICAL gap, explicitly called for by upstream task 26
4. **Secondary deliverable:** GAP 3 (trigger error DB update) -- MEDIUM priority, small scope, high value
5. **Defer:** GAPs 5-7 (LOW priority) unless time permits -- diminishing returns
6. **Drop:** GAP 2 (create_app factory) -- already covered by 52 existing tests, moot given _make_app() decision
7. **Do NOT** copy code from Task 54 spec details -- use Step 1's API surface area as reference
8. Follow existing conventions: class-based grouping, seeded fixtures, starlette TestClient, `**kw` in factory lambdas
