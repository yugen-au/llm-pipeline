# Research: Pipeline Event System Patterns

## Executive Summary

The llm-pipeline codebase already has a comprehensive event system fully integrated into `PipelineConfig.execute()`. This research documents the existing architecture, identifies remaining gaps for Task 4 (OTel instrumentation + token usage tracking), and recommends the implementation approach.

---

## 1. Existing Event System Inventory

### 1.1 Event Types (`llm_pipeline/events/types.py`)

25+ frozen dataclass event types organized by category:

| Category | Events | Status |
|---|---|---|
| `pipeline_lifecycle` | `PipelineStarted`, `PipelineCompleted`, `PipelineError` | Emitted in `execute()` |
| `step_lifecycle` | `StepSelecting`, `StepSelected`, `StepSkipped`, `StepStarted`, `StepCompleted` | Emitted in `execute()` |
| `cache` | `CacheLookup`, `CacheHit`, `CacheMiss`, `CacheReconstruction` | Emitted in `execute()` |
| `llm_call` | `LLMCallPrepared`, `LLMCallStarting`, `LLMCallCompleted` | Emitted in `execute()` |
| `llm_call` (orphaned) | `LLMCallRetry`, `LLMCallFailed`, `LLMCallRateLimited` | **Dead code** -- emitter (GeminiProvider) deleted in Task 2. CEO deferred removal. |
| `consensus` | `ConsensusStarted`, `ConsensusAttempt`, `ConsensusReached`, `ConsensusFailed` | Emitted in `_execute_with_consensus()` |
| `instructions_context` | `InstructionsStored`, `InstructionsLogged`, `ContextUpdated` | Emitted in `execute()` |
| `transformation` | `TransformationStarting`, `TransformationCompleted` | Emitted in `execute()` |
| `extraction` | `ExtractionStarting`, `ExtractionCompleted`, `ExtractionError` | Emitted in extraction logic |
| `state` | `StateSaved` | Emitted in state save logic |

**Design pattern**: Frozen dataclasses with `slots=True`. Auto-registration via `__init_subclass__` into `_EVENT_REGISTRY`. Derived `event_type` string from CamelCase class name. Serializable via `to_dict()`/`to_json()`. Deserializable via `PipelineEvent.resolve_event()`.

**Base hierarchy**:
- `PipelineEvent` -- pipeline-scoped (run_id, pipeline_name, timestamp)
- `StepScopedEvent(PipelineEvent)` -- adds `step_name: str | None`, skips registry

### 1.2 Emitter Protocol (`llm_pipeline/events/emitter.py`)

```python
@runtime_checkable
class PipelineEventEmitter(Protocol):
    def emit(self, event: PipelineEvent) -> None: ...

class CompositeEmitter:
    # Dispatches to multiple handlers with per-handler error isolation
    def emit(self, event: PipelineEvent) -> None:
        for handler in self._handlers:
            try:
                handler.emit(event)
            except Exception:
                logger.exception(...)
```

**Pattern**: Protocol-based (duck typing). Any object with `emit(event) -> None` satisfies. CompositeEmitter wraps multiple handlers, isolates failures.

### 1.3 Handlers (`llm_pipeline/events/handlers.py`)

| Handler | Purpose | Thread-safe |
|---|---|---|
| `LoggingEventHandler` | Logs events via Python logging with category-based log levels | Yes (logging is thread-safe) |
| `InMemoryEventHandler` | Thread-safe in-memory list store for UI/testing | Yes (threading.Lock) |
| `SQLiteEventHandler` | Persists to `pipeline_events` table via SQLModel | Yes (session-per-emit) |

### 1.4 DB Persistence (`llm_pipeline/events/models.py`)

`PipelineEventRecord` SQLModel table with columns: `id`, `run_id`, `event_type`, `pipeline_name`, `step_name`, `timestamp`, `event_data` (JSON). Indexed on `(run_id, event_type)`, `(event_type)`, `(run_id, step_name)`.

