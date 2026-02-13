# PLANNING

## Summary
Implement 3 PipelineEventEmitter handlers for event system: LoggingEventHandler (Python logging with category-based levels), InMemoryEventHandler (thread-safe list with query methods), SQLiteEventHandler (persistence to pipeline_events table). Creates handlers.py with ~400 LOC plus PipelineEventRecord model, comprehensive tests, complete exports. Uses Protocol duck typing, no internal error handling (CompositeEmitter isolation layer), session-per-emit DB pattern.

## Plugin & Agents
**Plugin:** python-development
**Subagents:** backend-developer, database-designer, test-engineer
**Skills:** none

## Phases
1. Implementation - Create handlers + model + tests
2. Review - Code review (Medium risk: new DB table, thread safety)

## Architecture Decisions

### Decision 1: Index Design for pipeline_events Table
**Choice:** Optimized 2-index set: composite (run_id, event_type) + standalone event_type
**Rationale:** Composite index covers run_id-only queries via leftmost prefix (no redundant run_id-only index needed). Standalone event_type supports category queries. Research verified against PipelineStepState precedent (composite cache index pattern). Reduces storage overhead vs 3-index approach.
**Alternatives:** 3 indexes (run_id + event_type + composite) is redundant. Single composite-only lacks event_type query optimization.

### Decision 2: Error Handling Strategy
**Choice:** No try/except in handler emit methods. Let exceptions propagate to CompositeEmitter.
**Rationale:** CompositeEmitter (emitter.py lines 58-67) catches Exception per handler, logs via logger.exception(), continues to next handler. Adding handler-level catching would hide errors from CompositeEmitter's isolation layer. Research + validated research recommend this pattern.
**Alternatives:** Handler-level catching silences errors and defeats CompositeEmitter's purpose.

### Decision 3: Thread Safety Approach
**Choice:** threading.Lock (not RLock) for InMemoryEventHandler, session-per-emit for SQLiteEventHandler, no locking for LoggingEventHandler
**Rationale:** Python logging is internally thread-safe (Handler.emit uses lock). InMemoryEventHandler list mutation requires Lock protection; re-entrant scenarios impossible in event flow per research. SQLite session-per-emit avoids session state accumulation. Lock over RLock is simpler + sufficient.
**Alternatives:** RLock is unnecessary overhead. Global session would accumulate state and violate thread safety.

### Decision 4: Consensus Event Log Level
**Choice:** CATEGORY_CONSENSUS maps to logging.INFO in DEFAULT_LEVEL_MAP
**Rationale:** CEO decision (VALIDATED_RESEARCH.md line 52): consensus events are lifecycle-significant pipeline events, not implementation details. Matches category grouping: pipeline_lifecycle + consensus at INFO, details (cache, instructions_context, transformation, extraction) at DEBUG.
**Alternatives:** DEBUG would hide critical voting outcomes in default logging configs.

### Decision 5: Logger Name Default
**Choice:** Use __name__ (= llm_pipeline.events.handlers)
**Rationale:** Codebase convention verified: every module uses logging.getLogger(__name__). Matches emitter.py line 17, types.py implicit pattern. Provides proper module hierarchy in logs.
**Alternatives:** Hardcoded "llm_pipeline.events" string breaks convention and loses specificity.

### Decision 6: SQLiteEventHandler Query Scope
**Choice:** Write-only (emit method only, no query methods)
**Rationale:** Task spec defines query methods only for InMemoryEventHandler (get_events, get_events_by_type, clear). SQLiteEventHandler is persistence sink; queries happen via direct ORM access to PipelineEventRecord. Separation of concerns: persistence vs querying.
**Alternatives:** Adding query methods duplicates InMemoryEventHandler functionality and violates single-responsibility.

## Implementation Steps

### Step 1: Define PipelineEventRecord Model
**Agent:** python-development:database-designer
**Skills:** none
**Context7 Docs:** /websites/sqlmodel_tiangolo
**Group:** S

