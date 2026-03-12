# PLANNING

## Summary

Implement AgentRegistry (Category A class-param pattern, stores `{step_name: output_type}` type refs), StepDeps dataclass (8 fields for pipeline DI), build_step_agent() factory, update StepDefinition with agent_name field and step_name property, update LLMStep with get_agent()/build_user_prompt() methods and deprecate create_llm_call(), extract shared snake_case utility to fix LLMStep.step_name regex bug. All changes are additive/backward-compatible -- Task 2 handles actual executor replacement.

## Plugin & Agents

**Plugin:** backend-development, python-development, llm-application-dev
**Subagents:** [available agents]
**Skills:** [available skills]

## Phases

1. **Shared Utility**: Extract snake_case normalization into `llm_pipeline/naming.py` to fix regex bug
2. **New Abstractions**: Create `agent_registry.py` and `agent_builders.py` with AgentRegistry, StepDeps, build_step_agent
3. **Updates**: Modify StepDefinition, LLMStep, PipelineConfig, pyproject.toml, and __init__.py

## Architecture Decisions

### Snake-case Utility Extraction

**Choice:** Create `llm_pipeline/naming.py` with a `to_snake_case(name: str) -> str` function using the double-regex pattern. Import it into step.py (fix bug), strategy.py, pipeline.py, and agent_registry.py.

**Rationale:** Three locations currently inline identical logic; step.py uses the wrong single-regex variant. Extracting ensures a single source of truth. Codebase convention is modular files at top level (registry.py, strategy.py, types.py).

**Alternatives:** Inline the double-regex in step.py only. Rejected: duplicated logic with no single authority.

### AgentRegistry as Category A Class-Param

**Choice:** `AgentRegistry(ABC)` with `agents: ClassVar[dict[str, Type[BaseModel]]]` storing `{step_name: output_type}` type refs. `__init_subclass__(agents=None)` guard pattern mirrors PipelineDatabaseRegistry exactly (underscore skip + direct-subclass enforcement). `get_output_type(step_name)` accessor. build_step_agent() called at runtime by Task 2.

**Rationale:** CEO decision. Matches PipelineDatabaseRegistry pattern (registry = WHAT, runtime = HOW). Stores type refs not Agent instances -- consistent with how PipelineDatabaseRegistry stores Type[SQLModel] not instances.

**Alternatives:** Instance-based dict registry (step-2 Option A). Rejected by CEO in favour of class-param pattern.

### StepDeps as @dataclass with 8 Fields

**Choice:** `@dataclass class StepDeps` with: session, pipeline_context, prompt_service (required); run_id, pipeline_name, step_name (required metadata); event_emitter, variable_resolver (optional, default None). No Task 3 fields (array_validation, validation_context, not_found_indicators).

**Rationale:** CEO decision. pydantic-ai official examples use @dataclass for deps. No validation/serialization needed. Matches ArrayValidationConfig/ValidationContext precedent in types.py. Task 3 will add its fields later.

**Alternatives:** Pydantic BaseModel. Rejected: requires arbitrary_types_allowed, unnecessary overhead.

### build_step_agent() in agent_builders.py

**Choice:** Factory function that accepts step_name, output_type, model (optional, defer_model_check=True when None), system_instruction_key, retries, model_settings. Registers a single `@agent.instructions` decorator that resolves system prompt via PromptService (with variable_resolver support). Returns `Agent[StepDeps, Any]`.

**Rationale:** Centralizes Agent construction pattern. defer_model_check=True allows testing without API keys (confirmed in pydantic-ai v1.0.5 docs). Variable resolver logic mirrors current create_llm_call() pattern.

**Alternatives:** Build agents inline in PipelineConfig. Rejected: not testable, not reusable.

### PipelineConfig agent_registry= Param (Optional)

**Choice:** Add optional `agent_registry=` to `PipelineConfig.__init_subclass__`. Validate `{Prefix}AgentRegistry` naming. Store as `cls.AGENT_REGISTRY: ClassVar`. Do NOT raise if absent (existing pipelines have no registry yet).

**Rationale:** Follows existing registry= and strategies= precedent. Optional to maintain backward compatibility -- Task 2 will require it when doing agent.run_sync(). Naming convention validated upfront for fail-fast behaviour.

