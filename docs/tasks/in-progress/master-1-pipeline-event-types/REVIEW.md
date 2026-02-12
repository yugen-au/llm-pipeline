# Architecture Review

## Overall Assessment
**Status:** complete

Implementation is solid. 31 concrete events across 9 categories, frozen+slots pattern works correctly, auto-registration via `__init_subclass__` verified, serialization round-trips cleanly, no import cycles. All 32 existing tests pass. Field names deviate from PLAN.md but step-4 documents this as intentional (task spec over plan). The `from __future__ import annotations` removal and explicit `super(PipelineEvent, cls)` workaround for CPython slots issue is well-reasoned and documented.

## Project Guidelines Compliance
**CLAUDE.md:** `C:\Users\SamSG\Documents\claude_projects\llm-pipeline\.claude\CLAUDE.md`
| Guideline | Status | Notes |
| --- | --- | --- |
| Python 3.11+ | pass | Uses `str \| None` union syntax (3.10+), `slots=True` (3.10+) |
| Pydantic v2 | pass | Not applicable -- stdlib dataclasses used per PRD "event dataclasses" |
| pytest testing | pass | 32 tests pass, no regressions |
| Hatchling build | pass | No build changes needed for pure Python modules |

## Issues Found
### Critical
None

### High
None

### Medium
#### LLMCallResult fields diverge significantly from PLAN.md without documented decision
**Step:** 1
**Details:** PLAN Step 1 specifies fields `model_name, prompt, response, token_usage, metadata`. Implementation has `parsed, raw_response, model_name, attempt_count, validation_errors`. step-1 implementation doc does not mention this as a decision or explain the rationale. step-4 documents field divergences for later events ("Field names follow task spec over PLAN.md") but step-1 has no equivalent note. The fields themselves are reasonable (better aligned with actual LLM call output patterns), but the undocumented deviation from plan is a process concern.

#### Numerous field-level deviations from PLAN.md across events
**Step:** 3, 4
**Details:** Many events have different field names/structures vs PLAN.md: CacheLookup uses `input_hash` not `cache_key`, CacheReconstruction uses `model_count/instance_count` not `original_step_name/reconstruction_reason`, LLMCallStarting uses `call_index/rendered_*` not `model_name/attempt_number`, LLMCallCompleted drops `execution_time_ms/token_usage` adds `call_index/raw_response/parsed_result/attempt_count/validation_errors`, etc. Step-4 doc acknowledges "Field names follow task spec over PLAN.md" which is valid, but the scope of changes is large enough that PLAN.md should be updated to remain useful as a reference doc.

#### `_EVENT_REGISTRY` and `_derive_event_type` exported in `__all__`
**Step:** 5
**Details:** Both `_EVENT_REGISTRY` and `_derive_event_type` are underscore-prefixed (private by Python convention) but exported in `events/__init__.py`'s `__all__`. This sends mixed signals -- either make them public (drop underscore) or remove from `__all__` and let consumers access via `PipelineEvent._EVENT_REGISTRY`. `resolve_event` is already a clean public alias for registry access.

### Low
#### `PipelineCompleted.steps_executed` field not in PLAN
**Step:** 3
**Details:** `PipelineCompleted` has `steps_executed: int` field not mentioned in PLAN Step 5. Useful field, but undocumented addition.

#### `StepSelecting` fields differ from PLAN
**Step:** 3
**Details:** PLAN Step 6 says `candidate_steps: list[str]`. Implementation has `step_index: int` and `strategy_count: int`. Different information model -- index+count vs list of names. The implementation aligns better with how the pipeline actually selects steps (by index into strategy list).

#### `InstructionsLogged` has no fields beyond inherited ones
**Step:** 4
**Details:** PLAN Step 10 specifies `logged_keys: list[str]` for `InstructionsLogged`. Implementation has no custom fields -- just inherits from `StepScopedEvent`. This means the event carries no information beyond "instructions were logged for this step" with no indication of which instructions. May limit observability value.

#### `ExtractionError` missing `validation_errors` and `error_type` from PLAN
**Step:** 4
**Details:** PLAN Step 12 specifies `error_type, error_message, validation_errors: list[str]`. Implementation has `extraction_class, error_message` only. Missing `error_type` means consumers can't distinguish exception classes. Missing `validation_errors` means Pydantic validation details are lost.

## Review Checklist
[x] Architecture patterns followed - frozen+slots, __init_subclass__ auto-registration, two-pass regex, ClassVar for class-level attrs
[x] Code quality and maintainability - clear section headers, docstrings on all classes, mutable container warnings
[x] Error handling present - resolve_event raises ValueError for unknown event types
[x] No hardcoded values - category constants used, no magic strings
[x] Project conventions followed - __all__ at bottom, categorized exports, snake_case, type hints
[x] Security considerations - N/A (pure data structures, no I/O)
[x] Properly scoped (DRY, YAGNI, no over-engineering) - single types.py file, no premature abstraction

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| llm_pipeline/llm/result.py | pass | Clean frozen+slots dataclass, mutable container warning |
| llm_pipeline/events/types.py | pass | 577 lines, well-structured with section headers. All 31 events verified frozen+slots+EVENT_CATEGORY. |
| llm_pipeline/events/__init__.py | pass | Categorized re-exports, resolve_event alias, 46-entry __all__ |
| llm_pipeline/llm/__init__.py | pass | LLMCallResult added to exports |

