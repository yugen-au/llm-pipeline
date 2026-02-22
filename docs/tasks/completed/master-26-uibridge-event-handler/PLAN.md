# PLANNING

## Summary

Create `llm_pipeline/ui/bridge.py` with `UIBridge` - a thin sync adapter that implements `PipelineEventEmitter` and delegates to `ConnectionManager.broadcast_to_run()` (threading.Queue, not asyncio.Queue per task 25 deviation). Wire UIBridge into `trigger_run()` in `runs.py` by extending the factory protocol with an `event_emitter` kwarg and wrapping any existing emitter in `CompositeEmitter`. Fix stale ConnectionManager docstring. Add tests in `tests/ui/test_bridge.py`.

**Spec deviation (documented):** Task 26 spec prescribes `asyncio.Queue` + `asyncio.run_coroutine_threadsafe`. Task 25 shipped `threading.Queue` with sync `put_nowait` methods. UIBridge uses sync delegation; no asyncio machinery needed.

## Plugin & Agents
**Plugin:** python-development
**Subagents:** [available agents]
**Skills:** none

## Phases
1. **Implementation**: Create UIBridge class, wire into trigger_run, fix stale docstring
2. **Testing**: Unit tests for UIBridge and integration test for wired trigger_run

## Architecture Decisions

### Sync Delegation (not asyncio.Queue)
**Choice:** UIBridge.emit() calls manager.broadcast_to_run() directly (sync threading.Queue put_nowait)
**Rationale:** Task 25 shipped threading.Queue. Pipeline runs in BackgroundTasks threadpool worker - sync calling sync, no bridging needed. Verified: websocket.py L3 `import queue as thread_queue`, L53-56 broadcast_to_run uses put_nowait.
**Alternatives:** asyncio.run_coroutine_threadsafe per original spec - obsolete given task 25 implementation; introduces wrong-event-loop bug class.

### Completion Signaling (Option C - Auto-detect + Explicit Fallback)
**Choice:** emit() auto-detects PipelineCompleted/PipelineError and calls signal_run_complete with idempotent _completed guard. complete() method as explicit fallback.
**Rationale:** CEO-approved. Auto-detect prevents orphaned connections. Idempotent guard prevents double-signaling. Explicit complete() gives trigger_run finally block a safety net.
**Alternatives:** A (explicit only) - orphaned connections if caller forgets. B (auto-detect only) - no fallback for edge cases.

### Factory Protocol Extension
**Choice:** Extend factory signature to (run_id, engine, event_emitter=None) -> pipeline. Wire UIBridge + CompositeEmitter in trigger_run's run_pipeline closure.
**Rationale:** CEO-approved. Avoids accessing private _event_emitter attr on PipelineConfig. PipelineConfig.__init__ already accepts event_emitter kwarg (verified: pipeline.py L146).
**Alternatives:** Post-construction assignment via pipeline._event_emitter - accesses private attribute, fragile.

### ConnectionManager DI
**Choice:** UIBridge accepts optional manager param; defaults to module-level singleton from websocket.py.
**Rationale:** Testability - tests inject a mock/stub ConnectionManager. Production code uses the singleton without callers needing to pass it.
**Alternatives:** Import singleton directly (untestable without monkeypatching at module level).

## Implementation Steps

### Step 1: Create llm_pipeline/ui/bridge.py
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Create `llm_pipeline/ui/bridge.py` with `UIBridge` class implementing `PipelineEventEmitter` protocol
2. `__init__(self, run_id: str, manager: ConnectionManager | None = None)` - store run_id, store manager (or import singleton from `llm_pipeline.ui.routes.websocket`), init `_completed = False`
3. `emit(self, event: PipelineEvent) -> None` - call `self._manager.broadcast_to_run(self.run_id, event.to_dict())`, then if `isinstance(event, (PipelineCompleted, PipelineError))` call `self.complete()`
4. `complete(self) -> None` - idempotent guard: if not `_completed`, set `_completed = True`, call `self._manager.signal_run_complete(self.run_id)`
5. Add `__repr__` returning `f"UIBridge(run_id={self.run_id!r})"`
6. Add module docstring explaining sync delegation, spec deviation note, and threading model
7. Export `UIBridge` in `__all__`

