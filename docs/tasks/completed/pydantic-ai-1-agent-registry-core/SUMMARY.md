# Task Summary

## Work Completed

Implemented AgentRegistry and core agent abstractions for pydantic-ai integration in the llm-pipeline framework. Created 3 new files (naming.py, agent_registry.py, agent_builders.py), modified 5 existing files (step.py, strategy.py, pipeline.py, pyproject.toml, __init__.py), and added 51 new tests. All changes are additive and backward-compatible; actual executor replacement is deferred to Task 2.

Key work:
- Extracted snake_case normalization to `naming.py`, fixing a pre-existing single-regex bug in `LLMStep.step_name` and standardizing all 4 callsites to the correct double-regex pattern
- Created `AgentRegistry` ABC following the Category A class-param pattern (mirrors `PipelineDatabaseRegistry` exactly)
- Created `StepDeps` dataclass (8 fields) and `build_step_agent()` factory with `defer_model_check=True` and `@agent.instructions` for system prompt injection
- Added `agent_name` field and `step_name` property to `StepDefinition`; added `get_agent()` and `build_user_prompt()` to `LLMStep`; deprecated `create_llm_call()` with `DeprecationWarning`
- Added optional `agent_registry=` param to `PipelineConfig.__init_subclass__` with naming convention validation
- Review cycle fixed 4 issues: pydantic-ai lazy import (HIGH), `variable_instance` preservation in `build_user_prompt` (MEDIUM), `pipeline_name` single-regex bug (MEDIUM), unclosed SQLite connection in test (LOW)

## Files Changed

### Created

| File | Purpose |
| --- | --- |
| `llm_pipeline/naming.py` | `to_snake_case(name, strip_suffix)` utility using double-regex pattern; single source of truth for CamelCase-to-snake conversion |
| `llm_pipeline/agent_registry.py` | `AgentRegistry` ABC with Category A class-param pattern; stores `{step_name: Type[BaseModel]}` type refs; `get_output_type()` accessor |
| `llm_pipeline/agent_builders.py` | `StepDeps` dataclass (8 fields) and `build_step_agent()` factory that constructs pydantic-ai `Agent` instances with system prompt injection via `@agent.instructions` |
| `tests/test_agent_registry_core.py` | 51 tests covering naming.py, agent_registry.py, agent_builders.py, and all new LLMStep/StepDefinition/PipelineConfig behaviour |

### Modified

| File | Changes |
| --- | --- |
| `llm_pipeline/step.py` | (1) `LLMStep.step_name` property: replaced single-regex with `to_snake_case`; (2) added `get_agent(registry)` concrete method with `_agent_name` override support; (3) added `build_user_prompt(variables, prompt_service, context)` concrete method with `variable_instance` preservation; (4) deprecated `create_llm_call()` with `DeprecationWarning`; (5) added `import warnings` |
| `llm_pipeline/strategy.py` | (1) `StepDefinition.create_step()`: replaced inline double-regex with `to_snake_case`; (2) added `agent_name: str | None = None` field to `StepDefinition`; (3) added `step_name` property to `StepDefinition`; (4) `create_step()` now sets `step._agent_name` on the created instance |
| `llm_pipeline/pipeline.py` | (1) `StepKeyDict._normalize_key()`: replaced inline double-regex with `to_snake_case`; (2) `PipelineConfig.pipeline_name` property: replaced single-regex with `to_snake_case` (review fix); (3) added `AGENT_REGISTRY: ClassVar` and `agent_registry=` param to `__init_subclass__` with `{Prefix}AgentRegistry` naming validation; (4) removed `import re` (no remaining usage) |
| `pyproject.toml` | Added `pydantic-ai = ["pydantic-ai>=1.0.5"]` to `[project.optional-dependencies]`; added `pydantic-ai>=1.0.5` to `dev` optional-dependencies |
| `llm_pipeline/__init__.py` | Added exports: `AgentRegistry` from `agent_registry`; `StepDeps`, `build_step_agent` from `agent_builders`; added `"Agent"` category section to `__all__` |

## Commits Made

