# Step 2: Event Emission Patterns Research

## Event Architecture Overview

### Base Classes (events/types.py)
- `PipelineEvent` - frozen dataclass (slots=True), fields: run_id, pipeline_name, timestamp, event_type (auto-derived via snake_case from class name)
- `StepScopedEvent(PipelineEvent)` - adds `step_name: str | None`, intermediate base with `_skip_registry = True`
- Auto-registration via `__init_subclass__` into `_EVENT_REGISTRY` dict
- Serialization: `to_dict()` (datetime -> ISO), `to_json()`
- Deserialization: `PipelineEvent.resolve_event(event_type, data)`

### Category Constants
- `CATEGORY_CONSENSUS = "consensus"` already defined (L31)
- Used by LoggingEventHandler for log-level mapping: CATEGORY_CONSENSUS -> logging.INFO (handlers.py L39)

### Emitter Protocol (events/emitter.py)
- `PipelineEventEmitter` - runtime_checkable Protocol with single `emit(event) -> None`
- `CompositeEmitter` - dispatches to multiple handlers, isolates per-handler errors via try/except

### Handlers (events/handlers.py)
- `LoggingEventHandler` - logs via Python logging with category-based levels
- `InMemoryEventHandler` - thread-safe list, used for testing
- `SQLiteEventHandler` - persists to `pipeline_events` table via PipelineEventRecord

## Existing Event Types

