# Research Summary

## Executive Summary

Validated step-1 (caching logic) and step-2 (event system) research against actual source. Line numbers, field signatures, guard patterns, and data availability all confirmed accurate. Two architectural ambiguities resolved with CEO: CacheReconstruction emits from caller using `step.step_name` (not inside helper with CamelCase), and skips emission when `step_def.extractions` is empty. Testing infrastructure gap identified: existing conftest pipelines lack extractions, requiring new fixtures for CacheReconstruction tests.

## Domain Findings

### Emission Points Verified
**Source:** step-1-caching-logic-research.md, pipeline.py L540-592

All 4 emission points confirmed against current source (line numbers accurate):

| Event | Location | Guard | Verified |
|-------|----------|-------|----------|
| CacheLookup | L546 inside `if use_cache:`, before L547 `_find_cached_state` | `if self._event_emitter:` | Yes |
| CacheHit | L549 inside `if cached_state:`, before L550 logger | `if self._event_emitter:` | Yes |
| CacheMiss | L572 `else:` -> L573 `if use_cache:`, before L574 logger | `if self._event_emitter:` | Yes |
| CacheReconstruction | L566-568 (caller-side, after `_reconstruct_extractions_from_cache` returns) | `if self._event_emitter:` + `if step_def.extractions:` | Yes (CEO decision) |

### CacheReconstruction Caller-Side Emission (CEO Decision)
**Source:** step-1 Finding 1, step-2 Recommendation, CEO answer

Emit from `execute()` at L566-568 (after `_reconstruct_extractions_from_cache` returns), NOT inside the helper method. Caller has:
- `step.step_name` (snake_case, consistent with all other events)
- `reconstructed_count` (return value = instance_count)
- `len(step_def.extractions)` (= model_count, equivalent to `len(extraction_classes)` inside helper)

Guard: only emit when `step_def.extractions` is non-empty (CEO decision). This matches the helper's early-return at L766-767.

Proposed emission point (between L568 and L569):
```python
reconstructed_count = self._reconstruct_extractions_from_cache(
    cached_state, step_def
)
if self._event_emitter and step_def.extractions:
    self._emit(CacheReconstruction(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
        step_name=step.step_name,
        model_count=len(step_def.extractions),
        instance_count=reconstructed_count,
    ))
if reconstructed_count == 0 and step_def.extractions:
    ...
```

### Event Type Definitions Verified
**Source:** step-2-event-system-research.md, events/types.py L266-302

All 4 cache event types exist with correct signatures:
- All inherit `StepScopedEvent` (step_name: str | None) -> `PipelineEvent` (run_id, pipeline_name, timestamp)
- All use `kw_only=True`, `frozen=True`, `slots=True`
- All have `EVENT_CATEGORY = CATEGORY_CACHE`
- `resolve_event()` dt_fields includes `cached_at` (L137) -- deserialization handled
- Exported in `events/__init__.py` and `__all__`

### Import Requirements Verified
**Source:** step-1, pipeline.py L35-39

Current import block at L35-39 needs 4 additions:
```python
from llm_pipeline.events.types import (
    PipelineStarted, PipelineCompleted, PipelineError,
    StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted,
    LLMCallPrepared,
    CacheLookup, CacheHit, CacheMiss, CacheReconstruction,  # Task 10
)
```

### Data Availability Verified
**Source:** step-1, step-2 field availability table

| Field | Source | Verified |
|-------|--------|----------|
| input_hash | `_hash_step_inputs()` L543, returns 16-char hex str | Yes |
| cached_at | `cached_state.created_at` (state.py L94, datetime via `utc_now()`) | Yes |
| model_count | `len(step_def.extractions)` at caller scope | Yes |
| instance_count | return value of `_reconstruct_extractions_from_cache()` (int) | Yes |
| run_id | `self.run_id` | Yes |
| pipeline_name | `self.pipeline_name` | Yes |
| step_name | `step.step_name` (set at L491) | Yes |

### Guard Pattern Verified
**Source:** step-2 double-guard pattern, pipeline.py L212-219

All events structurally confined to `use_cache=True` paths:
- CacheLookup: inside `if use_cache:` (L546)
- CacheHit: inside `if cached_state:` (L549); `cached_state` only set when `use_cache=True`
- CacheMiss: inside `if use_cache:` (L573)
- CacheReconstruction: inside `if cached_state:` (L549); only reached when `use_cache=True`

No additional `use_cache` guard needed beyond structural position. Standard `if self._event_emitter:` guard prevents dataclass construction cost.

### Testing Infrastructure Gaps
**Source:** step-2, tests/events/conftest.py

