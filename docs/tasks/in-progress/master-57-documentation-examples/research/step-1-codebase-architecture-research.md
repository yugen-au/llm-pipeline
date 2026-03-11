# Step 1: Codebase Architecture Research

Task 57 - README usage examples for event system, UI, and LLMCallResult.

---

## 1. Module Structure & Import Paths

### Top-level exports (`llm_pipeline/__init__.py`)

All infrastructure symbols are available at the top level:

```python
from llm_pipeline import (
    # Core pipeline
    PipelineConfig, LLMStep, LLMResultMixin, step_definition,
    PipelineStrategy, PipelineStrategies, StepDefinition,
    PipelineContext, PipelineInputData,
    PipelineDatabaseRegistry,
    # Events - infrastructure
    PipelineEvent, PipelineEventEmitter, CompositeEmitter,
    InMemoryEventHandler, LoggingEventHandler, SQLiteEventHandler,
    DEFAULT_LEVEL_MAP,
    # LLM result
    LLMCallResult,
    # State
    PipelineStepState, PipelineRunInstance, PipelineRun, PipelineEventRecord,
)
```

### Event types submodule (`llm_pipeline/events/__init__.py`)

Concrete event dataclasses are imported from the submodule:

```python
from llm_pipeline.events import (
    # Pipeline lifecycle
    PipelineStarted, PipelineCompleted, PipelineError,
    # Step lifecycle
    StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted,
    # LLM calls
    LLMCallPrepared, LLMCallStarting, LLMCallCompleted,
    LLMCallRetry, LLMCallFailed, LLMCallRateLimited,
    # Cache
    CacheLookup, CacheHit, CacheMiss, CacheReconstruction,
    # Consensus
    ConsensusStarted, ConsensusAttempt, ConsensusReached, ConsensusFailed,
    # Instructions & context
    InstructionsStored, InstructionsLogged, ContextUpdated,
    # Transformation & extraction
    TransformationStarting, TransformationCompleted,
    ExtractionStarting, ExtractionCompleted, ExtractionError,
    # State
    StateSaved,
    # Category constants
    CATEGORY_PIPELINE_LIFECYCLE, CATEGORY_STEP_LIFECYCLE,
    CATEGORY_LLM_CALL, CATEGORY_CACHE, CATEGORY_CONSENSUS,
    CATEGORY_INSTRUCTIONS_CONTEXT, CATEGORY_TRANSFORMATION,
    CATEGORY_EXTRACTION, CATEGORY_STATE,
    # Helpers
    resolve_event,  # alias for PipelineEvent.resolve_event
)
# LLMCallResult is also re-exported from llm_pipeline.events
from llm_pipeline.events import LLMCallResult
```

---

## 2. Event System

### Source files
- `llm_pipeline/events/types.py` - event dataclass definitions, base class, registry
- `llm_pipeline/events/emitter.py` - PipelineEventEmitter protocol, CompositeEmitter
- `llm_pipeline/events/handlers.py` - LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler

### PipelineEventEmitter (Protocol)

Defined in `llm_pipeline/events/emitter.py`:

```python
@runtime_checkable
class PipelineEventEmitter(Protocol):
    def emit(self, event: PipelineEvent) -> None: ...
```

- `@runtime_checkable` allows `isinstance(obj, PipelineEventEmitter)` checks
- Duck-typed: any object with a conforming `emit()` method satisfies the protocol
- Custom handlers need no inheritance, just implement `emit(self, event) -> None`

### Custom handler pattern

```python
class MyHandler:
    def emit(self, event: PipelineEvent) -> None:
        print(f"[{event.event_type}] run={event.run_id}")

handler = MyHandler()
assert isinstance(handler, PipelineEventEmitter)  # True at runtime
```

### CompositeEmitter

Defined in `llm_pipeline/events/emitter.py`:

```python
class CompositeEmitter:
    def __init__(self, handlers: list[PipelineEventEmitter]) -> None:
        self._handlers: tuple[PipelineEventEmitter, ...] = tuple(handlers)

    def emit(self, event: PipelineEvent) -> None:
        # Calls each handler sequentially; exceptions are logged, not re-raised
        for handler in self._handlers:
            try:
                handler.emit(event)
            except Exception:
                logger.exception("Handler %r failed for event %s", handler, event.event_type)
```

