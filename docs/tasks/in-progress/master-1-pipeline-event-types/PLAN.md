# PLANNING

## Summary
Create event system foundation with 31 concrete event dataclasses across 9 categories plus two base classes (PipelineEvent, StepScopedEvent). Implement automatic event type registration via `__init_subclass__`, frozen+slots dataclass pattern, and JSON serialization. Create llm/result.py for LLMCallResult, then events/types.py with full event hierarchy, then events/__init__.py for re-exports.

## Plugin & Agents
**Plugin:** python-development
**Subagents:** code-generator, refactorer
**Skills:** none

## Phases
1. **Prototype & Foundation** - Create LLMCallResult in llm/result.py, prototype frozen+slots+__init_subclass__ pattern
2. **Event Hierarchy** - Implement PipelineEvent base and StepScopedEvent intermediate with auto-registration
3. **Event Categories** - Define 31 concrete event dataclasses across 9 categories with section headers
4. **Exports & Integration** - Create events/__init__.py with categorized exports

## Architecture Decisions

### Dataclass Pattern: frozen=True, slots=True
**Choice:** Use `@dataclass(frozen=True, slots=True)` on all 33 dataclasses (PipelineEvent, StepScopedEvent, 31 events)
**Rationale:** CEO-confirmed decision. Frozen ensures immutability (event integrity), slots reduces memory overhead (33 classes). Mutable container fields (context_snapshot, validation_errors) accept mutation risk with docstring convention. ClassVar required for class-level attributes (_EVENT_REGISTRY, EVENT_TYPE, EVENT_CATEGORY).
**Alternatives:** No frozen/slots to match existing codebase patterns (ArrayValidationConfig, ValidationContext) - rejected for event-specific immutability needs

### Auto-Registration via __init_subclass__
**Choice:** Implement `PipelineEvent.__init_subclass__` to auto-populate `_EVENT_REGISTRY` and derive `event_type` from class name
**Rationale:** Pattern exists in codebase (PipelineStrategy.strategy.py:155, LLMResultMixin.step.py:192). Eliminates manual registry maintenance. Two-pass regex required: `re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', name)` then `re.sub(r'([a-z\d])([A-Z])', r'\1_\2', result).lower()` from strategy.py:189-190 to correctly convert "LLMCallStarting" -> "llm_call_starting".
**Alternatives:** Manual EVENT_TYPE constants - rejected (error-prone with 31 events)

### Two-Level Hierarchy with Optional step_name
**Choice:** PipelineEvent -> StepScopedEvent (step_name: str | None) -> step-specific events. StepSelecting inherits StepScopedEvent with step_name=None.
**Rationale:** CEO-changed from original research. StepScopedEvent.step_name changed from `str` to `str | None` to accommodate StepSelecting (before step chosen) and PipelineError (can occur outside step scope). All step events now filterable via `isinstance(e, StepScopedEvent)`. Cleaner hierarchy than having StepSelecting as direct PipelineEvent child.
**Alternatives:** Flat hierarchy with PipelineEvent only - rejected (loses type-level filtering for step events)

### Single types.py File
**Choice:** One `llm_pipeline/events/types.py` with section headers for 9 categories (~250-300 lines)
**Rationale:** Research estimates 250-300 lines. Within readability threshold. Simpler imports than category/ subdirectory. Matches codebase pattern (strategy.py is 400+ lines with multiple strategies).
**Alternatives:** events/categories/ subdirectory - rejected (overkill for v1, can refactor if grows beyond 500 lines)

### LLMCallResult Ownership
**Choice:** LLMCallResult dataclass in `llm/result.py`, re-exported from `events/__init__.py`
**Rationale:** CEO-confirmed. LLM package owns the dataclass (LLM call results are LLM domain, not event domain). No llm/ -> events/ dependency created. events/ imports from llm/ for convenience re-export.
**Alternatives:** events/result.py - rejected (wrong package ownership)

### execution_time_ms Type Precision
**Choice:** `execution_time_ms: float` on all events (not int)
**Rationale:** CEO-confirmed. Events capture sub-millisecond precision for timing analysis. Intentional divergence from PipelineStepState.execution_time_ms (Optional[int]) which truncates for DB storage. Document in field docstring: "float for sub-ms precision; PipelineStepState stores as int."
**Alternatives:** int to match state.py - rejected (loses timing precision for event stream analysis)

