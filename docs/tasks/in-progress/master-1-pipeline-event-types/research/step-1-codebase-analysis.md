# Step 1: Codebase Analysis for Event Dataclasses

## 1. Data Structure Patterns

Two paradigms coexist in the codebase:

| Pattern | Used In | Base Class | Purpose |
|---------|---------|------------|---------|
| `@dataclass` | `types.py` (`ArrayValidationConfig`, `ValidationContext`), `strategy.py` (`StepDefinition`) | stdlib `dataclass` | Simple data carriers, no DB persistence |
| `BaseModel` (Pydantic v2) | `context.py` (`PipelineContext`), `step.py` (`LLMResultMixin`) | `pydantic.BaseModel` | Validation, serialization, type coercion |
| `SQLModel` | `state.py` (`PipelineStepState`, `PipelineRunInstance`), `db/prompt.py` (`Prompt`) | `sqlmodel.SQLModel` | DB-persisted models |

**Decision: Use stdlib `@dataclass` for events.** Events are data carriers (no validation logic, no DB persistence in the base type). PRD explicitly specifies `@dataclass`. Existing codebase uses `@dataclass` for identical non-DB data carriers.

## 2. Import Style & Conventions

Import ordering (consistent across all files):
1. stdlib (`datetime`, `typing`, `abc`, `dataclasses`)
2. Third-party (`pydantic`, `sqlmodel`, `sqlalchemy`)
3. Internal (`llm_pipeline.*`)

TYPE_CHECKING guard used for circular imports:
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from llm_pipeline.pipeline import PipelineConfig
```

Type hint style (mixed, newer files use modern):
- `str | None` (modern, `step.py:187`) -- preferred
- `Optional[X]` (older, `types.py`, `state.py`) -- still present
- `list[str]` lowercase (modern, `rate_limiter.py:28`) -- preferred
- `List[str]` capitalized (`typing`) -- older files
- `Dict[str, Any]` from `typing` -- still prevalent
- `ClassVar` from `typing` for class-level attrs

**Decision for events:** Use modern syntax (`str | None`, `list[str]`, `dict[str, Any]`) matching newer files.

## 3. Module Structure & `__init__.py` Export Patterns

Every module follows:
```python
# Module docstring
"""..."""
# Imports
# Content
# __all__ at bottom
__all__ = ["Bar", "Baz"]
```

Package `__init__.py` (from `llm_pipeline/__init__.py`):
- Import all public symbols
- `__all__` organized by category with comments
- Top-level module docstring with usage examples

Sub-package `__init__.py` (from `llm_pipeline/llm/__init__.py`, `llm_pipeline/session/__init__.py`):
- Re-export from submodules
- Concise `__all__`

**For `events/__init__.py`:** Re-export `PipelineEvent`, all ~31 event classes, `PipelineEventEmitter`, `CompositeEmitter`, handler classes, `LLMCallResult`. Organized with category comments.

## 4. Naming Conventions

| Type | Convention | Examples |
|------|-----------|----------|
| Classes | CamelCase | `PipelineConfig`, `LLMStep`, `GeminiProvider` |
| Modules | snake_case | `pipeline.py`, `rate_limiter.py` |
| Functions | snake_case | `execute_llm_step`, `init_pipeline_db` |
| Constants | UPPER_SNAKE | `REGISTRY`, `STRATEGIES`, `MODELS` |
| Private | `_prefix` | `_instructions`, `_current_step` |
| ClassVar | UPPER_SNAKE on class | `MODEL: ClassVar`, `INPUT_TYPE: ClassVar` |

Naming enforcement via `__init_subclass__`:
- Pipeline -> must end `Pipeline`
- Step -> must end `Step`
- Strategy -> must end `Strategy`
- Extraction -> must end `Extraction`
- Instructions -> must end `Instructions`
- Context -> must end `Context`
- Transformation -> must end `Transformation`

**Event naming (from PRD):** CamelCase, no suffix enforcement: `PipelineStarted`, `StepCompleted`, `LLMCallRetry`, etc.

## 5. Dataclass Field Patterns

Existing `@dataclass` usage in codebase:

```python
# types.py - Simple defaults
@dataclass
class ArrayValidationConfig:
    input_array: List[Any]
    match_field: str = "original"
    filter_empty_inputs: bool = False