Key behavior: per-handler error isolation. A failing handler never prevents delivery to subsequent handlers.

Usage:

```python
from llm_pipeline import CompositeEmitter, InMemoryEventHandler, LoggingEventHandler

memory = InMemoryEventHandler()
logging_handler = LoggingEventHandler()
emitter = CompositeEmitter(handlers=[memory, logging_handler])

pipeline = MyPipeline(provider=provider, event_emitter=emitter)
```

### InMemoryEventHandler

Defined in `llm_pipeline/events/handlers.py`:

```python
class InMemoryEventHandler:
    def __init__(self) -> None:
        self._events: list[dict] = []
        self._lock = threading.Lock()

    def emit(self, event: PipelineEvent) -> None:
        # Appends event.to_dict() to internal list (thread-safe)

    def get_events(self, run_id: str | None = None) -> list[dict]:
        # Returns shallow copy, optionally filtered by run_id

    def get_events_by_type(self, event_type: str, run_id: str | None = None) -> list[dict]:
        # Returns events filtered by event_type string, optionally by run_id

    def clear(self) -> None:
        # Removes all stored events
```

- Events stored as dicts (via `event.to_dict()`)
- Thread-safe via `threading.Lock`
- Returns copies so callers cannot mutate internal state
- Can be used standalone (passed directly as `event_emitter=`) or inside `CompositeEmitter`

Usage example:

```python
from llm_pipeline import InMemoryEventHandler

handler = InMemoryEventHandler()
pipeline = MyPipeline(provider=provider, event_emitter=handler)
pipeline.execute(data=my_data)

# Query all events for a run
events = handler.get_events(run_id=pipeline.run_id)

# Query events by type
llm_events = handler.get_events_by_type("llm_call_completed", run_id=pipeline.run_id)

# Query all events (no run_id filter)
all_events = handler.get_events()

# Clear for next test
handler.clear()
```

### LoggingEventHandler

```python
class LoggingEventHandler:
    def __init__(
        self,
        logger: logging.Logger | None = None,   # defaults to module logger
        level_map: dict[str, int] | None = None, # defaults to DEFAULT_LEVEL_MAP
    ) -> None: ...

    def emit(self, event: PipelineEvent) -> None:
        # Logs: "{event_type}: {pipeline_name} - {run_id}" with extra={"event_data": ...}
```

DEFAULT_LEVEL_MAP (from `llm_pipeline/events/handlers.py`):

```python
DEFAULT_LEVEL_MAP = {
    # INFO level
    CATEGORY_PIPELINE_LIFECYCLE: logging.INFO,   # "pipeline_lifecycle"
    CATEGORY_STEP_LIFECYCLE: logging.INFO,       # "step_lifecycle"
    CATEGORY_LLM_CALL: logging.INFO,             # "llm_call"
    CATEGORY_CONSENSUS: logging.INFO,            # "consensus"
    # DEBUG level
    CATEGORY_CACHE: logging.DEBUG,               # "cache"
    CATEGORY_INSTRUCTIONS_CONTEXT: logging.DEBUG, # "instructions_context"
    CATEGORY_TRANSFORMATION: logging.DEBUG,       # "transformation"
    CATEGORY_EXTRACTION: logging.DEBUG,           # "extraction"
    CATEGORY_STATE: logging.DEBUG,               # "state"
}
```

### SQLiteEventHandler

```python
class SQLiteEventHandler:
    def __init__(self, engine: Engine) -> None:
        # Creates pipeline_events table (idempotent)
        # Migrates existing DBs: adds step_name column if missing
        # Creates composite index on (run_id, step_name)

    def emit(self, event: PipelineEvent) -> None:
        # Opens new Session per emit, persists PipelineEventRecord row, closes session
```

Persists to `pipeline_events` table as `PipelineEventRecord` rows.

### Event base class structure

All events are frozen=True, slots=True dataclasses. Base class fields:

```python
@dataclass(frozen=True, slots=True)
class PipelineEvent:
    run_id: str
    pipeline_name: str
    timestamp: datetime  # default_factory=utc_now
    event_type: str      # init=False, auto-derived from class name (CamelCase -> snake_case)
```

