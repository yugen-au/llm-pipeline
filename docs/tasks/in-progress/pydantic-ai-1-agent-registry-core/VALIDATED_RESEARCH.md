# Research Summary

## Executive Summary

Cross-referenced all 3 research documents against actual source code (registry.py, strategy.py, step.py, pipeline.py, executor.py, types.py, service.py, variables.py, __init__.py, provider.py) and pydantic-ai v1.0.5 docs via Context7. Core codebase findings are accurate. Found 2 architectural inconsistencies between research docs, 1 missing property on StepDefinition, 1 regex inconsistency in existing code, and several scope/field questions needing CEO input before planning can proceed.

## Domain Findings

### Codebase Architecture (Verified)
**Source:** step-1-codebase-architecture-research.md + source code

All source code references verified accurate:
- PipelineDatabaseRegistry pattern (registry.py) -- exact match
- StepDefinition fields and create_step() flow (strategy.py) -- exact match
- LLMStep methods and create_llm_call() signature (step.py) -- exact match
- execute_llm_step() flow (executor.py) -- exact match
- PromptService API (service.py) -- exact match, includes get_system_prompt and get_user_prompt with variable_instance param
- VariableResolver Protocol (variables.py) -- exact match
- PipelineConfig.__init_subclass__ naming validation (pipeline.py) -- exact match
- __init__.py exports -- exact match (24 symbols)
- Path mappings (task ref -> llm-pipeline) -- all correct

### pydantic-ai v1.0.5 API (Verified with caveats)
**Source:** step-2-pydantic-ai-agent-patterns.md + Context7 docs

Verified via Context7:
- Agent(model, output_type, deps_type, instructions, retries, name, model_settings, defer_model_check) -- confirmed
- @agent.instructions decorator with RunContext[T] -- confirmed in v1.0.5
- @agent.system_prompt decorator also exists (older API, still works) -- research uses @agent.instructions correctly
- agent.run_sync(user_prompt, deps=) returning RunResult with .output -- confirmed
- @agent.output_validator with ModelRetry -- confirmed
- Multiple @agent.instructions decorators concatenated -- confirmed

**Unverified:** `validation_context` parameter on Agent constructor. Not shown in any Context7 docs examples. May exist in source but not documented. Low risk: only relevant to Task 3, not Task 1.

### Python Patterns (Verified)
**Source:** step-3-python-registry-deprecation-patterns.md + source code

- All 6 __init_subclass__ patterns catalogued correctly against source
- Skip/guard patterns (underscore prefix, _skip_registry, direct-subclass check) -- verified
- DeprecationWarning with stacklevel=2 -- correct, codebase has zero existing warnings
- @dataclass for StepDeps -- good rationale, matches ArrayValidationConfig/ValidationContext precedent
- Python 3.11+ features inventory -- accurate

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| (pending) | (pending) | (pending) |

## Assumptions Validated
- [x] PipelineDatabaseRegistry uses __init_subclass__ with class-param syntax (verified registry.py:36)
- [x] StepDefinition is a @dataclass with step_class, system_instruction_key, user_prompt_key, instructions fields (verified strategy.py:21)
- [x] LLMStep.create_llm_call() returns ExecuteLLMStepParams dict (verified step.py:268)
- [x] Pipeline injects provider and prompt_service into call_kwargs before execute_llm_step (verified pipeline.py execution flow)
- [x] PipelineConfig.__init_subclass__ validates {Prefix}Registry and {Prefix}Strategies naming (verified pipeline.py:111-135)
- [x] pydantic-ai Agent supports deps_type with @dataclass (verified Context7 v1.0.5 docs)
- [x] pydantic-ai @agent.instructions decorator accepts RunContext[T] for dynamic system prompts (verified Context7)
- [x] @dataclass is correct choice for StepDeps over Pydantic BaseModel (matches codebase precedent, pydantic-ai examples)
- [x] DeprecationWarning is correct category for create_llm_call() deprecation (standard Python practice)
- [x] New files should go at top-level llm_pipeline/ (matches registry.py, strategy.py, step.py organization)
- [x] Codebase uses str | None union syntax throughout (verified in events/types.py, pipeline.py)

