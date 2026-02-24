# Architecture Review

## Overall Assessment
**Status:** complete

Implementation is solid and production-ready. All 8 steps follow existing codebase patterns closely. Backend global WS extension is minimal and correct. Frontend hooks/components are well-structured with proper lifecycle management, error handling, and responsive layout. Event cache seeding order is correct. No critical or high-severity issues found.

## Project Guidelines Compliance
**CLAUDE.md:** `C:\Users\SamSG\Documents\claude_projects\llm-pipeline\CLAUDE.md`
| Guideline | Status | Notes |
| --- | --- | --- |
| Python 3.11+ / Pydantic v2 | pass | No new Pydantic models added; existing patterns reused |
| SQLModel / SQLAlchemy 2.0 | pass | No new DB models; existing Session usage correct |
| Pipeline + Strategy + Step pattern | pass | No modifications to core pipeline architecture |
| LLMProvider abstraction | pass | Not touched by this task |
| Build with hatchling | pass | No build config changes |
| Error handling present | pass | All endpoints/hooks handle error states |
| No hardcoded values | pass | Constants extracted (HEARTBEAT_INTERVAL_S, MAX_RECONNECT_DELAY, etc.) |
| Tests pass | N/A | Testing phase excluded per plan |

## Issues Found

### Critical
None

### High
None

### Medium

#### Thread safety of _global_queues list iteration during concurrent mutation
**Step:** 1
**Details:** `broadcast_global` iterates `self._global_queues` while `connect_global`/`disconnect_global` can mutate it from different threads. In CPython, GIL protects individual bytecode ops (list.append, list.remove) but iterating while mutating can theoretically skip items or raise IndexError under concurrent access. However, this is **consistent with the existing pattern**: `broadcast_to_run` iterates `self._queues[run_id]` the same way. Not a regression. For the expected concurrency (few WS clients), CPython GIL provides sufficient protection. A `threading.Lock` or copying the list before iteration (`list(self._global_queues)`) would be the defensive fix if scaling to many concurrent subscribers.

### Low

#### StepDetailPanel receives runStatus={undefined}
**Step:** 8
**Details:** `live.tsx` L206 passes `runStatus={undefined}` to `StepDetailPanel`. This means `useStep` inside the panel won't apply `staleTime: Infinity` optimization for completed runs. Not a functional bug -- the click guard ensures only completed steps open the panel. The run status could be derived from WS events (stream_complete / replay_complete) but is not tracked in live.tsx state. Minor missed optimization.

#### Radix ScrollArea internal selector coupling
**Step:** 7
**Details:** `EventStream.tsx` L113 uses `node.querySelector('[data-slot="scroll-area-viewport"]')` to locate the ScrollArea viewport element. This couples to Radix/shadcn internal DOM structure. If Radix changes the `data-slot` attribute name in a future version, auto-scroll detection would silently break (no error, just no auto-scroll). Currently the documented approach for shadcn/Radix, so acceptable.

#### Silent no-op on running step click
**Step:** 8
**Details:** `handleSelectStep` (L100-107) silently returns when clicking a running step. No visual feedback (toast, tooltip, cursor change) is provided to the user. The PLAN.md mentioned showing a tooltip "Step in progress" but the implementation omits it. Functional but slightly degraded UX.

#### useEvents/useSteps called with undefined runStatus
**Step:** 8
**Details:** `useEvents(activeRunId ?? '', {}, undefined)` and `useSteps(activeRunId ?? '', undefined)` pass `undefined` for `runStatus`. This means polling is disabled (condition `runStatus && !isTerminalStatus(runStatus)` evaluates false), and staleTime defaults to 5_000ms. For live execution, WS events handle real-time updates so REST polling is less critical. Passing the actual run status would enable polling as a safety net, but since WS covers the primary update path, this is acceptable.

## Review Checklist
[x] Architecture patterns followed - extends existing ConnectionManager, follows hook patterns from useWebSocket
[x] Code quality and maintainability - clear separation of concerns, well-documented, consistent style
[x] Error handling present - all components handle loading/error/empty states; WS handles disconnect/error/reconnect
[x] No hardcoded values - all magic numbers extracted as named constants
[x] Project conventions followed - file structure, naming, import patterns match existing codebase
[x] Security considerations - no auth changes, no new API surface beyond WS endpoint, no user input injection vectors
[x] Properly scoped (DRY, YAGNI, no over-engineering) - reuses StepTimeline/StepDetailPanel/useWebSocket; no premature virtualization; placeholder for Task 38

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| `llm_pipeline/ui/routes/websocket.py` | pass | Global subscriber support added cleanly alongside existing per-run pattern. Route registration order correct (/ws/runs before /ws/runs/{run_id}). |
| `llm_pipeline/ui/routes/runs.py` | pass | broadcast_global call in trigger_run is correctly placed after run_id generation, before background task. No circular import (verified import chain). |
| `llm_pipeline/ui/frontend/src/api/types.ts` | pass | WsRunCreated interface correctly standalone (not in WsMessage union). Clean placement after existing WS types. |
| `llm_pipeline/ui/frontend/src/api/useRunNotifications.ts` | pass | Clean WS lifecycle. Exponential backoff matches useWebSocket pattern. mountedRef guards prevent post-unmount state updates. |
| `llm_pipeline/ui/frontend/src/components/live/PipelineSelector.tsx` | pass | Handles all states (loading/error/empty/data). Uses existing usePipelines hook. Correct shadcn Select usage. |
| `llm_pipeline/ui/frontend/src/components/live/EventStream.tsx` | pass | Auto-scroll with pause-on-scroll-up. Connection status indicator. Good event type badge mapping with dark mode support. |
| `llm_pipeline/ui/frontend/src/routes/live.tsx` | pass | 3-column responsive layout with tab fallback. Event cache seeding order correct. Python-initiated run auto-attach works via useRunNotifications. Task 38 placeholder present. |