Auto-derivation examples:
- `PipelineStarted` -> `"pipeline_started"`
- `LLMCallCompleted` -> `"llm_call_completed"`
- `CacheHit` -> `"cache_hit"`

Serialization methods available on all events:
- `event.to_dict()` -> `dict[str, Any]` (datetimes as ISO strings)
- `event.to_json()` -> `str`

Deserialization:
- `PipelineEvent.resolve_event(event_type, data)` -> reconstructs correct subclass from dict

### StepScopedEvent

Intermediate base for step-level events. Adds:

```python
step_name: str | None = None
```

All step, LLM call, cache, consensus, extraction, transformation, context, and state events inherit from `StepScopedEvent`.

### Event type reference

**Pipeline Lifecycle** (`EVENT_CATEGORY = "pipeline_lifecycle"`):
- `PipelineStarted(run_id, pipeline_name)`
- `PipelineCompleted(run_id, pipeline_name, execution_time_ms: float, steps_executed: int)`
- `PipelineError(run_id, pipeline_name, error_type: str, error_message: str, traceback: str|None, step_name: str|None)`

**Step Lifecycle** (`EVENT_CATEGORY = "step_lifecycle"`):
- `StepSelecting(step_index: int, strategy_count: int)`
- `StepSelected(step_number: int, strategy_name: str, step_name: str)`
- `StepSkipped(step_number: int, reason: str, step_name: str)`
- `StepStarted(step_number: int, system_key: str|None, user_key: str|None, step_name: str)`
- `StepCompleted(step_number: int, execution_time_ms: float, step_name: str)`

**LLM Call** (`EVENT_CATEGORY = "llm_call"`):
- `LLMCallPrepared(call_count: int, system_key: str|None, user_key: str|None)`
- `LLMCallStarting(call_index: int, rendered_system_prompt: str, rendered_user_prompt: str)`
- `LLMCallCompleted(call_index: int, raw_response: str|None, parsed_result: dict|None, model_name: str|None, attempt_count: int, validation_errors: list[str])`
- `LLMCallRetry(attempt: int, max_retries: int, error_type: str, error_message: str)`
- `LLMCallFailed(max_retries: int, last_error: str)`
- `LLMCallRateLimited(attempt: int, wait_seconds: float, backoff_type: str)`

**Cache** (`EVENT_CATEGORY = "cache"`):
- `CacheLookup(input_hash: str)`
- `CacheHit(input_hash: str, cached_at: datetime)`
- `CacheMiss(input_hash: str)`
- `CacheReconstruction(model_count: int, instance_count: int)`

**Consensus** (`EVENT_CATEGORY = "consensus"`):
- `ConsensusStarted(threshold: int, max_calls: int)`
- `ConsensusAttempt(attempt: int, group_count: int)`
- `ConsensusReached(attempt: int, threshold: int)`
- `ConsensusFailed(max_calls: int, largest_group_size: int)`

**Instructions & Context** (`EVENT_CATEGORY = "instructions_context"`):
- `InstructionsStored(instruction_count: int)`
- `InstructionsLogged(logged_keys: list[str])`
- `ContextUpdated(new_keys: list[str], context_snapshot: dict)`

**Transformation** (`EVENT_CATEGORY = "transformation"`):
- `TransformationStarting(transformation_class: str, cached: bool)`
- `TransformationCompleted(data_key: str, execution_time_ms: float, cached: bool)`

**Extraction** (`EVENT_CATEGORY = "extraction"`):
- `ExtractionStarting(extraction_class: str, model_class: str)`
- `ExtractionCompleted(extraction_class: str, model_class: str, instance_count: int, execution_time_ms: float)`
- `ExtractionError(extraction_class: str, error_type: str, error_message: str, validation_errors: list[str])`

**State** (`EVENT_CATEGORY = "state"`):
- `StateSaved(step_number: int, input_hash: str, execution_time_ms: float)`

### Subscription patterns

Pattern 1 - single handler directly:
```python
handler = InMemoryEventHandler()
pipeline = MyPipeline(provider=provider, event_emitter=handler)
```

