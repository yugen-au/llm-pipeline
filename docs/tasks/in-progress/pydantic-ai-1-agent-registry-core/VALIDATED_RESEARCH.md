# Research Summary

## Executive Summary

Cross-referenced all 3 research documents against actual source code (registry.py, strategy.py, step.py, pipeline.py, executor.py, types.py, service.py, variables.py, __init__.py, provider.py) and pydantic-ai v1.0.5 docs via Context7. Core codebase findings are accurate. Found 2 architectural inconsistencies between research docs, 1 missing property on StepDefinition, and 1 regex inconsistency in existing code. All 4 open items resolved via CEO Q&A. Architecture is now fully decided and ready for planning.

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
- StepKeyDict (pipeline.py:59-84) uses correct double-regex for snake_case derivation

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

### Snake-case Derivation Inconsistency (Verified)
**Source:** step.py line 261 vs strategy.py lines 59-61 vs pipeline.py lines 66-68

Three locations derive snake_case step names:
1. `StepKeyDict._normalize_key()` (pipeline.py:66-68) -- double regex (correct)
2. `StepDefinition.create_step()` (strategy.py:59-61) -- double regex (correct)
3. `LLMStep.step_name` (step.py:261) -- single regex (INCORRECT, mishandles consecutive capitals)

Example divergence: "HTMLParser" -> "html_parser" (double) vs "htmlparser" (single). CEO approved fixing this in Task 1 scope.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| AgentRegistry: instance-based (step-2) vs __init_subclass__ class-param (step-3)? | APPROVED Category A class-param. Store {step_name: output_type} class refs. build_step_agent() builds Agent instances at runtime with model string from pipeline context. "Registry = WHAT (static, declarative), Runtime = HOW (dynamic, instances)". | Resolves inconsistency between step-2 and step-3. AgentRegistry stores type references (like PipelineDatabaseRegistry stores SQLModel classes), not Agent instances. Agent instantiation is deferred to runtime via build_step_agent(). |
| StepDeps fields: minimal (3 fields) or with metadata (8 fields)? | WITH METADATA. Include run_id, pipeline_name, step_name, event_emitter, variable_resolver alongside session, pipeline_context, prompt_service. | Resolves step-2 vs step-3 field count inconsistency. 8 core+metadata fields for Task 1. Task 3 fields (array_validation, validation_context, not_found_indicators) excluded. |
| File organization: agents/ package or flat files? | FLAT FILES. agent_registry.py + agent_builders.py in llm_pipeline/ dir. | Matches existing convention (registry.py, strategy.py, step.py all top-level). No package overhead. |
| Fix LLMStep.step_name regex inconsistency now or defer? | FIX NOW. Include in Task 1 scope. | Extract double-regex to shared utility, fix step.py, use consistently in agent_registry.py and StepDefinition.step_name property. |

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
- [x] New files go at top-level llm_pipeline/ (matches registry.py, strategy.py, step.py organization)
- [x] Codebase uses str | None union syntax throughout (verified in events/types.py, pipeline.py)
- [x] AgentRegistry ClassVar stores type refs not instances (mirrors PipelineDatabaseRegistry storing Type[SQLModel] not SQLModel instances)
- [x] PipelineConfig.__init_subclass__ should validate {Prefix}AgentRegistry naming (follows {Prefix}Registry and {Prefix}Strategies precedent)
- [x] StepDefinition needs a step_name @property (create_step() derives it as local var but doesn't expose it)

## Open Items

### Deferred: validation_context Agent Constructor Parameter
Step-2 lists `validation_context` on Agent constructor but Context7 v1.0.5 docs don't show it. Only matters for Task 3 scope. Verify when Task 3 starts.

### Deferred: Agent Instance Caching Strategy
AgentRegistry stores declarations ({step_name: output_type}). Built Agent instances need to live somewhere at runtime. Options: (a) built fresh each execute() call, (b) cached on PipelineConfig instance in __init__(), (c) lazy on first access. Step-2 research says agents are lightweight and stateless, safe to build at init. This is a Task 2 integration concern -- Task 1 just provides the building blocks (AgentRegistry class, build_step_agent factory, StepDeps dataclass). Task 2 decides where to cache.

## Recommendations for Planning

1. **Create shared snake_case utility** -- extract double-regex pattern into `llm_pipeline/naming.py` (or similar). Use in LLMStep.step_name (fixing the bug), StepDefinition.step_name (new property), StepKeyDict._normalize_key, PipelineStrategy.__init_subclass__, and agent_registry.py. Single source of truth for name derivation.

2. **AgentRegistry as Category A class-param** -- `AGENTS: ClassVar[dict[str, Type[BaseModel]]]` storing `{step_name: output_type}`. __init_subclass__ with `agents=` param. get_agent_config(step_name) returns the output_type class. Follow PipelineDatabaseRegistry guard patterns (underscore skip, direct-subclass enforcement).

3. **Add agent_registry= to PipelineConfig.__init_subclass__** -- new class param alongside registry= and strategies=. Enforce `{Prefix}AgentRegistry` naming. Store as cls.AGENT_REGISTRY ClassVar. Make it optional (existing pipelines don't have it yet).

4. **StepDeps @dataclass with 8 fields** -- session, pipeline_context, prompt_service, run_id, pipeline_name, step_name, event_emitter (optional), variable_resolver (optional). No Task 3 fields.

5. **build_step_agent factory** -- accepts step_name, output_type, model (optional), system_instruction_key, retries, model_settings. Returns Agent[StepDeps, Any]. Registers @agent.instructions for dynamic system prompt injection via PromptService.

6. **StepDefinition.step_name @property** -- derive from step_class.__name__ using shared utility. Enables registry lookups without calling create_step().

7. **Add agent_name: str | None to StepDefinition** -- allows override of default step_name for agent lookup. Stored on step instance by create_step() as _agent_name.

8. **LLMStep additions (additive, non-breaking)** -- get_agent(registry) concrete method (lookup by step_name or _agent_name override), build_user_prompt(variables, prompt_service) concrete method with default impl. Deprecate create_llm_call() with DeprecationWarning.

9. **Export new symbols** -- add AgentRegistry, StepDeps, build_step_agent to llm_pipeline/__init__.py under "Agent" category.

10. **Pin pydantic-ai>=1.0.5** -- add to pyproject.toml optional dependencies (like google-generativeai). The @agent.instructions API requires v1.0.5+.