## New Issues Introduced
- None detected. No import cycles, no regressions in existing tests, no breaking changes to existing API.

## Recommendation
**Decision:** APPROVE

Core architecture is sound. The frozen+slots+__init_subclass__ pattern is correctly implemented with proper CPython workarounds documented. All 31 events register, serialize, and deserialize correctly. Import dependency is one-way (events -> llm, never reverse). Field-level deviations from PLAN.md are the main concern but step-4 explicitly documents the rationale ("task spec over PLAN.md"). The medium-severity items (private symbols in __all__, undocumented LLMCallResult field changes) are housekeeping issues that don't affect correctness or runtime behavior.

---

# Architecture Re-Review (Fix Verification)

## Overall Assessment
**Status:** complete

All 3 MEDIUM and 4 LOW issues from initial review verified resolved. No regressions -- 32 tests pass, 31 events register, serialization roundtrips clean.

## Project Guidelines Compliance
**CLAUDE.md:** `C:\Users\SamSG\Documents\claude_projects\llm-pipeline\.claude\CLAUDE.md`
| Guideline | Status | Notes |
| --- | --- | --- |
| Python 3.11+ | pass | No changes to runtime code patterns |
| Pydantic v2 | pass | N/A |
| pytest testing | pass | 32 tests pass, 0 failures |
| Hatchling build | pass | No build changes |

## Issues Found
### Critical
None

### High
None

### Medium
None

### Low
None

## Previous Issue Resolution

### MEDIUM - Step 1: LLMCallResult field divergence (RESOLVED)
**Fix:** Added "LLMCallResult field definitions" decision to `implementation/step-1-llmcallresult-prototype.md` under "Review Fix Iteration 0". Documents PRD as source of truth over PLAN.md placeholder fields.
**Verification:** Decision block present with choice, rationale, and PS-2 reference.

### MEDIUM - Step 3, 4: Field-level deviations from PLAN.md (RESOLVED - accepted)
**Fix:** Already documented in step-4 implementation doc ("Field names follow task spec over PLAN.md"). Step-1 now also documents its divergence. Combined, all field deviations are traceable to PRD spec decisions.
**Verification:** No action needed beyond step-1 fix above.

### MEDIUM - Step 5: _EVENT_REGISTRY and _derive_event_type in __all__ (RESOLVED)
**Fix:** Removed from `__all__` in both `events/types.py` and `events/__init__.py`. Comment added: "Helpers (public only; _EVENT_REGISTRY and _derive_event_type are internal)".
**Verification:** Programmatic check confirms neither symbol in either module's `__all__`. Both still importable directly for internal use. `resolve_event` remains public API for registry access.

### LOW - Step 3: PipelineCompleted.steps_executed not in PLAN (RESOLVED - accepted)
**Fix:** Covered by step-4's "task spec over PLAN.md" rationale. Useful field, no action needed.
**Verification:** Field present and functional.

### LOW - Step 3: StepSelecting fields differ from PLAN (RESOLVED - accepted)
**Fix:** Covered by same rationale. Implementation aligns with actual step selection mechanics.
**Verification:** Fields present and functional.

### LOW - Step 4: InstructionsLogged missing logged_keys (RESOLVED)
**Fix:** Added `logged_keys: list[str] = field(default_factory=list)` field with docstring warning about mutable container convention.
**Verification:** Programmatic check confirms field exists with type `list[str]`. Serialization roundtrip verified -- `to_dict()` includes `logged_keys` array.

### LOW - Step 4: ExtractionError missing error_type and validation_errors (RESOLVED)
**Fix:** Added `error_type: str` and `validation_errors: list[str] = field(default_factory=list)` fields. Docstring added documenting Pydantic validation detail capture and mutable container convention.
**Verification:** Programmatic check confirms both fields present. Full field set: `extraction_class, error_type, error_message, validation_errors`. Serialization roundtrip verified.

## Review Checklist
[x] Architecture patterns followed - no regression in frozen+slots+__init_subclass__ pattern
[x] Code quality and maintainability - new fields have docstrings, mutable container warnings added
[x] Error handling present - unchanged, resolve_event still raises ValueError
[x] No hardcoded values - unchanged
[x] Project conventions followed - __all__ now correctly excludes private symbols
[x] Security considerations - N/A
[x] Properly scoped (DRY, YAGNI, no over-engineering) - fixes are minimal and targeted

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| llm_pipeline/events/types.py | pass | InstructionsLogged now has logged_keys, ExtractionError has error_type+validation_errors, _EVENT_REGISTRY/_derive_event_type removed from __all__ |
| llm_pipeline/events/__init__.py | pass | _EVENT_REGISTRY/_derive_event_type removed from __all__, still imported for internal use |
| llm_pipeline/llm/result.py | pass | Unchanged, verified still correct |
| implementation/step-1-llmcallresult-prototype.md | pass | New "LLMCallResult field definitions" decision documenting PRD over PLAN divergence |

## New Issues Introduced
- None detected

## Recommendation
**Decision:** APPROVE

All 7 issues from initial review resolved. Code fixes (InstructionsLogged, ExtractionError, __all__ cleanup) are minimal and correct. Documentation fix (step-1 rationale) properly traces field decisions to PRD. No regressions in tests or runtime behavior. 31 events register correctly, serialization roundtrips verified programmatically.