Pattern 2 - composite for multiple handlers:
```python
emitter = CompositeEmitter(handlers=[
    InMemoryEventHandler(),
    LoggingEventHandler(),
    SQLiteEventHandler(engine),
])
pipeline = MyPipeline(provider=provider, event_emitter=emitter)
```

Pattern 3 - custom handler (duck typing):
```python
class PrintHandler:
    def emit(self, event):
        if event.event_type == "llm_call_completed":
            print(f"LLM used {event.attempt_count} attempt(s)")

pipeline = MyPipeline(provider=provider, event_emitter=PrintHandler())
```

Pattern 4 - no events (None disables all emission):
```python
pipeline = MyPipeline(provider=provider, event_emitter=None)
```

---

## 3. LLMCallResult

### Source file
`llm_pipeline/llm/result.py`

### Class definition

```python
@dataclass(frozen=True, slots=True)
class LLMCallResult:
    parsed: dict[str, Any] | None = None
    raw_response: str | None = None
    model_name: str | None = None
    attempt_count: int = 1
    validation_errors: list[str] = field(default_factory=list)
```

### Properties

```python
result.is_success  # True when parsed is not None
result.is_failure  # True when parsed is None
```

Note: `validation_errors` are diagnostic only (from prior retry attempts) and do NOT affect `is_success`. A result can be successful AND have validation_errors (if it succeeded on a retry after earlier validation failures).

### Factory classmethods

```python
# Create a successful result
result = LLMCallResult.success(
    parsed={"field": "value"},
    raw_response='{"field": "value"}',
    model_name="gemini-1.5-pro",
    attempt_count=1,
    validation_errors=None,  # optional, defaults to []
)

# Create a failed result
result = LLMCallResult.failure(
    raw_response='<invalid json>',
    model_name="gemini-1.5-pro",
    attempt_count=3,
    validation_errors=["field required: 'field'", "invalid type for 'count'"],
)
```

### Serialization

```python
result.to_dict()   # -> dict with all fields
result.to_json()   # -> JSON string
```

### Where LLMCallResult appears

Returned by `LLMProvider.call_structured()`:
```python
class LLMProvider(ABC):
    @abstractmethod
    def call_structured(
        self,
        prompt: str,
        system_instruction: str,
        result_class: Type[BaseModel],
        max_retries: int = 3,
        not_found_indicators: list[str] | None = None,
        strict_types: bool = True,
        array_validation: ArrayValidationConfig | None = None,
        validation_context: ValidationContext | None = None,
        event_emitter: PipelineEventEmitter | None = None,
        step_name: str | None = None,
        run_id: str | None = None,
        pipeline_name: str | None = None,
        **kwargs,
    ) -> LLMCallResult: ...
```

Captured in `LLMCallCompleted` event (fields mirror LLMCallResult):
- `event.raw_response` <- `result.raw_response`
- `event.parsed_result` <- `result.parsed`
- `event.model_name` <- `result.model_name`
- `event.attempt_count` <- `result.attempt_count`
- `event.validation_errors` <- `result.validation_errors`

Import paths:
```python
from llm_pipeline import LLMCallResult
# or
from llm_pipeline.events import LLMCallResult
# or
from llm_pipeline.llm.result import LLMCallResult
```

---

## 4. UI System

### Installation

```bash
# Base install (no UI)
pip install llm-pipeline

# With UI support
pip install llm-pipeline[ui]

# UI deps: fastapi>=0.115.0, uvicorn[standard]>=0.32.0, python-multipart>=0.0.9
```

From `pyproject.toml`:
```toml
[project.optional-dependencies]
gemini = ["google-generativeai>=0.3.0"]
ui = ["fastapi>=0.115.0", "uvicorn[standard]>=0.32.0", "python-multipart>=0.0.9"]
```

### CLI entry point

Registered in pyproject.toml: `llm-pipeline = "llm_pipeline.ui.cli:main"`

