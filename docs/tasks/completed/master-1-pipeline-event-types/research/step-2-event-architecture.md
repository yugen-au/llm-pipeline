# Step 2: Event Architecture Research

## Summary

Architecture recommendations for ~35 event dataclasses in `llm_pipeline/events/types.py`. Covers data model choice, inheritance hierarchy, type discrimination, serialization, category tracking, and deserialization registry.

---

## Decision 1: stdlib `@dataclass(frozen=True, slots=True)`

**Choice:** Python stdlib dataclasses, not Pydantic models or attrs.

**Rationale:**
- Events are internal observability data, not API contracts needing validation
- Codebase already uses `@dataclass` for value types (`ArrayValidationConfig`, `ValidationContext` in `llm_pipeline/types.py`)
- PRD explicitly says "event dataclasses" (FR-EV-002, DM-001)
- NFR-001 requires <1ms overhead per event point -- dataclass instantiation is ~10-50x faster than Pydantic
- `frozen=True` signals immutability, prevents accidental field reassignment
- `slots=True` reduces memory ~30% per instance (Python 3.11+ already required)

**Trade-off:** Mutable container fields (`dict`, `list`) inside frozen dataclasses can still have contents mutated. Acceptable -- frozen prevents field reassignment, not deep immutability.

**Rejected alternatives:**
- Pydantic: unnecessary validation overhead, events are constructed by trusted internal code
- attrs: external dependency for no gain over stdlib dataclasses
- NamedTuple: no inheritance support, no `__post_init__`, awkward for hierarchy

---

## Decision 2: Two-level hierarchy

**Choice:** `PipelineEvent` -> `StepScopedEvent`, no deeper category bases.

**Rationale:**
- `step_name` appears in 27 of 31 non-pipeline events -- warrants a shared intermediate
- No other field is shared enough within a category to justify deeper bases (e.g. `input_hash` only in 3/4 cache events)
- Deeper hierarchies add isinstance complexity and import overhead for ~1-2 shared fields
- `StepSelecting` is the one edge case (no step_name yet, step not selected) -- inherits from `PipelineEvent` directly

### Hierarchy

```
PipelineEvent (base: event_type, run_id, timestamp, pipeline_name)
├── PipelineStarted        (strategy_count, use_cache, use_consensus)
├── PipelineCompleted      (steps_executed, total_time_ms)
├── PipelineError          (error_type, error_message, step_name: str | None)
├── StepSelecting          (step_index, strategy_count)
│
└── StepScopedEvent (adds step_name: str)
    │
    │  # Step Lifecycle
    ├── StepSelected           (step_number, strategy_name)
    ├── StepSkipped            (step_number, reason)
    ├── StepStarted            (step_number, system_key, user_key)
    ├── StepCompleted          (step_number, execution_time_ms)
    │
    │  # Cache
    ├── CacheLookup            (input_hash)
    ├── CacheHit               (input_hash, cached_at)
    ├── CacheMiss              (input_hash)
    ├── CacheReconstruction    (model_count, instance_count)
    │
    │  # LLM Call
    ├── LLMCallPrepared        (call_count, system_key, user_key)
    ├── LLMCallStarting        (call_index, rendered_system_prompt, rendered_user_prompt)
    ├── LLMCallCompleted       (call_index, raw_response, parsed_result, model_name,
    │                           attempt_count, validation_errors)
    ├── LLMCallRetry           (attempt, max_retries, error_type, error_message)
    ├── LLMCallFailed          (max_retries, last_error)
    ├── LLMCallRateLimited     (attempt, wait_seconds, backoff_type)
    │
    │  # Consensus
    ├── ConsensusStarted       (threshold, max_calls)
    ├── ConsensusAttempt        (attempt, group_count)
    ├── ConsensusReached        (attempt, threshold)
    ├── ConsensusFailed         (max_calls, largest_group_size)
    │
    │  # Instructions & Context
    ├── InstructionsStored     (instruction_count)
    ├── InstructionsLogged     ()
    ├── ContextUpdated         (new_keys, context_snapshot)
    │
    │  # Transformation
    ├── TransformationStarting (transformation_class)
    ├── TransformationCompleted(data_key)
    │
    │  # Extraction
    ├── ExtractionStarting     (extraction_class, model_class)
    ├── ExtractionCompleted    (extraction_class, model_class, instance_count)
    ├── ExtractionError        (extraction_class, error_message)
    │
    │  # State
    └── StateSaved             (step_number, input_hash, execution_time_ms)
```