Existing fixtures support CacheLookup/CacheMiss/CacheHit testing but NOT CacheReconstruction:
- `SuccessRegistry` has `models=[]` (L176) -- no extraction classes
- `_reconstruct_extractions_from_cache` returns 0 immediately when no extractions (L766-767)
- CacheReconstruction event would never fire with current test pipelines

Testing requirements by event:
- **CacheLookup + CacheMiss**: Single run with `use_cache=True` on fresh DB. Straightforward with existing fixtures.
- **CacheLookup + CacheHit**: Two-run pattern. First run saves state via `_save_step_state`. Second run with `use_cache=True` + same pipeline_name/step_name/input_hash finds cached state. `_find_cached_state` queries by pipeline_name + step_name + input_hash (not run_id), so cross-run hits work. Prompt version must match ("1.0" in seeded_session).
- **CacheReconstruction**: Needs new test pipeline with non-empty extractions. New conftest fixture required: a step_definition with `extractions=[...]`, a registry with models, and seeded PipelineRunInstance records.

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| CacheReconstruction step_name: task spec says `step_def.step_class.__name__` (CamelCase, inside helper) vs research recommendation of `step.step_name` (snake_case, from caller). Which? | Use caller-side: `step.step_name` (snake_case), emit from `execute()`. Consistent with tasks 9/11 pattern. Do NOT emit inside helper. | Deviates from original task spec emission point. All 4 events now emit from `execute()`. No signature change to `_reconstruct_extractions_from_cache`. |
| CacheReconstruction empty-extractions guard: emit with model_count=0/instance_count=0 or skip? | Skip emission when `step_def.extractions` is empty. Reduces noise. | Adds `if step_def.extractions:` guard to CacheReconstruction emission. Compound guard: `if self._event_emitter and step_def.extractions:`. |

## Assumptions Validated

- [x] All 4 cache event types defined in events/types.py with correct field signatures (L266-302)
- [x] All 4 inherit StepScopedEvent -> PipelineEvent with expected base fields
- [x] All 4 use kw_only=True, frozen=True, slots=True, CATEGORY_CACHE
- [x] cached_state.created_at is timezone-aware datetime (state.py L94, utc_now)
- [x] _hash_step_inputs returns 16-char hex string (L713-719)
- [x] _reconstruct_extractions_from_cache returns int total count (L792)
- [x] Zero existing cache event emissions in pipeline.py (clean slate)
- [x] use_cache=True structurally gates all cache event emission points
- [x] Cache events exported in events/__init__.py (L43-46, __all__ L111-114)
- [x] No cache event imports in pipeline.py yet (L35-39 has lifecycle + LLMCallPrepared only)
- [x] Double-guard pattern (outer if + _emit inner if) established by tasks 9/11
- [x] resolve_event dt_fields includes "cached_at" for CacheHit deserialization (L137)
- [x] len(step_def.extractions) at caller equals len(extraction_classes) inside helper
- [x] Event ordering: CacheLookup always precedes CacheHit/CacheMiss (structurally guaranteed)
- [x] CacheReconstruction only reachable from cache-hit path (inside if cached_state:)

## Open Items

- Test fixture for CacheReconstruction requires new pipeline with extraction classes, registry with models, and seeded PipelineRunInstance records. Existing conftest insufficient for this event.
- Two-run test pattern needed for CacheHit: first run populates state, second run detects cache hit. Prompt versions must match between runs.
- No upstream task 9 folder found (may have been cleaned up post-completion). No deviations detected from examining the code task 9 produced.

## Recommendations for Planning

1. CacheReconstruction emission goes at L568 (after `_reconstruct_extractions_from_cache` returns), guarded by `if self._event_emitter and step_def.extractions:`. Uses `step.step_name`, `len(step_def.extractions)`, and return value.
2. CacheLookup/CacheHit/CacheMiss emissions are straightforward insertions at documented locations with standard `if self._event_emitter:` guard.
3. Import block at L35-39 needs 4 new imports added to existing `from llm_pipeline.events.types import (...)`.
4. Test plan should include 3 test scenarios: cache-miss path (fresh DB + use_cache=True), cache-hit path (two-run pattern), and CacheReconstruction path (pipeline with extractions). Plus a no-emitter test (no events when event_emitter=None).
5. New conftest fixtures needed for CacheReconstruction: step with extractions, registry with models, seeded PipelineRunInstance records. Consider adding to existing conftest or creating cache-specific conftest.
6. Event ordering test should verify: CacheLookup always appears before CacheHit or CacheMiss in event list; CacheReconstruction appears after CacheHit and before StepCompleted.
