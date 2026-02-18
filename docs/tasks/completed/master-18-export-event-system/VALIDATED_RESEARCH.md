# Research Summary

## Executive Summary

Both research steps correctly identify the core gaps: events/__init__.py missing 4 handler re-exports, and llm_pipeline/__init__.py missing all event infrastructure exports beyond PipelineEventRecord. Hybrid export strategy (Option C) confirmed by CEO over flat approach (task spec). 8 infrastructure symbols promoted to top-level; 31 concrete events + categories stay in llm_pipeline.events submodule. Several count errors in research (28 vs 31 concrete events, 43 vs 47 items in events/__init__.py, 17 vs 18 items in top-level __init__.py) don't affect gap analysis. All three architectural decisions resolved.

## Domain Findings

### Gap 1: events/__init__.py Missing Handler Re-exports
**Source:** step-1-module-structure-research.md, step-2-event-system-architecture.md

CONFIRMED against actual codebase. events/__init__.py has zero imports from handlers.py. Missing 4 symbols:
- LoggingEventHandler
- InMemoryEventHandler
- SQLiteEventHandler
- DEFAULT_LEVEL_MAP

Tests currently bypass events/__init__.py entirely, importing directly from `llm_pipeline.events.handlers` (conftest.py line 26, test_handlers.py lines 16-21, test_cache_events.py line 14, test_retry_ratelimit_events.py line 17). This confirms the gap is real and impacting import ergonomics.

No ambiguity -- this fix is required regardless of which export strategy is chosen.

### Gap 2: Top-level __init__.py Missing Event Exports
**Source:** step-1-module-structure-research.md, step-2-event-system-architecture.md

CONFIRMED. llm_pipeline/__init__.py currently has 18 exports (research says 17, off by 1). Only PipelineEventRecord comes from the event system. All other event infrastructure (emitters, handlers, base classes, concrete events, LLMCallResult) requires submodule imports.

### Export Strategy: Hybrid vs Flat
**Source:** step-2-event-system-architecture.md (Option C recommendation)

Research recommends hybrid: infrastructure symbols promoted to top-level, 31 concrete events + categories stay in llm_pipeline.events.

**RESOLVED.** Task 18 spec implied flat export but CEO confirmed hybrid approach. 8 infrastructure symbols at top-level (18->26 in __all__), concrete events submodule-only.

### Count Errors in Research (Cosmetic)
**Source:** both research files

| Claim | Research | Actual | Impact |
| --- | --- | --- | --- |
| Concrete event count | 28 | 31 | None (gap analysis unaffected) |
| types.py __all__ items | 46 | 42 | None |
| events/__init__.py __all__ items | 43 | 47 | None |
| top-level __init__.py exports | 17 | 18 | None |

Counts are wrong but all qualitative findings (which symbols are missing, which are present) are correct.

### Consumer Import Patterns
**Source:** step-2-event-system-architecture.md, verified against codebase grep

Internal code (pipeline.py, step.py, gemini.py, executor.py) imports directly from `llm_pipeline.events.types` -- this is correct for internal usage and would not change regardless of export strategy. External consumers (tests, downstream tasks) use mixed patterns: some via `llm_pipeline.events`, some via deep paths like `llm_pipeline.events.handlers`. The handler gap forces deep imports.

### Upstream Task Deviations
**Source:** task 1 SUMMARY, task 6 SUMMARY

- Task 3 spec said `events/result.py` but LLMCallResult landed at `llm/result.py` (corrected during task 3 validated research). No impact on task 18.
- Task 6 handlers.py re-exports PipelineEventRecord in its __all__ (convenience import). When adding handler imports to events/__init__.py, import only the 3 handlers + DEFAULT_LEVEL_MAP; do NOT re-import PipelineEventRecord from handlers (already imported from models).
- Task 1 removed _EVENT_REGISTRY and _derive_event_type from __all__ during review (private symbols). events/__init__.py still imports them (lines 30-31) but they're correctly excluded from __all__. No change needed.

### Downstream Task Compatibility
**Source:** task 19, 43, 45 details

- Task 19 (FastAPI): needs handlers at top-level for app factory, event types from submodule for route serialization. Compatible with hybrid.
- Task 43 (PipelineInputData): no event dependency, just needs __init__.py in stable state. Compatible with any approach.
- Task 45 (Meta-pipeline): may emit events, would use submodule imports. Compatible with hybrid.

No downstream task requires concrete events at top-level.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Flat (task spec) vs hybrid (research) for top-level exports? | Hybrid confirmed. 8 infrastructure symbols at top-level, concrete events submodule-only. | Overrides task 18 spec. __init__.py grows from 18 to 26 symbols (not 66+). |
| Should PipelineEvent base class be top-level? | Yes. Avoids mixed imports for custom handler authors. | PipelineEvent added to top-level promotion list (was 6, now 8 with PipelineEvent + DEFAULT_LEVEL_MAP). |
| Should DEFAULT_LEVEL_MAP be top-level alongside LoggingEventHandler? | Yes. Users customizing log levels get both from same import. | DEFAULT_LEVEL_MAP added to top-level promotion list. |

## Assumptions Validated
- [x] events/__init__.py missing 4 handler re-exports (verified: no imports from handlers.py)
- [x] Top-level __init__.py exports only PipelineEventRecord from events (verified: line 18, line 43)
- [x] LLMCallResult canonical location is llm_pipeline/llm/result.py (verified: file exists, re-exported in events/__init__)
- [x] handlers.py __all__ has 5 items including PipelineEventRecord re-export (verified: lines 182-188)
- [x] PipelineEventEmitter is Protocol with runtime_checkable (verified: emitter.py lines 20-21)
- [x] CompositeEmitter isolates handler errors via try/except (verified: emitter.py lines 61-66)
- [x] Internal code imports from events.types directly (verified: pipeline.py L35, step.py L18, gemini.py L89, executor.py L119)
- [x] Tests bypass events/__init__.py for handlers (verified: grep shows 5+ direct imports from events.handlers)
- [x] Existing pattern: infrastructure at top-level (init_pipeline_db, ReadOnlySession), implementations in submodules (LLMProvider in llm/) (verified: __init__.py lines 20-21, llm/ not re-exported)
- [x] All 31 concrete events registered in _EVENT_REGISTRY via __init_subclass__ (verified: types.py L83-104)
- [x] No downstream task requires concrete events at top-level (verified: tasks 19, 43, 45 details)

## Open Items
- None. All architectural decisions resolved.

## Recommendations for Planning
1. Fix events/__init__.py handler re-exports first -- add LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler, DEFAULT_LEVEL_MAP from handlers.py
2. Add 8 infrastructure symbols to top-level __init__.py: PipelineEvent, PipelineEventEmitter, CompositeEmitter, LLMCallResult, LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler, DEFAULT_LEVEL_MAP (__all__ grows from 18 to 26)
3. Add import tests verifying both `from llm_pipeline import X` and `from llm_pipeline.events import X` paths work for all 8 promoted symbols
4. Do NOT re-import PipelineEventRecord from handlers when adding handler imports to events/__init__.py (already imported from models)
5. Update module docstring in llm_pipeline/__init__.py to document the event import patterns (top-level infrastructure vs submodule concrete events)
6. Consider updating existing tests to use the new shorter import paths (optional, non-breaking)