### Already Defined Consensus Events (types.py L380-421)
All 4 consensus event dataclasses are ALREADY defined:

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class ConsensusStarted(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_CONSENSUS
    threshold: int
    max_calls: int

@dataclass(frozen=True, slots=True, kw_only=True)
class ConsensusAttempt(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_CONSENSUS
    attempt: int
    group_count: int

@dataclass(frozen=True, slots=True, kw_only=True)
class ConsensusReached(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_CONSENSUS
    attempt: int
    threshold: int

@dataclass(frozen=True, slots=True, kw_only=True)
class ConsensusFailed(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_CONSENSUS
    max_calls: int
    largest_group_size: int
```

Already exported in `events/__init__.py` and `events/types.py __all__`.

### Related Existing Events (for pattern reference)
- Cache events (task 10): CacheLookup, CacheHit, CacheMiss, CacheReconstruction - emitted in pipeline.py execute()
- Retry/ratelimit events (task 12): LLMCallRetry, LLMCallFailed, LLMCallRateLimited - emitted in GeminiProvider.call_structured()
- Step lifecycle (task 9): StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted - emitted in pipeline.py execute()

## _emit() Mechanism (pipeline.py L213-220)

```python
def _emit(self, event: "PipelineEvent") -> None:
    if self._event_emitter is not None:
        self._event_emitter.emit(event)
```

Guard pattern used at all emission sites: `if self._event_emitter:` before `self._emit(...)`. This provides zero overhead when no emitter configured.

## _execute_with_consensus() Analysis (pipeline.py L965-991)

### Current Signature
```python
def _execute_with_consensus(self, call_kwargs, consensus_threshold, maximum_step_calls):
```
**Does NOT receive step_name** - needs modification per task 13 description.

### Current Code Flow
```
1. results = [], result_groups = []
2. for attempt in range(maximum_step_calls):
   a. instruction = execute_llm_step(**call_kwargs)
   b. Group instruction into result_groups (match via _instructions_match)
   c. if len(matched_group) >= consensus_threshold: return matched_group[0]
3. After loop: largest_group = max(result_groups, key=len), return largest_group[0]
```

### Data Available at Each Emission Point

| Emission Point | Available Data |
|---|---|
| Method start (before loop) | consensus_threshold, maximum_step_calls, step_name (needs param), self.run_id, self.pipeline_name |
| Per attempt (after grouping) | attempt+1, len(result_groups), step_name |
| Consensus reached (inside threshold check) | attempt+1, consensus_threshold, step_name |
| After loop exhausted | maximum_step_calls, len(largest_group), step_name |

### Call Site (pipeline.py L638-641)
```python
instruction = self._execute_with_consensus(
    call_kwargs, consensus_threshold, maximum_step_calls
)
```
`step.step_name` (stored in `current_step_name`) is available at the call site.

## Emission Point Mapping

### 1. ConsensusStarted - Before the loop
```python
# After def _execute_with_consensus(self, call_kwargs, consensus_threshold, maximum_step_calls, step_name):
if self._event_emitter:
    self._emit(ConsensusStarted(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
        step_name=step_name,
        threshold=consensus_threshold,
        max_calls=maximum_step_calls,
    ))
```

### 2. ConsensusAttempt - After each attempt's grouping
```python
# After matched_group is determined (after the for group in result_groups loop)
if self._event_emitter:
    self._emit(ConsensusAttempt(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
        step_name=step_name,
        attempt=attempt + 1,
        group_count=len(result_groups),
    ))
```
Emitted for EVERY attempt including the one where consensus is reached (provides group_count progression data).

### 3. ConsensusReached - Inside threshold check
```python
# Inside: if len(matched_group) >= consensus_threshold:
if self._event_emitter:
    self._emit(ConsensusReached(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
        step_name=step_name,
        attempt=attempt + 1,
        threshold=consensus_threshold,
    ))
```

### 4. ConsensusFailed - After loop exhaustion
```python
# After loop, before return largest_group[0]
if self._event_emitter:
    self._emit(ConsensusFailed(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
        step_name=step_name,
        max_calls=maximum_step_calls,
        largest_group_size=len(largest_group),
    ))
```

## Required Changes Summary

### pipeline.py
1. Add imports: ConsensusStarted, ConsensusAttempt, ConsensusReached, ConsensusFailed to import block (L36)
2. Modify `_execute_with_consensus` signature: add `step_name` parameter
3. Update call site (L638-641): pass `step_name=step.step_name`
4. Add 4 emission points inside `_execute_with_consensus` with `if self._event_emitter:` guards

### events/types.py - NO CHANGES NEEDED
All 4 event classes already defined and exported.

### events/__init__.py - NO CHANGES NEEDED
Already re-exports all 4 consensus event classes.

## Event Ordering (expected sequence)

### Consensus Reached (e.g., threshold=3, reached on attempt 3):
```
ConsensusStarted(threshold=3, max_calls=5)
ConsensusAttempt(attempt=1, group_count=1)
ConsensusAttempt(attempt=2, group_count=1)
ConsensusAttempt(attempt=3, group_count=1)
ConsensusReached(attempt=3, threshold=3)
```

### Consensus Failed (threshold=3, max_calls=5, all different):
```
ConsensusStarted(threshold=3, max_calls=5)
ConsensusAttempt(attempt=1, group_count=1)
ConsensusAttempt(attempt=2, group_count=2)
ConsensusAttempt(attempt=3, group_count=3)
ConsensusAttempt(attempt=4, group_count=4)
ConsensusAttempt(attempt=5, group_count=5)
ConsensusFailed(max_calls=5, largest_group_size=1)
```

## Testing Patterns (from existing tests)

### Conventions observed:
- Use `InMemoryEventHandler` for capturing events
- Filter events by `event_type` string: `[e for e in events if e["event_type"] == "consensus_started"]`
- Event types are snake_case of class name: ConsensusStarted -> "consensus_started"
- Assert event count, field values, ordering
- Test zero-overhead (no emitter = no crash)
- Test field values match expected data
- Test event ordering within sequence
- Use conftest.py fixtures: `seeded_session`, `in_memory_handler`, MockProvider, SuccessPipeline

### Test needs for consensus:
- Need a pipeline that uses `consensus_polling` config to trigger consensus path
- Mock provider returning varied/identical responses to control consensus outcome
- Test ConsensusReached path (all identical responses)
- Test ConsensusFailed path (all different responses)
- Test event field values
- Test event ordering
- Test zero-overhead (no emitter)
