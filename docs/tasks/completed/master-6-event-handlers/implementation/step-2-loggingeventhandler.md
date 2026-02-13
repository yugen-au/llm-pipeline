# IMPLEMENTATION - STEP 2: LOGGINGEVENTHANDLER
**Status:** completed

## Summary
Created LoggingEventHandler in llm_pipeline/events/handlers.py with DEFAULT_LEVEL_MAP mapping 9 event categories to appropriate log levels (INFO for lifecycle-significant, DEBUG for implementation details). Handler uses Python logging with configurable logger and level map, format "%s: %s - %s" with extra event_data dict.

## Files
**Created:** llm_pipeline/events/handlers.py
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/events/handlers.py`
New file. Contains:
- DEFAULT_LEVEL_MAP: dict mapping 9 CATEGORY_* constants to logging.INFO or logging.DEBUG
- LoggingEventHandler class with __slots__ = ("_logger", "_level_map")
- __init__ with optional logger (defaults to __name__) and level_map (defaults to DEFAULT_LEVEL_MAP)
- emit() resolving category via getattr(type(event), "EVENT_CATEGORY", "unknown"), level from _level_map with INFO fallback
- __repr__ returning handler name
- __all__ exporting DEFAULT_LEVEL_MAP and LoggingEventHandler (other handlers will be added in steps 3-4)

```python
# Key implementation
DEFAULT_LEVEL_MAP: dict[str, int] = {
    CATEGORY_PIPELINE_LIFECYCLE: logging.INFO,
    CATEGORY_STEP_LIFECYCLE: logging.INFO,
    CATEGORY_LLM_CALL: logging.INFO,
    CATEGORY_CONSENSUS: logging.INFO,  # CEO decision
    CATEGORY_CACHE: logging.DEBUG,
    CATEGORY_INSTRUCTIONS_CONTEXT: logging.DEBUG,
    CATEGORY_TRANSFORMATION: logging.DEBUG,
    CATEGORY_EXTRACTION: logging.DEBUG,
    CATEGORY_STATE: logging.DEBUG,
}

def emit(self, event: "PipelineEvent") -> None:
    category: str = getattr(type(event), "EVENT_CATEGORY", "unknown")
    level = self._level_map.get(category, logging.INFO)
    self._logger.log(
        level,
        "%s: %s - %s",
        event.event_type,
        event.pipeline_name,
        event.run_id,
        extra={"event_data": event.to_dict()},
    )
```

## Decisions
### Logger default convention
**Choice:** logging.getLogger(__name__) as default
**Rationale:** Matches codebase convention (emitter.py line 17, every module uses __name__)

### No try/except in emit
**Choice:** Let exceptions propagate
**Rationale:** CompositeEmitter (emitter.py lines 58-67) catches per-handler exceptions. Adding handler-level catching would hide errors.

### CONSENSUS at INFO
**Choice:** CATEGORY_CONSENSUS mapped to logging.INFO
**Rationale:** CEO decision - consensus events are lifecycle-significant, not implementation details

## Verification
[x] isinstance(LoggingEventHandler(), PipelineEventEmitter) returns True
[x] DEFAULT_LEVEL_MAP contains all 9 category constants
[x] INFO-level event (PipelineStarted) logs at INFO
[x] DEBUG-level event (CacheLookup) logs at DEBUG
[x] Logger defaults to __name__ (llm_pipeline.events.handlers)
[x] __repr__ returns expected format
[x] __all__ exports DEFAULT_LEVEL_MAP and LoggingEventHandler