### Step 2: Wire UIBridge into trigger_run() in runs.py
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. In `llm_pipeline/ui/routes/runs.py`, import `UIBridge` from `llm_pipeline.ui.bridge` and `CompositeEmitter` from `llm_pipeline.events`
2. Inside `run_pipeline()` closure in `trigger_run()`: before calling `factory(...)`, construct `bridge = UIBridge(run_id=run_id)`
3. Call `factory(run_id=run_id, engine=engine, event_emitter=bridge)` - passes UIBridge as event_emitter kwarg
4. Update factory docstring in `trigger_run` to document extended signature `(run_id: str, engine: Engine, event_emitter: PipelineEventEmitter | None = None) -> pipeline`
5. In the `finally` block (add if not present, wrapping the try/except) of `run_pipeline`, call `bridge.complete()` as safety net after pipeline finishes or fails - this is idempotent so safe to call even if auto-detected terminal event already signaled

### Step 3: Fix stale ConnectionManager docstring
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. In `llm_pipeline/ui/routes/websocket.py` L20, update `ConnectionManager` class docstring from "Per-client asyncio.Queue fan-out" to "Per-client threading.Queue fan-out" to reflect actual task 25 implementation

### Step 4: Create tests/ui/test_bridge.py
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. Create `tests/ui/test_bridge.py` with unit tests for UIBridge using a stub ConnectionManager (track calls to broadcast_to_run and signal_run_complete)
2. `TestUIBridgeEmit`: test emit() calls broadcast_to_run with run_id and event.to_dict(); test non-terminal event (e.g. PipelineStarted) does NOT call signal_run_complete; test PipelineCompleted auto-calls signal_run_complete; test PipelineError auto-calls signal_run_complete
3. `TestUIBridgeComplete`: test explicit complete() calls signal_run_complete; test complete() is idempotent (second call does nothing - signal_run_complete called only once); test complete() after terminal event is a no-op (idempotent guard)
4. `TestUIBridgeDI`: test that UIBridge with no manager arg uses the module-level singleton (import and check `is` identity); test custom manager injection works
5. `TestUIBridgeRepr`: test `repr(bridge)` includes run_id
6. `TestUIBridgeProtocol`: test `isinstance(UIBridge(...), PipelineEventEmitter)` is True (runtime_checkable Protocol check)

## Risks & Mitigations
| Risk | Impact | Mitigation |
| --- | --- | --- |
| Factory callers not accepting event_emitter kwarg | Medium | Use kwarg (not positional) - existing callers without the param ignore it; verify PipelineConfig.__init__ accepts it (confirmed: pipeline.py L146) |
| Stale Graphiti fact about asyncio.Queue | Low | Update during implementation per VALIDATED_RESEARCH open items (uuid: d2762b82) |
| complete() in finally block races with auto-detect | Low | Idempotent _completed guard ensures signal_run_complete called exactly once regardless of call order |
| Import cycle (bridge.py imports from routes/websocket.py for singleton) | Medium | Use lazy import inside UIBridge.__init__ to defer until runtime, breaking any potential circular import |

## Success Criteria
- [ ] `llm_pipeline/ui/bridge.py` exists with UIBridge class
- [ ] UIBridge.emit() calls manager.broadcast_to_run(run_id, event.to_dict())
- [ ] PipelineCompleted and PipelineError events auto-trigger signal_run_complete
- [ ] complete() is idempotent (signal_run_complete called at most once per UIBridge instance)
- [ ] trigger_run() in runs.py constructs UIBridge and passes as event_emitter to factory
- [ ] trigger_run() calls bridge.complete() in finally block
- [ ] Factory protocol docstring updated to show event_emitter kwarg
- [ ] ConnectionManager docstring corrected to "threading.Queue"
- [ ] isinstance(UIBridge(...), PipelineEventEmitter) is True
- [ ] All new tests pass (pytest tests/ui/test_bridge.py)
- [ ] All existing tests still pass (pytest)

## Phase Recommendation
**Risk Level:** low
**Reasoning:** All assumptions validated against actual codebase. No schema changes, no new dependencies, no async machinery. Pure sync code addition. Factory extension uses optional kwarg - backward-compatible. Main risk is import cycle for singleton, mitigated by lazy import.
**Suggested Exclusions:** testing, review
