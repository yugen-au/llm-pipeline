# IMPLEMENTATION - STEP 3: WIRE RUN_CREATED BROADCAST
**Status:** completed

## Summary
Wired `broadcast_global` call into `trigger_run()` so global WebSocket subscribers receive `run_created` notification when a new pipeline run starts. Broadcast happens synchronously in the request handler before the background task begins.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/routes/runs.py
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/runs.py`
Added import of `manager` singleton and `broadcast_global` call in `trigger_run()`.

```
# Before
from llm_pipeline.ui.bridge import UIBridge
from llm_pipeline.ui.deps import DBSession

# After
from llm_pipeline.ui.bridge import UIBridge
from llm_pipeline.ui.deps import DBSession
from llm_pipeline.ui.routes.websocket import manager as ws_manager
```

```
# Before
    run_id = str(uuid.uuid4())
    engine = request.app.state.engine

    def run_pipeline() -> None:

# After
    run_id = str(uuid.uuid4())
    engine = request.app.state.engine

    # Notify global WS subscribers before background task starts
    ws_manager.broadcast_global({
        "type": "run_created",
        "run_id": run_id,
        "pipeline_name": body.pipeline_name,
        "started_at": datetime.now(timezone.utc).isoformat(),
    })

    def run_pipeline() -> None:
```

## Decisions
None

## Verification
[x] No circular import: `python -c "from llm_pipeline.ui.routes.runs import trigger_run"` succeeds
[x] Broadcast placed after run_id generation, before background_tasks.add_task()
[x] datetime and timezone already imported in runs.py (line 4)
[x] websocket.py does not import from runs.py -- no cycle risk