### 1.5 Pipeline Integration (`llm_pipeline/pipeline.py`)

- `PipelineConfig.__init__` accepts `event_emitter: PipelineEventEmitter | None`
- Private `_emit()` helper forwards if emitter configured, no-ops otherwise
- `execute()` emits events at every lifecycle point (~20 emission points)
- `_execute_with_consensus()` emits consensus events
- Guard pattern: `if self._event_emitter:` before each `self._emit(...)` call

### 1.6 UI Integration

- **UIBridge** (`ui/bridge.py`): Implements `PipelineEventEmitter`, bridges sync pipeline events to WebSocket via `ConnectionManager.broadcast_to_run()`. Auto-detects terminal events (PipelineCompleted/PipelineError) to send completion sentinel.
- **WebSocket** (`ui/routes/websocket.py`): `ConnectionManager` with per-client `queue.Queue` fan-out. Supports live streaming for running pipelines and batch replay for completed/failed runs. Heartbeat on inactivity.
- **REST API** (`ui/routes/events.py`): Paginated GET endpoint at `/runs/{run_id}/events` with `event_type` and `step_name` filters.

---

## 2. Gap Analysis for Task 4

### 2.1 What Already Exists (no work needed)

- Event type definitions (25+ types covering all lifecycle points)
- Event emitter protocol and CompositeEmitter
- Three handler implementations (logging, in-memory, SQLite)
- Full pipeline integration in `execute()` and `_execute_with_consensus()`
- WebSocket streaming and REST API for UI consumption
- UIBridge for sync-to-async bridging

### 2.2 What's Missing (Task 4 scope)

| Gap | Description | Files Affected |
|---|---|---|
| **OTel instrumentation** | pydantic-ai agents do not emit OTel spans. No `InstrumentationSettings` or `Agent.instrument_all()` call. | `agent_builders.py` or `pipeline.py` |
| **Token usage on LLMCallCompleted** | Event has no `request_tokens`, `response_tokens`, `total_tokens` fields. `run_result.usage()` is not called. | `events/types.py`, `pipeline.py` |
| **Token usage on PipelineStepState** | DB model has no token usage columns. Cannot persist or query cost data. | `state.py` (+ DB migration) |
| **Token usage on consensus** | Consensus loop calls `agent.run_sync()` N times but does not aggregate token usage. | `pipeline.py` |
| **Observability documentation** | No `docs/observability.md`. No documentation of OTel setup, env vars, or event system. | New file |

---

## 3. Patterns Research

### 3.1 Event System Patterns (Already Implemented)

The codebase uses a well-implemented observer pattern with these characteristics:

| Pattern | Implementation | Assessment |
|---|---|---|
| **Observer/Protocol** | `PipelineEventEmitter` Protocol with `emit()` | Clean, Pythonic, runtime-checkable |
| **Composite dispatcher** | `CompositeEmitter` with error isolation | Best practice for multi-handler |
| **Frozen dataclasses** | `@dataclass(frozen=True, slots=True)` | Immutable, memory-efficient, correct |
| **Auto-registration** | `__init_subclass__` + `_EVENT_REGISTRY` | Eliminates manual registration |
| **Serialization** | `to_dict()`/`to_json()` via `dataclasses.asdict()` | Standard, no Pydantic overhead |
| **Callback injection** | Constructor DI via `event_emitter=` param | Decoupled, testable |
| **Thread safety** | InMemoryEventHandler uses Lock, SQLiteHandler uses session-per-emit | Correct for sync pipeline |

**Alternative patterns NOT used (and why)**:

- **Async generators**: Not needed; pipeline is synchronous (`agent.run_sync()`). Would add complexity without benefit.
- **Pydantic models for events**: Dataclasses chosen intentionally for lower overhead. Frozen dataclasses provide immutability without Pydantic validation cost per event. Good decision.
- **Event bus / global singleton**: Avoided in favor of explicit DI via constructor. Better for testing and multi-pipeline isolation.

