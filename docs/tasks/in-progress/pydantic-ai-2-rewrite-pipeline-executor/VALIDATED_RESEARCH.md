# Research Summary

## Executive Summary

Cross-referenced 3 research documents against source code. Found 3 contradictions between docs, 4 hidden assumptions, 1 factual error, and 7 questions requiring CEO input before planning. The central unresolved question is GeminiProvider's fate -- it gates 5 other decisions (deletion targets, constructor API, test scope, event emission, model string source).

## Domain Findings

### Architecture: Call Chain Verified
**Source:** step-1-architecture-research.md, source code
- execute_llm_step() call sites verified at pipeline.py L462, L748, L1128, L1141
- Consensus mechanism (_execute_with_consensus) verified at pipeline.py L1127-1185
- _smart_compare() and _instructions_match() verified unchanged -- operate on instruction model instances regardless of LLM call source
- Caching, state saving, extraction, transformation all verified to operate on instruction objects (no changes needed)
- model_name for state saving currently from `getattr(self._provider, 'model_name', None)` at pipeline.py L792 -- needs new source if provider removed

### pydantic-ai API Surface Verified
**Source:** step-2-pydantic-ai-patterns.md, agent_builders.py
- Agent.run_sync() signature confirmed for v1.62.0 with model= override kwarg
- AgentRunResult.output is dataclass field (direct access), .usage() is method
- UnexpectedModelBehavior -> create_failure() mapping is correct pattern
- build_step_agent() with defer_model_check=True confirmed -- model must be set at call time via run_sync(model=...) or agent constructor
- StepDeps dataclass confirmed with 8 fields, no array_validation/validation_context fields yet

### Task 1 Artifacts: Ready for Task 2
**Source:** step-3-codebase-analysis.md, source code
- AgentRegistry.get_output_type() returns Type[BaseModel], NOT Agent instance -- confirmed
- build_step_agent() returns configured Agent[StepDeps, Any] -- confirmed
- LLMStep.get_agent(registry) returns output_type -- confirmed
- LLMStep.build_user_prompt(variables, prompt_service, context) -- confirmed ready
- create_llm_call() has DeprecationWarning -- confirmed at step.py L334

### Factual Error: save_step_yaml "still used"
**Source:** step-2-pydantic-ai-patterns.md vs prior VALIDATED_RESEARCH
- Step 2 claims save_step_yaml is "Still used for YAML export". This is **wrong**.
- Prior validated research (docs/tasks/completed/adhoc-20260210-docs-generation/VALIDATED_RESEARCH.md) confirms save_step_yaml is dead code: "Legacy utility from pre-Strategy architecture... never called by PipelineConfig.execute()."
- No imports of save_step_yaml exist outside executor.py itself.
- Safe to delete alongside executor.py.

### Contradiction: Deletion Targets Depend on GeminiProvider Decision
**Source:** all 3 research docs
- Step 1 says keep format_schema_for_llm if GeminiProvider kept; lists validate_array_response and check_not_found_response as Task 3 scope
- Step 2 says delete format_schema_for_llm, validate_structured_output in Task 2; defers validate_array_response and check_not_found_response to Task 3
- Step 3 proves ALL of these functions are ONLY called by GeminiProvider.call_structured()
- **Resolution depends on Q1 below**: if GeminiProvider deleted, all its deps are deletable; if kept, none are deletable without breaking it

### Contradiction: call_gemini_with_structured_output
**Source:** step-3-codebase-analysis.md, Task 2 description
- Task 2 description says to delete `call_gemini_with_structured_output`
- This function does NOT exist in llm-pipeline. It's a legacy name from the upstream logistics-intelligence project
- The equivalent is `GeminiProvider.call_structured()` in llm_pipeline/llm/gemini.py
- Not a blocking issue -- just a naming error in the task description

### Hidden Assumption: context Parameter Gap
**Source:** executor.py vs agent_builders.py
- execute_llm_step passes `context` dict to both get_system_prompt() and get_user_prompt()
- build_step_agent's @agent.instructions does NOT pass context to prompt_service calls
- build_user_prompt() accepts context= but the proposed integration code in step-2 doesn't pass it
- Verified: context parameter is vestigial per limitations.md ("Prompt.context vestigial code"). No functional impact.

### Hidden Assumption: AGENT_REGISTRY May Be None
**Source:** pipeline.py L107, step-2-pydantic-ai-patterns.md
- All research docs assume AGENT_REGISTRY is set when calling step.get_agent(self.AGENT_REGISTRY)
- AGENT_REGISTRY defaults to None (ClassVar[Optional[Type["AgentRegistry"]]] = None)
- If None, step.get_agent(None) will raise AttributeError
- Task 2 needs decision: require AGENT_REGISTRY for execute(), or dual-path fallback?

### array_validation Regression Risk: Low
**Source:** types.py, tests/, step-1-architecture-research.md
- array_validation is in StepCallParams but no test or known consumer pipeline step populates it in prepare_calls()
- Only used within GeminiProvider.call_structured() internally
- Temporary loss of array_validation between Task 2 and Task 3 has LOW regression risk
- validation_context same situation -- only used by executor.py and GeminiProvider

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| (awaiting first CEO Q&A loop) | - | - |

## Assumptions Validated
- [x] execute_llm_step call sites are exactly L462, L748, L1128, L1141 in pipeline.py
- [x] save_step_yaml is dead code (no external callers)
- [x] call_gemini_with_structured_output does not exist (legacy naming)
- [x] Task 1 artifacts (AgentRegistry, StepDeps, build_step_agent, get_agent, build_user_prompt) are complete and correct
- [x] Caching/state/extraction/transformation logic operates on instruction objects, not LLM mechanism
- [x] context parameter in prompt resolution is vestigial (no functional impact from omitting it)
- [x] array_validation not used by any tests or known consumer -- low regression risk if temporarily dropped
- [x] pydantic-ai handles 429 retries, validation retries, and structured output natively -- replaces RateLimiter + validate_structured_output + format_schema_for_llm + JSON extraction
- [x] Consensus comparison logic (_smart_compare, _instructions_match) is source-agnostic -- no changes needed

## Open Items
- All 7 questions below block planning. Need CEO answers before proceeding.

## Recommendations for Planning
1. **Resolve Q1 first** -- GeminiProvider fate is the linchpin; it gates deletion targets, constructor API, model string source, and test scope
2. **Prefer backward-compatible constructor** -- add model= alongside provider=, deprecate provider=, rather than breaking change
3. **Build agent once per step** -- reuse for consensus calls within same step; pydantic-ai Agents are designed for reuse
4. **Emit minimal events** -- simplified LLMCallStarting/Completed around agent.run_sync() in Task 2; full event rebuild in Task 4
5. **Keep create_llm_call() deprecated** -- stop calling it in pipeline.py but don't delete method until Task 6 (tests still reference it)
6. **Require AGENT_REGISTRY for new path** -- guard with `if self.AGENT_REGISTRY is not None` to allow existing pipelines to keep working during migration
7. **Add validation_context + array_validation to StepDeps now** -- forward-compatible for Task 3, even if unused in Task 2
