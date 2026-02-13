# Research Summary

## Executive Summary

Cross-referenced both research documents against actual codebase (pipeline.py, events/types.py, events/emitter.py, step.py). Research findings are largely accurate with two material gaps resolved via CEO Q&A: (1) PipelineError.traceback will include `traceback.format_exc()`, (2) step_name derived via local variable tracking from `step.step_name` each iteration. One semantic note documented: `steps_executed` includes skipped steps. All line references, type signatures, and injection points verified correct against current code.

## Domain Findings

### execute() Flow and Injection Points
**Source:** research/step-1-pipeline-execute-architecture.md

- execute() at pipeline.py:405-573. Signature verified: `execute(self, data, initial_context, use_cache=False, consensus_polling=None) -> PipelineConfig`
- No broad try/except wrapping the step loop (narrow AttributeError catch at line 484-488 for DataFrame preview only)
- Validation phase (lines 416-439): ValueError for missing provider, empty strategies, bad consensus config. These fire BEFORE pipeline "starts" and are NOT wrapped by PipelineError
- State init (lines 441-443): context copy, data/extractions reset
- Step loop (lines 447-571): strategy selection, step creation, skip check, cached vs fresh execution, post-step cleanup
- Cleanup (lines 572-573): `self._current_step = None; return self`

**Injection points verified:**
1. PipelineStarted: after line 443 (`self.extractions = {}`), before line 445 (`max_steps = ...`). Also capture `start_time = datetime.now(timezone.utc)` here
2. PipelineCompleted: after step loop ends, before line 572 (`self._current_step = None`)
3. PipelineError: try/except wrapping from `max_steps` through `return self`. except emits PipelineError then re-raises

### Event Type Signatures (Verified Against types.py)
**Source:** research/step-1-pipeline-execute-architecture.md, research/step-2-event-system-models.md

**PipelineStarted** (types.py:168-173):
- `@dataclass(frozen=True, slots=True)` -- NOT kw_only, positional args allowed
- Inherits PipelineEvent: `run_id: str`, `pipeline_name: str`, `timestamp: datetime` (default=utc_now), `event_type: str` (init=False)
- No additional instance fields. Has `EVENT_CATEGORY: ClassVar[str] = CATEGORY_PIPELINE_LIFECYCLE`
- Constructor: `PipelineStarted(run_id=self.run_id, pipeline_name=self.pipeline_name)`

**PipelineCompleted** (types.py:175-182):
- `@dataclass(frozen=True, slots=True, kw_only=True)` -- all keyword-only
- Additional: `execution_time_ms: float`, `steps_executed: int`
- Constructor: `PipelineCompleted(run_id=..., pipeline_name=..., execution_time_ms=..., steps_executed=...)`

**PipelineError** (types.py:185-197):
- `@dataclass(frozen=True, slots=True, kw_only=True)` -- all keyword-only
- Inherits StepScopedEvent -> PipelineEvent. Adds `step_name: str | None = None` from StepScopedEvent
- Additional: `error_type: str`, `error_message: str`, `traceback: str | None = None`
- Constructor: `PipelineError(run_id=..., pipeline_name=..., step_name=..., error_type=..., error_message=..., traceback=...)`

**Task spec deviations** (spec written before task 6 implemented types):
- `PipelineStarted.strategy_count`, `.use_cache`, `.use_consensus` -- DO NOT EXIST. PipelineStarted has no extra fields
- `PipelineCompleted.total_time_ms (int)` -- ACTUAL: `execution_time_ms (float)`. Renamed + retyped
- Resolution: types.py is source of truth, ignore task spec field names

### Emitter Wiring and Zero-Overhead Pattern
**Source:** research/step-2-event-system-models.md

- `self._event_emitter`: Optional[PipelineEventEmitter], set at `__init__` line 154, defaults to None
- `self._emit(event)`: lines 206-213, guards with `if self._event_emitter is not None`
- Call-site pattern: `if self._event_emitter:` guard BEFORE constructing event dataclass (skip frozen dataclass allocation when no emitter)
- Double-guard (call-site + `_emit` internal) is intentional safety net
- CompositeEmitter isolates per-handler errors via try/except + logger.exception. Event emission never throws to caller.

### Import Requirements
**Source:** research/step-1-pipeline-execute-architecture.md

- Currently in pipeline.py TYPE_CHECKING block (line 42): `from llm_pipeline.events.types import PipelineEvent`
- PipelineStarted, PipelineCompleted, PipelineError NOT currently imported
- Runtime construction requires real imports (not TYPE_CHECKING-only)
- Also need `import traceback` (not currently in pipeline.py) for `traceback.format_exc()`
- Recommended: inline import inside `if self._event_emitter:` guard for zero-overhead when no emitter configured
- `datetime` and `timezone` already imported at line 16 -- no additional import needed for timing

### Data Availability for Event Construction
**Source:** both research docs, verified against pipeline.py