**Total: 4 direct PipelineEvent children + 27 StepScopedEvent children = 31 concrete events.**

---

## Decision 3: Auto-derived `event_type` via `__init_subclass__`

**Choice:** CamelCase -> snake_case auto-derivation, matching existing codebase patterns.

**Rationale:**
- `PipelineStrategy.__init_subclass__` in `strategy.py` auto-derives strategy names
- `LLMStep.step_name` in `step.py:247-256` auto-derives from class name via regex
- Same regex pattern: `re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', cls_name).lower()`
- Set as class variable `EVENT_TYPE`, copied to instance `event_type` in `__post_init__`

**Examples:**
- `PipelineStarted` -> `"pipeline_started"`
- `LLMCallCompleted` -> `"llm_call_completed"`
- `ExtractionError` -> `"extraction_error"`
- `CacheReconstruction` -> `"cache_reconstruction"`

**Rejected alternatives:**
- String enum: adds a parallel enum to maintain alongside classes
- Manual string per class: error-prone, violates DRY
- `__class__.__name__` at runtime: no snake_case, inconsistent with DB/wire format

---

## Decision 4: Category constants + `EVENT_CATEGORY` class var

**Choice:** Module-level string constants + class-level `EVENT_CATEGORY`.

**Purpose:** Enables per-category log levels in `LoggingEventHandler`, UI filtering, handler routing.

```python
# Category constants
PIPELINE = "pipeline"
STEP = "step"
CACHE = "cache"
LLM = "llm"
CONSENSUS = "consensus"
INSTRUCTIONS = "instructions"
TRANSFORMATION = "transformation"
EXTRACTION = "extraction"
STATE = "state"
```

Each concrete event sets `EVENT_CATEGORY` as a class variable (not an instance field):

```python
@dataclass(frozen=True, slots=True)
class CacheHit(StepScopedEvent):
    EVENT_CATEGORY = CACHE
    input_hash: str
    cached_at: datetime
```

**Why not an Enum:** String constants are simpler, no import needed, JSON-serializable by default, and the categories are fixed (not user-extensible).

---

## Decision 5: Auto-populated type registry for deserialization

**Choice:** `_EVENT_REGISTRY: dict[str, type[PipelineEvent]]` populated by `__init_subclass__`.

**Purpose:** `SQLiteEventHandler` reads events from DB as dicts; WebSocket receives JSON. Both need to reconstruct typed event instances.

```python
_EVENT_REGISTRY: dict[str, type[PipelineEvent]] = {}

# Populated automatically in PipelineEvent.__init_subclass__:
#   _EVENT_REGISTRY[cls.EVENT_TYPE] = cls

def resolve_event(event_dict: dict) -> PipelineEvent:
    """Reconstruct typed event from dict."""
    event_type = event_dict.get('event_type')
    cls = _EVENT_REGISTRY.get(event_type)
    if cls is None:
        raise ValueError(f"Unknown event type: {event_type}")
    d = event_dict.copy()
    d.pop('event_type', None)
    # Convert ISO strings back to datetime
    for key in ('timestamp', 'cached_at'):
        if key in d and isinstance(d[key], str):
            d[key] = datetime.fromisoformat(d[key])
    return cls(**d)
```

**Registration exclusion:** Intermediate bases (`StepScopedEvent`) are excluded via a check (e.g. presence of `step_name` as an abstract marker, or explicit `_abstract = True` class var).

---

## Decision 6: Serialization via `to_dict()` / `to_json()` on base

**Choice:** Base `PipelineEvent` methods handling datetime conversion.

```python
def to_dict(self) -> dict[str, Any]:
    result = {}
    for f in dataclasses.fields(self):
        value = getattr(self, f.name)
        if isinstance(value, datetime):
            result[f.name] = value.isoformat()
        else:
            result[f.name] = value
    return result

def to_json(self) -> str:
    return json.dumps(self.to_dict(), default=str)
```

