# Task Summary

## Work Completed

Ported custom validation logic (`not_found_indicators` and `ArrayValidationConfig`) to pydantic-ai `@agent.output_validator` decorators. Created `validators.py` with two factory functions (`not_found_validator`, `array_length_validator`). Added `not_found_indicators` to `StepDefinition` and `array_field_name` to `ArrayValidationConfig`. Updated `build_step_agent()` to accept validators and wire `validation_context` lambda into the Agent constructor. Updated `pipeline.py` to rebuild `StepDeps` per-call (so per-call params flow to validators) and register both validators for every step. Exported new public symbols from `llm_pipeline/__init__.py`. Added 34 new tests (29 in `test_validators.py`, 5 in `test_agent_registry_core.py`). Architecture review passed after fixing 3 MEDIUM issues (stale comments, event loop leak, misleading test name).

## Files Changed

### Created
| File | Purpose |
| --- | --- |
| `llm_pipeline/validators.py` | Validator factory functions: `not_found_validator()`, `array_length_validator()`, `DEFAULT_NOT_FOUND_INDICATORS` constant, and `_reorder_items()` / `_strip_number_prefix()` private helpers |
| `tests/test_validators.py` | 29 tests covering both validator factories including edge cases, ModelRetry paths, reordering, strip_number_prefix, and no-op behavior |

### Modified
| File | Changes |
| --- | --- |
| `llm_pipeline/types.py` | Added `array_field_name: str = ""` field to `ArrayValidationConfig` dataclass |
| `llm_pipeline/strategy.py` | Added `not_found_indicators: list[str] \| None = None` field to `StepDefinition` dataclass |
| `llm_pipeline/agent_builders.py` | Added `validators: list[Any] \| None = None` param to `build_step_agent()`; added `validation_context=lambda ctx: ctx.deps.validation_context` to Agent constructor; added validator registration loop; updated stale Task 2/3 comments in StepDeps docstring and field comments |
| `llm_pipeline/pipeline.py` | Imported `not_found_validator`, `array_length_validator` from `llm_pipeline.validators`; moved `StepDeps` construction inside the `for idx, params` loop; added `step_validators` list built per-step and passed to `build_step_agent()` |
| `llm_pipeline/__init__.py` | Added import and `__all__` entries for `not_found_validator`, `array_length_validator`, `DEFAULT_NOT_FOUND_INDICATORS` |
| `tests/test_agent_registry_core.py` | Added `TestBuildStepAgentValidators` class with 5 tests: validators param accepted, None accepted, registration verified, order preserved, validation_context wired |

## Commits Made

| Hash | Message |
| --- | --- |
| `e944fd8d` | docs(implementation-A): pydantic-ai-3-port-validation-logic |
| `695842a6` | chore(state): pydantic-ai-3-port-validation-logic -> implementation (validators.py created) |
| `ffc53a2c` | docs(implementation-B): pydantic-ai-3-port-validation-logic |
| `79807980` | chore(state): pydantic-ai-3-port-validation-logic -> implementation (pipeline.py updated) |
| `96f07f7c` | docs(implementation-B): pydantic-ai-3-port-validation-logic |
| `e073b70a` | docs(implementation-C): pydantic-ai-3-port-validation-logic |
| `73860020` | docs(implementation-D): pydantic-ai-3-port-validation-logic |
| `e3326d27` | docs(implementation-D): pydantic-ai-3-port-validation-logic |
| `4c4f2197` | docs(fixing-review-B): pydantic-ai-3-port-validation-logic |
| `7ffbdfb3` | docs(fixing-review-D): pydantic-ai-3-port-validation-logic |
| `df1c6480` | docs(fixing-review-D): pydantic-ai-3-port-validation-logic |

## Deviations from Plan

- **Step 4 correction applied as planned**: `array_length_validator()` takes no config arg (reads `ctx.deps.array_validation` at runtime). PLAN.md included a correction note anticipating this; it was implemented correctly.
- **Step 5 was a no-op**: All obsolete validation functions (`validate_array_response`, `check_not_found_response`) were already deleted in Task 2. No code changes needed for that step.
- **validators.py committed via state transition commit**: The actual source file for `validators.py` was committed in a `chore(state)` commit (`695842a6`) rather than a `docs(implementation)` commit due to the workflow's state machine pattern. Same for `pipeline.py` changes (`79807980`).

