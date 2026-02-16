# Codebase Architecture Research: Consensus Event Emissions

## 1. Event Type Definitions (Already Complete)

All 4 consensus event types exist in `llm_pipeline/events/types.py` L383-421, fully wired:

| Event | Fields (beyond StepScopedEvent) | Line |
|-------|------|------|
| `ConsensusStarted` | threshold (int), max_calls (int) | L383-391 |
| `ConsensusAttempt` | attempt (int), group_count (int) | L393-401 |
| `ConsensusReached` | attempt (int), threshold (int) | L403-411 |
| `ConsensusFailed` | max_calls (int), largest_group_size (int) | L413-421 |

All inherit `StepScopedEvent` -> `PipelineEvent`, providing: run_id (str), pipeline_name (str), step_name (str | None), timestamp (datetime), event_type (str, derived).

All use `CATEGORY_CONSENSUS` (mapped to `logging.INFO` in handlers.py L39), `frozen=True`, `slots=True`, `kw_only=True`.

**Verified exports:**
- types.py `__all__` L579-582
- events/__init__.py L55-58
- `_EVENT_REGISTRY` auto-populated via `__init_subclass__`

**No changes needed to types.py, events/__init__.py, events/emitter.py, events/handlers.py, or events/models.py.**

## 2. _execute_with_consensus() Method (pipeline.py L965-991)

```python
def _execute_with_consensus(self, call_kwargs, consensus_threshold, maximum_step_calls):
    from llm_pipeline.llm.executor import execute_llm_step

    results = []
    result_groups = []
    for attempt in range(maximum_step_calls):
        instruction = execute_llm_step(**call_kwargs)       # L971
        results.append(instruction)
        matched_group = None
        for group in result_groups:
            if self._instructions_match(instruction, group[0]):
                group.append(instruction)
                matched_group = group
                break
        if matched_group is None:
            result_groups.append([instruction])
            matched_group = result_groups[-1]
        if len(matched_group) >= consensus_threshold:       # L982
            logger.info(...)
            return matched_group[0]                         # L986 CONSENSUS REACHED

    logger.info(f"  [NO CONSENSUS] After {maximum_step_calls} attempts")  # L988
    largest_group = max(result_groups, key=len)
    logger.info(f"  -> Using most common response ({len(largest_group)} occurrences)")
    return largest_group[0]                                 # L991 CONSENSUS FAILED
```

### Current signature

```python
def _execute_with_consensus(self, call_kwargs, consensus_threshold, maximum_step_calls)
```

**Missing:** step_name parameter. Method cannot emit step-scoped events without it.

### Call site (pipeline.py L638-641)

```python
if use_consensus:
    instruction = self._execute_with_consensus(
        call_kwargs, consensus_threshold, maximum_step_calls
    )
```

`current_step_name` is available in execute() scope (set at L492: `current_step_name = step.step_name`).

## 3. Emission Point Mapping

### Point 1: ConsensusStarted (method entry, before loop)

- **Location:** After L968 (`result_groups = []`), before L970 (`for attempt in range(...)`)
- **Guard:** `if self._event_emitter:`
- **Fields:** `run_id=self.run_id, pipeline_name=self.pipeline_name, step_name=current_step_name, threshold=consensus_threshold, max_calls=maximum_step_calls`

### Point 2: ConsensusAttempt (per iteration, after grouping)

- **Location:** After L981 (`matched_group = result_groups[-1]`), before L982 (`if len(matched_group) >= consensus_threshold`)
- **Guard:** `if self._event_emitter:`
- **Fields:** `run_id=self.run_id, pipeline_name=self.pipeline_name, step_name=current_step_name, attempt=attempt + 1, group_count=len(result_groups)`
- **Note:** Fires AFTER execute_llm_step + group matching, so group_count reflects current state

### Point 3: ConsensusReached (threshold met)

- **Location:** After L983 (`logger.info(...)`), before L986 (`return matched_group[0]`)
- **Guard:** `if self._event_emitter:`
- **Fields:** `run_id=self.run_id, pipeline_name=self.pipeline_name, step_name=current_step_name, attempt=attempt + 1, threshold=consensus_threshold`

### Point 4: ConsensusFailed (loop exhausted)

- **Location:** After L988 (`logger.info(...)`), before L991 (`return largest_group[0]`)
- **Guard:** `if self._event_emitter:`
- **Fields:** `run_id=self.run_id, pipeline_name=self.pipeline_name, step_name=current_step_name, max_calls=maximum_step_calls, largest_group_size=len(largest_group)`

## 4. Emission Pattern Comparison (Task 12 vs Task 13)

