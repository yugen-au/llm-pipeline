# Research Summary

## Executive Summary

All 3 research agents independently identified the same critical deviation: task 26 spec prescribes `asyncio.Queue` + `asyncio.run_coroutine_threadsafe()`, but the actual task 25 implementation uses `threading.Queue` with sync `broadcast_to_run()`/`signal_run_complete()` via `put_nowait()`. The spec was written before task 25 shipped. Research consensus is unanimous: UIBridge should be a thin sync adapter delegating to ConnectionManager (Pattern 3). No asyncio machinery needed.

Validation confirmed this consensus against the actual codebase. Two gaps surfaced and resolved by CEO: (1) trigger_run wiring included in task 26 scope (not separate task); (2) factory protocol to be extended with `event_emitter` kwarg. Completion signaling uses auto-detect terminal events + explicit `complete()` fallback with idempotent guard (Option C).

## Domain Findings

### Spec vs Codebase Deviation
**Source:** step-1 (section "Task Spec Deviation Analysis"), step-2 (section 6), step-3 (section 5)

- Task 26 spec assumes `asyncio.Queue` internally in ConnectionManager. Task 25 shipped `import queue as thread_queue` / `thread_queue.Queue()`.
- Task 25 VALIDATED_RESEARCH and SUMMARY both reference "asyncio.Queue" in documentation, but shipped code uses `threading.Queue`. ConnectionManager docstring still says "Per-client asyncio.Queue fan-out" -- stale.
- Graphiti memory has stale fact: "ConnectionManager handles per-client asyncio.Queue fan-out" (uuid: d2762b82). Needs correction.
- Task 25 SUMMARY recommendation #1 mentions `asyncio.run_coroutine_threadsafe()` but the parenthetical "(both are safe since the methods are sync put_nowait calls)" actually argues against needing it.

### UIBridge Design (Consensus: Pattern 3 -- Sync Delegation)
**Source:** step-1 (Pattern 3), step-2 (section 6 "Correct Approach"), step-3 (section 5 "Implication")

```python
class UIBridge(PipelineEventEmitter):
    def __init__(self, run_id: str, manager: ConnectionManager | None = None):
        self.run_id = run_id
        self._manager = manager or _get_default_manager()
        self._completed = False

    def emit(self, event: PipelineEvent) -> None:
        self._manager.broadcast_to_run(self.run_id, event.to_dict())
        # Auto-detect terminal events
        if isinstance(event, (PipelineCompleted, PipelineError)):
            self.complete()

    def complete(self) -> None:
        if not self._completed:
            self._completed = True
            self._manager.signal_run_complete(self.run_id)
```

Why this works:
- `broadcast_to_run()` uses `put_nowait()` on `threading.Queue` -- thread-safe by stdlib guarantee
- Pipeline runs in BackgroundTasks threadpool worker -- sync calling sync, zero bridging needed
- `PipelineEvent.to_dict()` creates new dict from frozen dataclass -- no shared mutable state
- No event loop reference needed, eliminating "wrong event loop" bug class

### Completion Signaling
**Source:** step-2 (section 3)

Three options evaluated:
- **A**: Explicit `complete()` only -- risk of orphaned connections if caller forgets
- **B**: Auto-detect terminal events (`PipelineCompleted`/`PipelineError`) -- couples UIBridge to specific event types
- **C**: Both with idempotent guard -- auto-detect default + explicit fallback, `auto_complete` flag

**CEO decision: Option C.** Auto-detect `PipelineCompleted`/`PipelineError` in `emit()`, call `signal_run_complete` automatically with idempotent `_completed` guard. `complete()` remains as explicit fallback/safety net. Coupling to terminal event types is acceptable -- these are stable pipeline lifecycle events.

### Thread Safety
**Source:** step-1 (section "Thread Safety Analysis"), step-2 (section 7), step-3 (section 7)

Call path: `pipeline.execute()` [bg thread] -> `UIBridge.emit()` -> `manager.broadcast_to_run()` -> `queue.put_nowait()` [thread-safe].

Known race in ConnectionManager: `broadcast_to_run()` reads `_queues[run_id]` list while `disconnect()` may remove entries from event loop thread. Python GIL makes list iteration atomic at bytecode level. Accepted in task 25 (CEO decision).

No additional locking needed in UIBridge. `_completed` flag is boolean accessed from single pipeline thread (CompositeEmitter dispatches sequentially).

### Wiring Gap (trigger_run)
**Source:** step-2 (section 8.3), step-3 (section 7), codebase verification

Current `trigger_run()` (runs.py L204-226): `factory(run_id=run_id, engine=engine)` -- no event_emitter, no UIBridge, no signal_run_complete.

Factory protocol documented as `(run_id: str, engine: Engine) -> pipeline`. Does NOT accept `event_emitter` kwarg. Two options to wire:
1. Extend factory protocol to `(run_id, engine, event_emitter=None) -> pipeline`
2. Post-construction: `pipeline._event_emitter = emitter` (accesses private attr)

