# Research Summary

## Executive Summary

Validated research findings from step-1 (event system research) and step-2 (pipeline emission points) against actual source code. All 4 event types are correctly defined in `events/types.py` and emission point locations in `pipeline.py` are accurate. Two inconsistencies between research files resolved via CEO decisions: (1) `logged_keys` uses storage key semantics `[step.step_name]`, (2) ContextUpdated always emits, even on empty context merges. All findings validated -- ready for planning.

## Domain Findings

### Event Type Definitions
**Source:** research/step-1-event-system-research.md, events/types.py L426-538

All 4 event types verified as already defined with correct structure:
- `InstructionsStored(StepScopedEvent)` -- L426-432, field: `instruction_count: int`
- `InstructionsLogged(StepScopedEvent)` -- L435-445, field: `logged_keys: list[str]` (default_factory=list)
- `ContextUpdated(StepScopedEvent)` -- L448-459, fields: `new_keys: list[str]`, `context_snapshot: dict[str, Any]`
- `StateSaved(StepScopedEvent)` -- L530-538, fields: `step_number: int`, `input_hash: str`, `execution_time_ms: float`

All use `@dataclass(frozen=True, slots=True, kw_only=True)`. Categories: CATEGORY_INSTRUCTIONS_CONTEXT (first 3), CATEGORY_STATE (last). Already in `__all__` exports.

### Emission Point Accuracy
**Source:** research/step-2-pipeline-emission-points.md, pipeline.py

| Event | Research Location | Verified | Notes |
| --- | --- | --- | --- |
| InstructionsStored (cached) | After L573 | YES | `self._instructions[step.step_name] = instructions` |
| InstructionsStored (fresh) | After L669 | YES | Same pattern, instructions is always a list |
| InstructionsLogged (cached) | After L603 | YES | `step.log_instructions(instructions)` |
| InstructionsLogged (fresh) | After L707 | YES | Same pattern |
| ContextUpdated | After L372 in `_validate_and_merge_context` | YES | Called from both paths (L575, L671) |
| StateSaved | After L910 in `_save_step_state` | YES | Fresh path only (L704-706), correct |

### Import Requirements
**Source:** research/step-1-event-system-research.md, pipeline.py L35-42

Current import block at L35-42 does NOT include the 4 new types. Must add: `InstructionsStored, InstructionsLogged, ContextUpdated, StateSaved`. Verified extraction events (ExtractionStarting, etc.) are correctly imported in step.py instead, not pipeline.py.

### Data Availability at Emission Points
**Source:** research/step-2-pipeline-emission-points.md, pipeline.py

- InstructionsStored: `len(instructions)` always valid -- cached path returns list from `_load_from_cache` (L822-832), fresh path builds list via `.append()` (L667).
- ContextUpdated: `step.step_name` available via LLMStep property (step.py L252-262). `new_context.keys()` valid after dict coercion (L360-366). `dict(self._context)` shallow copy post-merge matches convention.
- StateSaved: All fields from method params (`step_number`, `input_hash`, `execution_time_ms`). `execution_time_ms` is int from L700-701 cast; event field is float; int is subtype of float in Python. None fallback to 0.0 is defensive for the default param.

### Emission Pattern Consistency
**Source:** pipeline.py (all existing emissions)

Established pattern: `if self._event_emitter:` guard before event construction. All 18 existing emissions in pipeline.py follow this. `_emit()` method (L215-222) has its own null check but the outer guard avoids constructing the event object when disabled. Research correctly identifies this convention.

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| What should `logged_keys` contain for InstructionsLogged? | Use storage key: `[step.step_name]`. Simpler, matches storage semantics. | Resolves step-1 vs step-2 disagreement. Implementation uses `[step.step_name]` at both cached (L603) and fresh (L707) paths. |
| Should ContextUpdated emit when new_context is empty? | Always emit, even when empty. Emit with `new_keys=[]` to signal validation happened. Useful for tracing. | Guard pattern is `if self._event_emitter:` only (no `new_context and` check). Emit at L372 unconditionally. |

## Assumptions Validated

- [x] All 4 event types already defined in events/types.py with correct fields and decorators
- [x] Emission point line numbers match actual source code
- [x] `instructions` is always a list at both InstructionsStored emission points
- [x] `step.step_name` property works on all LLMStep instances (verified step.py L252-262)
- [x] `_validate_and_merge_context` receives `step` (LLMStep instance) as first param -- has access to step_name
- [x] `_save_step_state` only called from fresh path (L704-706), not cached path
- [x] `execution_time_ms` param is int but float field works (int subtype of float in Python)
- [x] Shallow copy `dict(self._context)` matches existing convention for mutable container fields
- [x] Import block at L35-42 needs 4 additions; no other import changes needed
- [x] `log_instructions()` is a void method (step.py L317-319), no return value to capture

## Open Items

- context_snapshot captures post-merge state only. No pre-merge snapshot. Consecutive ContextUpdated events enable diffing at the UI level. Not blocking but worth noting for downstream task 53 test design.

## Recommendations for Planning

1. Implementation is straightforward: 6 emission blocks (~36 lines), 1 import addition. Low risk.
2. InstructionsLogged uses `logged_keys=[step.step_name]` at both emission points (CEO decision).
3. ContextUpdated uses `if self._event_emitter:` guard only -- no `new_context` check (CEO decision). Emits with `new_keys=[]` when context is empty.
4. Test strategy should cover both cached and fresh paths for InstructionsStored and InstructionsLogged (2 emission points each).
5. StateSaved tests need fresh path (use_cache=False or no cache), not cached path.
6. ContextUpdated test should verify `context_snapshot` reflects merged state (not pre-merge).
7. ContextUpdated test should also verify emission occurs with `new_keys=[]` on empty context merge.
