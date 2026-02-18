# Step 2: Event System Architecture Research

## Inheritance Hierarchy

```
PipelineEvent (frozen dataclass, base)
  |-- PipelineStarted          [pipeline_lifecycle]
  |-- PipelineCompleted        [pipeline_lifecycle]  + execution_time_ms, steps_executed
  |
  |-- StepScopedEvent (intermediate, _skip_registry=True)  + step_name: str|None
  |     |-- PipelineError      [pipeline_lifecycle]  + error_type, error_message, traceback
  |     |-- StepSelecting      [step_lifecycle]      + step_index, strategy_count
  |     |-- StepSelected       [step_lifecycle]      + step_number, strategy_name
  |     |-- StepSkipped        [step_lifecycle]      + step_number, reason
  |     |-- StepStarted        [step_lifecycle]      + step_number, system_key, user_key
  |     |-- StepCompleted      [step_lifecycle]      + step_number, execution_time_ms
  |     |-- CacheLookup        [cache]               + input_hash
  |     |-- CacheHit           [cache]               + input_hash, cached_at
  |     |-- CacheMiss          [cache]               + input_hash
  |     |-- CacheReconstruction[cache]               + model_count, instance_count
  |     |-- LLMCallPrepared    [llm_call]            + call_count, system_key, user_key
  |     |-- LLMCallStarting    [llm_call]            + call_index, rendered prompts
  |     |-- LLMCallCompleted   [llm_call]            + call_index, raw_response, parsed_result, model_name, attempt_count, validation_errors
  |     |-- LLMCallRetry       [llm_call]            + attempt, max_retries, error_type, error_message
  |     |-- LLMCallFailed      [llm_call]            + max_retries, last_error
  |     |-- LLMCallRateLimited [llm_call]            + attempt, wait_seconds, backoff_type
  |     |-- ConsensusStarted   [consensus]           + threshold, max_calls
  |     |-- ConsensusAttempt   [consensus]           + attempt, group_count
  |     |-- ConsensusReached   [consensus]           + attempt, threshold
  |     |-- ConsensusFailed    [consensus]           + max_calls, largest_group_size
  |     |-- InstructionsStored [instructions_context] + instruction_count
  |     |-- InstructionsLogged [instructions_context] + logged_keys
  |     |-- ContextUpdated     [instructions_context] + new_keys, context_snapshot
  |     |-- TransformationStarting  [transformation] + transformation_class, cached
  |     |-- TransformationCompleted [transformation] + data_key, execution_time_ms, cached
  |     |-- ExtractionStarting [extraction]          + extraction_class, model_class
  |     |-- ExtractionCompleted[extraction]          + extraction_class, model_class, instance_count, execution_time_ms
  |     |-- ExtractionError    [extraction]          + extraction_class, error_type, error_message, validation_errors
  |     |-- StateSaved         [state]               + step_number, input_hash, execution_time_ms
```

Total: 2 bases + 28 concrete events = 30 classes. 9 categories.

---

## Event Registration Mechanism

- `__init_subclass__` auto-registers concrete events in `_EVENT_REGISTRY` dict
- `_derive_event_type()` converts CamelCase to snake_case (e.g. LLMCallStarting -> llm_call_starting)
- `_skip_registry = True` on StepScopedEvent prevents intermediate base registration
- `resolve_event(event_type, data)` reconstructs from serialized form
- `EVENT_CATEGORY` ClassVar on each concrete event maps to one of 9 category constants

---

## Emitter Architecture

```
PipelineEventEmitter (Protocol, runtime_checkable)
  |-- CompositeEmitter        (dispatches to N handlers, error-isolated)
  |-- LoggingEventHandler     (logs via Python logging, category-based levels)
  |-- InMemoryEventHandler    (thread-safe list, query methods)
  |-- SQLiteEventHandler      (persists to pipeline_events table via PipelineEventRecord)
```

- PipelineEventEmitter is a Protocol (duck-typing), not ABC
- Any object with `emit(event: PipelineEvent) -> None` satisfies it
- CompositeEmitter wraps N handlers, catches/logs per-handler exceptions
- Handlers have NO internal try/except -- CompositeEmitter provides isolation
- PipelineConfig constructor accepts optional event_emitter param

---

## LLMCallResult Structure

Located: `llm_pipeline/llm/result.py` (canonical), re-exported from `llm_pipeline/events/__init__.py`

```python
@dataclass(frozen=True, slots=True)
class LLMCallResult:
    parsed: dict[str, Any] | None = None
    raw_response: str | None = None
    model_name: str | None = None
    attempt_count: int = 1
    validation_errors: list[str] = field(default_factory=list)
```

- Factory classmethods: `success()`, `failure()`
- Properties: `is_success`, `is_failure`
- Serialization: `to_dict()`, `to_json()`
- Return type of `LLMProvider.call_structured()`

