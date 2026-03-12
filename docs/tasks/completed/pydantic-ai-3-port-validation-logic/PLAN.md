# PLANNING

## Summary

Port custom validation logic (not_found_indicators, ArrayValidationConfig) to pydantic-ai `@agent.output_validator` decorators. Create `validators.py` with factory functions, add `not_found_indicators` to `StepDefinition`, add `array_field_name` to `ArrayValidationConfig`, update `build_step_agent()` to accept and register validators, move StepDeps construction inside the per-call loop in `pipeline.py`, and delete obsolete validation functions from `llm_pipeline/llm/__init__.py` or any utils file.

## Plugin & Agents
**Plugin:** [available agents]
**Subagents:** [available agents]
**Skills:** none

## Phases
1. Create validators.py - new file with not_found_validator and array_length_validator factories
2. Update types and strategy - add array_field_name to ArrayValidationConfig, add not_found_indicators to StepDefinition
3. Update agent_builders - accept validators param, register them, wire validation_context lambda
4. Update pipeline.py - pass not_found_indicators/array_validation to build_step_agent, rebuild StepDeps per-call
5. Delete obsolete code - remove validate_array_response/check_not_found_response from llm/__init__.py or utils
6. Update __init__.py exports - expose validators.py public symbols if needed

## Architecture Decisions

### Validator Registration Pattern
**Choice:** `build_step_agent(validators: list[Callable] | None = None)` accepts pre-built validator callables and registers each via `agent.output_validator(fn)` in the loop.
**Rationale:** Programmatic `agent.output_validator(fn)` (not decorator) confirmed to work. Factory functions (`not_found_validator(indicators)`, `array_length_validator(config)`) close over their config at build time; `ctx.deps` provides per-call StepDeps at runtime. Clean separation: factories live in validators.py, registration in agent_builders.py.
**Alternatives:** Decorating within factory functions (not possible without agent reference); passing validator config to build_step_agent and constructing inside (mixed concerns).

### StepDeps Per-Call Rebuild
**Choice:** Move StepDeps construction inside the `for idx, params` loop in pipeline.py (currently at lines 735-744, outside loop at line 746).
**Rationale:** CEO confirmed. Per-call params (`array_validation`, `validation_context`) from `StepCallParams` must flow into StepDeps so validators read correct per-call data via `ctx.deps`. Agent is still built once before the loop; only StepDeps changes per call.
**Alternatives:** Mutating shared StepDeps (shared mutable state, race-prone); adding a separate per-call context dict (extra indirection).

### not_found_indicators Flow
**Choice:** `StepDefinition.not_found_indicators: list[str] | None = None` -> read in pipeline.py execute loop -> passed to `build_step_agent(not_found_indicators=...)` -> `not_found_validator(indicators)` factory bakes into closure at agent-build time.
**Rationale:** CEO confirmed. None = framework defaults (common LLM evasion phrases). Set = override. Indicators known at pipeline definition time, not per-call, so baking into closure is correct.
**Alternatives:** Per-call indicators via StepCallParams (overkill, indicators are step-level config, not call-level).

### Array Reordering
**Choice:** Silent `model_copy(update={array_field_name: reordered_list})` for ordering issues. `ModelRetry` only for length mismatch.
**Rationale:** CEO confirmed. Matches old behavior exactly. Ordering is correctable silently; length mismatch is unrecoverable by reordering.
**Alternatives:** Always ModelRetry (forces LLM retry for fixable issue); hybrid with threshold.