### Mutable Container Safety
**Choice:** Accept mutation risk for mutable fields (context_snapshot: dict, validation_errors: list[str]). Document "don't mutate" convention in PipelineEvent docstring.
**Rationale:** CEO-confirmed. No runtime enforcement (deep-copy rejected for performance, immutable types rejected for ergonomics). Convention documented: "Event fields containing mutable containers (dict, list) must not be mutated after creation."
**Alternatives:** Deep-copy on construction, use tuple/MappingProxyType - both rejected

### Timestamp Helper
**Choice:** Use existing `utc_now()` from state.py:18-20 for timestamp defaults
**Rationale:** Pattern already exists: `datetime.now(timezone.utc)`. Import from llm_pipeline.state. Consistent with codebase.
**Alternatives:** Inline `datetime.now(timezone.utc)` - rejected (DRY violation)

### Category Constants
**Choice:** Define CATEGORY_* string constants (CATEGORY_PIPELINE_LIFECYCLE, etc.) and EVENT_CATEGORY ClassVar on each event
**Rationale:** Enables category-level filtering without isinstance checks. Constants are DRY (reused in EVENT_CATEGORY assignments). Matches codebase pattern (PipelineStrategy.NAME/DISPLAY_NAME).
**Alternatives:** Magic strings in EVENT_CATEGORY - rejected (typo-prone)

## Implementation Steps

### Step 1: Create LLMCallResult in llm/result.py
**Agent:** python-development:code-generator
**Skills:** none
**Context7 Docs:** /llmstxt/pydantic_dev_llms-full_txt
**Group:** A

1. Create `llm_pipeline/llm/result.py` with LLMCallResult dataclass
2. Use `@dataclass(frozen=True, slots=True)` decorator
3. Add fields from PRD: model_name, prompt, response, token_usage, metadata
4. Add `__post_init__` validation if needed (prompt/response non-empty)
5. Import typing annotations with `from __future__ import annotations`

### Step 2: Prototype frozen+slots+__init_subclass__
**Agent:** python-development:code-generator
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Create minimal test in `llm_pipeline/events/types.py` (will be replaced in Step 4)
2. Define PipelineEvent stub with `@dataclass(frozen=True, slots=True)`
3. Add `_EVENT_REGISTRY: ClassVar[dict[str, type[PipelineEvent]]] = {}`
4. Implement `__init_subclass__` with two-pass regex for event_type derivation
5. Add one concrete event subclass (e.g., PipelineStarted) to verify pattern works
6. Test: instantiate event, verify frozen/slots behavior, check registry populated

### Step 3: Implement PipelineEvent Base
**Agent:** python-development:code-generator
**Skills:** none
**Context7 Docs:** /llmstxt/pydantic_dev_llms-full_txt
**Group:** B

1. Replace stub from Step 2 with full PipelineEvent implementation
2. Add base fields: event_type (str, init=False), run_id (str), timestamp (datetime with utc_now() default), pipeline_name (str)
3. Import utc_now from llm_pipeline.state
4. Add docstring with mutable container warning
5. Implement `__init_subclass__` with two-pass regex (strategy.py:189-190 pattern)
6. Add ClassVar: `_EVENT_REGISTRY: ClassVar[dict[str, type[PipelineEvent]]] = {}`
7. Implement `to_dict()` method handling datetime serialization (isoformat())
8. Implement `to_json()` method using json.dumps(to_dict())
9. Implement class method `resolve_event(event_type: str, data: dict) -> PipelineEvent` for deserialization

### Step 4: Implement StepScopedEvent Intermediate
**Agent:** python-development:code-generator
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. Add StepScopedEvent(PipelineEvent) in types.py below PipelineEvent
2. Add field: `step_name: str | None` (changed from str to accommodate StepSelecting)
3. Keep `@dataclass(frozen=True, slots=True)` decorator
4. Add docstring explaining step_name=None case (StepSelecting, errors outside step scope)