# strategy.py - field(default_factory=...)
@dataclass
class StepDefinition:
    step_class: Type
    system_instruction_key: str
    action_after: Optional[str] = None
    extractions: List[Type['PipelineExtraction']] = field(default_factory=list)
```

**For `PipelineEvent` base:** Use `field(default_factory=...)` for timestamp:
```python
from dataclasses import dataclass, field
from datetime import datetime, timezone

@dataclass
class PipelineEvent:
    event_type: str
    run_id: str
    pipeline_name: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
```

## 6. Pipeline Execution Flow (Event Emission Points)

From `pipeline.py:execute()`:

1. **Pipeline start** (line 427-429): Init context, data, extractions
2. **Step loop** (line 433): For each step index...
   - a. **Strategy selection** (line 438-443): Loop strategies, `can_handle()`
   - b. **Step skip check** (line 454): `should_skip()`
   - c. **Step start** (line 459-466): Log step name, strategy, prompt keys
   - d. **Input hash** (line 477): `_hash_step_inputs()`
   - e. **Cache check** (line 479-481): `_find_cached_state()`
   - f. **Cache path** (line 483-505): Load from cache, reconstruct extractions
   - g. **Fresh path** (line 506-549):
     - `prepare_calls()` (line 515)
     - For each call: `create_llm_call()` -> `execute_llm_step()` (line 518-530)
     - Consensus path (line 525-527): `_execute_with_consensus()`
     - Store instructions (line 532)
     - `process_instructions()` -> merge context (line 533-534)
     - Transformation (line 536-540)
     - `extract_data()` (line 542)
     - `_save_step_state()` (line 543-548)
     - `log_instructions()` (line 549)
   - h. **Post-step** (line 551): Add to `_executed_steps`
   - i. **Action after** (line 552-555): Optional post-step action
3. **Pipeline complete** (line 557-558): Clear `_current_step`, return self

## 7. LLM Call Flow (Retry/Rate-Limit Patterns)

From `gemini.py:call_structured()`:

1. Rate limiter wait (line 88)
2. Model creation (line 90-93)
3. Schema formatting + prompt augmentation (line 95-96)
4. API call (line 98)
5. Response check (line 100-103): Empty response -> retry
6. Not-found check (line 108-113)
7. JSON extraction (line 117-127): Regex for code blocks, fallback brace-finding
8. JSON parse (line 129-135): `json.loads`
9. Schema validation (line 138-149): `validate_structured_output()`
10. Array validation (line 152-164): `validate_array_response()`
11. Pydantic validation (line 167-181): `result_class.model_validate()` or `result_class(**)`
12. Rate limit error (line 186-207): Detect 429/quota, exponential backoff or API-suggested delay
13. General error (line 208-213)

Events map to: retry attempts (per-attempt data), rate limit events (wait duration, backoff type), validation failures (accumulated errors), final success/failure.

## 8. Consensus Flow

From `pipeline.py:_execute_with_consensus()`:

1. Loop up to `maximum_step_calls` (line 818)
2. Each iteration: `execute_llm_step()` (line 819)
3. Group matching via `_instructions_match()` (line 822-828)
4. Check threshold (line 830): If group size >= threshold, return
5. Fallback (line 836-839): Return most common response

Events: `ConsensusStarted`, `ConsensusAttempt` (per call), `ConsensusReached` or `ConsensusFailed`.

## 9. Extraction Flow

From `step.py:extract_data()`:

1. Loop extraction classes (line 321)
2. Instantiate extraction with pipeline (line 323)
3. Set `_current_extraction` (line 324)
4. Call `extraction.extract()` (line 326)
5. Store extractions (line 327)
6. Add instances to session + flush (line 328-330)
7. Clear `_current_extraction` (line 332)

Events: `ExtractionStarting` (per extraction class), `ExtractionCompleted` (with count), `ExtractionError` (on exception).

## 10. Event Type Inventory (from PRD Section 11)

| Category | Events | Count |
|----------|--------|-------|
| Pipeline Lifecycle | `PipelineStarted`, `PipelineCompleted`, `PipelineError` | 3 |
| Step Lifecycle | `StepSelecting`, `StepSelected`, `StepSkipped`, `StepStarted`, `StepCompleted` | 5 |
| Cache | `CacheLookup`, `CacheHit`, `CacheMiss`, `CacheReconstruction` | 4 |
| LLM Calls | `LLMCallPrepared`, `LLMCallStarting`, `LLMCallCompleted`, `LLMCallRetry`, `LLMCallFailed`, `LLMCallRateLimited` | 6 |
| Consensus | `ConsensusStarted`, `ConsensusAttempt`, `ConsensusReached`, `ConsensusFailed` | 4 |
| Instructions/Context | `InstructionsStored`, `InstructionsLogged`, `ContextUpdated` | 3 |
| Transformation | `TransformationStarting`, `TransformationCompleted` | 2 |
| Extraction | `ExtractionStarting`, `ExtractionCompleted`, `ExtractionError` | 3 |
| State | `StateSaved` | 1 |
| **Total** | | **31** |

Plus `LLMCallResult` (separate dataclass, not an event) = 32 dataclasses total.

## 11. Design Decisions for Events

Based on codebase patterns:

1. **Use `@dataclass`** -- matches existing data carrier pattern (not Pydantic)
2. **Inherit from `PipelineEvent` base** -- common fields: `event_type`, `run_id`, `pipeline_name`, `timestamp`
3. **`event_type` auto-derives from class name** -- CamelCase -> snake_case (`PipelineStarted` -> `"pipeline_started"`)
4. **`datetime.now(timezone.utc)` for timestamps** -- matches `state.py:utc_now()` pattern
5. **`str | None` for optional fields** -- modern style
6. **`list[str]` for list fields** -- modern style
7. **`dict[str, Any]` for dict fields** -- matches existing usage
8. **File location: `llm_pipeline/events/types.py`** -- per PRD TA-EV-001
9. **`__all__` at bottom of every file** -- universal pattern
10. **Module docstring at top** -- universal pattern

## 12. `LLMCallResult` Specifics

Separate from events, lives in `llm_pipeline/events/result.py`:
```python
@dataclass
class LLMCallResult:
    parsed: dict[str, Any] | None
    raw_response: str | None
    model_name: str | None
    attempt_count: int
    validation_errors: list[str]