No task between 26 and 54 handles this wiring. Task 54 (integration tests) requires WebSocket streaming end-to-end, which requires UIBridge wired into trigger_run.

### Backpressure Assessment
**Source:** step-2 (section 5)

Not needed. <200 events/run, ~500 bytes each. 100 concurrent connections = ~10MB worst case. Unbounded `threading.Queue` is acceptable. Options documented for future scale (bounded queues, event batching, consumer timeout).

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| Sync delegation vs asyncio.Queue? | **Sync delegation confirmed.** UIBridge calls `manager.broadcast_to_run()` directly. No asyncio.Queue. | Eliminates asyncio machinery, event loop refs, entire class of threading bugs. Spec deviation documented. |
| Include trigger_run wiring in task 26? | **Yes, include in task 26.** Extend factory protocol with `event_emitter` kwarg. Wire UIBridge + CompositeEmitter in trigger_run. | UIBridge immediately usable. Task 54 can test e2e. Factory protocol extended. |
| Auto-complete on terminal events (Option C)? | **Option C confirmed.** Auto-detect PipelineCompleted/PipelineError with idempotent guard. complete() as explicit fallback. | UIBridge auto-signals run completion. Coupling to terminal event types accepted as stable. |

## Assumptions Validated

- [x] `ConnectionManager.broadcast_to_run()` is sync and thread-safe (verified: `put_nowait` on `threading.Queue`, L53-56 of websocket.py)
- [x] `ConnectionManager.signal_run_complete()` is sync and thread-safe (verified: `put_nowait(None)`, L58-61)
- [x] `PipelineEventEmitter` is runtime_checkable Protocol with sync `emit()` (verified: emitter.py L20-41)
- [x] `CompositeEmitter` provides per-handler error isolation (verified: emitter.py L58-67)
- [x] `PipelineConfig.__init__` accepts `event_emitter: Optional[PipelineEventEmitter]` (verified: pipeline.py L146)
- [x] `PipelineEvent` is frozen dataclass; `to_dict()` creates new dict (verified: types.py)
- [x] Pipeline executes synchronously in BackgroundTasks threadpool (verified: runs.py L204-226)
- [x] `PipelineCompleted` and `PipelineError` are terminal event types (verified: types.py L176, L186)
- [x] No event loop reference needed for ConnectionManager delegation (verified: all CM methods are sync)
- [x] Task 25 shipped `threading.Queue`, NOT `asyncio.Queue` (verified: websocket.py L3 `import queue as thread_queue`)
- [ ] Factory protocol supports `event_emitter` kwarg -- **INVALIDATED but RESOLVED**: current signature is `(run_id, engine)` only (runs.py L189-191). CEO approved extending to `(run_id, engine, event_emitter=None)` as part of task 26 scope.

## Open Items

- Graphiti stale fact (uuid: d2762b82): "ConnectionManager handles per-client asyncio.Queue fan-out" should be "threading.Queue" -- fix during implementation
- ConnectionManager docstring (websocket.py L20) says "Per-client asyncio.Queue fan-out" but uses `threading.Queue` -- fix during implementation
- Task 25 SUMMARY L5 says "per-client asyncio.Queue fan-out" -- stale, read-only historical artifact (no fix needed)
- `_event_emitter` is a private attribute on PipelineConfig -- factory protocol extension (CEO-approved) avoids needing public setter

## Recommendations for Planning

1. **Adopt sync delegation (Pattern 3)** -- UIBridge as thin adapter calling `manager.broadcast_to_run()` directly. No asyncio.Queue, no run_coroutine_threadsafe, no event loop reference. (CEO confirmed)
2. **Auto-detect terminal events (Option C)** -- `emit()` checks for `PipelineCompleted`/`PipelineError`, auto-calls `signal_run_complete` with idempotent `_completed` guard. `complete()` as explicit fallback. (CEO confirmed)
3. **Include trigger_run wiring in task 26** -- extend factory protocol to `(run_id, engine, event_emitter=None)`, wire UIBridge + CompositeEmitter in `trigger_run()`, call `bridge.complete()` in finally block. (CEO confirmed)
4. **Document spec deviation** explicitly in PLAN.md. The spec's asyncio approach is obsolete given task 25's threading.Queue implementation.
5. **DI for ConnectionManager** -- accept `manager` parameter with singleton default for testability: `def __init__(self, run_id, manager=None)` with fallback to module-level singleton.
6. **File placement**: `llm_pipeline/ui/bridge.py` per task spec -- separates bridge from route handlers.
7. **Fix stale docstrings** -- correct ConnectionManager docstring from "asyncio.Queue" to "threading.Queue" during implementation.
8. **Update Graphiti** -- correct stale facts about asyncio.Queue fan-out during implementation.