**Alternatives:** No PipelineConfig integration in Task 1. Deferred to Task 2. Rejected: naming validation belongs at definition time, not runtime.

### Deprecation of create_llm_call()

**Choice:** Add `warnings.warn("create_llm_call() is deprecated, use get_agent() + build_user_prompt() instead", DeprecationWarning, stacklevel=2)` at the top of the method body. Keep full implementation unchanged.

**Rationale:** Standard Python deprecation pattern. stacklevel=2 points warning at caller. DeprecationWarning is correct category (shown in test output, hidden in production by default). Zero existing warnings in codebase -- this establishes the convention.

**Alternatives:** Remove immediately. Rejected: Task 2 has not replaced the executor yet.

## Implementation Steps

### Step 1: Create naming.py Utility

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Create `llm_pipeline/naming.py` with `to_snake_case(name: str, strip_suffix: str | None = None) -> str` function
2. Implement using double-regex: `re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', name)` then `re.sub(r'([a-z\d])([A-Z])', r'\1_\2', result).lower()`
3. If strip_suffix provided and name ends with it, strip before converting
4. Add `__all__ = ["to_snake_case"]`

### Step 2: Fix LLMStep.step_name in step.py

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. Add `from llm_pipeline.naming import to_snake_case` import to `llm_pipeline/step.py`
2. In `LLMStep.step_name` property (line ~252-262): replace single-regex inline logic with `return to_snake_case(class_name[:-4])` (strip 'Step' suffix before converting, or pass strip_suffix='Step')
3. Verify the fixed property no longer uses `re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()` (old single-regex)

### Step 3: Fix StepDefinition snake_case in strategy.py

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. Add `from llm_pipeline.naming import to_snake_case` import to `llm_pipeline/strategy.py`
2. In `StepDefinition.create_step()` (lines ~57-61): replace inline double-regex block with `step_name = to_snake_case(step_class_name, strip_suffix='Step')`
3. Remove the `import re` local import if no other re usage remains in create_step (check full method)

### Step 4: Fix StepKeyDict._normalize_key in pipeline.py

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. Add `from llm_pipeline.naming import to_snake_case` import to `llm_pipeline/pipeline.py`
2. In `StepKeyDict._normalize_key()` (lines ~63-68): replace inline double-regex with `return to_snake_case(class_name[:-4])` where class_name is `key.__name__`
3. Remove inline `re.sub` calls from the method

### Step 5: Create agent_registry.py

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /pydantic/pydantic-ai
**Group:** C

1. Create `llm_pipeline/agent_registry.py`
2. Import: `ABC` from abc, `ClassVar, Type` from typing, `BaseModel` from pydantic, `to_snake_case` from llm_pipeline.naming
3. Define `AgentRegistry(ABC)` class:
   - `AGENTS: ClassVar[dict[str, Type[BaseModel]]] = {}`
   - `__init_subclass__(cls, agents=None, **kwargs)`: call super, if agents is not None set `cls.AGENTS = agents`, elif not cls.__name__.startswith('_') and cls.__bases__[0] is AgentRegistry raise ValueError requiring agents param with example syntax
   - `get_output_type(cls, step_name: str) -> Type[BaseModel]` classmethod: raise KeyError if not found, return `cls.AGENTS[step_name]`
4. Add `__all__ = ["AgentRegistry"]`

### Step 6: Create agent_builders.py

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /pydantic/pydantic-ai
**Group:** C

1. Create `llm_pipeline/agent_builders.py`
2. Imports: `dataclass` from dataclasses, `Any, TYPE_CHECKING` from typing, `Agent, RunContext` from pydantic_ai; TYPE_CHECKING guard for PromptService, PipelineEventEmitter, VariableResolver, Session imports
3. Define `@dataclass class StepDeps` with fields:
   - Required: `session: Any` (avoid circular import with Session type), `pipeline_context: dict[str, Any]`, `prompt_service: Any`
   - Required metadata: `run_id: str`, `pipeline_name: str`, `step_name: str`
   - Optional: `event_emitter: Any | None = None`, `variable_resolver: Any | None = None`