### validation_context Agent Constructor
**Choice:** Pass `validation_context=lambda ctx: ctx.deps.validation_context` to Agent constructor in `build_step_agent`. This is the Pydantic field validator context, distinct from StepDeps.
**Rationale:** Confirmed via inspect: `Agent.__init__` accepts `validation_context` as `Any | Callable[[RunContext[AgentDepsT]], Any]`. Lambda resolves at `run_sync()` time reading per-call StepDeps. Enables Pydantic `model_validator` methods in output types to access ValidationContext via `info.context`.
**Alternatives:** Static validation_context at build time (can't support per-call values).

### Type Location
**Choice:** Keep `ArrayValidationConfig` and `ValidationContext` in `types.py`. No move.
**Rationale:** CEO confirmed. Backward compatible. validators.py imports from types.py.
**Alternatives:** Move to validators.py (breaks existing imports from public API).

## Implementation Steps

### Step 1: Add array_field_name to ArrayValidationConfig and not_found_indicators to StepDefinition
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /pydantic/pydantic-ai
**Group:** A

1. In `llm_pipeline/types.py`, add `array_field_name: str = ""` field to `ArrayValidationConfig` dataclass (after `strip_number_prefix`). This field is required when using array_length_validator; empty string is a safe default that will raise clearly if misconfigured.
2. In `llm_pipeline/strategy.py`, add `not_found_indicators: list[str] | None = None` field to the `StepDefinition` dataclass (after `agent_name`). Import `list` is already available via `List` from typing; use built-in `list` (Python 3.11+).

### Step 2: Create llm_pipeline/validators.py
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /pydantic/pydantic-ai
**Group:** A

1. Create `llm_pipeline/validators.py` as a new file.
2. Add module docstring explaining validator factories for pydantic-ai output_validator.
3. Import: `from __future__ import annotations`, `from typing import Any`, `from pydantic_ai import ModelRetry, RunContext`, and `from llm_pipeline.agent_builders import StepDeps` (TYPE_CHECKING guard not needed since validators.py is not imported by agent_builders.py).
4. Define `DEFAULT_NOT_FOUND_INDICATORS: list[str]` constant at module level with common LLM evasion phrases: `["not found", "no data", "n/a", "none", "not available", "not provided", "unknown", "no information"]`.
5. Define `not_found_validator(indicators: list[str] | None = None)` factory:
   - If `indicators is None`, use `DEFAULT_NOT_FOUND_INDICATORS`.
   - Returns an async or sync function `_validator(ctx: RunContext[StepDeps], output: Any) -> Any` that checks if the output is a string containing any indicator phrase (case-insensitive). If matched, raises `ModelRetry(f"Response indicates not found: {output!r}")`. Returns output unchanged otherwise.
   - The returned function should have a clear name for debugging (e.g., assign `__name__`).
6. Define `array_length_validator(config)` factory (config type: `ArrayValidationConfig`):
   - Validates `config.array_field_name` is set (non-empty string); raise `ValueError` at factory call time if not.
   - Returns a function `_validator(ctx: RunContext[StepDeps], output: Any) -> Any` that:
     a. Gets `items = getattr(output, config.array_field_name)` (list from model).
     b. Filters `input_array` if `config.filter_empty_inputs` is True (filter falsy values).
     c. If `len(items) != len(effective_input)`: raise `ModelRetry(f"Expected {len(effective_input)} items, got {len(items)}")`.
     d. If `config.allow_reordering` is True: reorder items to match `input_array` order using `config.match_field` to find matches. Build `reordered` list by matching each input item against `config.match_field` in items. Silent reorder via `output.model_copy(update={config.array_field_name: reordered})`, return reordered output.
     e. If `config.strip_number_prefix`: strip leading numeric prefix (e.g. "1. ") from `config.match_field` values when matching.
     f. Return output unchanged if no reordering needed.
7. Add `__all__ = ["not_found_validator", "array_length_validator", "DEFAULT_NOT_FOUND_INDICATORS"]`.

### Step 3: Update build_step_agent() to accept validators and wire validation_context
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /pydantic/pydantic-ai
**Group:** B

1. In `llm_pipeline/agent_builders.py`, update `build_step_agent` signature to add `validators: list[Any] | None = None` parameter (after `model_settings`).
2. Pass `validation_context=lambda ctx: ctx.deps.validation_context` to the `Agent(...)` constructor. This wires per-call `ValidationContext` into the Pydantic model validator context at `run_sync()` time.
3. After the `@agent.instructions` block (after the `_inject_system_prompt` registration), add a loop: `for v in (validators or []): agent.output_validator(v)`. This registers each factory-produced validator in order (not_found first, array_length second - enforced by caller order).
4. Update the docstring to document the `validators` parameter and `validation_context` wiring.
5. Update `TYPE_CHECKING` imports: add `from typing import Callable` (already in `Any` import; add `Callable` to the typing import if needed for type hints).

### Step 4: Update pipeline.py to pass validators and rebuild StepDeps per-call
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. In `llm_pipeline/pipeline.py`, import `not_found_validator` and `array_length_validator` from `llm_pipeline.validators` at the top of the file (add to existing llm_pipeline imports block).
2. In the execute loop, after `step_def` is resolved (line ~552) and before `build_step_agent` is called (line ~731), build the validators list for this step:
   ```
   step_validators = []
   if step_def.not_found_indicators is not None or True:  # always add not_found
       step_validators.append(not_found_validator(step_def.not_found_indicators))
   ```
   Note: not_found_validator is always registered (handles both None=defaults and explicit list).
3. Pass `validators=step_validators` to `build_step_agent(...)` call.
4. Move StepDeps construction inside the `for idx, params` loop (currently outside at lines 735-744). Inside the loop, after `user_prompt` is built, construct:
   ```python
   step_deps = StepDeps(
       session=self.session,
       pipeline_context=self._context,
       prompt_service=prompt_service,
       run_id=self.run_id,
       pipeline_name=self.pipeline_name,
       step_name=step.step_name,
       event_emitter=self._event_emitter,
       variable_resolver=self._variable_resolver,
       array_validation=params.get("array_validation"),
       validation_context=params.get("validation_context"),
   )
   ```
5. If `params` also has `array_validation` set, append `array_length_validator(params["array_validation"])` to `step_validators` before the call (note: agent is already built; validators must be registered before run_sync). Reconsider: since agent is built once per step before the loop, per-call `array_length_validator` cannot be registered after agent is built. Instead, array_length_validator reads `ctx.deps.array_validation` from the per-call StepDeps at run time. Update `array_length_validator` factory to accept `None` config and read config from `ctx.deps.array_validation` if not provided at factory time. Register a single array_length_validator on the agent (before the loop), which checks `ctx.deps.array_validation` at call time; if None, it's a no-op.
6. This means both validators are registered once on the agent at step build time. They use `ctx.deps` for per-call data. Update Step 2's `array_length_validator` accordingly (see correction note below).

**Correction for Step 2 (array_length_validator factory):** The factory must handle two modes:
- `array_length_validator(config)` with explicit config: uses config directly (no ctx.deps lookup).
- `array_length_validator()` / registered as always-on: reads `ctx.deps.array_validation`; if None, returns output unchanged (no-op).
- Recommended: always register via `array_length_validator()` (no config arg), reads from `ctx.deps.array_validation`, no-op if None. This avoids rebuilding agent per call.

### Step 5: Delete obsolete validation functions
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. Search `llm_pipeline/llm/__init__.py` and any other files in `llm_pipeline/` for `validate_array_response`, `check_not_found_response`, and `strip_number_prefix` (if defined there). Confirmed by research: validation.py was deleted in Task 2; check if any remnants exist in `llm_pipeline/llm/__init__.py` exports or other files.
2. Run `grep -r "validate_array_response\|check_not_found_response" llm_pipeline/` to confirm zero references remain after deletion.
3. Remove any export stubs or re-exports of these functions from `llm_pipeline/llm/__init__.py`.
4. Do not delete `strip_number_prefix` if it is used elsewhere; move to validators.py as a private helper `_strip_number_prefix` if needed.

### Step 6: Update exports in __init__.py
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. In `llm_pipeline/__init__.py`, add imports from `llm_pipeline.validators`:
   `from llm_pipeline.validators import not_found_validator, array_length_validator, DEFAULT_NOT_FOUND_INDICATORS`
2. Add to `__all__`: `"not_found_validator"`, `"array_length_validator"`, `"DEFAULT_NOT_FOUND_INDICATORS"`.
3. Verify `ArrayValidationConfig` and `ValidationContext` remain exported (already present at line 29, no change needed).

### Step 7: Update tests for StepDeps field count and build_step_agent signature
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** D

1. In `tests/test_agent_registry_core.py`, `TestStepDepsFields.test_field_count` asserts `len(f) == 10`. StepDeps field count does not change in this task (array_validation and validation_context already exist), so no update needed unless Step 3 adds fields.
2. Add new test class `TestBuildStepAgentValidators` in `tests/test_agent_registry_core.py`:
   - `test_validators_param_accepted`: calls `build_step_agent("step", SimpleOutput, validators=[])` without error.
   - `test_validators_registered`: creates a dummy validator function, passes it, checks `agent._output_validators` (or pydantic-ai equivalent internal) has the validator registered.
   - `test_validation_context_wired`: checks agent has a validation_context callable set.
3. Add new test file `tests/test_validators.py` with tests for:
   - `not_found_validator`: default indicators match, custom indicators match, non-matching passes through, `ModelRetry` raised on match.
   - `array_length_validator`: length mismatch raises `ModelRetry`, correct length passes, reordering works, strip_number_prefix works, no-op when `ctx.deps.array_validation` is None.
   - Use mock `RunContext` with mock `deps` (simple dataclass or MagicMock).

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| array_length_validator registered once but needs per-call config | High | Read config from ctx.deps.array_validation at call time; no-op if None. Agent built once, validator behavior adapts per call. |
| StepDeps move inside loop breaks consensus path | Medium | _execute_with_consensus() already receives step_deps as parameter (verified line 1199); passing per-call step_deps is correct. Consensus method signature unchanged. |
| test_field_count asserts exactly 10 fields on StepDeps | Low | No new fields added to StepDeps in this task. Test passes unchanged. |
| not_found_validator applied to non-string output types | Medium | Guard: check `isinstance(output, str)` at start of validator; return unchanged if not string. |
| validation_context lambda: Agent constructor signature change in future pydantic-ai version | Low | Verified via inspect in research. Pin pydantic-ai version in pyproject.toml if needed. |
| step_validators list built before loop but array_length_validator must be no-op when no config | Medium | Factory with no args reads ctx.deps.array_validation; explicit no-op return if None (see Step 4 correction). |

## Success Criteria

- [ ] `llm_pipeline/validators.py` exists with `not_found_validator`, `array_length_validator`, `DEFAULT_NOT_FOUND_INDICATORS`
- [ ] `ArrayValidationConfig` has `array_field_name: str` field in `types.py`
- [ ] `StepDefinition` has `not_found_indicators: list[str] | None = None` field in `strategy.py`
- [ ] `build_step_agent()` accepts `validators` param and registers each via `agent.output_validator()`
- [ ] `build_step_agent()` passes `validation_context=lambda ctx: ctx.deps.validation_context` to Agent constructor
- [ ] `pipeline.py` constructs StepDeps inside `for idx, params` loop with per-call `array_validation` and `validation_context`
- [ ] `pipeline.py` registers `not_found_validator(step_def.not_found_indicators)` for every step
- [ ] `pipeline.py` registers `array_length_validator()` (no-op when deps.array_validation is None) for every step
- [ ] No references to `validate_array_response` or `check_not_found_response` in `llm_pipeline/` source
- [ ] `not_found_validator` and `array_length_validator` exported from `llm_pipeline/__init__.py`
- [ ] All existing tests pass (`pytest`)
- [ ] New tests in `tests/test_validators.py` cover both validator factories

## Phase Recommendation
**Risk Level:** medium
**Reasoning:** The array_length_validator "registered once, per-call config" pattern requires care - the no-op-when-None approach must be correctly implemented or steps without array validation will fail. The StepDeps move inside the loop is straightforward but touches the core execution path. No external dependencies change.
**Suggested Exclusions:** review