```bash
# Production mode (default port 8642)
llm-pipeline ui

# Custom port
llm-pipeline ui --port 8000

# Custom database path
llm-pipeline ui --db ./my_pipeline.db

# Combined
llm-pipeline ui --port 8000 --db ./my_pipeline.db

# Development mode with hot reload (requires Node.js + npx)
llm-pipeline ui --dev

# Dev mode with custom port (Vite runs on port+1 = 8643)
llm-pipeline ui --dev --port 8642
```

### CLI behavior details (`llm_pipeline/ui/cli.py`)

**Production mode** (`_run_prod_mode`):
- Runs uvicorn on `0.0.0.0:{port}`
- Serves built frontend from `llm_pipeline/ui/frontend/dist/` via StaticFiles if it exists
- Falls back to API-only mode with warning if `dist/` not found

**Development mode** (`_run_dev_mode`):
- If `frontend/` directory exists: starts Vite dev server as subprocess + FastAPI
  - Vite port = `port + 1` (default 8643)
  - FastAPI port = `port` (default 8642)
  - Open the Vite URL (not FastAPI) in browser
  - Requires `npx` (Node.js)
  - Cleans up Vite subprocess on exit via `atexit` + SIGTERM handler
- If `frontend/` directory absent: headless reload mode (uvicorn with `reload=True`)

**Missing UI deps**: raises ImportError with message directing user to `pip install llm-pipeline[ui]`. Returns exit code 1.

**DB path**: if `--db` not provided, defaults to `LLM_PIPELINE_DB` env var, then `.llm_pipeline/pipeline.db`.

### Programmatic usage (`llm_pipeline/ui/app.py`)

```python
from llm_pipeline.ui import create_app
# or
from llm_pipeline.ui.app import create_app

def make_my_pipeline(run_id, engine, event_emitter=None, input_data=None):
    return MyPipeline(
        provider=GeminiProvider(),
        engine=engine,
        event_emitter=event_emitter,
        run_id=run_id,
    )

app = create_app(
    db_path="./pipeline.db",          # Optional; uses init_pipeline_db() default if None
    cors_origins=["*"],               # Optional; defaults to ["*"]
    pipeline_registry={               # Optional; maps name -> factory callable
        "my_pipeline": make_my_pipeline,
    },
    introspection_registry={          # Optional; maps name -> PipelineConfig subclass type
        "my_pipeline": MyPipeline,
    },
)
```

Pipeline registry factory signature:
```python
def factory(
    run_id: str,
    engine: Engine,
    event_emitter: PipelineEventEmitter | None = None,
    input_data: dict | None = None,
) -> pipeline_object:  # must expose .execute() and .save()
```

### REST API routes

All routes prefixed with `/api`:
- `GET /api/runs` - list runs (pagination: offset, limit; filters: pipeline_name, status, started_after, started_before)
- `GET /api/runs/{run_id}` - run detail with step summaries
- `GET /api/runs/{run_id}/context` - context evolution snapshots per step
- `POST /api/runs` - trigger pipeline run (async, returns 202 with run_id)
- `GET /api/steps` - step states
- `GET /api/events` - persisted events
- `GET /api/prompts` - prompt records
- `GET /api/pipelines` - pipeline introspection

### WebSocket endpoints

- `ws://host/ws/runs/{run_id}` - live event stream for a run
  - Completed/failed runs: replays persisted events then sends `{"type": "replay_complete", ...}`
  - Running runs: live stream via per-client `threading.Queue`
  - Unknown run_id: closes with code 4004
  - Heartbeat every 30s when no events: `{"type": "heartbeat", "timestamp": "..."}`
  - Completion sentinel: `{"type": "stream_complete", "run_id": "..."}`
- `ws://host/ws/runs` - global run-creation notifications
  - Receives `{"type": "run_created", "run_id": "...", "pipeline_name": "...", "started_at": "..."}`

### UIBridge (`llm_pipeline/ui/bridge.py`)

Bridges sync pipeline event emission to WebSocket clients:

```python
class UIBridge:
    def __init__(self, run_id: str, manager: ConnectionManager | None = None) -> None: ...
    def emit(self, event: PipelineEvent) -> None:
        # Serializes event.to_dict(), broadcasts to all WebSocket clients for run_id
        # Auto-calls complete() on PipelineCompleted or PipelineError

    def complete(self) -> None:
        # Sends None sentinel to signal stream_complete (idempotent)
```

