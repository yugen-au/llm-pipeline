# Research Summary

## Executive Summary

Cross-referenced 3 research documents against source code. Found 3 contradictions between docs, 4 hidden assumptions, 1 factual error. CEO answered all 7 blocking questions. All ambiguities resolved. One new finding surfaced during CEO Q&A: LLMCallStarting.rendered_system_prompt is unavailable before agent.run_sync() because pydantic-ai resolves it internally. Workaround identified. No remaining gaps block planning.

## Domain Findings

### Architecture: Call Chain Verified
**Source:** step-1-architecture-research.md, source code
- execute_llm_step() call sites verified at pipeline.py L462, L748, L1128, L1141
- Consensus mechanism (_execute_with_consensus) at pipeline.py L1127-1185: currently accepts call_kwargs dict, calls execute_llm_step(**call_kwargs). Must change to accept agent + user_prompt + step_deps and call agent.run_sync()
- _smart_compare() and _instructions_match() verified unchanged -- operate on instruction model instances regardless of LLM call source
- Caching, state saving, extraction, transformation all verified to operate on instruction objects (no changes needed)
- model_name for state saving currently from `getattr(self._provider, 'model_name', None)` at pipeline.py L792 -- RESOLVED: use self._model (the new model string param)

### pydantic-ai API Surface Verified
**Source:** step-2-pydantic-ai-patterns.md, agent_builders.py
- Agent.run_sync() signature confirmed for v1.62.0 with model= override kwarg
- AgentRunResult.output is dataclass field (direct access), .usage() is method
- UnexpectedModelBehavior -> create_failure() mapping is correct pattern
- build_step_agent() with defer_model_check=True confirmed -- model can be set at constructor time or via run_sync(model=...)
- StepDeps dataclass confirmed with 8 fields; array_validation and validation_context to be added (CEO decision)

### Task 1 Artifacts: Ready for Task 2
**Source:** step-3-codebase-analysis.md, source code
- AgentRegistry.get_output_type() returns Type[BaseModel], NOT Agent instance -- confirmed
- build_step_agent() returns configured Agent[StepDeps, Any] -- confirmed
- LLMStep.get_agent(registry) returns output_type -- confirmed
- LLMStep.build_user_prompt(variables, prompt_service, context) -- confirmed ready
- create_llm_call() has DeprecationWarning -- confirmed at step.py L334; CEO says DELETE entirely

### Factual Error: save_step_yaml "still used"
**Source:** step-2-pydantic-ai-patterns.md vs prior VALIDATED_RESEARCH
- Step 2 claims save_step_yaml is "Still used for YAML export". This is **wrong**.
- Prior validated research confirms save_step_yaml is dead code.
- No imports of save_step_yaml exist outside executor.py itself.
- Safe to delete alongside executor.py.

### RESOLVED: Deletion Targets (GeminiProvider DELETE)
**Source:** all 3 research docs, CEO decision Q1
- CEO decided: DELETE GeminiProvider, LLMProvider, LLMCallResult entirely
- This unlocks deletion of ALL their dependencies:
  - `llm_pipeline/llm/gemini.py` (entire file)
  - `llm_pipeline/llm/provider.py` (entire file)
  - `llm_pipeline/llm/result.py` (entire file)
  - `llm_pipeline/llm/executor.py` (entire file, includes save_step_yaml)
  - `llm_pipeline/llm/schema.py` (format_schema_for_llm, flatten_schema)
  - `llm_pipeline/llm/validation.py` (validate_structured_output, validate_array_response, check_not_found_response, strip_number_prefix)
  - `llm_pipeline/llm/rate_limiter.py` (RateLimiter)
- `llm_pipeline/llm/__init__.py` must be rewritten (currently exports LLMProvider, RateLimiter, LLMCallResult, flatten_schema, format_schema_for_llm)
- `llm_pipeline/__init__.py` must remove LLMCallResult export (L31) and update docstring imports (L8-9)
- `llm_pipeline/events/__init__.py` must remove LLMCallResult import (L83) and __all__ entry (L103)

### RESOLVED: PipelineConfig Constructor API
**Source:** pipeline.py L159-183, CEO decision Q2
- Replace `provider: Optional["LLMProvider"] = None` with `model: str` (required)
- Remove `self._provider = provider` (L183), replace with `self._model = model`
- Remove provider None check at L466-468, replace with AGENT_REGISTRY check
- model_name at L792: change from `getattr(self._provider, 'model_name', None)` to `self._model`
- call_kwargs["provider"] at L732: entire block replaced by new agent flow
- Breaking change accepted by CEO