### 3.2 pydantic-ai OTel Instrumentation

Two approaches available:

**Approach A: `Agent.instrument_all()` (recommended)**
```python
from pydantic_ai import Agent
Agent.instrument_all(include_content=True)
```
- Global: instruments all Agent instances
- One call at app startup
- Emits OTel spans for model requests, retries, tool calls
- No per-agent configuration needed
- Works with any OTel collector (Jaeger, Grafana Tempo, OTLP)

**Approach B: Per-agent `InstrumentationSettings`**
```python
from pydantic_ai import Agent, InstrumentationSettings
agent = Agent(
    ...,
    instrument=InstrumentationSettings(include_content=True),
)
```
- Per-agent: only instruments agents created with this setting
- Requires modifying `build_step_agent()` to accept and pass through
- More granular control but unnecessary for our use case (all agents should be instrumented)

**Recommendation**: Approach A. Call `Agent.instrument_all(include_content=True)` once in `PipelineConfig.execute()` or at module import time. Zero changes to `build_step_agent()`. All agents automatically instrumented.

**OTel configuration**: Standard env vars, no code changes needed:
- `OTEL_EXPORTER_OTLP_ENDPOINT` -- collector endpoint
- `OTEL_SERVICE_NAME` -- service name for spans
- `OTEL_TRACES_EXPORTER` -- exporter type (otlp, jaeger, console)
- Requires `opentelemetry-sdk` + `opentelemetry-exporter-otlp` (or similar) as optional deps

**logfire vs standard OTel**: `logfire.instrument_pydantic_ai()` is a convenience wrapper that internally uses OTel. Task 4 specifies "configuration via standard OTel environment variables" which suggests using pydantic-ai's native `Agent.instrument_all()` rather than adding logfire as a dependency. logfire is optional and not required.

### 3.3 Token Usage Extraction from pydantic-ai

After `run_result = agent.run_sync(user_prompt, deps=step_deps, model=self._model)`:

```python
usage = run_result.usage()
# RunUsage(input_tokens=N, output_tokens=N, requests=N, tool_calls=N)
usage.input_tokens   # int -- prompt tokens
usage.output_tokens  # int -- completion tokens
# Note: no explicit total_tokens field; compute as input_tokens + output_tokens
```

Also available per-response on `ModelResponse.usage`:
```python
# RequestUsage(input_tokens=N, output_tokens=N)
```

**Integration points**:

1. **LLMCallCompleted event** -- add 3 fields:
   ```python
   request_tokens: int | None = None
   response_tokens: int | None = None
   total_tokens: int | None = None
   ```

2. **PipelineStepState table** -- add 3 nullable int columns:
   ```python
   request_tokens: Optional[int] = Field(default=None)
   response_tokens: Optional[int] = Field(default=None)
   total_tokens: Optional[int] = Field(default=None)
   ```

3. **Consensus aggregation** -- sum usage across all consensus `agent.run_sync()` calls:
   ```python
   total_request = sum(r.usage().input_tokens for r in results)
   total_response = sum(r.usage().output_tokens for r in results)
   ```

### 3.4 Event Payload Design Assessment

Current LLMCallCompleted:
```python
@dataclass(frozen=True, slots=True, kw_only=True)
class LLMCallCompleted(StepScopedEvent):
    call_index: int
    raw_response: str | None        # Always None (pydantic-ai limitation, Task 2 noted)
    parsed_result: dict[str, Any] | None
    model_name: str | None
    attempt_count: int              # Always 1 (pydantic-ai limitation, Task 2 noted)
    validation_errors: list[str]
```

Proposed additions:
```python
    request_tokens: int | None = None
    response_tokens: int | None = None
    total_tokens: int | None = None
```

