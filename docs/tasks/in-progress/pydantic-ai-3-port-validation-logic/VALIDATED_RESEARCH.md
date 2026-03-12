# Research Summary

## Executive Summary

Cross-referenced step-1 (existing validation analysis) and step-2 (pydantic-ai output validators) research against the actual codebase. Both research documents are accurate. All code references verified. **All 5 architectural decisions resolved by CEO.** The research correctly identifies the per-call StepDeps wiring gap and the validation_context Agent constructor pattern. One gap unaddressed by research (array field discovery on Pydantic models) resolved via CEO decision to use explicit `array_field_name` on ArrayValidationConfig.

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
| not_found_indicators source: StepDefinition field vs LLMStep attribute vs build_step_agent param? | StepDefinition field. `not_found_indicators: list[str] \| None = None`. None = framework defaults (common LLM evasion phrases). Set = override. Flow: StepDefinition -> pipeline.execute() -> build_step_agent() -> not_found_validator factory. | Adds field to StepDefinition dataclass (strategy.py). Pipeline.execute() reads from step_def. Framework provides sensible defaults when None. |
| Array reordering: silent model_copy vs ModelRetry vs hybrid? | Silent reorder via model_copy matching old behavior. No ModelRetry for ordering issues. | Validator returns reordered model via model_copy(update={...}). Only ModelRetry for length mismatch (unrecoverable by reorder). Matches old behavior exactly. |
| Array field discovery: scan model_fields or explicit array_field_name? | Explicit `array_field_name: str` on ArrayValidationConfig. Caller specifies which field. No auto-scanning. | Add `array_field_name: str` field to ArrayValidationConfig in types.py. Validator uses `getattr(output, config.array_field_name)` directly. |
| Type location: keep in types.py or move to validators.py? | Keep ArrayValidationConfig and ValidationContext in types.py. Backward compatible. | No import changes for downstream. validators.py imports from types.py. |
| StepDeps construction: rebuild per-call or mutate? | Rebuild per-call inside execute loop. Clean, no shared mutable state. | Move StepDeps construction inside `for idx, params` loop. Each call gets fresh StepDeps with per-call array_validation and validation_context from StepCallParams. |

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
- Task 3 description references wrong file path (schemas/validation.py vs llm/validation.py) -- cosmetic, no action needed
- Framework-level default not_found_indicators list needs defining during implementation (common LLM evasion phrases like "not found", "no data available", etc.)

## Recommendations for Planning
1. Keep `ArrayValidationConfig` and `ValidationContext` in `types.py` (backward compatible) -- **CEO confirmed**
2. Create `llm_pipeline/validators.py` with `not_found_validator()`, `array_length_validator()`, and `strip_number_prefix()`
3. Add `not_found_indicators: list[str] | None = None` to `StepDefinition` (strategy.py). None = framework defaults. Flow: StepDefinition -> pipeline.execute() -> build_step_agent() -> not_found_validator factory -- **CEO confirmed**
4. Add `array_field_name: str` to `ArrayValidationConfig` (types.py). Caller specifies target field explicitly -- **CEO confirmed**
5. Rebuild `StepDeps` per-call inside the `for idx, params` loop. Each call gets fresh instance with per-call array_validation/validation_context from StepCallParams -- **CEO confirmed**
6. Register validators via `build_step_agent(validators=[...])` parameter
7. Wire `Agent(validation_context=lambda ctx: ...)` in `build_step_agent()` for Pydantic field validator context
8. Array reordering: silent `model_copy(update={...})` matching old behavior. ModelRetry only for length mismatch -- **CEO confirmed**
9. Output validator registration order: not_found first (cheap), array_length second (heavier)
