# PLANNING

## Summary
Create PipelineEventEmitter Protocol and CompositeEmitter class for thread-safe event dispatching. Protocol uses @runtime_checkable with single emit() method following existing VariableResolver pattern. CompositeEmitter stores handlers as immutable tuple (no Lock), isolates per-handler errors via logger.exception(), includes __slots__/__repr__ for consistency with codebase patterns.

## Plugin & Agents
**Plugin:** python-development
**Subagents:** python-developer
**Skills:** none

## Phases
1. **Implementation**: Create emitter.py with Protocol and CompositeEmitter class
2. **Export**: Update events/__init__.py to export new symbols
3. **Testing**: Unit tests for CompositeEmitter behavior and thread safety

## Architecture Decisions

### Decision 1: Immutable Tuple Storage (No Lock)
**Choice:** Store handlers as tuple in __init__, never mutate, no threading.Lock
**Rationale:** Task spec has no add/remove handler API. Immutable tuple at construction is thread-safe (CPython GIL protects reference reads). VALIDATED_RESEARCH.md confirms CEO approval. YAGNI for Lock - can add later if dynamic registration needed.
**Alternatives:** threading.Lock (Agent 1 recommendation, rejected by Agent 2 and CEO)

### Decision 2: Protocol Over ABC
**Choice:** typing.Protocol with @runtime_checkable, single emit() method
**Rationale:** Matches existing VariableResolver pattern (verified in llm_pipeline/prompts/variables.py:10-43). Enables duck typing. Codebase uses ABC for complex hierarchies (PipelineConfig, LLMProvider), Protocol for simple interfaces. Single stateless method = Protocol domain.
**Alternatives:** ABC (rejected - overkill for single method)

### Decision 3: Error Isolation Strategy
**Choice:** Catch Exception (not BaseException) per handler, logger.exception() with handler repr and event_type context, continue to next handler
**Rationale:** Both research agents agree. Matches codebase patterns in pipeline.py/executor.py (catch, log, continue). Fire-and-forget semantics. No re-raise, no error collection.
**Alternatives:** ErrorCallback pattern (Agent 2 mentions, explicitly rejects for Task 2)

### Decision 4: Include __slots__ and __repr__
**Choice:** CompositeEmitter has __slots__ = ("_handlers",) and __repr__ showing handler count
**Rationale:** CEO confirmed both in VALIDATED_RESEARCH.md Q&A. Consistent with frozen+slots events in types.py. __repr__ aids debugging ("CompositeEmitter(handlers=3)").
**Alternatives:** Omit (rejected - CEO requested)

### Decision 5: Omit `from __future__ import annotations`
**Choice:** Do not import annotations from __future__
**Rationale:** Consistency with llm_pipeline/events/types.py which omits it (documented CPython edge case with slots+__init_subclass__). Same package, same convention.
**Alternatives:** Include (rejected - inconsistent with types.py in same package)

## Implementation Steps

### Step 1: Create emitter.py with Protocol and CompositeEmitter
**Agent:** python-development:python-developer
**Skills:** none
**Context7 Docs:** /python/typing
**Group:** A

1. Create llm_pipeline/events/emitter.py
2. Add module docstring describing PipelineEventEmitter Protocol and CompositeEmitter class
3. Add imports: `import logging`, `from typing import Protocol, runtime_checkable, TYPE_CHECKING`
4. Add conditional import: `if TYPE_CHECKING: from llm_pipeline.events.types import PipelineEvent`
5. Create logger: `logger = logging.getLogger(__name__)`
6. Define PipelineEventEmitter Protocol with @runtime_checkable decorator
7. Add Protocol docstring with example (follow VariableResolver pattern)
8. Define single method: `def emit(self, event: PipelineEvent) -> None: ...` (use Ellipsis, not pass)
9. Define CompositeEmitter class with __slots__ = ("_handlers",)
10. Add CompositeEmitter docstring describing dispatching and error isolation
11. Implement __init__(self, handlers: list[PipelineEventEmitter]) -> None: store tuple(handlers) as _handlers
12. Implement emit(self, event: PipelineEvent) -> None: iterate _handlers, catch Exception per handler, logger.exception with handler repr and event.event_type
13. Implement __repr__(self) -> str: return f"CompositeEmitter(handlers={len(self._handlers)})"
14. Define __all__ = ["PipelineEventEmitter", "CompositeEmitter"]