4. Define `build_step_agent(step_name, output_type, model=None, system_instruction_key=None, retries=3, model_settings=None) -> Agent[StepDeps, Any]`:
   - Construct `Agent(model=model, output_type=output_type, deps_type=StepDeps, name=step_name, retries=retries, model_settings=model_settings, defer_model_check=True)`
   - Register `@agent.instructions` decorated function `_inject_system_prompt(ctx: RunContext[StepDeps]) -> str`:
     - Resolve sys_key = system_instruction_key or step_name
     - If ctx.deps.variable_resolver: resolve var_class, instantiate system_variables, call get_system_prompt with variable_instance
     - Else: call prompt_service.get_prompt(sys_key, 'system') for raw prompt string
   - Return agent
5. Add `__all__ = ["StepDeps", "build_step_agent"]`

### Step 7: Add agent_name field and step_name property to StepDefinition

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** D

1. In `llm_pipeline/strategy.py`, add `agent_name: str | None = None` field to `StepDefinition` dataclass (after `context: Optional[Type] = None` field, before methods)
2. Add `step_name` property to `StepDefinition`: use `to_snake_case(self.step_class.__name__, strip_suffix='Step')` and return result (to_snake_case already imported from Step 3)
3. In `create_step()` method: after constructing step instance, also set `step._agent_name = self.agent_name` on the step (for get_agent() override lookup in Step 8)

### Step 8: Add get_agent() and build_user_prompt() to LLMStep; deprecate create_llm_call()

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /pydantic/pydantic-ai
**Group:** D

1. In `llm_pipeline/step.py`, add TYPE_CHECKING import for `AgentRegistry` from llm_pipeline.agent_registry and `Agent` from pydantic_ai
2. Add `get_agent(self, registry: 'AgentRegistry') -> 'Agent'` concrete method:
   - `agent_name = getattr(self, '_agent_name', None) or self.step_name`
   - Return `registry.get_output_type(agent_name)` -- NOTE: get_output_type returns the type; actual Agent building is Task 2. This method returns the output_type for now, or alternatively accept that this returns output_type and rename to `get_output_type`. Use the research-consistent name `get_agent` but return output_type with docstring noting Task 2 will provide the full Agent instance.
   - Alternative cleaner approach: registry.get_output_type() returns type ref; LLMStep.get_output_type() wraps it. Rename to match. Confirm naming with research: VALIDATED_RESEARCH says "get_agent(registry) concrete method (lookup by step_name or agent_name override)". Keep get_agent name, returns the type for now.
3. Add `build_user_prompt(self, variables: dict[str, Any], prompt_service: Any, context: dict[str, Any] | None = None) -> str` concrete method:
   - If variables has model_dump: call it
   - Return `prompt_service.get_user_prompt(self.user_prompt_key, variables=variables, variable_instance=variables, context=context)`
4. In `create_llm_call()`: add `warnings.warn("create_llm_call() is deprecated, use get_agent() + build_user_prompt() instead", DeprecationWarning, stacklevel=2)` as first statement; keep rest of implementation unchanged
5. Add `import warnings` to file imports

### Step 9: Update PipelineConfig to accept agent_registry= param

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** E

1. In `llm_pipeline/pipeline.py`, add `AGENT_REGISTRY: ClassVar[Optional[Type['AgentRegistry']]] = None` class variable alongside REGISTRY and STRATEGIES
2. In `__init_subclass__(cls, registry=None, strategies=None, **kwargs)`: add `agent_registry=None` param; when agent_registry is not None validate `{prefix}AgentRegistry` naming and set `cls.AGENT_REGISTRY = agent_registry`; naming validation: `expected = f"{pipeline_name_prefix}AgentRegistry"` -- but only run prefix validation if cls has Pipeline suffix (reuse existing pipeline_name_prefix logic, ensure branch only triggered when registry or strategies or agent_registry is not None)
3. Add TYPE_CHECKING import for AgentRegistry from llm_pipeline.agent_registry

### Step 10: Add pydantic-ai optional dependency to pyproject.toml

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** E

1. In `pyproject.toml`, add `pydantic-ai = ["pydantic-ai>=1.0.5"]` to `[project.optional-dependencies]`
2. Add `"pydantic-ai>=1.0.5"` to the `dev` optional-dependencies list (so tests can import pydantic_ai)