1. Create llm_pipeline/events/models.py (new file)
2. Import: SQLModel, Field, Column, JSON from sqlmodel; Optional, utc_now from llm_pipeline.state; Index from sqlalchemy
3. Define PipelineEventRecord(SQLModel, table=True) with __tablename__ = "pipeline_events"
4. Fields: id (Optional[int] PK), run_id (str, max_length=36), event_type (str, max_length=100), pipeline_name (str, max_length=100), timestamp (datetime, default_factory=utc_now), event_data (dict, sa_column=Column(JSON))
5. Add __table_args__ with 2 indexes: Index("ix_pipeline_events_run_event", "run_id", "event_type"), Index("ix_pipeline_events_type", "event_type")
6. Add __repr__ returning f"<PipelineEventRecord(id={self.id}, run={self.run_id}, type={self.event_type})>"
7. Set __all__ = ["PipelineEventRecord"]

### Step 2: Implement LoggingEventHandler
**Agent:** python-development:backend-developer
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Create llm_pipeline/events/handlers.py (new file)
2. Imports: logging, threading, TYPE_CHECKING; from typing import Optional; conditional import PipelineEvent
3. Define DEFAULT_LEVEL_MAP dict mapping 9 category constants to logging levels: CATEGORY_PIPELINE_LIFECYCLE/STEP_LIFECYCLE/LLM_CALL/CONSENSUS -> INFO, CATEGORY_CACHE/INSTRUCTIONS_CONTEXT/TRANSFORMATION/EXTRACTION/STATE -> DEBUG
4. Define LoggingEventHandler class with __slots__ = ("_logger", "_level_map")
5. __init__ accepts optional logger (Logger | None, defaults to logging.getLogger(__name__)), optional level_map (dict[str, int] | None, defaults to DEFAULT_LEVEL_MAP)
6. emit(event: PipelineEvent) -> None: get category via getattr(type(event), "EVENT_CATEGORY", "unknown"), get level from _level_map with fallback to INFO, call logger.log with level, message "%s: %s - %s" % (event.event_type, event.pipeline_name, event.run_id), extra={"event_data": event.to_dict()}
7. Add __repr__ returning f"LoggingEventHandler(logger={self._logger.name})"

### Step 3: Implement InMemoryEventHandler
**Agent:** python-development:backend-developer
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. In handlers.py, import threading.Lock
2. Define InMemoryEventHandler class with __slots__ = ("_events", "_lock")
3. __init__: initialize _events as empty list, _lock as Lock()
4. emit(event: PipelineEvent) -> None: acquire lock, append event.to_dict() to _events, release lock (use context manager)
5. get_events(run_id: str | None = None) -> list[dict]: acquire lock, copy _events, release lock; if run_id is None return copy, else filter by event["run_id"] == run_id
6. get_events_by_type(event_type: str, run_id: str | None = None) -> list[dict]: call get_events(run_id), filter by event["event_type"] == event_type
7. clear() -> None: acquire lock, clear _events list, release lock
8. Add __repr__ returning f"InMemoryEventHandler(events={len(self._events)})"

### Step 4: Implement SQLiteEventHandler
**Agent:** python-development:backend-developer
**Skills:** none
**Context7 Docs:** /websites/sqlmodel_tiangolo
**Group:** B

1. In handlers.py, import Engine from sqlalchemy, Session and SQLModel from sqlmodel
2. Import PipelineEventRecord from llm_pipeline.events.models
3. Define SQLiteEventHandler class with __slots__ = ("_engine",)
4. __init__(engine: Engine): store engine, call SQLModel.metadata.create_all(engine, tables=[PipelineEventRecord.__table__]) for idempotent table creation
5. emit(event: PipelineEvent) -> None: create Session(self._engine), create PipelineEventRecord from event fields (run_id, event_type=event.event_type, pipeline_name, timestamp, event_data=event.to_dict()), session.add(record), session.commit(), session.close() (use try/finally for close)
6. Add __repr__ returning f"SQLiteEventHandler(engine={self._engine.url})"
7. Update handlers.py __all__ to include DEFAULT_LEVEL_MAP, LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler

