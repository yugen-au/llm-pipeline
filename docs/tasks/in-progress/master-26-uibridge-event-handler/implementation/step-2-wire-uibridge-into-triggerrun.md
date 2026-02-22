# IMPLEMENTATION - STEP 2: WIRE UIBRIDGE INTO TRIGGER_RUN
**Status:** completed

## Summary
Wired UIBridge into `trigger_run()` in runs.py so pipeline execution emits events to WebSocket clients. Constructed UIBridge per run, passed as `event_emitter` kwarg to factory, added `finally` block calling `bridge.complete()` as idempotent safety net.

## Files
**Created:** none
**Modified:** `llm_pipeline/ui/routes/runs.py`, `tests/ui/test_runs.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/runs.py`
Added `UIBridge` import. Updated `trigger_run` docstring to document extended factory signature with `event_emitter` kwarg. In `run_pipeline()` closure: construct `bridge = UIBridge(run_id=run_id)` before try block, pass `event_emitter=bridge` to factory call, added `finally` block calling `bridge.complete()`.

```
# Before
from llm_pipeline.state import PipelineRun, PipelineStepState
from llm_pipeline.ui.deps import DBSession
...
    """Trigger a pipeline run in the background.

    The pipeline_registry on app.state maps pipeline names to factory
    callables with signature ``(run_id: str, engine: Engine) -> pipeline``
    where the returned object exposes ``.execute()`` and ``.save()``.
    """
...
    def run_pipeline() -> None:
        try:
            pipeline = factory(run_id=run_id, engine=engine)
            ...
        except Exception:
            ...

# After
from llm_pipeline.state import PipelineRun, PipelineStepState
from llm_pipeline.ui.bridge import UIBridge
from llm_pipeline.ui.deps import DBSession
...
    """Trigger a pipeline run in the background.

    The pipeline_registry on app.state maps pipeline names to factory
    callables with signature
    ``(run_id: str, engine: Engine, event_emitter: PipelineEventEmitter | None = None) -> pipeline``
    where the returned object exposes ``.execute()`` and ``.save()``.

    A :class:`~llm_pipeline.ui.bridge.UIBridge` is constructed per run and
    passed as ``event_emitter`` so pipeline events are forwarded to
    WebSocket clients in real time.
    """
...
    def run_pipeline() -> None:
        bridge = UIBridge(run_id=run_id)
        try:
            pipeline = factory(run_id=run_id, engine=engine, event_emitter=bridge)
            ...
        except Exception:
            ...
        finally:
            bridge.complete()
```

### File: `tests/ui/test_runs.py`
Updated three test factory lambdas from `lambda run_id, engine:` to `lambda run_id, engine, **kw:` to accept the new `event_emitter` kwarg passed by the updated `trigger_run`.

```
# Before
lambda run_id, engine: _FakePipeline(run_id, engine)
lambda run_id, engine: type("P", ...)()
lambda run_id, engine: _TrackedPipeline(run_id, engine)

# After
lambda run_id, engine, **kw: _FakePipeline(run_id, engine)
lambda run_id, engine, **kw: type("P", ...)()
lambda run_id, engine, **kw: _TrackedPipeline(run_id, engine)
```

## Decisions
### Removed unused CompositeEmitter import
**Choice:** Did not import `CompositeEmitter` despite plan listing it
**Rationale:** Plan step 2 lists the import but never uses it in the wiring logic. UIBridge is passed directly as `event_emitter` to factory. Leaving an unused import would trigger ruff F401. CompositeEmitter remains available for future composition if needed.

### Test factory kwargs update
**Choice:** Added `**kw` to test factory lambdas
**Rationale:** `trigger_run` now passes `event_emitter=bridge` to factory. Test factories with fixed `(run_id, engine)` signature would raise TypeError. Using `**kw` keeps tests forward-compatible with any future kwarg additions.

## Verification
[x] `trigger_run()` constructs UIBridge and passes as event_emitter to factory
[x] `trigger_run()` calls bridge.complete() in finally block
[x] Factory protocol docstring updated to show event_emitter kwarg
[x] All existing tests pass (683 passed, 1 pre-existing failure excluded)
[x] No unused imports (CompositeEmitter intentionally omitted)
