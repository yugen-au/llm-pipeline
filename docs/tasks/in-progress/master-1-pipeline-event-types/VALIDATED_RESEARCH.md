# Research Summary

## Executive Summary

Validated research from step-1 (codebase analysis) and step-2 (event architecture). Both files are thorough and aligned with PRD Section 11 requirements. Found one critical bug (regex pattern) and five architectural assumptions requiring CEO input. All five questions answered in Q&A round 1. Research is now fully validated with CEO-confirmed decisions integrated.

31 concrete events across 9 categories, plus LLMCallResult (owned by llm/ package). Two-level hierarchy PipelineEvent -> StepScopedEvent with frozen=True, slots=True on all event dataclasses. StepSelecting now inherits StepScopedEvent with optional step_name.

## Domain Findings

### Codebase Pattern Alignment
**Source:** step-1-codebase-analysis.md, verified against live codebase via Serena

- `@dataclass` for data carriers: confirmed. `ArrayValidationConfig`, `ValidationContext`, `StepDefinition` all use stdlib `@dataclass` without frozen/slots. PRD explicitly says "event dataclasses" (FR-EV-002, DM-001).
- Import style: confirmed. TYPE_CHECKING guards, modern `str | None` in newer files, `__all__` at bottom.
- `__init_subclass__` pattern: confirmed in `PipelineStrategy` (strategy.py:154-196) and `LLMResultMixin` (step.py:192-206). Both use `**kwargs` passthrough.
- `utc_now()` helper: confirmed at state.py:18-20. Returns `datetime.now(timezone.utc)`.
- `__init__.py` exports: confirmed. Categorized `__all__` with section comments at llm_pipeline/__init__.py:24+.

### Event Inventory
**Source:** step-1-codebase-analysis.md Section 10, cross-referenced with PRD Section 11

31 concrete events across 9 categories. Matches PRD exactly:
- Pipeline Lifecycle: 3 (PipelineStarted, PipelineCompleted, PipelineError)
- Step Lifecycle: 5 (StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted)
- Cache: 4 (CacheLookup, CacheHit, CacheMiss, CacheReconstruction)
- LLM Calls: 6 (LLMCallPrepared, LLMCallStarting, LLMCallCompleted, LLMCallRetry, LLMCallFailed, LLMCallRateLimited)
- Consensus: 4 (ConsensusStarted, ConsensusAttempt, ConsensusReached, ConsensusFailed)
- Instructions & Context: 3 (InstructionsStored, InstructionsLogged, ContextUpdated)
- Transformation: 2 (TransformationStarting, TransformationCompleted)
- Extraction: 3 (ExtractionStarting, ExtractionCompleted, ExtractionError)
- State: 1 (StateSaved)

Plus LLMCallResult (separate dataclass in llm/result.py, re-exported from events/) = 32 total dataclasses.

### Architecture Decisions (CEO-Confirmed)
**Source:** step-2-event-architecture.md + CEO Q&A Round 1

9 decisions documented, 5 refined via CEO input:
1. `@dataclass(frozen=True, slots=True)` on ALL event dataclasses -- **CEO confirmed**
2. Two-level hierarchy: PipelineEvent -> StepScopedEvent. StepScopedEvent.step_name is `str | None` (was `str`) -- **CEO changed**: StepSelecting now inherits StepScopedEvent with step_name=None
3. Auto-derived event_type via `__init_subclass__` -- **must use two-pass regex** (bug fix)
4. Category string constants + EVENT_CATEGORY class var
5. Auto-populated `_EVENT_REGISTRY` for deserialization
6. `to_dict()` / `to_json()` on base (handles datetime)
7. Single `types.py` with section headers (~250-300 lines)
8. `execution_time_ms: float` for sub-ms precision -- **CEO confirmed** intentional divergence from state.py's `int`
9. Mutable containers (context_snapshot, validation_errors): **CEO confirmed** accept risk, document "don't mutate" convention. No deep-copy.
10. LLMCallResult lives in `llm/result.py`, re-exported from `events/__init__.py` -- **CEO confirmed** llm/ owns it

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| LLMCallResult location: events/result.py or llm/result.py? | llm/result.py, re-exported from events/ | LLM package owns the dataclass. events/ package has no result.py file. Import in events/__init__.py: `from llm_pipeline.llm.result import LLMCallResult`. No llm/ -> events/ dependency. |
| frozen=True + slots=True or match existing pattern (neither)? | Use BOTH frozen=True and slots=True | All 33 dataclasses (31 events + PipelineEvent base + StepScopedEvent base) use `@dataclass(frozen=True, slots=True)`. LLMCallResult in llm/ also uses both. Must use ClassVar for class-level attributes (EVENT_TYPE, EVENT_CATEGORY, _EVENT_REGISTRY). |
| Mutable container safety: deep-copy, accept risk, or immutable types? | Accept risk. Document convention. | Add docstring note on PipelineEvent base: "Event fields containing mutable containers (dict, list) must not be mutated after creation." No runtime enforcement. |
| execution_time_ms: float or int? | float (sub-ms precision) | Intentional type divergence from PipelineStepState.execution_time_ms (Optional[int]). Events capture higher precision timing; DB storage truncates to int. Document in field docstring. |
| StepSelecting: PipelineEvent child or StepScopedEvent with optional step_name? | StepScopedEvent with step_name: str \| None = None | StepScopedEvent.step_name changes from `str` to `str \| None`. StepSelecting inherits StepScopedEvent, sets step_name=None. All step events now filterable via isinstance(e, StepScopedEvent). Hierarchy is cleaner. PipelineError also benefits: its step_name was already `str \| None`. |