Used internally by `POST /api/runs` to connect pipeline events to WebSocket clients. Not typically instantiated by users.

### ImportError behavior

When `llm_pipeline.ui` is imported without UI deps installed:

```python
# llm_pipeline/ui/__init__.py raises on import:
ImportError: "llm_pipeline.ui requires FastAPI. Install with: pip install llm-pipeline[ui]"
```

CLI (`llm-pipeline ui`) prints:
```
ERROR: UI dependencies not installed. Run: pip install llm-pipeline[ui]
```
Then exits with code 1.

---

## 5. Pipeline Execution Flow

### Source file
`llm_pipeline/pipeline.py`

### PipelineConfig class declaration

```python
class MyPipeline(PipelineConfig,
                 registry=MyRegistry,      # PipelineDatabaseRegistry subclass
                 strategies=MyStrategies): # PipelineStrategies subclass
    pass
```

Naming conventions enforced at class definition time:
- Pipeline class must end with `Pipeline`
- Registry class must be named `{PipelinePrefix}Registry`
- Strategies class must be named `{PipelinePrefix}Strategies`

Example: `MyPipeline` requires `MyRegistry` and `MyStrategies`.

### Constructor

```python
pipeline = MyPipeline(
    strategies=None,          # Optional list[PipelineStrategy]; uses STRATEGIES.create_instances() if None
    session=None,             # Optional SQLModel Session; overrides engine
    engine=None,              # Optional SQLAlchemy Engine; auto-SQLite if both None
    provider=None,            # LLMProvider instance (required for execute())
    variable_resolver=None,   # Optional VariableResolver for prompt variable classes
    event_emitter=None,       # Optional PipelineEventEmitter; None disables events
    run_id=None,              # Optional str; auto-generated UUID if None
)
```

### execute() method

```python
pipeline.execute(
    data=None,               # Raw input data (any type)
    initial_context=None,    # dict; merged into pipeline.context before execution
    input_data=None,         # dict; validated against INPUT_DATA schema if declared
    use_cache=False,         # Enable step-level caching via database
    consensus_polling=None,  # dict: {"enable": True, "consensus_threshold": 3, "maximum_step_calls": 5}
) -> PipelineConfig          # Returns self for chaining
```

### Event emission sequence

Events emitted during `execute()` in order:

1. `PipelineStarted` - run begins
2. For each step position:
   - `StepSelecting` - strategy evaluation starts
   - `StepSelected` - strategy chosen for this position
   - `StepSkipped` (if `step.should_skip()` returns True) OR:
     - `StepStarted` - step execution begins
     - `CacheLookup` (if `use_cache=True`)
     - `CacheHit`/`CacheMiss` (if `use_cache=True`)
     - `LLMCallPrepared` - LLM calls prepared
     - For each LLM call:
       - `LLMCallStarting` - includes rendered prompts
       - `LLMCallRetry` / `LLMCallRateLimited` (if retries occur)
       - `LLMCallCompleted` - includes raw_response, parsed_result, model_name, attempt_count
       - `LLMCallFailed` (if all retries exhausted)
     - `ConsensusStarted` / `ConsensusAttempt` / `ConsensusReached` / `ConsensusFailed` (if consensus enabled)
     - `InstructionsStored`
     - `ContextUpdated` (if step returns context)
     - `TransformationStarting` / `TransformationCompleted` (if step has transformation)
     - `ExtractionStarting` / `ExtractionCompleted` / `ExtractionError` (for each extraction class)
     - `StateSaved`
     - `StepCompleted`
3. `PipelineCompleted` (success) or `PipelineError` (exception)

### PipelineStrategy

```python
class MyStrategy(PipelineStrategy):
    # NAME and DISPLAY_NAME auto-generated from class name:
    # MyStrategy -> NAME="my", DISPLAY_NAME="My"
    # LaneBasedStrategy -> NAME="lane_based", DISPLAY_NAME="Lane Based"

    def can_handle(self, context: dict) -> bool:
        """Return True if this strategy applies given current context."""
        return True

    def get_steps(self) -> list[StepDefinition]:
        """Return ordered list of step definitions."""
        return [MyStep.create_definition()]
```