---

## Consumer Import Patterns (actual codebase usage)

| Consumer | Import Path | What |
|----------|-------------|------|
| pipeline.py (internal) | `from llm_pipeline.events.types import ...` | 20+ concrete events |
| step.py (internal) | `from llm_pipeline.events.types import ...` | Extraction events |
| llm/gemini.py (internal) | `from llm_pipeline.events.types import ...` | LLM retry/fail events |
| llm/executor.py (internal) | `from llm_pipeline.events.types import ...` | LLM call events |
| tests/test_pipeline.py | `from llm_pipeline.events import PipelineEventEmitter, PipelineEvent, PipelineStarted` | Submodule |
| tests/events/conftest.py | `from llm_pipeline.events.handlers import InMemoryEventHandler` | Deep import |
| tests/events/conftest.py | `from llm_pipeline.llm.result import LLMCallResult` | Deep import |

Key observation: Tests bypass events/__init__.py for handlers, going directly to handlers.py. This confirms handlers are missing from events/__init__.py re-exports.

---

## Gap Analysis (confirmed by step-1)

### events/__init__.py missing re-exports:
- LoggingEventHandler
- InMemoryEventHandler
- SQLiteEventHandler
- DEFAULT_LEVEL_MAP

### llm_pipeline/__init__.py missing exports:
- All event infrastructure except PipelineEventRecord

---

## Export Strategy Recommendation: Hybrid

### Rationale

Three options were evaluated:

**Option A (Flat):** Export all ~48 event symbols at top-level.
- Rejected: __init__.py grows from 17 to 65+ symbols. Pollutes namespace. Most users never need ConsensusAttempt or CacheMiss directly. Forces all event machinery to load on `import llm_pipeline`.

**Option B (Submodule only):** Keep everything in llm_pipeline.events, no new top-level exports.
- Rejected: Too restrictive. LLMCallResult is the return type of every LLM call -- should be top-level. PipelineEventEmitter/CompositeEmitter are needed by anyone configuring a pipeline with events.

**Option C (Hybrid, RECOMMENDED):** Promote infrastructure to top-level, keep concrete events in submodule.

### Recommended Top-Level Additions (llm_pipeline/__init__.py)

| Symbol | Justification |
|--------|---------------|
| PipelineEventEmitter | Protocol needed by anyone configuring event handling |
| CompositeEmitter | Needed to set up multi-handler dispatch |
| LLMCallResult | Return type of call_structured(), used in every pipeline |
| LoggingEventHandler | Most common handler, default for production |
| InMemoryEventHandler | Default for testing/UI |
| SQLiteEventHandler | Default for persistence |

Total: 6 new exports (17 -> 23 symbols in __all__)

### Recommended events/__init__.py Additions

| Symbol | Source |
|--------|--------|
| LoggingEventHandler | handlers.py |
| InMemoryEventHandler | handlers.py |
| SQLiteEventHandler | handlers.py |
| DEFAULT_LEVEL_MAP | handlers.py |

Total: 4 new re-exports (43 -> 47 symbols in __all__)

### What stays submodule-only (llm_pipeline.events)

- PipelineEvent, StepScopedEvent (base classes -- specialized usage)
- All 28 concrete event types (specialized, category-specific)
- 9 CATEGORY_* constants
- resolve_event helper
- DEFAULT_LEVEL_MAP

### Import ergonomics after implementation

```python
# Common usage (pipeline author)
from llm_pipeline import PipelineConfig, LLMCallResult, PipelineEventEmitter

# Setting up event handling
from llm_pipeline import CompositeEmitter, LoggingEventHandler, InMemoryEventHandler

# Specialized (event consumer, custom handler)
from llm_pipeline.events import PipelineStarted, StepCompleted, PipelineEvent

# Category-based filtering
from llm_pipeline.events import CATEGORY_LLM_CALL, CATEGORY_PIPELINE_LIFECYCLE
```

### Precedent in codebase

Follows existing pattern: `LLMProvider` stays in `llm_pipeline.llm` (implementation detail), while `init_pipeline_db` and `ReadOnlySession` are at top-level (infrastructure). Event handlers and emitter protocol are infrastructure; concrete event types are implementation details.

---

## Downstream Task Compatibility

- **Task 19 (FastAPI):** Routes will import event types from `llm_pipeline.events` for API serialization. Handler setup via `from llm_pipeline import InMemoryEventHandler, SQLiteEventHandler`. Compatible.
- **Task 43 (PipelineInputData):** No event dependency. Just needs __init__.py working. Compatible.
- **Task 45 (Meta-pipeline):** May emit events. Will use `from llm_pipeline.events import ...`. Compatible.