### Step 2: Export in events/__init__.py
**Agent:** python-development:python-developer
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. Open llm_pipeline/events/__init__.py
2. Add import after types.py imports: `from llm_pipeline.events.emitter import PipelineEventEmitter, CompositeEmitter`
3. Add to __all__ list after "StepScopedEvent": "PipelineEventEmitter", "CompositeEmitter"
4. Update module docstring to mention emitter exports

### Step 3: Create unit tests
**Agent:** python-development:python-developer
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. Create tests/test_emitter.py with module docstring
2. Add imports: pytest, unittest.mock (Mock, MagicMock), PipelineEventEmitter, CompositeEmitter, PipelineEvent (for duck typing test)
3. Create TestPipelineEventEmitter class: test isinstance check with @runtime_checkable, test duck typing (object with emit method passes isinstance), test non-conforming object fails isinstance
4. Create TestCompositeEmitter class with TestInstantiation: empty list, single handler, multiple handlers
5. Add TestCompositeEmitter.TestEmit: verify all handlers called with same event, verify handlers called in order
6. Add TestCompositeEmitter.TestErrorIsolation: mock handler raising Exception, verify other handlers still called, verify logger.exception called with correct context
7. Add TestCompositeEmitter.TestThreadSafety: create CompositeEmitter with thread-safe mock handlers, spawn multiple threads calling emit concurrently, join threads, verify all handlers received all events (thread count * event count total calls)
8. Add TestCompositeEmitter.TestRepr: verify __repr__ format matches "CompositeEmitter(handlers=N)"
9. Add TestCompositeEmitter.TestSlots: verify __slots__ defined, verify cannot add arbitrary attributes

## Risks & Mitigations
| Risk | Impact | Mitigation |
| --- | --- | --- |
| Thread safety assumptions incorrect (immutable tuple insufficient) | High | Comprehensive threading test with concurrent emit calls. VALIDATED_RESEARCH.md documents CEO approval and CPython GIL rationale. |
| Error isolation breaks on edge case (BaseException like KeyboardInterrupt) | Low | Spec says catch Exception, not BaseException. SystemExit/KeyboardInterrupt propagate (expected). Document in docstring. |
| Protocol isinstance check fails at runtime | Medium | Use @runtime_checkable decorator. Test with duck-typed object in tests. |
| Downstream Task 6 expects Lock in InMemoryEventHandler | Low | VALIDATED_RESEARCH.md confirms Task 6 needs its OWN Lock (InMemoryEventHandler stores mutable list). CompositeEmitter is separate concern. |

## Success Criteria
- [ ] PipelineEventEmitter Protocol defined with @runtime_checkable and single emit() method
- [ ] CompositeEmitter class created with tuple storage, __slots__, __repr__
- [ ] CompositeEmitter.emit() dispatches to all handlers sequentially
- [ ] Per-handler exceptions caught and logged via logger.exception(), other handlers continue
- [ ] PipelineEventEmitter and CompositeEmitter exported in events/__init__.py
- [ ] Unit tests pass: Protocol isinstance, duck typing, error isolation, thread safety, repr, slots
- [ ] pytest runs without errors
- [ ] No threading import in emitter.py (immutable tuple strategy)

## Phase Recommendation
**Risk Level:** low
**Reasoning:** Straightforward Protocol + class implementation. No DB changes, no external dependencies. Pattern verified in existing codebase (VariableResolver). CEO approved all design decisions. Comprehensive threading test mitigates main risk.
**Suggested Exclusions:** testing, review