### RESOLVED: AGENT_REGISTRY Required
**Source:** pipeline.py L107, CEO decision Q3
- AGENT_REGISTRY mandatory for execute(). Add validation in execute():
  ```python
  if self.AGENT_REGISTRY is None:
      raise ValueError(f"{cls.__name__} must specify agent_registry= parameter.")
  ```
- No fallback to old execute_llm_step path

### RESOLVED: create_llm_call() DELETE NOW
**Source:** step.py L317-359, CEO decision Q7
- Delete entire create_llm_call() method from LLMStep (step.py L317-359)
- Delete ExecuteLLMStepParams from types.py (L74-89, and __all__ entry L96)
- Remove TYPE_CHECKING import of ExecuteLLMStepParams from step.py L32
- All 7 test files using create_llm_call() in step implementations must be updated:
  - `tests/events/conftest.py` (4 step classes: SimpleStep, SkippableStep, ItemDetectionStep, TransformationStep)
  - `tests/events/test_ctx_state_events.py` (local step)
  - `tests/events/test_extraction_events.py` (FailingItemDetectionStep)
  - `tests/test_introspection.py` (WidgetDetectionStep, ScanDetectionStep, GadgetDetectionStep)
  - `tests/test_pipeline.py` (WidgetDetectionStep)
  - `tests/test_pipeline_run_tracking.py` (GadgetStep)
  - `tests/test_agent_registry_core.py` (has create_llm_call in test step but only tests registry)

### RESOLVED: Event Emission -- Simplified LLM Events
**Source:** executor.py L117-176, events/types.py L319-344, CEO decision Q6
- Emit LLMCallStarting + LLMCallCompleted around agent.run_sync()
- CEO confirmed: event system is real, used by frontend StepDetailPanel.tsx
- PRD Task 4 is wrong about "no existing event system"

**NEW FINDING: rendered_system_prompt unavailable before run_sync()**
- LLMCallStarting requires `rendered_system_prompt: str` and `rendered_user_prompt: str`
- user_prompt is available (built via step.build_user_prompt() before the call)
- system_prompt is resolved INSIDE agent.run_sync() by the @agent.instructions callback
- Workaround: resolve system prompt manually before the call using the same logic as build_step_agent's _inject_system_prompt (call prompt_service.get_system_prompt() or get_prompt() directly). This duplicates the resolution but provides the rendered text for the event.
- Alternative: emit LLMCallStarting with rendered_system_prompt="" and document that system prompt is resolved internally by pydantic-ai. Less accurate but simpler.

### RESOLVED: Agent Construction Strategy
**Source:** CEO decision Q4
- Build agent ONCE per step via build_step_agent()
- Reuse same agent instance for consensus iterations
- Agent built in the per-call_params loop (one agent per step per call, reused across consensus)

### RESOLVED: StepDeps Forward Compatibility
**Source:** agent_builders.py, CEO decision Q5
- Add to StepDeps now (even if unused in Task 2):
  - `array_validation: Any | None = None`
  - `validation_context: Any | None = None`
- Task 3 will use these for output_validators

### Full Test Update Scope
**Source:** source code grep, CEO decision Q7

Tests directly testing deleted symbols (must delete/rewrite):
| Test File | Tests to Delete | Symbol |
|-----------|----------------|--------|
| `tests/test_pipeline.py` | `TestImports.test_llm_imports` | LLMProvider, RateLimiter, format_schema_for_llm |
| `tests/test_pipeline.py` | `TestSchemaUtils.test_format_schema_for_llm` | format_schema_for_llm |
| `tests/test_pipeline.py` | `TestValidation.*` | validate_structured_output |
| `tests/test_pipeline.py` | `TestRateLimiter.*` | RateLimiter |
| `tests/test_pipeline.py` | `TestStripNumberPrefix.*` | strip_number_prefix |
| `tests/test_llm_call_result.py` | entire file | LLMCallResult |
| `tests/events/test_retry_ratelimit_events.py` | entire file | GeminiProvider |
| `tests/events/test_llm_call_events.py` | `test_no_event_params_in_call_kwargs` | execute_llm_step monkeypatch |

Tests with MockProvider(LLMProvider) that must change to model= string:
| Test File | MockProvider Location |
|-----------|---------------------|
| `tests/test_pipeline.py` L38 | `class MockProvider(LLMProvider)` |
| `tests/test_pipeline_run_tracking.py` L133 | `class MockProvider(LLMProvider)` |
| `tests/test_pipeline_input_data.py` L204 | `class MockProvider(LLMProvider)` |
| `tests/events/conftest.py` L32 | `class MockProvider(LLMProvider)` |
| `tests/benchmarks/conftest.py` L38 | `class _BenchmarkMockProvider(LLMProvider)` |