**Why not `dataclasses.asdict()`:** It recursively converts nested dataclasses and doesn't handle `datetime`. Custom `to_dict()` is more predictable and handles only the types we actually use.

**Deserialization:** Handled by `resolve_event()` (Decision 5), not a `from_dict()` classmethod. Single entry point avoids needing to know the concrete class upfront.

---

## Decision 7: Single `types.py` with section headers

**Choice:** All 31 concrete events in one file, organized by comment sections.

**Rationale:**
- ~6-8 lines per event = ~250-300 lines total, well within single-file readability
- One file aids discoverability and grep-ability
- `__all__` list organized by category for clean imports
- Avoids 9 separate files + import wiring overhead

**File sections:**
```
# --- Category Constants ---
# --- Event Registry ---
# --- Base Events ---
# --- Pipeline Lifecycle (3) ---
# --- Step Lifecycle (5) ---
# --- Cache (4) ---
# --- LLM Call (6) ---
# --- Consensus (4) ---
# --- Instructions & Context (3) ---
# --- Transformation (2) ---
# --- Extraction (3) ---
# --- State (1) ---
```

---

## Decision 8: Field type conventions

| Field | Type | Rationale |
|-------|------|-----------|
| `run_id` | `str` | UUID string, matches `PipelineStepState.run_id` in `state.py:43` |
| `timestamp` | `datetime` | UTC-aware via `datetime.now(timezone.utc)`, matches `utc_now()` in `state.py:19` |
| `step_name` | `str` | Snake_case, matches `step.py` convention |
| `execution_time_ms` | `float` | Float for sub-ms precision per PRD |
| `total_time_ms` | `float` | Same as above |
| `context_snapshot` | `dict` | Direct dict, event frozen but dict contents mutable |
| `validation_errors` | `list[str]` | Accumulated across retries |
| `parsed_result` | `dict \| None` | None when parse failed |
| `raw_response` | `str \| None` | None when no response received |
| `model_name` | `str \| None` | None when provider doesn't report model |
| `cached_at` | `datetime` | When the cached result was originally created |
| `new_keys` | `list[str]` | Keys added to context by this step |
| `step_name` (on PipelineError) | `str \| None` | None when error occurs outside step scope |
| `threshold` | `float` | Consensus threshold (0.0-1.0) |
| `wait_seconds` | `float` | Rate limit backoff duration |

---

## Decision 9: `__init_subclass__` + `frozen=True` + `slots=True` compatibility

**Constraint:** Python 3.11+ dataclass inheritance with `slots=True` requires all levels to use `slots=True`. Children cannot add `__dict__`-based attributes.

**Solution:** `EVENT_TYPE` and `EVENT_CATEGORY` are class variables set in `__init_subclass__`, not instance fields. Class variables live on the class object, not in slots. No conflict.

For `__post_init__` with `frozen=True`: use `object.__setattr__` to set computed instance fields. This is the standard pattern:

```python
def __post_init__(self):
    object.__setattr__(self, 'event_type', self.__class__.EVENT_TYPE)
```

---

## Skeleton Implementation

