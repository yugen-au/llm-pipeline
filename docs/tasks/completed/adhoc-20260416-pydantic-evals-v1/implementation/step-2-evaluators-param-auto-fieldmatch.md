# IMPLEMENTATION - STEP 2: EVALUATORS= PARAM + AUTO FIELDMATCH
**Status:** completed

## Summary
Added `evaluators=` parameter to `@step_definition` decorator and `StepDefinition` dataclass, following the same pattern as `review=`. Created `FieldMatchEvaluator` callable class and `build_auto_evaluators()` factory in `llm_pipeline/evals/evaluators.py`.

## Files
**Created:** `llm_pipeline/evals/evaluators.py`, `tests/test_evaluators.py`
**Modified:** `llm_pipeline/strategy.py`, `llm_pipeline/step.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/strategy.py`
Added `evaluators` field to `StepDefinition` dataclass.
```
# Before
    review: 'StepReview | None' = None

# After
    review: 'StepReview | None' = None
    evaluators: list = field(default_factory=list)
```

### File: `llm_pipeline/step.py`
Added `evaluators` kwarg to `step_definition()` signature, stored on class as `_step_evaluators`, passed through to `StepDefinition` in `create_definition()`.
```
# Before (signature)
    review: Optional[Type] = None,

# After (signature)
    review: Optional[Type] = None,
    evaluators: Optional[List[Type]] = None,

# Before (class attrs)
        step_class.REVIEW = review

# After (class attrs)
        step_class.REVIEW = review
        step_class._step_evaluators = evaluators or []

# Before (create_definition)
            return StepDefinition(

# After (create_definition)
            if 'evaluators' not in kwargs and cls._step_evaluators:
                kwargs['evaluators'] = cls._step_evaluators
            return StepDefinition(
```

### File: `llm_pipeline/evals/evaluators.py`
New file. `FieldMatchEvaluator(field_name)` callable: returns `{}` on skip (None expected or field absent), `bool` on match/mismatch. `build_auto_evaluators(instructions_cls)` returns one evaluator per `model_fields` key.

### File: `tests/test_evaluators.py`
13 tests: 7 for FieldMatchEvaluator (skip/match/mismatch/edge cases), 3 for build_auto_evaluators (count/type/empty), 3 for step_definition evaluators param (stored on class/passed to StepDefinition/default empty).

## Decisions
### Evaluator callable signature
**Choice:** `__call__(output, expected) -> dict | bool` - returns `{}` for skip, `bool` for result
**Rationale:** Matches pydantic-evals `{}` skip contract per PLAN.md. Standalone callable (no base class inheritance) since pydantic_evals.evaluators.Evaluator base class is not required for the runner to call evaluators.

### Field access on expected
**Choice:** Support both dict and object access patterns for expected values
**Rationale:** Expected data comes from YAML/DB as dicts, but could also be Pydantic model instances in programmatic usage.

## Verification
[x] 13/13 tests pass via `uv run pytest tests/test_evaluators.py -v`
[x] `evaluators=` follows same pattern as `review=` in decorator
[x] `StepDefinition.evaluators` defaults to empty list (no breaking change)
[x] `build_auto_evaluators` returns one evaluator per model field
[x] FieldMatchEvaluator skips when expected is None or field absent