### Step 11: Update __init__.py exports

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** F

1. In `llm_pipeline/__init__.py`, add imports:
   - `from llm_pipeline.agent_registry import AgentRegistry`
   - `from llm_pipeline.agent_builders import StepDeps, build_step_agent`
2. Add "Agent" category section to `__all__` list with entries: `"AgentRegistry"`, `"StepDeps"`, `"build_step_agent"`

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| to_snake_case utility changes existing step name derivation | High | Unit test that HTMLParser -> "html_parser" (not "htmlparser") before and after; verify no existing step names change for normal CamelCase inputs |
| Circular imports between agent_builders.py and step.py/strategy.py | Medium | Use TYPE_CHECKING guards for all cross-module type refs; use `Any` for runtime types |
| pydantic-ai import at module level fails if not installed | Medium | Only import pydantic_ai inside agent_builders.py; existing code has no pydantic_ai dependency; make it optional dependency; users who don't use AgentRegistry don't need it |
| get_agent() naming confusion (returns output_type, not Agent instance) | Low | Clear docstring explaining it returns output_type ref; full Agent available via build_step_agent(); Task 2 doc clarifies integration |
| StepDefinition.step_name property name collision | Low | Check that no existing code accesses step_def.step_name (it's currently only a local var in create_step()); add property is additive |
| PipelineConfig.agent_registry= param validation triggers on abstract subclasses | Low | Guard on pipeline suffix check: only validate if cls.__name__.endswith('Pipeline'), matches existing registry/strategies guard |

## Success Criteria

- [ ] `llm_pipeline/naming.py` exists with `to_snake_case()` and `"HTMLParser"` -> `"html_parser"` (double-regex correct)
- [ ] `LLMStep.step_name` uses `to_snake_case` and produces correct output for consecutive capitals
- [ ] `StepDefinition.create_step()` uses `to_snake_case` (no inline re.sub)
- [ ] `StepKeyDict._normalize_key()` uses `to_snake_case` (no inline re.sub)
- [ ] `llm_pipeline/agent_registry.py` exists with `AgentRegistry` ABC following Category A pattern
- [ ] `AgentRegistry.__init_subclass__` raises ValueError for concrete subclass without `agents=`
- [ ] `AgentRegistry.__init_subclass__` skips validation for `_*` named classes
- [ ] `llm_pipeline/agent_builders.py` exists with `StepDeps` dataclass (8 fields) and `build_step_agent()` factory
- [ ] `StepDeps` has: session, pipeline_context, prompt_service, run_id, pipeline_name, step_name (required) + event_emitter, variable_resolver (optional None)
- [ ] `build_step_agent()` returns `Agent` with `defer_model_check=True` and `@agent.instructions` registered
- [ ] `StepDefinition` has `agent_name: str | None = None` field
- [ ] `StepDefinition` has `step_name` property using `to_snake_case`
- [ ] `StepDefinition.create_step()` sets `step._agent_name` on the created step instance
- [ ] `LLMStep` has `get_agent(registry)` concrete method with agent_name override support
- [ ] `LLMStep` has `build_user_prompt(variables, prompt_service, context)` concrete method
- [ ] `LLMStep.create_llm_call()` emits `DeprecationWarning` with `stacklevel=2`
- [ ] `PipelineConfig.__init_subclass__` accepts optional `agent_registry=` param and validates `{Prefix}AgentRegistry` naming
- [ ] `PipelineConfig.AGENT_REGISTRY` ClassVar added
- [ ] `pyproject.toml` has `pydantic-ai` optional dep and dev dep at `>=1.0.5`
- [ ] `llm_pipeline/__init__.py` exports `AgentRegistry`, `StepDeps`, `build_step_agent`
- [ ] All existing tests pass (no regressions from naming.py refactor)

## Phase Recommendation

**Risk Level:** medium
**Reasoning:** Changes touch 5 existing files (step.py, strategy.py, pipeline.py, pyproject.toml, __init__.py) plus create 3 new files. The snake_case refactor across 3 files is the main regression risk -- existing step names must remain identical for all existing CamelCase inputs. New abstractions are purely additive. No executor replacement yet (Task 2).
**Suggested Exclusions:** review
