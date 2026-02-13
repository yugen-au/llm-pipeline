# Research Summary

## Executive Summary

Validated 3 domain research outputs (codebase architecture, Python event patterns, SQLite schema) against actual codebase on `dev` branch. All 31 event types, 9 categories, Protocol/CompositeEmitter patterns, PipelineConfig integration, and DB patterns verified correct. Found 1 contradiction requiring CEO input (consensus log level), 2 internally-resolvable contradictions (logger name default, index duplication), 3 gaps (missing `__all__` entries, undefined SQLiteEventHandler query scope, missing Engine import), and 5 validated hidden assumptions. Research is sound for planning; gaps are minor and addressable during implementation.

## Domain Findings

### Codebase Architecture (Event System Foundation)
**Source:** step-1-codebase-event-architecture.md, verified against `llm_pipeline/events/types.py`, `emitter.py`, `__init__.py`

- 31 concrete events across 9 categories: VERIFIED (counted each class in types.py)
- `PipelineEvent` base: `@dataclass(frozen=True, slots=True)`, auto-registration via `__init_subclass__`, `to_dict()`/`to_json()`/`resolve_event()` serialization: VERIFIED
- `StepScopedEvent` intermediate with `_skip_registry = True`: VERIFIED
- `EVENT_CATEGORY` is `ClassVar[str]` on concrete subclasses only, NOT on `PipelineEvent` base: VERIFIED (critical for `getattr()` fallback in LoggingEventHandler)
- `PipelineEventEmitter` Protocol: single `emit()` method, `@runtime_checkable`: VERIFIED (emitter.py line 21-41)
- `CompositeEmitter`: immutable tuple storage, sequential dispatch, per-handler `Exception` catch with `logger.exception()`: VERIFIED (emitter.py line 44-70)
- `PipelineConfig.__init__()` accepts `event_emitter: Optional[PipelineEventEmitter]` at line 136, `_emit()` helper at lines 206-213: VERIFIED
- `events/__init__.py`: 141 lines, 44-entry `__all__`, re-exports all types + emitter classes + `LLMCallResult`: VERIFIED

### Python Event Patterns (Thread Safety, Logging, Protocol)
**Source:** step-2-python-event-patterns.md, verified against codebase conventions

- `threading.Lock` (not RLock) for InMemoryEventHandler: CORRECT rationale (no re-entrant scenarios)
- Lock-protected list with copy-on-read query methods: CORRECT pattern
- Python logging is internally thread-safe (Handler.emit uses Lock): VERIFIED (stdlib docs)
- `getattr(type(event), "EVENT_CATEGORY", "unknown")` safe access: CORRECT (EVENT_CATEGORY absent from base)
- `%s` lazy formatting over f-strings in log calls: CORRECT per Python logging best practice
- `extra={"event_data": event.to_dict()}` for structured logging compat: sound addition, no conflict with default formatter
- Protocol structural conformance (no inheritance needed): matches codebase pattern and task 2 tests
- `__slots__` on all handler classes: matches CompositeEmitter precedent
- `__repr__` on all handler classes: matches CompositeEmitter precedent

### SQLite Schema Design
**Source:** step-3-sqlite-event-schema.md, verified against `llm_pipeline/state.py`, `llm_pipeline/db/prompt.py`, `llm_pipeline/db/__init__.py`

- `PipelineEventRecord(SQLModel, table=True)` with `__tablename__ = "pipeline_events"`: follows existing pattern
- Column types match codebase conventions: `Optional[int]` PK, `Field(max_length=N)`, `sa_column=Column(JSON)`, `Field(default_factory=utc_now)`: VERIFIED against PipelineStepState and Prompt models
- Intentional duplication (run_id/event_type/timestamp both as columns AND in event_data JSON): sound for query efficiency
- Handler self-init table creation via `SQLModel.metadata.create_all(engine, tables=[...])`: CORRECT pattern, idempotent, does not modify `init_pipeline_db()`
- Session-per-emit pattern: CORRECT for thread safety and avoiding session state accumulation
- No foreign keys to existing tables (run_id is logical link only): CORRECT
- New table only, zero migration risk: VERIFIED

## Contradictions Found

### 1. CATEGORY_CONSENSUS Log Level (REQUIRES CEO INPUT)
- **Step-1** (line 98-99): Groups consensus under "DEBUG: detail events"
- **Step-2** DEFAULT_LEVEL_MAP (line 99): Maps `CATEGORY_CONSENSUS` to `logging.INFO`
- **Task 6 spec**: "INFO for lifecycle, DEBUG for details" -- does not explicitly classify consensus
- **Impact**: Determines whether consensus voting events show at INFO or DEBUG verbosity

### 2. Logger Name Default (RESOLVED)
- **Step-1** (line 127): Constructor default `logger_name="llm_pipeline.events"`
- **Step-2** (line 117-121): Uses `__name__` (= `llm_pipeline.events.handlers`)
- **Resolution**: Use `__name__` per codebase convention. Every module in codebase uses `logging.getLogger(__name__)`. Step-2 skeleton code already implements this correctly.