## Assumptions Validated

- [x] `@dataclass` is correct choice for events (PRD says "event dataclasses", codebase uses `@dataclass` for data carriers)
- [x] `@dataclass(frozen=True, slots=True)` on all event dataclasses (CEO confirmed)
- [x] `__init_subclass__` pattern exists in codebase (strategy.py, step.py) and is appropriate for auto-registration
- [x] `utc_now()` / `datetime.now(timezone.utc)` is the correct timestamp pattern (state.py:18-20)
- [x] 31 concrete events is the correct count (matches PRD Section 11 exactly)
- [x] Two-level hierarchy justified -- StepScopedEvent.step_name is `str | None` (CEO decision)
- [x] StepSelecting inherits StepScopedEvent with step_name=None (CEO changed from original research)
- [x] Single types.py file is appropriate (~250-300 lines, within readability threshold)
- [x] Modern type syntax (`str | None`, `list[str]`) matches newer codebase files
- [x] PipelineError.step_name is `str | None` (error can occur outside step scope)
- [x] event_type field must come after init=True fields (dataclass ordering constraint)
- [x] LLMCallResult owned by llm/ package at llm/result.py, re-exported from events/__init__.py (CEO confirmed)
- [x] execution_time_ms as float for events, intentional divergence from state.py int (CEO confirmed)
- [x] Mutable container fields: accept risk, document convention (CEO confirmed)
- [x] Two-pass regex required for event_type derivation (bug fix, not a CEO question)

## Open Items

- **Regex fix required in implementation**: Research skeleton uses single-pass regex. Implementation must use two-pass pattern from strategy.py:189-190: `re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', name)` then `re.sub(r'([a-z\d])([A-Z])', r'\1_\2', result).lower()`. Affects 6+ LLM-prefixed event type strings.
- **Prototype frozen+slots+__init_subclass__**: Should be done early in implementation to confirm no CPython edge cases. Low risk per analysis but worth a 10-line verification.
- **resolve_event() datetime handling**: Current hardcoded field names ('timestamp', 'cached_at') work for v1 but should be revisited if new datetime fields are added to events in future.

## Recommendations for Planning

1. **Fix the regex** to two-pass pattern from strategy.py:189-190 in the implementation plan. This is a correctness precondition.
2. **Create llm/result.py first** (LLMCallResult dataclass), since events/types.py and events/__init__.py depend on it for re-export.
3. **Prototype frozen+slots+__init_subclass__** as first implementation subtask to de-risk the pattern before writing 31 event classes.
4. **StepScopedEvent.step_name is now `str | None`** -- update research skeleton accordingly. This changes the intermediate hierarchy: StepSelecting moves from PipelineEvent child to StepScopedEvent child.
5. **Add "don't mutate" docstring** on PipelineEvent base class per CEO decision on mutable container safety.
6. **Document execution_time_ms type divergence** in field docstring: "float for sub-ms precision; PipelineStepState stores as int."
7. **Use `from __future__ import annotations`** (already in research skeleton) for forward reference safety.
8. **events/__init__.py re-exports**: LLMCallResult from llm/result.py, all event types from types.py, emitter protocol from emitter.py. No result.py in events/ package.