### Step 5: Define Pipeline Lifecycle Events (3)
**Agent:** python-development:code-generator
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. Add section header comment in types.py: "# Pipeline Lifecycle Events"
2. Define CATEGORY_PIPELINE_LIFECYCLE constant
3. Implement PipelineStarted(PipelineEvent) with EVENT_CATEGORY ClassVar
4. Implement PipelineCompleted(PipelineEvent) with execution_time_ms: float
5. Implement PipelineError(StepScopedEvent) with error_type, error_message, traceback, step_name: str | None

### Step 6: Define Step Lifecycle Events (5)
**Agent:** python-development:code-generator
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. Add section header comment: "# Step Lifecycle Events"
2. Define CATEGORY_STEP_LIFECYCLE constant
3. Implement StepSelecting(StepScopedEvent) with step_name=None, candidate_steps: list[str]
4. Implement StepSelected(StepScopedEvent) with selection_reason: str
5. Implement StepSkipped(StepScopedEvent) with skip_reason: str
6. Implement StepStarted(StepScopedEvent)
7. Implement StepCompleted(StepScopedEvent) with execution_time_ms: float, result_summary: str

### Step 7: Define Cache Events (4)
**Agent:** python-development:code-generator
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. Add section header comment: "# Cache Events"
2. Define CATEGORY_CACHE constant
3. Implement CacheLookup(StepScopedEvent) with cache_key: str
4. Implement CacheHit(StepScopedEvent) with cache_key, cached_at: datetime
5. Implement CacheMiss(StepScopedEvent) with cache_key: str
6. Implement CacheReconstruction(StepScopedEvent) with original_step_name: str, reconstruction_reason: str

### Step 8: Define LLM Call Events (6)
**Agent:** python-development:code-generator
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. Add section header comment: "# LLM Call Events"
2. Define CATEGORY_LLM_CALL constant
3. Implement LLMCallPrepared(StepScopedEvent) with model_name, prompt_length: int
4. Implement LLMCallStarting(StepScopedEvent) with model_name, attempt_number: int
5. Implement LLMCallCompleted(StepScopedEvent) with model_name, execution_time_ms: float, token_usage: dict
6. Implement LLMCallRetry(StepScopedEvent) with attempt_number: int, retry_reason: str, wait_time_ms: float
7. Implement LLMCallFailed(StepScopedEvent) with error_type, error_message
8. Implement LLMCallRateLimited(StepScopedEvent) with retry_after_ms: float

### Step 9: Define Consensus Events (4)
**Agent:** python-development:code-generator
**Skills:** none
**Context7 Docs:** -
**Group:** D

1. Add section header comment: "# Consensus Events"
2. Define CATEGORY_CONSENSUS constant
3. Implement ConsensusStarted(StepScopedEvent) with num_calls: int
4. Implement ConsensusAttempt(StepScopedEvent) with attempt_number: int, responses: list[str]
5. Implement ConsensusReached(StepScopedEvent) with final_response: str, num_attempts: int
6. Implement ConsensusFailed(StepScopedEvent) with failure_reason: str

### Step 10: Define Instructions & Context Events (3)
**Agent:** python-development:code-generator
**Skills:** none
**Context7 Docs:** -
**Group:** D

1. Add section header comment: "# Instructions & Context Events"
2. Define CATEGORY_INSTRUCTIONS_CONTEXT constant
3. Implement InstructionsStored(StepScopedEvent) with instruction_key: str, instruction_length: int
4. Implement InstructionsLogged(StepScopedEvent) with logged_keys: list[str]
5. Implement ContextUpdated(StepScopedEvent) with context_snapshot: dict

### Step 11: Define Transformation Events (2)
**Agent:** python-development:code-generator
**Skills:** none
**Context7 Docs:** -
**Group:** D

1. Add section header comment: "# Transformation Events"
2. Define CATEGORY_TRANSFORMATION constant
3. Implement TransformationStarting(StepScopedEvent) with transformer_name: str
4. Implement TransformationCompleted(StepScopedEvent) with transformer_name: str, execution_time_ms: float

### Step 12: Define Extraction Events (3)
**Agent:** python-development:code-generator
**Skills:** none
**Context7 Docs:** -
**Group:** D

