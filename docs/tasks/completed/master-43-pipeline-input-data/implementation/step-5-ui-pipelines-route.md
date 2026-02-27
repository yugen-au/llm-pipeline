# IMPLEMENTATION - STEP 5: UI PIPELINES ROUTE
**Status:** completed

## Summary
Updated has_input_schema logic in list_pipelines() to use pipeline-level INPUT_DATA via metadata.pipeline_input_schema instead of iterating step-level instruction schemas.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/routes/pipelines.py
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/pipelines.py`
Replaced step-level instruction schema iteration with direct pipeline_input_schema metadata check at L98.

```
# Before
has_input_schema = any(
    step.get("instructions_schema") is not None
    for strategy in strategies
    for step in strategy.get("steps", [])
)

# After
has_input_schema = metadata.get("pipeline_input_schema") is not None
```

## Decisions
None

## Verification
[x] has_input_schema now checks metadata.pipeline_input_schema (set by Step 4 introspection)
[x] No other references to step-level instructions_schema in this route for has_input_schema
[x] PipelineMetadata response model already has pipeline_input_schema field (L62)

## Fix Iteration 0
**Issues Source:** TESTING.md
**Status:** fixed

### Issues Addressed
[x] test_list_has_input_schema_true_for_pipeline_with_instructions fails - asserts True but Step 5 changed logic to pipeline-level INPUT_DATA check

### Changes Made
#### File: `tests/ui/test_pipelines.py`
Replaced single test with two tests: one verifying has_input_schema=False for pipelines without INPUT_DATA, one verifying has_input_schema=True when pipeline_input_schema present in metadata.

```
# Before
def test_list_has_input_schema_true_for_pipeline_with_instructions(self, populated_introspection_client):
    """WidgetPipeline and ScanPipeline both have instructions classes, so has_input_schema=True."""
    resp = populated_introspection_client.get("/api/pipelines")
    body = resp.json()
    for item in body["pipelines"]:
        assert item["has_input_schema"] is True

# After
def test_list_has_input_schema_false_without_input_data(self, populated_introspection_client):
    """WidgetPipeline/ScanPipeline have step instructions but no INPUT_DATA ClassVar, so has_input_schema=False."""
    resp = populated_introspection_client.get("/api/pipelines")
    body = resp.json()
    for item in body["pipelines"]:
        assert item["has_input_schema"] is False

def test_list_has_input_schema_true_with_pipeline_input_schema(self):
    """has_input_schema=True when introspection metadata includes pipeline_input_schema."""
    app = _make_app()
    app.state.introspection_registry = {"widget": WidgetPipeline}
    fake_schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
    orig_get_metadata = PipelineIntrospector.get_metadata
    def _with_input_schema(self):
        meta = orig_get_metadata(self)
        meta["pipeline_input_schema"] = fake_schema
        return meta
    with patch.object(PipelineIntrospector, "get_metadata", _with_input_schema):
        with TestClient(app) as client:
            resp = client.get("/api/pipelines")
    body = resp.json()
    assert len(body["pipelines"]) == 1
    assert body["pipelines"][0]["has_input_schema"] is True
```

### Verification
[x] test_list_has_input_schema_false_without_input_data passes
[x] test_list_has_input_schema_true_with_pipeline_input_schema passes
[x] Full test_pipelines.py suite: 21/21 passed, 0 failures