### PipelineStrategies

```python
class MyStrategies(PipelineStrategies, strategies=[
    PrimaryStrategy,
    FallbackStrategy,
]):
    pass
```

### PipelineDatabaseRegistry

```python
class MyRegistry(PipelineDatabaseRegistry, models=[
    Vendor,    # No FK dependencies
    RateCard,  # FK -> Vendor
    Lane,      # FK -> RateCard
]):
    pass
```

FK dependency order enforced at class instantiation time.

### LLMStep

```python
@step_definition(
    instructions=MyInstructions,          # Pydantic model class; must be named {StepPrefix}Instructions
    default_system_key="my_system_key",   # Optional prompt key
    default_user_key="my_user_key",       # Optional prompt key
    context=MyContext,                    # Optional PipelineContext subclass; must be named {StepPrefix}Context
)
class MyStep(LLMStep):
    def prepare_calls(self) -> list[StepCallParams]:
        """Return list of LLM call parameter dicts."""
        return [self.create_llm_call(variables={"key": "value"})]

    def process_instructions(self, instructions: list) -> dict | PipelineContext:
        """Process LLM results, return context updates."""
        return {}

    def should_skip(self) -> bool:
        """Return True to skip this step."""
        return False
```

Naming convention: step class must end with `Step`, e.g. `MyStep` matches `MyInstructions` and `MyContext`.

---

## 6. Supporting Types

### LLMResultMixin

Base class for LLM instruction/result schemas:

```python
class MyInstructions(LLMResultMixin):
    # Adds: confidence_score: float (0-1, default 0.95), notes: str|None
    my_field: str
    my_count: int

    example = {"my_field": "value", "my_count": 5}  # Optional; validated at class definition
```

Class methods on LLMResultMixin:
- `cls.get_example()` -> returns instance from `example` dict if defined
- `cls.create_failure(reason, **safe_defaults)` -> creates instance with confidence_score=0.0

### PipelineContext

```python
class MyContext(PipelineContext):
    table_type: str
    row_count: int
```

Returned from `step.process_instructions()`. Merged into `pipeline.context` dict via `model_dump()`.

### PipelineInputData

```python
class MyInputData(PipelineInputData):
    document_text: str
    document_id: str

class MyPipeline(PipelineConfig, registry=..., strategies=...):
    INPUT_DATA = MyInputData
```

When `INPUT_DATA` declared, `execute(input_data=...)` validates the dict against the schema.

---

## 7. Key Implementation Notes for README Examples

1. `InMemoryEventHandler` can be passed directly as `event_emitter=` without wrapping in `CompositeEmitter`. Both satisfy the `PipelineEventEmitter` protocol.

2. Events stored in `InMemoryEventHandler` are dicts (result of `event.to_dict()`), not event objects. Query by string event_type e.g. `"pipeline_started"`, `"llm_call_completed"`.

3. `LLMCallResult.is_success` is True iff `parsed is not None`. `validation_errors` being non-empty does NOT make a result a failure.

4. The UI CLI default port is `8642`. Dev mode opens Vite on port+1 (8643 by default). Users should open the Vite URL (port 8643) in the browser, not the FastAPI port.

5. The `pipeline_registry` factory receives `event_emitter` as a `UIBridge` instance when triggered via `POST /api/runs`. The bridge must be forwarded to the pipeline constructor for live WebSocket streaming to work.

6. `CompositeEmitter.__init__` takes `handlers` as a `list`, not `*args`. `CompositeEmitter(handlers=[h1, h2])`.

7. `PipelineEvent.resolve_event(event_type, data)` reconstructs event objects from serialized dicts. Available as `resolve_event` convenience alias from `llm_pipeline.events`.

8. Event emission is disabled entirely when `event_emitter=None` (default). No overhead if events not needed.

9. `SQLiteEventHandler` creates/migrates its table independently. Can be used with a pipeline's own engine without conflicting with pipeline DB initialization (`init_pipeline_db` is idempotent).

10. Upstream task 53 integration test code shows confirmed usage of `handler.get_events(pipeline.run_id)` and `handler.get_events_by_type('llm_call_starting')[0]` patterns.
