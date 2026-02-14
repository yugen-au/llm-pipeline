# Step 1: Caching Logic Research

## Executive Summary

Analyzed pipeline.py cache flow (L542-633) and _reconstruct_extractions_from_cache (L760-792). Identified 4 emission points for CacheLookup, CacheHit, CacheMiss, CacheReconstruction. All event types already defined in events/types.py (L266-302) with correct field signatures. Data available at all emission points. No imports of cache events in pipeline.py yet -- needs 4 new imports added to L35-38.

## Cache Flow in pipeline.py execute()

### Flow Overview (L542-633)

```
L543: input_hash = self._hash_step_inputs(step, step_num)   # ALWAYS computed
L545: cached_state = None
L546: if use_cache:
L547:     cached_state = self._find_cached_state(step, input_hash)
L549: if cached_state:                                        # CACHE HIT path
L550-570:   [load from cache, process, reconstruct extractions]
L572: else:                                                   # CACHE MISS or use_cache=False
L573:     if use_cache:
L574:         logger.info("  [FRESH] No cache found, running fresh")
L575-633:   [fresh LLM call path]
```

### Key Observation: else Block Dual Purpose
The `else` at L572 handles both:
- Cache miss (use_cache=True, no cached_state) -- CacheMiss should emit
- Cache disabled (use_cache=False, cached_state always None) -- NO event should emit

The existing guard at L573 (`if use_cache:`) already differentiates these cases. CacheMiss emission should go inside this guard.

## Emission Points

### 1. CacheLookup -- Before Cache Check

**Location:** Inside `if use_cache:` block, before L547 (`_find_cached_state` call)
**When:** Always when use_cache=True, before looking up cache
**Data available:**
- step_name: `step.step_name` (set at L491)
- input_hash: computed at L543
- run_id: `self.run_id`
- pipeline_name: `self.pipeline_name`

**Proposed code:**
```python
if use_cache:
    if self._event_emitter:
        self._emit(CacheLookup(
            run_id=self.run_id,
            pipeline_name=self.pipeline_name,
            step_name=step.step_name,
            input_hash=input_hash,
        ))
    cached_state = self._find_cached_state(step, input_hash)
```

### 2. CacheHit -- When Cached State Found

**Location:** Inside `if cached_state:` block at L549, before L550 logger.info
**When:** use_cache=True and _find_cached_state returns a match
**Data available:**
- step_name: `step.step_name`
- input_hash: from L543
- cached_at: `cached_state.created_at` (datetime field on PipelineStepState, L94 in state.py)

**Proposed code:**
```python
if cached_state:
    if self._event_emitter:
        self._emit(CacheHit(
            run_id=self.run_id,
            pipeline_name=self.pipeline_name,
            step_name=step.step_name,
            input_hash=input_hash,
            cached_at=cached_state.created_at,
        ))
    logger.info(...)
```

### 3. CacheMiss -- No Cache Found

**Location:** Inside `else:` block at L572, inside the existing `if use_cache:` guard at L573
**When:** use_cache=True but _find_cached_state returns None
**Data available:**
- step_name: `step.step_name`
- input_hash: from L543

**Proposed code:**
```python
else:
    if use_cache:
        if self._event_emitter:
            self._emit(CacheMiss(
                run_id=self.run_id,
                pipeline_name=self.pipeline_name,
                step_name=step.step_name,
                input_hash=input_hash,
            ))
        logger.info("  [FRESH] No cache found, running fresh")
```

### 4. CacheReconstruction -- After Reconstruction

**Location:** Inside `_reconstruct_extractions_from_cache()` at L760-792
**When:** Extraction classes exist and reconstruction completes (total computed at L787)
**Data available:**
- step_name: Two options (see Findings below)
- model_count: `len(extraction_classes)` (L765)
- instance_count: `total` (L787, computed at end)

**Proposed placement:** After L787 (`total` computed), before L788 return. Emit only when extraction_classes exist (L766 early-return handles empty case).

**Proposed code:**
```python
# After L787: total += len(instances)
if self._event_emitter:
    self._emit(CacheReconstruction(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
        step_name=step_def.step_class.__name__,  # or pass from caller
        model_count=len(extraction_classes),
        instance_count=total,
    ))
return total
```

## Event Type Definitions (events/types.py L266-302)

All 4 cache events already defined, verified field signatures:

| Event | Line | Fields (beyond StepScopedEvent) | kw_only | Category |
|-------|------|--------------------------------|---------|----------|
| CacheLookup | 266-273 | input_hash: str | Yes | CATEGORY_CACHE |
| CacheHit | 275-283 | input_hash: str, cached_at: datetime | Yes | CATEGORY_CACHE |
| CacheMiss | 285-292 | input_hash: str | Yes | CATEGORY_CACHE |
| CacheReconstruction | 294-302 | model_count: int, instance_count: int | Yes | CATEGORY_CACHE |

All inherit StepScopedEvent (step_name: str | None = None) -> PipelineEvent (run_id, pipeline_name, timestamp).

