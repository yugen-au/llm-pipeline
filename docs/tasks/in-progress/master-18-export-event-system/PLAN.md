# PLANNING

## Summary

Add missing handler re-exports to `llm_pipeline/events/__init__.py` (4 symbols: LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler, DEFAULT_LEVEL_MAP) and promote 8 infrastructure symbols to `llm_pipeline/__init__.py` top-level. The `events/__init__.py` already exports all 31 concrete events and 9 category constants - only the handler gap needs fixing there. Top-level `__init__.py` grows from 18 to 26 exports via hybrid strategy (concrete events stay submodule-only).

## Plugin & Agents

**Plugin:** python-development
**Subagents:** [available agents]
**Skills:** none

## Phases

1. **Fix events/__init__.py**: Add 4 missing handler imports + update `__all__`
2. **Update top-level __init__.py**: Import and expose 8 infrastructure symbols, update `__all__` and module docstring

## Architecture Decisions

### Hybrid Export Strategy
**Choice:** 8 infrastructure symbols promoted to top-level; 31 concrete events + category constants remain submodule-only in `llm_pipeline.events`
**Rationale:** CEO confirmed hybrid over flat. Internal code imports directly from `events.types` (pipeline.py, step.py, gemini.py, executor.py) - no change needed. Downstream tasks 19, 43, 45 all compatible with hybrid. Avoids polluting top-level namespace with 60+ symbols.
**Alternatives:** Flat export (all 66+ symbols at top-level) - rejected by CEO

### PipelineEvent at Top-Level
**Choice:** Promote `PipelineEvent` base class to top-level alongside the 6 handler/emitter symbols
**Rationale:** Custom handler authors need `PipelineEvent` for type annotations. Without it, they must mix import levels (`from llm_pipeline import LoggingEventHandler` but `from llm_pipeline.events import PipelineEvent`).
**Alternatives:** Keep PipelineEvent submodule-only - rejected, creates awkward mixed imports for custom handler authors

### DEFAULT_LEVEL_MAP at Top-Level
**Choice:** Promote `DEFAULT_LEVEL_MAP` alongside `LoggingEventHandler`
**Rationale:** Users customizing log levels need both from the same import. Pairing them avoids users having to discover a second import location for a tightly-coupled constant.
**Alternatives:** Keep DEFAULT_LEVEL_MAP submodule-only - rejected, paired usage requires paired availability

### No PipelineEventRecord Re-export in handlers
**Choice:** When adding handler imports to `events/__init__.py`, import only 3 handlers + DEFAULT_LEVEL_MAP; do NOT re-import PipelineEventRecord from handlers
**Rationale:** handlers.py `__all__` includes PipelineEventRecord as a convenience, but events/__init__.py already imports it from models.py (line 74). Re-importing would create a duplicate.
**Alternatives:** Import entire handlers `__all__` - rejected, causes duplicate PipelineEventRecord

## Implementation Steps

### Step 1: Fix events/__init__.py - Add Handler Re-exports
**Agent:** python-development:coder
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. In `llm_pipeline/events/__init__.py`, add import after line 73 (after the emitter import):
   `from llm_pipeline.events.handlers import DEFAULT_LEVEL_MAP, InMemoryEventHandler, LoggingEventHandler, SQLiteEventHandler`
2. In `__all__` (line 80 onwards), add a `# Handlers` section before `# Base Classes` with the 4 new symbols: `"LoggingEventHandler"`, `"InMemoryEventHandler"`, `"SQLiteEventHandler"`, `"DEFAULT_LEVEL_MAP"`
3. Update the module docstring (lines 1-13) to mention handlers are also re-exported: add `from llm_pipeline.events import LoggingEventHandler, InMemoryEventHandler` to the Usage example

### Step 2: Update top-level __init__.py - Promote 8 Infrastructure Symbols
**Agent:** python-development:coder
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. In `llm_pipeline/__init__.py`, add imports from event infrastructure after line 18 (`from llm_pipeline.events.models import PipelineEventRecord`):
   - `from llm_pipeline.events.types import PipelineEvent`
   - `from llm_pipeline.events.emitter import PipelineEventEmitter, CompositeEmitter`
   - `from llm_pipeline.events.handlers import LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler, DEFAULT_LEVEL_MAP`
2. In `__all__`, add an `# Events` section after `# State` with all 8 symbols: `"PipelineEvent"`, `"PipelineEventEmitter"`, `"CompositeEmitter"`, `"LLMCallResult"`, `"LoggingEventHandler"`, `"InMemoryEventHandler"`, `"SQLiteEventHandler"`, `"DEFAULT_LEVEL_MAP"`
3. Also add `from llm_pipeline.llm.result import LLMCallResult` import (LLMCallResult is already in events/__init__.py via `from llm_pipeline.llm.result import LLMCallResult`, but top-level needs its own import)
4. Update module docstring: replace current Usage block to add event import examples showing top-level infrastructure vs submodule concrete events pattern

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| handlers.py imports SQLAlchemy/SQLModel at module level - pulling it into top-level __init__.py forces SQLAlchemy import on every `import llm_pipeline` | Medium | Verify handlers.py top-level imports; if heavy, use lazy import pattern (`__getattr__`) for SQLiteEventHandler only |
| PipelineEventRecord imported twice (from models in events/__init__ and re-exported in handlers.__all__) | Low | Step 1 explicitly imports only 4 named symbols from handlers, not `*` - no duplicate |
| Circular import if events/__init__.py imports from handlers which imports from events.models | Low | handlers.py already imports from events.models and events.types - no new circular dependency introduced |
| __all__ count mismatch (research says 26 at top-level, actual is 18 now + 8 new = 26) | Low | Verify count after implementation matches expected 26 |

## Success Criteria

- [ ] `from llm_pipeline.events import LoggingEventHandler` works
- [ ] `from llm_pipeline.events import InMemoryEventHandler` works
- [ ] `from llm_pipeline.events import SQLiteEventHandler` works
- [ ] `from llm_pipeline.events import DEFAULT_LEVEL_MAP` works
- [ ] `from llm_pipeline import PipelineEvent` works
- [ ] `from llm_pipeline import PipelineEventEmitter` works
- [ ] `from llm_pipeline import CompositeEmitter` works
- [ ] `from llm_pipeline import LLMCallResult` works
- [ ] `from llm_pipeline import LoggingEventHandler` works
- [ ] `from llm_pipeline import InMemoryEventHandler` works
- [ ] `from llm_pipeline import SQLiteEventHandler` works
- [ ] `from llm_pipeline import DEFAULT_LEVEL_MAP` works
- [ ] `llm_pipeline/__init__.py __all__` has exactly 26 entries
- [ ] `llm_pipeline/events/__init__.py __all__` has exactly 51 entries (47 existing + 4 handler symbols)
- [ ] `pytest` passes with no new failures
- [ ] No duplicate PipelineEventRecord in events/__init__.py

## Phase Recommendation

**Risk Level:** low
**Reasoning:** Pure export plumbing - no logic changes, no new files, no schema changes. Both target files are well-understood. The only non-trivial risk (SQLAlchemy lazy import) can be assessed during implementation and is Medium at worst. All architectural decisions resolved with zero open items.
**Suggested Exclusions:** testing, review