```

Replaces `Optional[Dict[str, Any]]` return from `LLMProvider.call_structured()` (breaking change per PRD FR-PR-002).

## 13. Existing `utc_now()` Helper

`state.py:19-21`:
```python
def utc_now():
    return datetime.now(timezone.utc)
```

Events should either import this or replicate the pattern via `field(default_factory=lambda: datetime.now(timezone.utc))`.

## 14. Key Source Files Referenced

| File | Relevance |
|------|-----------|
| `llm_pipeline/types.py` | `@dataclass` patterns (`ArrayValidationConfig`, `ValidationContext`) |
| `llm_pipeline/state.py` | `SQLModel` patterns, `utc_now()`, `PipelineStepState` fields |
| `llm_pipeline/strategy.py` | `@dataclass` `StepDefinition`, `field(default_factory=...)` |
| `llm_pipeline/pipeline.py` | Execution flow, all emission points, consensus logic |
| `llm_pipeline/step.py` | Extraction flow, `LLMResultMixin`, step definition decorator |
| `llm_pipeline/llm/gemini.py` | Retry/rate-limit logic, raw response capture, validation errors |
| `llm_pipeline/llm/executor.py` | Prompt rendering, `execute_llm_step()` |
| `llm_pipeline/llm/provider.py` | `LLMProvider` ABC, `call_structured()` signature |
| `llm_pipeline/context.py` | `PipelineContext` Pydantic model |
| `llm_pipeline/__init__.py` | Export pattern with categorized `__all__` |
| `llm_pipeline/registry.py` | `PipelineDatabaseRegistry`, `__init_subclass__` pattern |