Using `None` defaults preserves backward compatibility with existing event consumers and cached events.

---

## 4. Implementation Recommendations

### 4.1 OTel Enablement

**Location**: Early in `PipelineConfig.execute()`, before the step loop.

```python
# In execute(), after prompt_service creation:
from pydantic_ai import Agent
Agent.instrument_all(include_content=True)
```

Or as a classmethod/module-level call for one-time initialization. `instrument_all()` is idempotent so calling it multiple times is safe.

**Dependencies**: Add `opentelemetry-sdk` and `opentelemetry-exporter-otlp` as optional deps in `pyproject.toml` under a new `[project.optional-dependencies].otel` group.

### 4.2 Token Usage on LLMCallCompleted

Add 3 optional fields to `LLMCallCompleted` in `events/types.py`. Extract from `run_result.usage()` in `pipeline.py` after `agent.run_sync()`. Pass to `LLMCallCompleted` constructor.

### 4.3 Token Usage on PipelineStepState

Add 3 nullable int columns to `PipelineStepState` in `state.py`. Populate in `_save_step_state()`. Requires ALTER TABLE migration in `SQLiteEventHandler.__init__` pattern (add column if missing, catch OperationalError).

### 4.4 Consensus Token Aggregation

Modify `_execute_with_consensus()` to:
1. Store `run_result` (not just `run_result.output`) for each attempt
2. Sum `usage().input_tokens` and `usage().output_tokens` across attempts
3. Return aggregated usage along with the consensus instruction

### 4.5 Observability Documentation

Create `docs/observability.md` covering:
- Event system architecture overview
- Available event types and categories
- Handler configuration (logging, in-memory, SQLite, WebSocket)
- OTel setup with env var reference
- Token usage tracking and cost analysis
- Example: connecting to Jaeger/Grafana Tempo

---

## 5. Orphaned Event Types (Deferred)

Three event types are defined but never emitted after Task 2:
- `LLMCallRetry` -- was emitted by deleted `GeminiProvider` retry loop
- `LLMCallFailed` -- was emitted by deleted `GeminiProvider` retry exhaustion
- `LLMCallRateLimited` -- was emitted by deleted `RateLimiter`

pydantic-ai manages retries internally without exposing per-retry callbacks. These events cannot be emitted without pydantic-ai API changes. CEO deferred their removal in Task 2 summary as "breaking events API change."

---

## 6. Thread Safety and Async Considerations

**Current model**: Pipeline execution is synchronous (`agent.run_sync()`). Events emitted from the main thread. When running via FastAPI UI, pipeline runs in a `BackgroundTasks` threadpool worker.

**Thread safety**: Already handled:
- `InMemoryEventHandler` uses `threading.Lock`
- `SQLiteEventHandler` uses session-per-emit
- `UIBridge` uses `queue.Queue.put_nowait()` (thread-safe by design)
- `CompositeEmitter` dispatches sequentially (no concurrent handler calls)

**OTel thread safety**: OpenTelemetry SDK is thread-safe by design. `Agent.instrument_all()` sets a global flag; subsequent `agent.run_sync()` calls emit spans from whatever thread they run on. OTel TracerProvider handles thread-safe span creation.

**No async changes needed**: The pipeline is sync. Event emission is sync. OTel span creation via pydantic-ai is sync. No async/await patterns needed for Task 4.

---

## 7. Risk Assessment

| Risk | Likelihood | Mitigation |
|---|---|---|
| OTel dependency adds weight | Low | Make optional via extras group `[otel]` |
| Token usage None for cached steps | Expected | Cached steps don't call LLM; token fields stay None |
| DB migration for PipelineStepState | Low | Use ADD COLUMN IF NOT EXISTS pattern (already used in handlers.py) |
| instrument_all() called multiple times | None | Idempotent by design |
| Consensus token aggregation changes return type | Medium | Return a tuple/dataclass instead of bare instruction, or store usage on step_deps |