Tests with create_llm_call() in step implementations (must rewrite prepare_calls):
| Test File | Step Classes |
|-----------|-------------|
| `tests/events/conftest.py` | SimpleStep, SkippableStep, ItemDetectionStep, TransformationStep |
| `tests/events/test_ctx_state_events.py` | local step |
| `tests/events/test_extraction_events.py` | FailingItemDetectionStep |
| `tests/test_introspection.py` | WidgetDetectionStep, ScanDetectionStep, GadgetDetectionStep |
| `tests/test_pipeline.py` | WidgetDetectionStep |
| `tests/test_pipeline_run_tracking.py` | GadgetStep |

### Public API / Export Cleanup
**Source:** __init__.py files

Files requiring export updates:
- `llm_pipeline/__init__.py`: remove LLMCallResult (L31), update docstring (L8-9, L13), remove from __all__ (L66)
- `llm_pipeline/llm/__init__.py`: gut entirely (all 5 current exports are deleted symbols). Becomes empty or re-exports agent_builders only
- `llm_pipeline/events/__init__.py`: remove LLMCallResult import (L83) and __all__ entry (L103)

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Q1: GeminiProvider fate? | DELETE entirely. pydantic-ai replaces provider abstraction | Unlocks deletion of GeminiProvider + LLMProvider + LLMCallResult + all helper functions (schema, validation, rate_limiter). Entire llm/ subpackage gutted. |
| Q2: PipelineConfig constructor API? | model: str, breaking change | Replace provider= with model= in __init__. Remove LLMProvider import. model_name at L792 becomes self._model. |
| Q3: AGENT_REGISTRY requirement? | REQUIRED, no fallback | Add validation in execute(). Existing pipelines without registry will fail -- intentional forcing function for migration. |
| Q4: Agent construction? | Per-step, reuse for consensus | Build agent once per step via build_step_agent(), reuse across consensus iterations within same step. |
| Q5: StepDeps forward-compat? | Add array_validation + validation_context NOW | Forward-compatible for Task 3 output_validators. Fields optional, unused in Task 2. |
| Q6: LLM event emission? | EMIT SIMPLIFIED events | Emit LLMCallStarting + LLMCallCompleted around agent.run_sync(). Frontend StepDetailPanel.tsx consumes these. PRD Task 4 is wrong about "no existing event system". |
| Q7: create_llm_call() removal? | REMOVE NOW, update all 14 test files | Delete method from LLMStep. All test step implementations must be rewritten. No deprecation period. |

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
- [x] GeminiProvider DELETE unlocks deletion of all llm/ helper modules (verified: only production caller of format_schema_for_llm, validate_structured_output, validate_array_response, check_not_found_response, RateLimiter is GeminiProvider.call_structured)
- [x] MockProvider(LLMProvider) exists in 5 test files + 1 benchmark conftest -- all must be updated
- [x] LLMCallResult exported from 3 locations (__init__.py, llm/__init__.py, events/__init__.py) -- all must be cleaned up
- [x] _execute_with_consensus must change signature from call_kwargs dict to agent + user_prompt + step_deps

## Open Items
- None. All questions answered, all ambiguities resolved. Planning can proceed.

## Recommendations for Planning
1. **Delete entire llm/ subpackage contents first** -- gemini.py, provider.py, result.py, executor.py, schema.py, validation.py, rate_limiter.py. Keep __init__.py but empty/minimal.
2. **Rewrite PipelineConfig.__init__** -- replace provider= with model: str, store as self._model
3. **Add AGENT_REGISTRY validation** in execute() -- raise ValueError if None
4. **Rewrite pipeline.py execution loop** (L729-748) -- build agent per step, call agent.run_sync(), extract .output
5. **Rewrite _execute_with_consensus** -- new signature accepting agent + user_prompt + step_deps instead of call_kwargs dict
6. **Add array_validation + validation_context to StepDeps** -- optional fields, unused in Task 2
7. **Delete create_llm_call()** from LLMStep and ExecuteLLMStepParams from types.py
8. **Emit simplified LLM events** -- LLMCallStarting before run_sync() (resolve system prompt inline for rendered_system_prompt field), LLMCallCompleted after
9. **Update all test files** -- delete tests for deleted symbols, replace MockProvider with model= string, rewrite step prepare_calls() implementations to not use create_llm_call()
10. **Clean up exports** -- __init__.py, llm/__init__.py, events/__init__.py
11. **Update model_name** at pipeline.py L792 to use self._model instead of getattr(self._provider, 'model_name', None)
12. **Handle LLMCallCompleted fields** -- model_name from self._model, attempt_count from run_result.usage() or 1, raw_response and parsed_result from run_result