| Aspect | Task 12 (retry/ratelimit) | Task 13 (consensus) |
|--------|--------------------------|---------------------|
| Emission location | GeminiProvider (gemini.py) | PipelineConfig (pipeline.py) |
| Emission method | `event_emitter.emit(...)` | `self._emit(...)` |
| Guard pattern | `if event_emitter:` | `if self._event_emitter:` |
| Event context source | params (run_id, pipeline_name, step_name) | self.run_id, self.pipeline_name, param (step_name) |
| Import location | Lazy inside method (`if event_emitter: from ...`) | Top of file (existing import block at L35-40) |
| Files modified | provider.py, executor.py, gemini.py | pipeline.py only |

Task 13 follows the **pipeline.py emission pattern** (used by PipelineStarted, StepSelecting, CacheLookup, LLMCallPrepared, etc.), NOT the task 12 provider-level pattern. This is correct because consensus logic lives in PipelineConfig.

## 5. Import Requirements

Current pipeline.py imports (L35-40):
```python
from llm_pipeline.events.types import (
    PipelineStarted, PipelineCompleted, PipelineError,
    StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted,
    CacheLookup, CacheHit, CacheMiss, CacheReconstruction,
    LLMCallPrepared,
)
```

**Need to add:** `ConsensusStarted, ConsensusAttempt, ConsensusReached, ConsensusFailed`

## 6. Call Chain for Consensus Path

```
execute() [pipeline.py]
  -> _execute_with_consensus() [pipeline.py]  <-- EMIT consensus events here
    -> execute_llm_step() [executor.py]       <-- emits LLMCallStarting/LLMCallCompleted
      -> provider.call_structured() [gemini.py] <-- emits LLMCallRetry/Failed/RateLimited
```

Each execute_llm_step call inside _execute_with_consensus loop already emits LLM-level events (via call_kwargs containing event_emitter). Consensus events wrap around these, providing higher-level visibility into the polling logic.

Event sequence for a 3-attempt consensus (threshold=2):
1. ConsensusStarted
2. [LLMCallStarting, LLMCallCompleted] (from executor)
3. ConsensusAttempt(attempt=1, group_count=1)
4. [LLMCallStarting, LLMCallCompleted]
5. ConsensusAttempt(attempt=2, group_count=1)  -- if matched first
6. ConsensusReached(attempt=2, threshold=2)

## 7. Signature Change

**Current:** `_execute_with_consensus(self, call_kwargs, consensus_threshold, maximum_step_calls)`

**Proposed:** `_execute_with_consensus(self, call_kwargs, consensus_threshold, maximum_step_calls, current_step_name)`

**Call site change:** Pass `current_step_name` at L639-641.

This is a private method (underscore prefix), no external API impact.

## 8. Files to Modify

| File | Changes |
|------|---------|
| `llm_pipeline/pipeline.py` | (1) Add 4 consensus event imports to L35-40. (2) Add `current_step_name` param to `_execute_with_consensus()` signature. (3) Emit 4 events at mapped points. (4) Update call site at L639-641 to pass `current_step_name`. |

| File | Status |
|------|--------|
| `llm_pipeline/events/types.py` | No changes (events already defined) |
| `llm_pipeline/events/__init__.py` | No changes (already exported) |
| `llm_pipeline/events/emitter.py` | No changes |
| `llm_pipeline/events/handlers.py` | No changes (CATEGORY_CONSENSUS mapped) |
| `llm_pipeline/events/models.py` | No changes |
| `llm_pipeline/llm/executor.py` | No changes |
| `llm_pipeline/llm/provider.py` | No changes |
| `llm_pipeline/llm/gemini.py` | No changes |

**New file:** `tests/events/test_consensus_events.py`

## 9. Test Strategy

Mock at `execute_llm_step` level (not Gemini API level like task 12) because consensus operates on parsed results, not raw API calls.

Test cases needed:
1. ConsensusStarted emitted at method entry with correct threshold/max_calls
2. ConsensusAttempt emitted per iteration with correct attempt/group_count
3. ConsensusReached emitted when threshold met with correct attempt/threshold
4. ConsensusFailed emitted when loop exhausted with correct max_calls/largest_group_size
5. Multi-group scenario (different results create multiple groups)
6. Zero overhead when event_emitter=None
7. Event field values verified (run_id, pipeline_name, step_name, timestamp)
8. Event ordering (Started -> Attempt x N -> Reached/Failed)

Mock pattern: `unittest.mock.patch('llm_pipeline.pipeline.execute_llm_step')` with side_effect returning Pydantic model instances. Use `_instructions_match` behavior to control group matching.

## 10. Upstream Task Context

**Task 9 (done):** Emit Step Lifecycle Events. Established the pipeline.py emission pattern (self._emit, if self._event_emitter guard, import at top of file). Task 13 follows this exact pattern.

## 11. Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Wrong emission point ordering | Low | Only 4 simple insertion points in straightforward loop |
| Missing step_name threading | Medium | Single param addition to private method + call site update |
| Test mock complexity | Low | execute_llm_step is clean mock boundary, returns Pydantic models |
| Import collision or circular | Low | Same import pattern as existing 13 event imports at L35-40 |