| Hash | Message |
| --- | --- |
| `e38efca` | docs(implementation-A): pydantic-ai-1-agent-registry-core |
| `1e4c51d` | docs(implementation-B): pydantic-ai-1-agent-registry-core |
| `afa63ac` | docs(implementation-B): pydantic-ai-1-agent-registry-core |
| `f41180b` | docs(implementation-B): pydantic-ai-1-agent-registry-core |
| `be173cf` | docs(implementation-C): pydantic-ai-1-agent-registry-core |
| `8881f18` | docs(implementation-D): pydantic-ai-1-agent-registry-core |
| `200b56a` | docs(implementation-E): pydantic-ai-1-agent-registry-core |
| `5972079` | docs(implementation-E): pydantic-ai-1-agent-registry-core |
| `4ed29a8` | docs(implementation-F): pydantic-ai-1-agent-registry-core |
| `52ff578` | docs(fixing-review-B): pydantic-ai-1-agent-registry-core |
| `b82f6f4` | docs(fixing-review-C): pydantic-ai-1-agent-registry-core |
| `96f0071` | docs(fixing-review-D): pydantic-ai-1-agent-registry-core |

## Deviations from Plan

- `pipeline_name` property bug fix was not in the original plan (plan only covered 3 callsites: step.py, strategy.py StepDefinition, pipeline.py StepKeyDict). Review identified a 4th callsite (`PipelineConfig.pipeline_name`) with the identical single-regex bug. Fixed in review phase to keep all callsites consistent.
- `build_user_prompt()` variable_instance handling: plan specified passing `variables` as both `variables=` and `variable_instance=`. Review identified this loses the original Pydantic model reference before `model_dump()`. Implementation changed to preserve `variable_instance = variables` before mutation.
- pydantic-ai imports in `agent_builders.py`: plan did not specify lazy import strategy. Initial implementation used runtime import at module level. Review required moving to `TYPE_CHECKING` guard + lazy import inside `build_step_agent()` to honour optional dependency contract.
- Step 8 `get_agent()` method: plan had ambiguity about whether to return `output_type` or an `Agent` instance. Implemented to return output_type via `registry.get_output_type()`, with docstring noting Task 2 will provide the full `Agent` instance via `build_step_agent()`.

## Issues Encountered

### HIGH: pydantic-ai runtime import breaks optional dependency contract
`agent_builders.py` initially had `from pydantic_ai import Agent, RunContext` as a module-level import. Since `__init__.py` unconditionally imports `StepDeps` and `build_step_agent`, any `import llm_pipeline` without pydantic-ai installed raised `ImportError`. pydantic-ai is declared optional in pyproject.toml.

**Resolution:** Added `from __future__ import annotations` (enabling string-form annotations), moved `from pydantic_ai import Agent, RunContext` inside `TYPE_CHECKING` block, and added lazy import inside `build_step_agent()` function body. `StepDeps` dataclass has no pydantic_ai references and remains safely importable.

### MEDIUM: build_user_prompt loses Pydantic model reference for variable_instance
Initial implementation called `variables = variables.model_dump()` then passed the resulting dict as both `variables=` and `variable_instance=`. `PromptService` uses `hasattr(variable_instance, 'model_fields')` for diagnostic error reporting -- passing a dict degraded error messages silently.

**Resolution:** Added `variable_instance = variables` before the `model_dump()` call to preserve original model reference. `variables` binding is then mutated to dict while `variable_instance` retains the Pydantic model.

### MEDIUM: PipelineConfig.pipeline_name had same single-regex bug as LLMStep.step_name
`pipeline.py` line 274 used `re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()` (single-regex). Not in original plan scope but was inconsistent with naming.py existing after the fix.

**Resolution:** Replaced with `return to_snake_case(class_name, strip_suffix="Pipeline")`. Removed `import re` from pipeline.py as no remaining re usage existed.

### LOW: Unclosed SQLite connection warning in test
`test_create_step_sets_agent_name_on_instance` created an in-memory SQLite engine and Session without closing them, producing `ResourceWarning: unclosed database`.

**Resolution:** Added `session.close()` and `engine.dispose()` at end of test.