## Import Requirements

Current imports at L35-38:
```python
from llm_pipeline.events.types import (
    PipelineStarted, PipelineCompleted, PipelineError,
    StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted,
    LLMCallPrepared,
)
```

Need to add: `CacheLookup, CacheHit, CacheMiss, CacheReconstruction`

## Helper Methods

### _find_cached_state (L721-746)
- Queries PipelineStepState by pipeline_name, step_name, input_hash
- Optionally filters by prompt_version
- Returns most recent match or None
- Returns PipelineStepState instance (has created_at: datetime)

### _reconstruct_extractions_from_cache (L760-792)
- Receives cached_state (PipelineStepState) and step_def
- Iterates extraction_classes from step_def.extractions
- Queries PipelineRunInstance for cached run_id
- Reconstructs model instances from DB
- Returns total count (int)

### _hash_step_inputs (L713-719)
- Computes SHA256 hash of step.prepare_calls() or context
- Returns 16-char hex string
- Called BEFORE use_cache check (L543)

## Findings and Recommendations

### Finding 1: CacheReconstruction step_name Inconsistency
Task description specifies `step_name=step_def.step_class.__name__` which returns CamelCase (e.g. "SimpleStep"). All other events use `step.step_name` which returns snake_case (e.g. "simple"). Two options:

**Option A (task description):** `step_def.step_class.__name__` -- CamelCase, available inside method
**Option B (consistent):** Pass `step.step_name` from caller scope in execute() -- snake_case, consistent with all other events

Recommendation: Option B for consistency. Either pass step_name as parameter to _reconstruct_extractions_from_cache, or emit CacheReconstruction in execute() after the method returns using its return value. The caller at L566-567 has access to both `step.step_name` and the return value.

### Finding 2: Guard Pattern
All cache events naturally fire only when use_cache=True due to code structure:
- CacheLookup/CacheHit: inside `if use_cache:` / `if cached_state:` blocks
- CacheMiss: inside `if use_cache:` guard at L573
- CacheReconstruction: called only from cache-hit path (L566)

Standard `if self._event_emitter:` guard sufficient. No additional use_cache guard needed.

### Finding 3: No Existing Cache Event Emissions
Grep confirmed zero existing cache event emissions in pipeline.py. The events are only defined in types.py, exported in __init__.py, but never emitted.

### Finding 4: Partial Cache Path
At L569-571, if _reconstruct_extractions_from_cache returns 0 but step_def.extractions exist, extraction re-runs. CacheReconstruction emitting instance_count=0 correctly signals this partial cache scenario. The subsequent extraction will be tracked by extraction events (Task 14 scope).

### Finding 5: Event Ordering Within Cache-Hit Path
Expected sequence for cache-hit:
```
StepStarted -> CacheLookup -> CacheHit -> CacheReconstruction -> StepCompleted
```

Expected sequence for cache-miss:
```
StepStarted -> CacheLookup -> CacheMiss -> [LLMCallPrepared, ...] -> StepCompleted
```

Expected sequence for use_cache=False:
```
StepStarted -> [LLMCallPrepared, ...] -> StepCompleted
```
(No cache events emitted)

## Scope Boundaries

### In Scope (Task 10)
- CacheLookup, CacheHit, CacheMiss, CacheReconstruction event emissions
- Import additions to pipeline.py L35-38
- Guard pattern: `if self._event_emitter:` at each emission point

### Out of Scope
- LLM call events (Task 11 -- done)
- Consensus events (Task 13)
- Extraction/transformation events (Task 14)
- Instructions/context/state events (Task 15)

## Upstream Task 9 Deviations
None. Task 9 completed as planned per SUMMARY.md. All step lifecycle events properly emitted. Shared conftest.py created for tests. No deviations that affect Task 10.

## Test Infrastructure Available
- `tests/events/conftest.py` -- MockProvider, SuccessPipeline, SkipPipeline, seeded_session, in_memory_handler fixtures
- `InMemoryEventHandler.get_events()` returns list of dicts for assertion
- `InMemoryEventHandler.get_events_by_type()` for filtered queries
- Existing patterns in test_step_lifecycle_events.py for reference

## Verified Assumptions
- [x] All 4 cache event types defined in events/types.py with correct signatures
- [x] All 4 inherit StepScopedEvent -> PipelineEvent
- [x] All 4 use kw_only=True
- [x] All 4 have EVENT_CATEGORY = CATEGORY_CACHE
- [x] cached_state.created_at is datetime (state.py L94)
- [x] _hash_step_inputs returns str (16-char hex)
- [x] _reconstruct_extractions_from_cache returns int (total count)
- [x] Zero existing cache event emissions in pipeline.py
- [x] use_cache parameter controls cache flow at L546
- [x] Cache events already exported in events/__init__.py
- [x] No import of cache events in pipeline.py yet
- [x] Zero-overhead guard pattern established (if self._event_emitter:)