```python
"""~35 pipeline event dataclasses organized by category."""

from __future__ import annotations

import dataclasses
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# --- Category Constants ---

PIPELINE = "pipeline"
STEP = "step"
CACHE = "cache"
LLM = "llm"
CONSENSUS = "consensus"
INSTRUCTIONS = "instructions"
TRANSFORMATION = "transformation"
EXTRACTION = "extraction"
STATE = "state"

# --- Event Registry ---

_EVENT_REGISTRY: dict[str, type[PipelineEvent]] = {}


def _derive_event_type(cls_name: str) -> str:
    """CamelCase -> snake_case. Same regex as step.py:255."""
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', cls_name)
    return s.lower()


def resolve_event(event_dict: dict) -> PipelineEvent:
    """Reconstruct typed event from serialized dict."""
    event_type = event_dict.get("event_type")
    cls = _EVENT_REGISTRY.get(event_type)
    if cls is None:
        raise ValueError(f"Unknown event type: {event_type}")
    d = event_dict.copy()
    d.pop("event_type", None)
    for key in ("timestamp", "cached_at"):
        if key in d and isinstance(d[key], str):
            d[key] = datetime.fromisoformat(d[key])
    return cls(**d)


# --- Base Events ---

@dataclass(frozen=True, slots=True)
class PipelineEvent:
    """Base for all pipeline events."""
    run_id: str
    pipeline_name: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: str = field(init=False)

    EVENT_TYPE: str = ""
    EVENT_CATEGORY: str = ""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.__name__ not in ("StepScopedEvent",):
            cls.EVENT_TYPE = _derive_event_type(cls.__name__)
            _EVENT_REGISTRY[cls.EVENT_TYPE] = cls

    def __post_init__(self):
        object.__setattr__(self, "event_type", self.__class__.EVENT_TYPE)

    def to_dict(self) -> dict[str, Any]:
        result = {}
        for f in dataclasses.fields(self):
            value = getattr(self, f.name)
            if isinstance(value, datetime):
                result[f.name] = value.isoformat()
            else:
                result[f.name] = value
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


@dataclass(frozen=True, slots=True)
class StepScopedEvent(PipelineEvent):
    """Base for events scoped to a specific pipeline step."""
    step_name: str = ""


# --- Pipeline Lifecycle (3) ---

@dataclass(frozen=True, slots=True)
class PipelineStarted(PipelineEvent):
    EVENT_CATEGORY = PIPELINE
    strategy_count: int = 0
    use_cache: bool = False
    use_consensus: bool = False


@dataclass(frozen=True, slots=True)
class PipelineCompleted(PipelineEvent):
    EVENT_CATEGORY = PIPELINE
    steps_executed: int = 0
    total_time_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class PipelineError(PipelineEvent):
    EVENT_CATEGORY = PIPELINE
    error_type: str = ""
    error_message: str = ""
    step_name: str | None = None


# --- Step Lifecycle (5) ---

@dataclass(frozen=True, slots=True)
class StepSelecting(PipelineEvent):  # no step_name yet
    EVENT_CATEGORY = STEP
    step_index: int = 0
    strategy_count: int = 0


@dataclass(frozen=True, slots=True)
class StepSelected(StepScopedEvent):
    EVENT_CATEGORY = STEP
    step_number: int = 0
    strategy_name: str = ""

# ... remaining ~26 events follow same pattern ...
```

---

## Extensibility Notes

**Adding new events:** Define a new frozen dataclass inheriting from `PipelineEvent` or `StepScopedEvent`. `__init_subclass__` auto-registers it. No manual registry updates needed.

**Adding new categories:** Add a new string constant. Set `EVENT_CATEGORY` on new events. No structural changes.

**Custom fields on future events:** Just add dataclass fields. `to_dict()` handles any JSON-serializable type. Add datetime conversion in `resolve_event()` if new datetime fields appear.

---

## Decisions Summary Table

| # | Decision | Choice | Key Rationale |
|---|----------|--------|---------------|
| 1 | Data model | `@dataclass(frozen=True, slots=True)` | Performance, simplicity, PRD alignment |
| 2 | Hierarchy depth | 2 levels (PipelineEvent, StepScopedEvent) | step_name shared by 27/31 events |
| 3 | event_type | Auto-derived via `__init_subclass__` | Matches strategy/step naming patterns |
| 4 | Category tracking | String constants + EVENT_CATEGORY class var | Per-category handler config |
| 5 | Deserialization | Auto-populated `_EVENT_REGISTRY` + `resolve_event()` | SQLiteEventHandler + WebSocket |
| 6 | Serialization | `to_dict()` / `to_json()` on base | Handles datetime, predictable |
| 7 | File organization | Single `types.py` with section headers | ~250 lines, one-file discoverability |
| 8 | Field types | `float` for timing, `datetime` UTC-aware, nullable where appropriate | Matches existing state.py conventions |
| 9 | slots compatibility | Class vars for EVENT_TYPE/CATEGORY, `object.__setattr__` in `__post_init__` | Python 3.11+ slots inheritance works cleanly |