## New Issues Introduced
- None detected. All changes are additive and do not modify existing tested components (StepTimeline, StepDetailPanel, useWebSocket, useCreateRun).

## Recommendation
**Decision:** APPROVE

Implementation is architecturally sound, follows all established patterns, and introduces no regressions. The medium-severity thread safety note is consistent with the pre-existing ConnectionManager design and does not represent a new risk. All four architecture decisions from PLAN.md are validated as correct. Low-severity items are polish improvements that can be addressed in follow-up work.

---

# Re-verification Review (Post-Fix)

## Overall Assessment
**Status:** complete

All 5 previously identified issues have been resolved. Fixes are minimal, correct, and introduce no new issues. The additional ES2020 compatibility fix (Array.findLast replacement) is also correct.

## Fix Verification

### Fix 1: Thread safety of list iteration (MEDIUM, Step 1) -- RESOLVED
**File:** `llm_pipeline/ui/routes/websocket.py` L56, L61, L81
**Verification:** All three iteration sites (`broadcast_to_run`, `signal_run_complete`, `broadcast_global`) now copy the list with `list(...)` before iterating. This creates a snapshot immune to concurrent append/remove on the original list. Standard Python pattern for thread-safe iteration.

### Fix 2: ScrollArea internal selector coupling (LOW, Step 7) -- RESOLVED
**File:** `llm_pipeline/ui/frontend/src/components/live/EventStream.tsx` L107, L114, L165
**Verification:** Replaced `querySelector('[data-slot="scroll-area-viewport"]')` callback ref with a simple `contentRef` on the inner div + `parentElement` traversal. No Radix-internal selectors remain. The content div is a direct child of ScrollArea viewport by Radix's DOM structure, so `parentElement` is reliable. Unused `useCallback` import also removed.

### Fix 3: runStatus undefined for StepDetailPanel (LOW, Step 8) -- RESOLVED
**File:** `llm_pipeline/ui/frontend/src/routes/live.tsx` L27-69, L97-102, L272
**Verification:** New `deriveRunStatus()` function correctly maps WsConnectionStatus + event stream to RunStatus. `useMemo` at L97 computes derived status with proper deps `[wsStoreStatus, activeRunId, queryClient]`. Passed to StepDetailPanel at L272 as `runStatus={runStatus}`. Cache-read-in-useMemo is correct: during active connection returns 'running' without reading events; on terminal transition re-reads final event list.

### Fix 4: Silent no-op on running step click (LOW, Step 8) -- RESOLVED
**File:** `llm_pipeline/ui/frontend/src/components/runs/StepTimeline.tsx` L183-184, L188
**Verification:** Running steps now show `cursor-not-allowed opacity-70` visual styling and `title="Step still in progress"` native tooltip. `console.info` in live.tsx L167 provides dev-level feedback. Note: implementation uses native tooltip instead of a toast component -- this is actually superior for repeated interactions (no toast stacking). The change in StepTimeline is shared across all usages (run detail page too), which is beneficial since the same click guard issue exists there.

### Fix 5: useEvents/useSteps REST polling disabled (LOW, Step 8) -- RESOLVED
**File:** `llm_pipeline/ui/frontend/src/routes/live.tsx` L104-105
**Verification:** Both hooks now receive `runStatus` from `deriveRunStatus`. When status is 'running', hooks enable `refetchInterval: 3_000` as REST polling safety net alongside WS updates. When terminal, `staleTime: Infinity` prevents unnecessary refetches.

### Additional Fix: Array.findLast ES2023 -> ES2020 compatibility -- RESOLVED
**File:** `llm_pipeline/ui/frontend/src/routes/live.tsx` L51-58
**Verification:** Replaced `events.findLast(...)` with reverse for loop + `Set.has()`. Correct ES2020-compatible equivalent. No semantic difference.

## New Issues Introduced
None detected. Specific checks performed:
- `deriveRunStatus` useMemo deps are correct -- re-computes on wsStatus change, which is the only time event-list inspection matters.
- StepTimeline cursor/title changes are in shared component but benefit all consumers equally (run detail page has same issue).
- `RunStatus | undefined` type is assignable to StepDetailPanel's `runStatus?: string` prop -- no type mismatch.
- No unused imports introduced by the fixes.

## Recommendation
**Decision:** APPROVE

All 5 issues from the original review are resolved with minimal, correct fixes. No regressions or new issues detected. Implementation is production-ready.