### Step 5: Comprehensive Tests
**Agent:** python-development:test-engineer
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. Create tests/events/test_handlers.py (new file if not exists)
2. Imports: pytest, logging, threading, create_engine from sqlalchemy, Session from sqlmodel, all handlers + PipelineEventRecord + DEFAULT_LEVEL_MAP from llm_pipeline.events.handlers, PipelineEvent types from llm_pipeline.events.types
3. Fixtures: sample_event (PipelineStarted), in_memory_handler, sqlite_handler (with in-memory DB engine)
4. Test LoggingEventHandler: test_logging_handler_default_levels (verify INFO for lifecycle/consensus, DEBUG for details), test_logging_handler_custom_logger (caplog fixture), test_logging_handler_custom_level_map, test_logging_handler_extra_data (verify extra dict in log record), test_logging_handler_unknown_category (fallback to INFO)
5. Test InMemoryEventHandler: test_inmemory_handler_emit_and_get, test_inmemory_handler_get_by_run_id (None + specific run_id), test_inmemory_handler_get_by_type, test_inmemory_handler_clear, test_inmemory_handler_thread_safety (concurrent emit from 10 threads, verify event count)
6. Test SQLiteEventHandler: test_sqlite_handler_table_creation (verify table exists), test_sqlite_handler_emit (verify record in DB), test_sqlite_handler_multiple_emits, test_sqlite_handler_indexes (query via ORM, verify index usage via EXPLAIN QUERY PLAN), test_sqlite_handler_session_isolation (no lingering session state)
7. Test Protocol conformance: test_handlers_satisfy_protocol (isinstance check for all 3 handlers)
8. Test PipelineEventRecord: test_event_record_serialization (to_dict if exists), test_event_record_json_field (verify event_data dict storage)

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Thread safety bugs in InMemoryEventHandler under high concurrency | High | Comprehensive thread safety test with 10+ concurrent threads. Use threading.Lock context manager (with statement) for automatic release. |
| SQLiteEventHandler table creation conflicts with existing pipeline DB init | Medium | Use explicit tables=[PipelineEventRecord.__table__] in create_all(), verified idempotent. Research confirmed init_pipeline_db() uses explicit table list (no conflict). |
| Category-based log level mapping breaks if new categories added without DEFAULT_LEVEL_MAP update | Medium | Use getattr fallback to INFO for unknown categories. Add test_logging_handler_unknown_category to verify fallback behavior. |
| Missing __all__ exports prevent handler imports in downstream tasks | Low | Explicit verification: handlers.py __all__ includes all 5 names (DEFAULT_LEVEL_MAP + 3 handlers + PipelineEventRecord), models.py __all__ includes PipelineEventRecord. |
| Session leaks in SQLiteEventHandler if emit() raises before close | Low | Use try/finally block to ensure session.close() even on exception. Test with DB constraint violation scenario. |

## Success Criteria

- [ ] LoggingEventHandler logs CATEGORY_CONSENSUS events at INFO level
- [ ] LoggingEventHandler logs CATEGORY_CACHE/INSTRUCTIONS_CONTEXT/TRANSFORMATION/EXTRACTION/STATE at DEBUG level
- [ ] DEFAULT_LEVEL_MAP contains all 9 category constants correctly mapped
- [ ] InMemoryEventHandler thread safety verified with 10+ concurrent threads, final count correct
- [ ] InMemoryEventHandler query methods (get_events, get_events_by_type, clear) function correctly
- [ ] SQLiteEventHandler creates pipeline_events table with 2 indexes (composite + standalone event_type)
- [ ] SQLiteEventHandler emit() persists records with correct JSON serialization of event_data
- [ ] All 3 handlers pass isinstance(handler, PipelineEventEmitter) check
- [ ] PipelineEventRecord model follows state.py conventions (Optional[int] PK, Field(max_length=N), sa_column=Column(JSON))
- [ ] handlers.py __all__ exports 5 names: DEFAULT_LEVEL_MAP, LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler, PipelineEventRecord
- [ ] All tests pass (pytest tests/events/test_handlers.py)
- [ ] No session leaks in SQLiteEventHandler (try/finally close)

## Phase Recommendation

**Risk Level:** medium
**Reasoning:** New DB table (migration-free but needs index verification), thread safety critical for InMemoryEventHandler (requires concurrent testing), log level mapping must be correct (impacts downstream debugging). No changes to existing pipeline/event core. Handlers are independent implementations (low coupling risk).
**Suggested Exclusions:** testing