### 3. Index Design Internal Contradiction (RESOLVED)
- **Step-3 model code** (lines 89-93): Shows 3 explicit indexes PLUS `Field(index=True)` on run_id (4 total)
- **Step-3 recommendation** (lines 117-120): Optimized 2-index set (composite + standalone event_type)
- **Resolution**: Use the optimized 2-index set. Composite `(run_id, event_type)` covers standalone run_id queries via leftmost prefix. Drop `Field(index=True)` from run_id field.

## Gaps Found

### 1. Missing `__all__` Entries for SQLiteEventHandler + PipelineEventRecord
- Step-2 skeleton `__all__` (line 446-450) only lists `DEFAULT_LEVEL_MAP`, `LoggingEventHandler`, `InMemoryEventHandler`
- Step-3 defines `PipelineEventRecord` model but never mentions updating `__all__`
- **Fix**: Final `handlers.py` `__all__` must include all 5 public names: `DEFAULT_LEVEL_MAP`, `LoggingEventHandler`, `InMemoryEventHandler`, `SQLiteEventHandler`, `PipelineEventRecord`

### 2. SQLiteEventHandler Query Methods Undefined
- InMemoryEventHandler has explicit query methods (`get_events`, `get_events_by_type`, `clear`)
- SQLiteEventHandler has only `emit()` defined across all research
- Task 6 spec defines query methods only for InMemoryEventHandler
- **Assumed**: SQLiteEventHandler is write-only (persistence sink). Queries happen via direct DB/ORM access. Needs confirmation.

### 3. Missing Engine Import in Skeleton
- Step-2 skeleton imports from `llm_pipeline.events.types` and stdlib, but does not import `from sqlalchemy import Engine` or `from sqlmodel import Session, SQLModel, Column, JSON, Field`
- Step-3 shows these imports in isolation but no consolidated import block
- **Fix**: Implementation must include full imports for SQLiteEventHandler + PipelineEventRecord.

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| Should CATEGORY_CONSENSUS be logged at INFO or DEBUG? Research step-1 says DEBUG, step-2 says INFO. Consensus events (Started/Attempt/Reached/Failed) represent voting outcomes. | PENDING | Determines DEFAULT_LEVEL_MAP value for consensus category |

## Assumptions Validated

- [x] Handler must manage its own Session (cannot reuse pipeline's ReadOnlySession or _real_session) -- verified via `llm_pipeline/session/readonly.py` write-blocking and `_real_session` being pipeline-internal
- [x] SQLiteEventHandler is opt-in; `pipeline_events` table NOT created by `init_pipeline_db()` -- verified `init_pipeline_db()` uses explicit table list (PipelineStepState, PipelineRunInstance, Prompt only)
- [x] Frozen dataclass events are safe for multi-handler dispatch without defensive copying -- verified `@dataclass(frozen=True)` on PipelineEvent base
- [x] PipelineEvent base class has no EVENT_CATEGORY; only concrete subclasses define it as ClassVar -- verified in types.py; requires `getattr(type(event), "EVENT_CATEGORY", "unknown")` fallback
- [x] `to_dict()` produces JSON-safe output (datetime to ISO string conversion) -- verified in types.py `to_dict()` method
- [x] `from __future__ import annotations` should be omitted from handlers.py -- correct, but for SQLModel Field() runtime type evaluation, NOT the slots+__init_subclass__ reason cited in step-2
- [x] `PipelineEventRecord` registered in `SQLModel.metadata` globally does not conflict with `init_pipeline_db()` because both use explicit table lists in `create_all()` -- verified in `db/__init__.py`
- [x] Multiple `SQLiteEventHandler` instances with same engine calling `create_all()` is safe (idempotent) -- standard SQLAlchemy behavior
- [x] Task 7 work (event_emitter param + _emit helper in PipelineConfig) is already present in codebase -- verified at pipeline.py lines 136, 154, 206-213

## Open Items

- CATEGORY_CONSENSUS log level: awaiting CEO decision (INFO vs DEBUG)
- SQLiteEventHandler write-only confirmation: assumed per spec but not explicitly stated
- Step-2 `from __future__ import annotations` rationale is incorrect (cites events package consistency/slots reason; actual reason is SQLModel compatibility) -- cosmetic, doesn't affect implementation

## Recommendations for Planning

1. Use optimized 2-index set for `pipeline_events` table: composite `(run_id, event_type)` + standalone `event_type`. Drop redundant `Field(index=True)` from run_id.
2. Use `__name__` for logger default (= `llm_pipeline.events.handlers`), matching codebase convention.
3. Include `extra={"event_data": event.to_dict()}` in LoggingEventHandler for structured logging compatibility.
4. Implement SQLiteEventHandler as write-only (emit only, no query methods) per task spec. Direct ORM queries can access PipelineEventRecord for reads.
5. Final `__all__` in handlers.py: `["DEFAULT_LEVEL_MAP", "LoggingEventHandler", "InMemoryEventHandler", "SQLiteEventHandler", "PipelineEventRecord"]`
6. Omit `from __future__ import annotations` in handlers.py for SQLModel compatibility.
7. Error handling strategy: NO internal try/except in handlers. Let exceptions propagate to CompositeEmitter's error isolation layer. Use defensive `getattr()` only for category lookup.
8. All three handlers should define `__slots__` and `__repr__` per CompositeEmitter precedent.
9. InMemoryEventHandler `get_events()` should accept `run_id: str | None = None` (None returns all events) for testing convenience.