1. Add section header comment: "# Extraction Events"
2. Define CATEGORY_EXTRACTION constant
3. Implement ExtractionStarting(StepScopedEvent) with extractor_name: str, target_schema: str
4. Implement ExtractionCompleted(StepScopedEvent) with extractor_name: str, execution_time_ms: float, extracted_count: int
5. Implement ExtractionError(StepScopedEvent) with error_type, error_message, validation_errors: list[str]

### Step 13: Define State Event (1)
**Agent:** python-development:code-generator
**Skills:** none
**Context7 Docs:** -
**Group:** D

1. Add section header comment: "# State Events"
2. Define CATEGORY_STATE constant
3. Implement StateSaved(StepScopedEvent) with state_id: int, db_commit_time_ms: float

### Step 14: Create events/__init__.py
**Agent:** python-development:code-generator
**Skills:** none
**Context7 Docs:** -
**Group:** E

1. Create `llm_pipeline/events/__init__.py`
2. Import LLMCallResult from llm_pipeline.llm.result
3. Import all events from types (PipelineEvent, StepScopedEvent, 31 concrete events)
4. Import category constants (CATEGORY_*)
5. Create categorized `__all__` list with section comments: Base Classes, LLM Results, Pipeline Lifecycle, Step Lifecycle, Cache, LLM Call, Consensus, Instructions & Context, Transformation, Extraction, State
6. Follow codebase pattern from llm_pipeline/__init__.py:24+

### Step 15: Update llm/__init__.py
**Agent:** python-development:refactorer
**Skills:** none
**Context7 Docs:** -
**Group:** E

1. Add LLMCallResult to llm_pipeline/llm/__init__.py exports
2. Import from llm_pipeline.llm.result
3. Add to `__all__` list in LLM Results section

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| frozen+slots+__init_subclass__ CPython edge case | High | Prototype in Step 2 before implementing 31 events. If incompatibility found, fall back to manual event_type assignment. |
| Two-pass regex incorrect for LLM-prefixed events | Medium | Use exact pattern from strategy.py:189-190. Add comment referencing strategy.py. Test with "LLMCallStarting" -> "llm_call_starting". |
| Mutable field mutation breaks event integrity | Low | Document convention in PipelineEvent docstring. Accept risk per CEO decision. Consider linter rule in future. |
| datetime serialization edge cases in resolve_event() | Low | Hardcoded field names ('timestamp', 'cached_at') work for v1. Add TODO comment to revisit if new datetime fields added. |
| Import cycle llm/ <-> events/ | Medium | LLMCallResult in llm/result.py. events/__init__.py imports from llm/ (one-way dependency). No llm/ -> events/ imports. |

## Success Criteria

- [ ] LLMCallResult dataclass exists in llm_pipeline/llm/result.py with frozen=True, slots=True
- [ ] PipelineEvent base with _EVENT_REGISTRY, __init_subclass__, to_dict(), to_json(), resolve_event()
- [ ] StepScopedEvent intermediate with step_name: str | None
- [ ] 31 concrete event dataclasses across 9 categories in types.py
- [ ] All events use @dataclass(frozen=True, slots=True)
- [ ] Two-pass regex in __init_subclass__ (strategy.py:189-190 pattern)
- [ ] StepSelecting inherits StepScopedEvent with step_name=None
- [ ] execution_time_ms is float (not int) with docstring explaining divergence
- [ ] Mutable container warning in PipelineEvent docstring
- [ ] events/__init__.py exports all events, LLMCallResult, category constants
- [ ] llm/__init__.py exports LLMCallResult
- [ ] Category constants defined (CATEGORY_PIPELINE_LIFECYCLE, etc.)
- [ ] EVENT_CATEGORY ClassVar on all events
- [ ] utc_now() imported from llm_pipeline.state for timestamp defaults
- [ ] Section headers in types.py for 9 categories

## Phase Recommendation

**Risk Level:** low
**Reasoning:** Pure data structure definition. No business logic, DB migrations, or external integrations. Prototype in Step 2 de-risks frozen+slots+__init_subclass__ pattern. LLMCallResult in llm/ prevents import cycles. Two-pass regex pattern proven in strategy.py.
**Suggested Exclusions:** testing, review
