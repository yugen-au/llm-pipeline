# Research Summary

## Executive Summary

Cross-referenced two research agents (backend-architect, python-pro) against codebase and Task Master specs. Core design is consistent: `@runtime_checkable` Protocol with single `emit()` method, CompositeEmitter with tuple storage and per-handler Exception catch. One key contradiction on thread safety resolved: immutable tuple, no Lock. Event count (31), codebase patterns, downstream task compatibility all verified against source code. All CEO decisions received -- ready for planning.

## Domain Findings

### Protocol Design
**Source:** step-1-codebase-events-architecture.md, step-2-python-protocol-thread-safety.md

Both agents converge on:
- `@runtime_checkable` Protocol with single `emit(self, event: PipelineEvent) -> None` method
- Matches existing `VariableResolver` pattern in `llm_pipeline/prompts/variables.py` (verified)
- Protocol over ABC: single method, stateless interface, duck-typing desired
- ABC used in codebase for complex hierarchies (PipelineConfig, LLMProvider, PipelineStrategy -- 7 ABCs total, verified)

No contradictions. Both recommend Ellipsis body (`...`), not `pass`.

### Thread Safety (CONTRADICTION RESOLVED)
**Source:** step-1 section "Threading Status", step-2 section 2.2

**Agent 1 position:** Use `threading.Lock` to protect handler list. Lock held during tuple copy, released before handler.emit() calls. Blueprint imports `threading`.

**Agent 2 position:** Initially analyzes Lock vs RLock, then REVERSES in section 2.2. Final recommendation: No Lock needed if handlers stored as immutable tuple at construction. Presents Option A (no Lock, RECOMMENDED) and Option B (Lock, for future mutable handlers).

**Resolution:** Agent 2 (Option A) is correct for current task spec:
- Task 2 spec has no add/remove handler API
- `_handlers` is tuple set once in `__init__`, never reassigned
- Multiple threads reading same immutable tuple is safe (CPython GIL protects reference reads; tuple contents are immutable)
- Agent 1's Lock-then-copy pattern only matters if tuple ref could change at runtime
- YAGNI: Lock can be added later if dynamic registration is needed

**CEO confirmed:** Immutable tuple, no Lock. Lock can be added later if dynamic handler registration needed.

### Error Isolation
**Source:** step-1 section "Error Handling Patterns", step-2 section 3

Both agents agree:
- Catch `Exception` (not `BaseException`) per handler
- Use `logger.exception()` for automatic traceback at ERROR level
- Log handler repr and event_type for debugging context
- Do NOT re-raise or collect -- fire-and-forget
- Matches codebase pattern: pipeline.py, executor.py both use "catch, log, continue"

No contradictions. Agent 2 mentions ErrorCallback alternative but explicitly says "not recommended for task 2."

### Event System Verification
**Source:** step-1 section "Event System Architecture", codebase verification

Claims verified against `llm_pipeline/events/types.py`:
- [x] 31 concrete frozen event dataclasses (counted via grep, excludes StepScopedEvent)
- [x] PipelineEvent base with frozen=True, slots=True
- [x] StepScopedEvent intermediate with `_skip_registry = True`
- [x] `event_type` field derived via `__init_subclass__`, set in `__post_init__`
- [x] `EVENT_CATEGORY: ClassVar[str]` on all concrete events
- [x] No `from __future__ import annotations` in types.py (documented CPython edge case)
- [x] Events carry `to_dict()`, `to_json()`, `resolve_event()` classmethod

### Codebase Patterns
**Source:** step-1 sections "Logging Pattern", "Export Structure"; step-2 section 6

Verified against codebase:
- All modules use `logger = logging.getLogger(__name__)` -- confirmed
- All modules define `__all__` -- confirmed
- `events/__init__.py` currently exports 44 symbols, does NOT include emitter types yet -- confirmed
- `llm_pipeline/__init__.py` does NOT import from events/ (Task 18 handles this) -- confirmed
- No threading anywhere in codebase currently -- confirmed (grep shows zero results outside research docs)
- Google-style docstrings used throughout -- confirmed

