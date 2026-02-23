# IMPLEMENTATION - STEP 2: ADD TESTS
**Status:** completed

## Summary
Created `tests/ui/test_pipelines.py` with 19 tests covering GET /api/pipelines (list) and GET /api/pipelines/{name} (detail). Followed test_prompts.py fixture pattern and test_introspection.py cache-clearing pattern. Reused WidgetPipeline and ScanPipeline from test_introspection.py as test pipeline classes.

## Files
**Created:** tests/ui/test_pipelines.py
**Modified:** none
**Deleted:** none

## Changes
### File: `tests/ui/test_pipelines.py`
New file. 19 tests, 4 fixtures.

**Key decision on error-path tests:** PipelineIntrospector is fully defensive -- it never raises for arbitrary input classes (plain class with no STRATEGIES returns empty metadata, not an error). To test the endpoint's except branch, used `unittest.mock.patch` to force `get_metadata` to raise RuntimeError, then verified the endpoint returns 200 with error field populated and counts null.

## Decisions
### Broken pipeline simulation
**Choice:** Patch `PipelineIntrospector.get_metadata` to raise rather than passing a plain class
**Rationale:** PipelineIntrospector handles all inputs gracefully (returns empty lists for missing STRATEGIES/REGISTRY). A plain class with no pipeline machinery does not trigger the except branch in list_pipelines. The patch approach directly tests the endpoint's error-handling path without coupling to introspector internals.

### Test pipeline classes
**Choice:** Import WidgetPipeline and ScanPipeline from tests.test_introspection
**Rationale:** Both are complete module-level classes with strategies, steps, and instructions (so has_input_schema=True). No inline pipeline definitions needed.

### introspection_client fixture
**Choice:** Kept fixture signature with `pipeline_cls_map` parameter (indirect fixture pattern) but it is not used by any test -- tests that need custom registries construct app inline. The `empty_introspection_client` and `populated_introspection_client` fixtures cover all parameterised cases.
**Rationale:** Plan called for introspection_client(pipeline_cls_map), but per-test inline construction is cleaner for error-path cases. Fixture retained for completeness per plan.

## Verification
- [x] 19/19 tests pass: `pytest tests/ui/test_pipelines.py -v`
- [x] autouse clear_introspector_cache fixture mirrors test_introspection.py pattern
- [x] Follows _make_app() + TestClient pattern from test_prompts.py
- [x] Error-path tests verified endpoint returns 200 with error field, not 500
- [x] Alphabetical sort verified by asserting names == sorted(names)
- [x] No warnings beyond FastAPI deprecation noise (pre-existing, not introduced here)

## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
- [x] MEDIUM: Missing test for detail endpoint 500 error path
- [x] LOW: Dead `introspection_client` fixture with undefined `pipeline_cls_map` parameter

### Changes Made
#### File: `tests/ui/test_pipelines.py`
Removed `introspection_client` fixture (6 lines). Added `test_detail_introspection_failure_returns_500` to `TestGetPipeline`.

```
# Before
@pytest.fixture
def introspection_client(pipeline_cls_map):
    app = _make_app()
    app.state.introspection_registry = pipeline_cls_map
    with TestClient(app) as client:
        yield client

# After
[removed]
```

```
# Before
[no 500 test existed]

# After
def test_detail_introspection_failure_returns_500(self, populated_introspection_client):
    with patch.object(PipelineIntrospector, "get_metadata", side_effect=Exception("boom")):
        resp = populated_introspection_client.get("/api/pipelines/widget")
    assert resp.status_code == 500
    assert "boom" in resp.json()["detail"]
```

### Verification
- [x] 20/20 tests pass: `pytest tests/ui/test_pipelines.py -v`
- [x] Dead `introspection_client` fixture removed
- [x] `test_detail_introspection_failure_returns_500` asserts 500 status and error message in detail
