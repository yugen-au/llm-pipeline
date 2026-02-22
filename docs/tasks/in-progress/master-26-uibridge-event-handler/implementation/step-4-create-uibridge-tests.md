# IMPLEMENTATION - STEP 4: CREATE UIBRIDGE TESTS
**Status:** completed (review fix applied)

## Summary
Created `tests/ui/test_bridge.py` with 26 unit tests for UIBridge using a `_StubManager` stub. All 5 test classes implemented per PLAN.md spec. All 26 tests pass; pre-existing failure in `test_ui.py::TestRoutersIncluded::test_events_router_prefix` is unrelated.

## Files
**Created:** `tests/ui/test_bridge.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `tests/ui/test_bridge.py`
New file. 26 tests across 5 classes:

- `_StubManager` - stub tracking broadcast_calls and signal_calls lists
- `TestUIBridgeEmit` (8 tests) - emit() delegates to broadcast_to_run with correct run_id/dict; non-terminal no signal; PipelineCompleted/PipelineError auto-signal; ordering; content
- `TestUIBridgeComplete` (7 tests) - explicit complete(); idempotent (10 calls = 1 signal); after terminal event = no-op; _completed flag; correct run_id
- `TestUIBridgeDI` (5 tests) - custom manager stored; no-arg uses module singleton via `is` identity; run_id stored; _completed=False initially
- `TestUIBridgeRepr` (3 tests) - repr includes run_id; exact format `UIBridge(run_id='...')`
- `TestUIBridgeProtocol` (3 tests) - isinstance(bridge, PipelineEventEmitter) is True; various run_ids; no-manager arg

## Decisions
### Stub over Mock
**Choice:** Hand-written `_StubManager` stub with list-append tracking instead of `unittest.mock.Mock`
**Rationale:** Lists give ordered call history for broadcast_calls (run_id + data) and signal_calls (run_id). More readable assertions than mock.call_args_list. Consistent with spec ("stub ConnectionManager").

### Singleton DI test uses `is` identity
**Choice:** `assert bridge._manager is _singleton` (identity check, not equality)
**Rationale:** Tests that UIBridge actually stores the singleton object, not just an equal-looking one. Matches PLAN.md step 4 spec ("import and check `is` identity").

## Verification
- [x] 26 tests collected and passed (`pytest tests/ui/test_bridge.py -v`)
- [x] Full suite: 709 passed, 1 pre-existing failure (unrelated router prefix test)
- [x] TestUIBridgeEmit covers all 4 spec cases + extras
- [x] TestUIBridgeComplete covers idempotent guard in all scenarios
- [x] TestUIBridgeDI verifies singleton `is` identity and custom injection
- [x] TestUIBridgeRepr checks repr format exactly
- [x] TestUIBridgeProtocol verifies runtime_checkable isinstance

## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
- [x] Missing test for emit() when broadcast_to_run raises (LOW) -- no test verified UIBridge behavior when broadcast_to_run() raises during a terminal event

### Changes Made
#### File: `tests/ui/test_bridge.py`
Added `test_emit_broadcast_raises_on_terminal_event_propagates_and_no_signal` to `TestUIBridgeEmit`. Uses a local `_RaisingManager` whose `broadcast_to_run` always raises `RuntimeError`. Asserts: exception propagates to caller, `_completed` remains `False`, `signal_run_complete` not called.

```python
# Before (no such test)

# After
def test_emit_broadcast_raises_on_terminal_event_propagates_and_no_signal(self):
    class _RaisingManager:
        def __init__(self) -> None:
            self.signal_calls: list[str] = []
        def broadcast_to_run(self, run_id: str, event_data: dict) -> None:
            raise RuntimeError("queue full")
        def signal_run_complete(self, run_id: str) -> None:
            self.signal_calls.append(run_id)

    raising_manager = _RaisingManager()
    bridge = UIBridge(run_id=RUN_ID, manager=raising_manager)

    with pytest.raises(RuntimeError, match="queue full"):
        bridge.emit(_make_completed())

    assert bridge._completed is False
    assert raising_manager.signal_calls == []
```

### Verification
- [x] 27 tests collected and passed (`pytest tests/ui/test_bridge.py -v`)
- [x] `_completed` is False after broadcast raises -- complete() was never reached
- [x] `signal_run_complete` not called -- no orphaned completion sentinel sent
- [x] Exception propagates -- caller (trigger_run finally block) is the safety net