## Issues Encountered

### array_length_validator registration before call loop
**Resolution:** The PLAN.md correction note (Step 4) correctly anticipated this: since the agent is built once per step before the call loop, `array_length_validator` cannot be registered per-call. Solution: factory takes no args, reads `ctx.deps.array_validation` at runtime. No-op when `None`. Both validators registered unconditionally on every agent.

### Event loop leak in test helper
**Resolution:** Initial `_run()` helper used `asyncio.new_event_loop().run_until_complete()` without closing the loop. Fixed to `asyncio.run()` (review fix commit `7ffbdfb3`).

### Stale "Task 2/Task 3" comments in agent_builders.py
**Resolution:** `StepDeps` docstring and field inline comments still referenced Task 2/3 context. Updated to accurately describe the fields' purpose (review fix commit `4c4f2197`).

### Misleading test name
**Resolution:** `test_already_correct_order_no_copy_needed` implied `model_copy` is skipped when order is already correct, but code unconditionally calls `model_copy` when `allow_reordering=True`. Renamed to `test_already_correct_order_preserved` (review fix commit `7ffbdfb3`).

## Success Criteria

- [x] `llm_pipeline/validators.py` exists with `not_found_validator`, `array_length_validator`, `DEFAULT_NOT_FOUND_INDICATORS` - confirmed via import
- [x] `ArrayValidationConfig` has `array_field_name: str` field in `types.py` - default `""` confirmed
- [x] `StepDefinition` has `not_found_indicators: list[str] | None = None` field in `strategy.py` - confirmed via dataclass fields
- [x] `build_step_agent()` accepts `validators` param and registers each via `agent.output_validator()` - confirmed at `agent_builders.py`
- [x] `build_step_agent()` passes `validation_context=lambda ctx: ctx.deps.validation_context` to Agent constructor - confirmed, validated by `TestBuildStepAgentValidators::test_validation_context_wired`
- [x] `pipeline.py` constructs `StepDeps` inside `for idx, params` loop with per-call `array_validation` and `validation_context` - confirmed at `pipeline.py:747`
- [x] `pipeline.py` registers `not_found_validator(step_def.not_found_indicators)` for every step - confirmed at `pipeline.py:735`
- [x] `pipeline.py` registers `array_length_validator()` (no-op when `deps.array_validation` is None) for every step - confirmed at `pipeline.py:736`
- [x] No references to `validate_array_response` or `check_not_found_response` in `llm_pipeline/` source - grep zero results
- [x] `not_found_validator` and `array_length_validator` exported from `llm_pipeline/__init__.py` - confirmed via import test
- [x] All existing tests pass (`pytest`) - 837 pass, 1 pre-existing unrelated failure (`test_events_router_prefix`)
- [x] New tests in `tests/test_validators.py` cover both validator factories - 29 tests covering all branches

## Recommendations for Follow-up

1. Fix pre-existing test failure `tests/test_ui.py::TestRoutersIncluded::test_events_router_prefix` - update assertion from `'/events'` to `'/runs/{run_id}/events'` to match current router prefix.
2. Add `__post_init__` validation to `ArrayValidationConfig` to raise early when `array_field_name` is empty and the config is used with `array_length_validator` - currently the `ValueError` fires at validator call time (inside `agent.run_sync()`), not at config construction time.
3. Consider word-boundary matching in `not_found_validator` to avoid false positives on valid content containing indicator substrings (e.g., "Unknown approach yields good results" contains "unknown"). This is existing behavior parity, not a regression.
4. Document the `validation_context` lambda pattern in public API docs: output types using Pydantic `field_validator` with `info.context` must guard for `None` when no per-call `ValidationContext` is set.
5. Consider `pytest-asyncio` for cleaner async test support in `test_validators.py` rather than the `asyncio.run()` helper wrapper.