| Field | Source | Available | Notes |
|-------|--------|-----------|-------|
| `self.run_id` | `__init__` line 190 | Always | UUID string |
| `self.pipeline_name` | property (line ~226) | Always | snake_case from class name |
| `self._event_emitter` | `__init__` line 154 | Always | None when disabled |
| `self._executed_steps` | set, accumulated in loop | After loop for count | Includes skipped steps |
| `self._current_step` | Type, set line 466, cleared line 572 | During loop | Class, NOT instance |
| `step.step_name` | property on LLMStep instance | During loop iteration only | snake_case |

### step_name Derivation for PipelineError (GAP RESOLVED)
**Source:** cross-reference of both docs against step.py:246-256

- `self._current_step` stores the step CLASS (Type), not instance (line 466: `self._current_step = step_class`)
- `step.step_name` is a PROPERTY on LLMStep instances that converts CamelCase -> snake_case (step.py:246-256)
- Research doc 1's `getattr(self._current_step, '__name__', None)` returns raw class name (e.g. "ConstraintExtractionStep"), NOT snake_case
- **Resolution (CEO decision):** track local `current_step_name: str | None = None`, update from `step.step_name` each iteration

### Timing Calculation
**Source:** research/step-2-event-system-models.md, verified against pipeline.py:490,557-558

- Per-step timing already uses `datetime.now(timezone.utc)` at line 490 and computes ms at 557-558 as `int(...)`
- Pipeline-level timing: `start_time = datetime.now(timezone.utc)` captured after state init, before step loop
- `execution_time_ms` for PipelineCompleted is `float` (per type annotation), NOT `int` -- use `(datetime.now(timezone.utc) - start_time).total_seconds() * 1000` without int() cast

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| Traceback in PipelineError: doc 1 says omit (None), doc 2 says include via traceback.format_exc(). Include or leave None? | INCLUDE via traceback.format_exc() on error path | Adds `import traceback` to pipeline.py. PipelineError construction includes `traceback=traceback.format_exc()` in except block. Valuable debug info on rare error path. |
| step_name derivation: self._current_step is Type (class), __name__ gives "ConstraintExtractionStep" not "constraint_extraction". Approach? | Track local `current_step_name: str \| None` variable, updated each iteration from step.step_name | Adds one local var assignment per loop iteration. Reliable snake_case name. No logic duplication from LLMStep.step_name property. |
| steps_executed semantics: len(self._executed_steps) includes skipped steps. Accept or track separately? | Accept as-is, document the semantics | No code change. steps_executed counts all steps entered (executed + skipped). Document in PipelineCompleted docstring or inline comment. |

## Assumptions Validated

- [x] execute() has no broad try/except -- verified at pipeline.py:405-573, only narrow AttributeError at 484-488
- [x] self._event_emitter stored at __init__ line 154, _emit() at lines 206-213 -- verified exact lines
- [x] PipelineStarted has no extra fields beyond PipelineEvent base -- verified types.py:168-173
- [x] PipelineCompleted.execution_time_ms is float, not int -- verified types.py:181
- [x] PipelineError inherits StepScopedEvent with step_name: str | None = None -- verified types.py:185-197, StepScopedEvent:149-162
- [x] PipelineError.traceback field exists with default None -- verified types.py:197
- [x] Validation errors (lines 416-439) should NOT be wrapped by PipelineError -- fires before pipeline "starts", logically correct
- [x] self._current_step is Type (class), not instance -- verified pipeline.py:465-466
- [x] self._executed_steps.add() called for both executed and skipped steps -- verified lines 470, 566
- [x] datetime and timezone already imported at pipeline.py:16 -- verified
- [x] CompositeEmitter isolates handler errors -- verified emitter.py:60-67
- [x] Thread safety: all 3 handlers (Logging, InMemory, SQLite) are safe for concurrent emit calls -- verified handlers.py

## Open Items

- Import strategy (inline vs top-of-method vs module-level) deferred to implementation. Recommendation: inline inside `if self._event_emitter:` guard for zero-overhead.
- Minor line number discrepancy in doc 1: PipelineError claimed "types.py:185-198" but actual ends at line 197. Non-blocking.

## Recommendations for Planning

1. Wrap from `max_steps = max(...)` through `return self` in try/except, placing PipelineStarted emission and start_time capture immediately before the try block (after line 443)
2. Add local `current_step_name: str | None = None` before the loop, update to `step.step_name` at line ~468 (after step instance creation, before skip check)
3. Use `traceback.format_exc()` in except block -- requires `import traceback` at top of pipeline.py or inline
4. Keep `raise` as final statement in except block to preserve existing exception propagation behavior
5. Guard ALL event constructions with `if self._event_emitter:` for zero-overhead when events disabled
6. Add brief inline comment on `steps_executed=len(self._executed_steps)` noting it includes skipped steps
7. Task 9 compatibility: the try/except scope wrapping the step loop is fully compatible with task 9's step-level event additions inside the loop body
