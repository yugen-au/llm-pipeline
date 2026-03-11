# IMPLEMENTATION - STEP 3: FIX DOCS/INDEX.MD
**Status:** completed

## Summary
Added Events row to Module Index table, updated LLM Integration cross-reference to mention event system, added event imports to Most Common Imports quick reference.

## Files
**Created:** none
**Modified:** docs/index.md
**Deleted:** none

## Changes
### File: `docs/index.md`
Three targeted edits to docs/index.md.

```
# Before (Module Index table - rows 42-43)
| **[State](api/state.md)** | Execution state tracking | `PipelineStepState`, `PipelineRunInstance` |
| **[Registry](api/registry.md)** | Database registry with FK ordering | `PipelineDatabaseRegistry`, `ReadOnlySession` |

# After
| **[State](api/state.md)** | Execution state tracking | `PipelineStepState`, `PipelineRunInstance` |
| **Events** | Event system for pipeline observability | `InMemoryEventHandler`, `CompositeEmitter`, `LoggingEventHandler` |
| **[Registry](api/registry.md)** | Database registry with FK ordering | `PipelineDatabaseRegistry`, `ReadOnlySession` |
```

```
# Before (LLM Integration section)
#### LLM Integration
- [LLM Provider API Reference](api/llm.md)
- [Getting Started](guides/getting-started.md)

# After
#### LLM Integration
- [LLM Provider API Reference](api/llm.md)
- [Getting Started](guides/getting-started.md)
- [API Reference Index](api/index.md) - event system: `InMemoryEventHandler`, `CompositeEmitter` for observability
```

```
# Before (Most Common Imports)
# Database
from llm_pipeline import PipelineDatabaseRegistry, ReadOnlySession

# Prompts

# After
# Database
from llm_pipeline import PipelineDatabaseRegistry, ReadOnlySession

# Events (observability)
from llm_pipeline import InMemoryEventHandler, CompositeEmitter, LoggingEventHandler
from llm_pipeline.events import PipelineStarted, LLMCallStarting  # concrete events

# Prompts
```

## Decisions
### Events row link target
**Choice:** Plain text `**Events**` without hyperlink in the Module Index table.
**Rationale:** docs/api/events.md does not exist and creating it is out of scope per PLAN.md. Using plain text avoids a broken link.

### LLM Integration cross-reference target
**Choice:** Link to `api/index.md` (existing file) rather than `api/events.md` (non-existent).
**Rationale:** api/index.md is the complete import reference and exists. Linking there is accurate and navigable.

## Verification
- [x] Events row added between State and Registry rows in Module Index table
- [x] Events row uses plain text (no broken link to non-existent api/events.md)
- [x] Key classes InMemoryEventHandler, CompositeEmitter, LoggingEventHandler listed
- [x] LLM Integration section updated with event system reference
- [x] Most Common Imports includes event handler imports and concrete event types
- [x] No other files modified
