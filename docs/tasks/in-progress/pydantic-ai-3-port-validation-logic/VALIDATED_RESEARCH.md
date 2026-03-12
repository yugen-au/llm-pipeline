# Research Summary

## Executive Summary

Cross-referenced step-1 (existing validation analysis) and step-2 (pydantic-ai output validators) research against the actual codebase. Both research documents are accurate. All code references verified. Key finding: **5 architectural decisions require CEO input** before planning can proceed. The research correctly identifies the per-call StepDeps wiring gap and the validation_context Agent constructor pattern. One gap unaddressed by research: array field discovery on Pydantic models (old code scanned raw dicts, new code operates on typed models).

## Domain Findings

### Codebase State Post-Task-2
**Source:** step-1-existing-validation-analysis.md, codebase inspection

- `llm/validation.py` confirmed deleted in Task 2 (commit 4aae017f). Zero references to `not_found` or `indicators` in any `llm_pipeline/` source file.
- `StepDeps.array_validation` and `StepDeps.validation_context` exist (agent_builders.py:49-51), default None, tested in test_agent_registry_core.py:159-172.
- `StepCallParams` declares `array_validation` and `validation_context` (types.py:54-67) but pipeline.py never reads them from `params` -- confirmed gap.
- `StepDeps` built once at pipeline.py:735-744, outside call loop at line 746. Agent built once at lines 730-734.
- `ArrayValidationConfig` and `ValidationContext` remain in types.py, exported from `__init__.py` (public API).
- `validators.py` does not exist -- must be created.
- `StepDefinition` (strategy.py:23-38) has no field for not_found_indicators or validators.

### pydantic-ai Output Validator Mechanics
**Source:** step-2-pydanticai-output-validators.md, pydantic-ai source inspection

- `agent.output_validator(fn)` works programmatically (not just as decorator). Verified.
- Multiple validators stack, execute in registration order. Verified.
- `ModelRetry` triggers retry with message sent to LLM. Max retries = `build_step_agent(retries=3)`.
- `RunContext[StepDeps]` provides `ctx.deps` at call-time (not build-time). Validators registered at build time read deps at execution time. **Verified: per-call StepDeps pattern works.**
- `Agent(validation_context=...)` accepts `Any | Callable[[RunContext[AgentDepsT]], Any]`. **Verified via `inspect.signature(Agent.__init__)`**. Callable resolves at run_sync() time.
- Agent built once before call loop -> lambda reads StepDeps from whichever run_sync() call -> per-call ValidationContext flows correctly.

### Consensus Path Impact
**Source:** codebase inspection (pipeline.py:1199-1260)

- `_execute_with_consensus()` receives `step_deps` as a parameter (line 1199) and passes it to `agent.run_sync()` (line 1214).
- If StepDeps moves inside per-call loop, consensus receives per-call StepDeps. Consensus runs serially on one call_params entry, so no concurrency concern.
- No additional changes needed in consensus method beyond receiving the right StepDeps.

### Gap: Array Field Discovery on Pydantic Models
**Source:** cross-reference analysis (not in research)

- Old `validate_array_response()` found "first list in response_json where items have config.match_field key" by scanning a raw dict.
- New output validator receives a Pydantic model instance, not raw dict.
- Must find list-type fields on the model, then check items for match_field.
- Options: (a) scan `model.model_fields` for `list` type annotations, (b) add `array_field_name: str` to `ArrayValidationConfig`.
- Research did not address this gap.

### Gap: not_found_indicators Has No Home
**Source:** cross-reference analysis

- Zero references to `not_found` or `indicators` in current `llm_pipeline/` source.
- Old code: passed as parameter to `LLMProvider.call_structured()` by downstream consumers.
- Factory `not_found_validator(indicators)` bakes indicators into closure at agent-build time.
- No existing field on `StepDefinition`, `LLMStep`, `StepCallParams`, or `StepDeps` carries indicators.
- Pipeline.execute() has no mechanism to discover indicators from step/strategy config.

### Task Description Inaccuracy
**Source:** Task 3 description vs codebase

- Task 3 says "Delete schemas/validation.py". Actual path was `llm_pipeline/llm/validation.py`, already deleted in Task 2.
- No `schemas/` directory exists in `llm_pipeline/`. Task description path is wrong but irrelevant since file is already gone.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Pending - see Questions below | - | - |

## Assumptions Validated
- [x] StepDeps has array_validation and validation_context fields defaulting to None (agent_builders.py:49-51)
- [x] StepCallParams declares array_validation and validation_context (types.py:54-67)
- [x] pipeline.py builds StepDeps once outside call loop, ignoring per-call params (lines 735-744)
- [x] Agent is built once per step before call loop (pipeline.py:730-734)
- [x] pydantic-ai Agent constructor accepts validation_context as static value or callable (verified via inspect)
- [x] Callable validation_context receives RunContext[AgentDepsT] at run_sync() time (verified via type annotation)
- [x] Output validators can return modified output (not just raise ModelRetry) -- per pydantic-ai docs
- [x] Consensus path passes step_deps through without issue (pipeline.py:1214)
- [x] llm/validation.py was already deleted in Task 2 -- no delete action needed
- [x] ArrayValidationConfig and ValidationContext are public API exports (__init__.py:29)

## Open Items
- Array field discovery on Pydantic models not addressed in research (see Gap above)
- Task 3 description references wrong file path (schemas/validation.py vs llm/validation.py) -- cosmetic, no action needed
- Research step-2 section 8 claims about validation_context callable form are now verified but were originally unsubstantiated

## Recommendations for Planning
1. Keep `ArrayValidationConfig` and `ValidationContext` in `types.py` (backward compatible, no import breakage for downstream)
2. Create `llm_pipeline/validators.py` with `not_found_validator()`, `array_length_validator()`, and `strip_number_prefix()`
3. Rebuild `StepDeps` per-call inside the `for idx, params` loop (cleaner than mutation, avoids side effects)
4. Register validators via `build_step_agent(validators=[...])` parameter
5. Wire `Agent(validation_context=lambda ctx: ...)` in `build_step_agent()` for Pydantic field validator context
6. Array reordering should use `model_copy(update={...})` to match old silent-reorder behavior (not ModelRetry)
7. Output validator registration order: not_found first (cheap), array_length second (heavier)
