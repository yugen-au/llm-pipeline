# IMPLEMENTATION - STEP 2: APP WIRING
**Status:** completed

## Summary
Registered creator router in both `create_app()` and test conftest `_make_app()` so all creator endpoints are accessible at `/api/creator/*`.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/app.py, tests/ui/conftest.py
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/app.py`
Added creator router import and include_router call after pipelines_router, matching existing pattern.
```
# Before
from llm_pipeline.ui.routes.websocket import router as ws_router

app.include_router(pipelines_router, prefix="/api")
app.include_router(ws_router)

# After
from llm_pipeline.ui.routes.websocket import router as ws_router
from llm_pipeline.ui.routes.creator import router as creator_router

app.include_router(pipelines_router, prefix="/api")
app.include_router(creator_router, prefix="/api")
app.include_router(ws_router)
```

### File: `tests/ui/conftest.py`
Same pattern in `_make_app()` -- import + include_router after pipelines_router.
```
# Before
from llm_pipeline.ui.routes.websocket import router as ws_router

app.include_router(pipelines_router, prefix="/api")
app.include_router(ws_router)

# After
from llm_pipeline.ui.routes.websocket import router as ws_router
from llm_pipeline.ui.routes.creator import router as creator_router

app.include_router(pipelines_router, prefix="/api")
app.include_router(creator_router, prefix="/api")
app.include_router(ws_router)
```

## Decisions
None

## Verification
[x] app.py import added in Route modules section
[x] app.py include_router placed after pipelines_router, before ws_router
[x] conftest.py import added inside _make_app() local imports
[x] conftest.py include_router placed after pipelines_router, before ws_router
[x] All 146 existing UI tests pass (1 pre-existing failure in test_cli.py unrelated)