### Upstream Task 1 Deviations
**Source:** step-1 section 9, master-1-pipeline-event-types/SUMMARY.md

Key deviations from Task 1 (all documented, none affect Task 2):
- LLMCallResult fields differ from PLAN.md (follows PRD PS-2)
- Event field names follow task spec over PLAN.md
- `from __future__ import annotations` omitted from types.py
- Private symbols removed from `__all__`
- InstructionsLogged added `logged_keys`; ExtractionError added `error_type`/`validation_errors`

### Downstream Task Compatibility
**Source:** Task Master tasks 6, 7, 18

- **Task 6** (handlers): Consumes PipelineEventEmitter Protocol. InMemoryEventHandler needs its OWN Lock. No impact on Task 2.
- **Task 7** (PipelineConfig): Adds `event_emitter: Optional[PipelineEventEmitter] = None` to `__init__()`. PipelineConfig is ABC (verified at line 73 of pipeline.py), NOT Pydantic. Current `__init__` at line 127 has 5 optional params. No impact on Task 2.
- **Task 18** (exports): Adds emitter types to `llm_pipeline/__init__.py`. No impact on Task 2.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Is immutable-tuple-without-Lock sufficient for "thread-safe concurrent access"? Or should Lock be present explicitly? | Yes, immutable tuple without Lock. Lock can be added later if dynamic handler registration needed. | No threading import needed. Simpler implementation. |
| Should CompositeEmitter include `__repr__` for debugging? | Yes, `CompositeEmitter(handlers=3)` style. | Add `__repr__` showing handler count. |
| Should CompositeEmitter use `__slots__`? | Yes, `__slots__ = ("_handlers",)` for consistency with codebase patterns. | Add `__slots__`, consistent with frozen+slots events. |

## Assumptions Validated
- [x] PipelineEvent is frozen dataclass, safe to pass to multiple handlers without copying (verified types.py line 57)
- [x] VariableResolver is the only existing Protocol in codebase (grep confirmed)
- [x] No existing threading in codebase -- CompositeEmitter would be first (grep confirmed)
- [x] 31 concrete event classes registered in _EVENT_REGISTRY (grep count matches)
- [x] events/__init__.py already imports from types.py; adding emitter imports is straightforward
- [x] PipelineConfig is ABC, not Pydantic -- no type adapter needed for event_emitter param (pipeline.py line 73)
- [x] `from __future__ import annotations` is safe in emitter.py (no slots+__init_subclass__ interaction)
- [x] Both agents agree on file placement: `llm_pipeline/events/emitter.py`
- [x] Both agents agree on export: add to `events/__init__.py` `__all__`

## Open Items
- None. All CEO decisions received.

## Recommendations for Planning
1. Use Agent 2's Option A skeleton (no Lock, immutable tuple) as implementation baseline (CEO confirmed)
2. Follow VariableResolver pattern exactly for Protocol definition (@runtime_checkable, single method, __all__ export, Google docstrings)
3. Keep CompositeEmitter simple: no ErrorCallback, no dynamic handler registration, no event filtering -- these can be added in future tasks
4. Add to events/__init__.py only (not llm_pipeline/__init__.py -- that's Task 18)
5. Omit `from __future__ import annotations` for consistency with types.py in same package
6. Test plan from Agent 2 Section 8 is comprehensive: mock handlers, error isolation, threading, duck typing, isinstance, empty handlers, composite nesting
7. Include `__slots__ = ("_handlers",)` on CompositeEmitter (CEO confirmed, consistent with frozen+slots events)
8. Include `__repr__` on CompositeEmitter showing handler count, e.g. `CompositeEmitter(handlers=3)` (CEO confirmed)