## Open Items

### Critical: AgentRegistry Pattern Inconsistency
Step-2 proposes instance-based AgentRegistry (dict with __init__, register/get methods, from_strategies classmethod).
Step-3 proposes __init_subclass__ class-param AgentRegistry (ClassVar AGENTS, `class MyAgentRegistry(AgentRegistry, agents={...})`).

These are fundamentally different. The class-param approach has a problem: Agent instances require a model string at creation time, but model is a runtime/environment concern. Static declaration at import time means the model must be hardcoded or globally configured before class definition. The instance-based approach defers agent creation to PipelineConfig.__init__ which has access to runtime config.

**Needs CEO decision.**

### Critical: StepDefinition Missing step_name Property
Research step-2 section 6 calls `step_def.step_name` in AgentRegistry.from_strategies(). But StepDefinition has NO step_name property -- the name derivation only happens inside create_step() as a local variable. Either:
1. Add a `step_name` @property to StepDefinition (clean, reusable)
2. Inline the snake_case derivation in from_strategies()

Option 1 is recommended. This is a code gap, not just a research gap.

### Medium: StepDeps Field Scope for Task 1
Step-2 includes 11 fields (core + metadata + step-specific). Step-3 includes 4 fields (minimal core). For Task 1 scope, the step-specific fields (array_validation, validation_context, not_found_indicators) belong in Task 3. But the metadata fields (run_id, pipeline_name, step_name, event_emitter, variable_resolver) are needed by @agent.instructions and event emission.

**Needs CEO decision on exact field list.**

### Medium: File Organization Undecided
Step-2 proposes two options: `agents/` package or flat `agents.py`. Step-3 proposes flat files (`agent_registry.py`, `agent_builders.py`). No decision made.

**Needs CEO decision.**

### Low: LLMStep.step_name Regex Inconsistency
step.py line 261 uses simple regex: `re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()`
strategy.py line 59-61 uses double regex: `re.sub(r'([A-Z]+)([A-Z][a-z])', ...)` then `re.sub(r'([a-z\d])([A-Z])', ...)`

These produce different results for consecutive capitals (e.g., "HTMLParser" -> "htmlparser" vs "html_parser"). Not a new issue introduced by this task, but relevant since AgentRegistry will need consistent name derivation.

### Low: validation_context Agent Constructor Parameter Unverified
Step-2 lists this parameter but Context7 v1.0.5 docs don't show it in examples. Only matters for Task 3 scope. Can defer verification.

### Low: PipelineConfig Naming Validation for AgentRegistry
If AgentRegistry is integrated via PipelineConfig.__init_subclass__ (like registry= and strategies=), should it enforce `{Prefix}AgentRegistry` naming? Step-3 recommends yes. Depends on whether AgentRegistry is class-param or instance-based (links to critical item above).

## Recommendations for Planning

1. **Resolve AgentRegistry pattern first** -- this is the foundational decision. Recommend instance-based (step-2 Option A) because Agent creation needs runtime model string. The __init_subclass__ pattern can still be used for declaration (mapping step names to output types/config), with actual Agent instantiation deferred to PipelineConfig.__init__.

2. **Add step_name @property to StepDefinition** -- prerequisite for AgentRegistry.from_strategies() or any pattern that needs step name before create_step(). Extract the snake_case logic into a shared utility.

3. **Start StepDeps minimal, extend in Task 3** -- for Task 1: session, pipeline_context, prompt_service, run_id, pipeline_name, step_name, event_emitter, variable_resolver. Exclude array_validation/validation_context/not_found_indicators (Task 3 will add them).

4. **Use flat file organization** -- agent_registry.py + agent_builders.py at llm_pipeline/ top level. Matches existing convention. Package structure (agents/) adds complexity without current benefit.

5. **Standardize snake_case derivation** -- extract the double-regex pattern from strategy.py into a utility function, use it everywhere (StepDefinition.step_name, LLMStep.step_name, AgentRegistry key derivation). Fix the inconsistency in step.py.

6. **Pin pydantic-ai>=1.0.5 in dependencies** -- ensure the @agent.instructions API is available. Add to pyproject.toml optional dependencies.
