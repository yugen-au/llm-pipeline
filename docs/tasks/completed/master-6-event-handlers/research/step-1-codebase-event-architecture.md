# Research: Codebase Event Architecture for Task 6

## 1. Event System Foundation (Tasks 1+2, Complete)

### PipelineEvent Base (`llm_pipeline/events/types.py`)
- `@dataclass(frozen=True, slots=True)` with auto-registration via `__init_subclass__`
- Fields: `run_id: str`, `pipeline_name: str`, `timestamp: datetime` (default utc_now()), `event_type: str` (derived, init=False)
- Serialization: `to_dict()` (datetime->ISO), `to_json()`, `resolve_event()` classmethod for reconstruction
- `_EVENT_REGISTRY: dict[str, type[PipelineEvent]]` populated automatically from CamelCase class names
- `StepScopedEvent` intermediate base adds `step_name: str | None = None`, has `_skip_registry = True`
- No `from __future__ import annotations` in types.py (CPython slots+__init_subclass__ edge case)

### 31 Concrete Events, 9 Categories
| Category | Constant | Events |
|---|---|---|
| Pipeline Lifecycle | `CATEGORY_PIPELINE_LIFECYCLE` | PipelineStarted, PipelineCompleted, PipelineError |
| Step Lifecycle | `CATEGORY_STEP_LIFECYCLE` | StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted |
| Cache | `CATEGORY_CACHE` | CacheLookup, CacheHit, CacheMiss, CacheReconstruction |
| LLM Call | `CATEGORY_LLM_CALL` | LLMCallPrepared, LLMCallStarting, LLMCallCompleted, LLMCallRetry, LLMCallFailed, LLMCallRateLimited |
| Consensus | `CATEGORY_CONSENSUS` | ConsensusStarted, ConsensusAttempt, ConsensusReached, ConsensusFailed |
| Instructions/Context | `CATEGORY_INSTRUCTIONS_CONTEXT` | InstructionsStored, InstructionsLogged, ContextUpdated |
| Transformation | `CATEGORY_TRANSFORMATION` | TransformationStarting, TransformationCompleted |
| Extraction | `CATEGORY_EXTRACTION` | ExtractionStarting, ExtractionCompleted, ExtractionError |
| State | `CATEGORY_STATE` | StateSaved |

All events have `EVENT_CATEGORY: ClassVar[str]` for category-based filtering.

### PipelineEventEmitter Protocol (`llm_pipeline/events/emitter.py`)
```python
@runtime_checkable
class PipelineEventEmitter(Protocol):
    def emit(self, event: "PipelineEvent") -> None: ...
```
- Single method, duck-typed, `isinstance()` checks supported
- Matches existing `VariableResolver` pattern in codebase

### CompositeEmitter (`llm_pipeline/events/emitter.py`)
- Stores handlers as immutable tuple (no Lock, CEO-confirmed in task 2)
- Sequential dispatch, per-handler `Exception` catch with `logger.exception()`
- `__slots__ = ("_handlers",)`, `__repr__` shows handler count

### PipelineConfig Integration (Task 7, Complete)
- `__init__()` accepts `event_emitter: Optional[PipelineEventEmitter] = None` (line 136)
- Stored as `self._event_emitter`
- Helper `_emit(event)`: no-op if `_event_emitter is None`, calls `emit()` otherwise (line 206-213)

## 2. Database Patterns

### SQLModel/SQLAlchemy Usage
- All models: `SQLModel` with `table=True`, `Field()` with constraints, `Column(JSON)` for dicts
- Composite indexes via `Index()` in `__table_args__` tuple
- `Optional[int] = Field(default=None, primary_key=True)` for auto-increment IDs
- `datetime` fields use `Field(default_factory=utc_now)` from `llm_pipeline.state`

### Existing Tables
| Table | Model | File |
|---|---|---|
| `pipeline_step_states` | `PipelineStepState` | `llm_pipeline/state.py` |
| `pipeline_run_instances` | `PipelineRunInstance` | `llm_pipeline/state.py` |
| `prompts` | `Prompt` | `llm_pipeline/db/prompt.py` |

### Table Creation
- `init_pipeline_db()` in `llm_pipeline/db/__init__.py` creates framework tables
- Uses `SQLModel.metadata.create_all(engine, tables=[...])` with explicit table list
- Default SQLite at `.llm_pipeline/pipeline.db` (env `LLM_PIPELINE_DB` overrides)
- `PipelineConfig.__init__()` calls `init_pipeline_db(engine)` on startup

### Session Management
- `PipelineConfig._real_session`: writable Session for state saves, extractions
- `PipelineConfig.session`: ReadOnlySession wrapper blocking writes during step execution
- ReadOnlySession wraps Session, raises RuntimeError on add/delete/flush/commit/merge
- `_save_step_state()` uses `_real_session.add(state)` then `_real_session.flush()`