### Implementation step sequencing conflict (Group B)
Steps 2, 3, 4 were assigned to Group B (parallel execution) but step 3 (strategy.py) and step 2 (step.py) were landed in the same commit (1e4c51d) while step 4's doc (afa63ac) and step 2's doc (f41180b) were separate commits. No functional impact.

**Resolution:** No action needed; implementation correctness was verified in testing phase.

## Success Criteria

- [x] `llm_pipeline/naming.py` exists with `to_snake_case()` and `"HTMLParser"` -> `"html_parser"` (double-regex correct)
- [x] `LLMStep.step_name` uses `to_snake_case` and produces correct output for consecutive capitals
- [x] `StepDefinition.create_step()` uses `to_snake_case` (no inline re.sub)
- [x] `StepKeyDict._normalize_key()` uses `to_snake_case` (no inline re.sub)
- [x] `llm_pipeline/agent_registry.py` exists with `AgentRegistry` ABC following Category A pattern
- [x] `AgentRegistry.__init_subclass__` raises `ValueError` for concrete subclass without `agents=`
- [x] `AgentRegistry.__init_subclass__` skips validation for `_*` named classes
- [x] `llm_pipeline/agent_builders.py` exists with `StepDeps` dataclass (8 fields) and `build_step_agent()` factory
- [x] `StepDeps` has: session, pipeline_context, prompt_service, run_id, pipeline_name, step_name (required) + event_emitter, variable_resolver (optional None)
- [x] `build_step_agent()` returns `Agent` with `defer_model_check=True` and `@agent.instructions` registered
- [x] `StepDefinition` has `agent_name: str | None = None` field
- [x] `StepDefinition` has `step_name` property using `to_snake_case`
- [x] `StepDefinition.create_step()` sets `step._agent_name` on the created step instance
- [x] `LLMStep` has `get_agent(registry)` concrete method with agent_name override support
- [x] `LLMStep` has `build_user_prompt(variables, prompt_service, context)` concrete method
- [x] `LLMStep.create_llm_call()` emits `DeprecationWarning` with `stacklevel=2`
- [x] `PipelineConfig.__init_subclass__` accepts optional `agent_registry=` param and validates `{Prefix}AgentRegistry` naming
- [x] `PipelineConfig.AGENT_REGISTRY` ClassVar added
- [x] `pyproject.toml` has `pydantic-ai` optional dep and dev dep at `>=1.0.5`
- [x] `llm_pipeline/__init__.py` exports `AgentRegistry`, `StepDeps`, `build_step_agent`
- [x] All existing tests pass (853 -> 854 pass, 1 pre-existing UI test failure unrelated)
- [x] 51 new tests pass

## Recommendations for Follow-up

1. **Task 2 - Executor replacement**: Replace `create_llm_call()` usage in the pipeline executor with `get_agent()` + `build_step_agent()` + `agent.run_sync(deps=StepDeps(...))`. `AgentRegistry` must be required (not optional) when using the new executor path.
2. **Task 3 - Array validation**: Add `array_validation: ArrayValidationConfig | None = None` and `validation_context: ValidationContext | None = None` fields to `StepDeps` once Task 3 scope is defined. These were explicitly excluded from this task per plan.
3. **PipelineStrategy inline regex**: `PipelineStrategy.__init_subclass__` in strategy.py still contains an inline `import re` and `re.sub` for `display_name` generation (double-regex, so functionally correct). Consider partial refactor for consistency -- blocked only by the `display_name` generation which `to_snake_case` does not handle.
4. **StepDeps type annotations**: `session`, `prompt_service`, `event_emitter`, `variable_resolver` fields use `Any` to avoid circular imports. Consider replacing with `Protocol` definitions in a new `llm_pipeline/protocols.py` for better IDE support without circular dependency risk.
5. **get_agent() naming**: Currently returns `output_type` (a `Type[BaseModel]`), not an `Agent` instance. After Task 2 completes, evaluate renaming to `get_output_type()` for clarity, or updating the implementation to return a fully built `Agent` instance from the registry.
6. **Deprecation timeline**: `create_llm_call()` is deprecated with `DeprecationWarning`. Plan a removal milestone aligned with Task 2 completion and a major version bump.