### Key Implication for SQLiteEventHandler
- Handler is opt-in, NOT created by `init_pipeline_db()`
- Must accept `Engine` in constructor (same engine PipelineConfig uses)
- Must create `pipeline_events` table itself via `SQLModel.metadata.create_all()`
- Must manage own Session (cannot use pipeline's sessions -- ReadOnlySession blocks writes, _real_session is pipeline-internal)
- Thread safety: new Session per `emit()` call, commit, close

## 3. Logging Patterns

### Module-Level Logger Convention
All modules use: `logger = logging.getLogger(__name__)`

### Existing Log Levels in Pipeline
| Level | Usage |
|---|---|
| `logger.info` | Step lifecycle ("STEP N: name..."), strategy selection, cache status, consensus results, data previews |
| `logger.warning` | Retry attempts, validation failures (in gemini.py) |
| `logger.error` | Pydantic validation failures, all retries exhausted |
| `logger.exception` | Handler failures in CompositeEmitter (auto-traceback) |

### Supplementation Strategy
Task 6 spec: LoggingEventHandler "supplements existing `logger.info` calls, doesn't replace." The existing `logger.info` calls in pipeline.py are ad-hoc text logs. LoggingEventHandler adds structured event logging alongside these. Both can coexist -- different loggers (`llm_pipeline.pipeline` vs `llm_pipeline.events.handlers`).

### Category-to-Level Mapping (from task spec)
- INFO: lifecycle events (pipeline_lifecycle, step_lifecycle)
- DEBUG: detail events (cache, llm_call, consensus, instructions_context, transformation, extraction, state)

## 4. Module Structure

### Current `llm_pipeline/events/` Layout
```
llm_pipeline/events/
  __init__.py    - Re-exports all types + emitter classes (140 lines, 44-entry __all__)
  types.py       - 31 event dataclasses + bases + registry (592 lines)
  emitter.py     - Protocol + CompositeEmitter (73 lines)
```

### Planned Addition
```
llm_pipeline/events/
  handlers.py    - LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler, PipelineEventRecord
```

### Export Path
- `handlers.py` defines handler classes + PipelineEventRecord SQLModel
- `events/__init__.py` will need handler exports added (but that's Task 18 scope -- task 6 only creates the file)
- For task 6, handlers importable via `from llm_pipeline.events.handlers import LoggingEventHandler`

## 5. Handler Design Specifications

### LoggingEventHandler
- Implements `emit(event: PipelineEvent) -> None`
- Constructor: optional `logger_name: str` (default "llm_pipeline.events"), optional `category_levels: dict[str, int]` for overrides
- Default levels: INFO for CATEGORY_PIPELINE_LIFECYCLE + CATEGORY_STEP_LIFECYCLE, DEBUG for all others
- Log format: structured message with event_type, run_id, key fields
- Uses `logging.getLogger(logger_name)` internally

### InMemoryEventHandler
- Constructor: no required params
- `emit()`: appends to `list[PipelineEvent]` protected by `threading.Lock`
- `get_events(run_id: str) -> list[PipelineEvent]`: filter by run_id
- `get_events_by_type(event_type: str) -> list[PipelineEvent]`: filter by event_type
- `clear() -> None`: reset list for testing
- Events are frozen dataclasses -- safe to store/return references

### SQLiteEventHandler
- Constructor: `engine: Engine`
- Creates `pipeline_events` table on init
- `emit()`: creates new Session, inserts PipelineEventRecord, commits, closes
- Thread-safe via session-per-emit pattern

### PipelineEventRecord (new SQLModel)
- `__tablename__ = "pipeline_events"`
- Fields: `id: Optional[int]` (PK), `run_id: str` (indexed), `event_type: str` (indexed), `event_data: dict` (JSON column), `timestamp: datetime`
- Indexes on `run_id` and `event_type`

## 6. Upstream Task Deviations (Impact on Task 6)

### Task 1 Deviations
- Event field names follow PRD task spec over PLAN.md (documented)
- LLMCallResult fields differ from PLAN.md (follows PRD PS-2)
- `from __future__ import annotations` omitted from types.py
- **Impact on Task 6:** None. Handlers consume PipelineEvent via `to_dict()` -- field names are transparent.

### Task 2 Deviations
- None from PLAN.md (SUMMARY.md confirms)
- CEO confirmed: immutable tuple, no Lock for CompositeEmitter
- **Impact on Task 6:** InMemoryEventHandler needs its OWN Lock (confirmed in VALIDATED_RESEARCH.md)

### Task 7 (Complete)
- `event_emitter` param and `_emit()` helper already in PipelineConfig
- **Impact on Task 6:** None. Handlers plug in via CompositeEmitter or directly as event_emitter.

## 7. Downstream Tasks (OUT OF SCOPE)

- **Task 8:** Emit pipeline lifecycle events in execute() -- uses handlers from task 6 but wires them in pipeline.py
- **Task 18:** Export handlers in `llm_pipeline/__init__.py` and `events/__init__.py`
- **Task 26:** UIBridge handler -- separate async bridge handler, depends on task 6 pattern

## 8. Test Patterns

### Existing Test Structure
- `tests/test_emitter.py`: 20 tests, uses pytest classes, Mock, threading
- `tests/test_pipeline.py`: integration tests
- `tests/test_llm_call_result.py`: unit tests for LLMCallResult
- Pattern: class-based grouping (TestClassName), `_make_event()` helpers, `@patch` for logger mocking

### Handler Test Strategy
- LoggingEventHandler: `@patch` logger, verify log calls per category level
- InMemoryEventHandler: store/retrieve events, thread-safety with concurrent emits, clear()
- SQLiteEventHandler: in-memory SQLite engine, verify persistence, query by run_id/event_type

## 9. Open Questions

None. All design decisions are inferrable from:
- Task 6 specification
- Codebase patterns (SQLModel, logging, module structure)
- Upstream task decisions (Lock for InMemoryEventHandler, thread safety patterns)
