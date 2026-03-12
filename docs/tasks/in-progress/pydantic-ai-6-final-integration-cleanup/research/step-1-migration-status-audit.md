# Migration Status Audit - pydantic-ai Tasks 1-5

## Summary

All 5 upstream tasks are fully implemented in the codebase. The migration from the old LLM provider pattern (create_llm_call, execute_llm_step, LLMProvider/GeminiProvider) to pydantic-ai agents (agent.run_sync, build_step_agent, StepDeps) is complete. 951 of 952 tests pass; the single failure is unrelated to the migration.

---

## Task-by-Task Verification

### Task 1: AgentRegistry and Core Agent Abstractions -- COMPLETE

| Component | File | Status |
|-----------|------|--------|
| AgentRegistry ABC | `llm_pipeline/agent_registry.py` | Present, uses `__init_subclass__` pattern |
| StepDeps dataclass | `llm_pipeline/agent_builders.py` L22-52 | Present, 10 fields including validation config |
| build_step_agent() factory | `llm_pipeline/agent_builders.py` L55-152 | Present, constructs Agent with `@agent.instructions` |
| LLMStep.get_agent() | `llm_pipeline/step.py` L263-280 | Present, looks up output_type from registry |
| LLMStep.build_user_prompt() | `llm_pipeline/step.py` L282-309 | Present, delegates to PromptService |
| StepDefinition.agent_name | `llm_pipeline/strategy.py` L39 | Present, `str | None = None` |
| naming.py utility | `llm_pipeline/naming.py` | Present, to_snake_case() |
| Exports in __init__.py | `llm_pipeline/__init__.py` L41-43, L86-92 | AgentRegistry, StepDeps, build_step_agent exported |

Tests: `tests/test_agent_registry_core.py` - comprehensive coverage of registry, builders, step integration.

### Task 2: Rewrite Pipeline Executor -- COMPLETE

| Component | File | Status |
|-----------|------|--------|
| execute() uses agent.run_sync() | `llm_pipeline/pipeline.py` L820, L1247 | Both normal and consensus paths use run_sync |
| StepDeps constructed per-call | `llm_pipeline/pipeline.py` L750-761 | Correct, includes array_validation and validation_context |
| UnexpectedModelBehavior handling | `llm_pipeline/pipeline.py` L837-838, L1260-1261 | Mapped to create_failure() |
| Old LLM files deleted | `llm_pipeline/llm/` | Only `__init__.py` stub remains |
| create_llm_call() removed | grep across all .py | Zero matches in source code |
| execute_llm_step() removed | grep across all .py | Zero matches in source code |
| LLMProvider/GeminiProvider removed | grep across all .py | Zero matches in source (1 stale docstring ref) |
| RateLimiter removed | grep across all .py | Zero matches |
| ExecuteLLMStepParams removed | grep across all .py | Zero matches |

Tests: `tests/test_pipeline.py`, `tests/test_pipeline_run_tracking.py` - use MagicMock for agent.run_sync.

### Task 3: Port Validation Logic -- COMPLETE

| Component | File | Status |
|-----------|------|--------|
| not_found_validator() factory | `llm_pipeline/validators.py` L37-60 | Async validator, uses ModelRetry |
| array_length_validator() factory | `llm_pipeline/validators.py` L63-115 | Async validator, reads from ctx.deps.array_validation |
| _reorder_items() utility | `llm_pipeline/validators.py` L118-161 | Extracted helper for array reordering |
| DEFAULT_NOT_FOUND_INDICATORS | `llm_pipeline/validators.py` L18-27 | 8 default phrases |
| Validators registered in agent | `llm_pipeline/pipeline.py` L731-734 | Both validators always registered per step |
| ArrayValidationConfig/ValidationContext | `llm_pipeline/types.py` | Retained, used by StepDeps |

Tests: `tests/test_validators.py` - dedicated validator tests with RunContext mocks.

### Task 4: OpenTelemetry/Event System -- COMPLETE

| Component | File | Status |
|-----------|------|--------|
| PipelineStepState token fields | `llm_pipeline/state.py` L99-115 | input_tokens, output_tokens, total_tokens, total_requests |
| LLMCallCompleted token fields | `llm_pipeline/events/types.py` L348-350 | input_tokens, output_tokens, total_tokens |
| StepCompleted token fields | `llm_pipeline/events/types.py` L261-263 | input_tokens, output_tokens, total_tokens |
| build_step_agent instrument= param | `llm_pipeline/agent_builders.py` L63, L113-114 | Passed to Agent constructor |
| PipelineConfig.instrumentation_settings | `llm_pipeline/pipeline.py` L170, L190 | Stored and threaded to build_step_agent |
| Token capture - normal path | `llm_pipeline/pipeline.py` L827-836 | From run_result.usage() |
| Token capture - consensus path | `llm_pipeline/pipeline.py` L1249-1259 | Per-attempt with accumulation |
| _save_step_state token args | `llm_pipeline/pipeline.py` L906-911 | All 4 token fields saved |
| otel optional deps | `pyproject.toml` L26-29 | opentelemetry-sdk, exporter-otlp |

Tests: `tests/test_token_tracking.py` - 7 test classes covering normal, consensus, None usage, instrumentation threading.

### Task 5: Consensus Strategy Pattern -- COMPLETE

| Component | File | Status |
|-----------|------|--------|
| ConsensusStrategy ABC | `llm_pipeline/consensus.py` L105-143 | name, max_attempts, threshold, should_continue, select |
| ConsensusResult model | `llm_pipeline/consensus.py` L87-98 | Frozen Pydantic model with 7 fields |
| MajorityVoteStrategy | `llm_pipeline/consensus.py` L150-204 | Reproduces original behavior |
| ConfidenceWeightedStrategy | `llm_pipeline/consensus.py` L207-296 | Weighted by confidence_score |
| AdaptiveStrategy | `llm_pipeline/consensus.py` L299-366 | Lowers threshold at 70% progress |
| SoftVoteStrategy | `llm_pipeline/consensus.py` L369-429 | Picks highest avg confidence group |
| _smart_compare() extracted | `llm_pipeline/consensus.py` L43-67 | Module-level utility |
| instructions_match() extracted | `llm_pipeline/consensus.py` L70-80 | Module-level utility |
| StepDefinition.consensus_strategy | `llm_pipeline/strategy.py` L41 | `ConsensusStrategy | None = None` |
| _execute_with_consensus() updated | `llm_pipeline/pipeline.py` L1212-1341 | Uses strategy.should_continue() and strategy.select() |
| Consensus events | `llm_pipeline/events/types.py` L386-428 | ConsensusStarted, Attempt, Reached, Failed |

Tests: `tests/test_consensus.py` - comprehensive coverage of all 4 strategies + utility functions.

---

## Issues Found

### 1. pydantic-ai is optional but used at runtime (DECISION NEEDED)

`pydantic-ai` is listed under `[project.optional-dependencies]` in pyproject.toml L24, but it's imported at runtime in:
- `llm_pipeline/pipeline.py` L470: `from pydantic_ai import UnexpectedModelBehavior`
- `llm_pipeline/pipeline.py` L1222: same
- `llm_pipeline/agent_builders.py` L101: `from pydantic_ai import Agent, RunContext`
- `llm_pipeline/validators.py` L14: `from pydantic_ai import ModelRetry, RunContext` (module-level)

Without pydantic-ai installed, importing `llm_pipeline.validators` will fail immediately. `pipeline.execute()` will also fail. This is effectively a hard dependency.

### 2. gemini optional dep may be dead (DECISION NEEDED)

`pyproject.toml` L23: `gemini = ["google-generativeai>=0.3.0"]` and L34 in dev deps. GeminiProvider was deleted in Task 2. The library no longer uses google-generativeai directly; pydantic-ai handles model backends. Unless downstream consumers need this dep, it appears dead.

### 3. Stale __pycache__ in llm/ subpackage (cleanup item)

`llm_pipeline/llm/__pycache__/` contains .pyc files for deleted modules: rate_limiter, schema, validation, result, provider, gemini, executor. Harmless but messy. Should be cleaned.

### 4. Stale docstring reference to GeminiProvider (cleanup item)

`llm_pipeline/prompts/variables.py` L26: `provider=GeminiProvider()` in the docstring example. Should be updated to use `model='...'` pattern.

### 5. llm/ subpackage is now a stub (cleanup item)

`llm_pipeline/llm/__init__.py` contains only: `# LLM subpackage - provider abstraction removed, use pydantic-ai agents via agent_builders.py`. No code. Could be deleted along with __pycache__.

### 6. Pre-existing test failure (not migration related)

`tests/test_ui.py::TestRoutersIncluded::test_events_router_prefix` - asserts prefix `/events` but actual is `/runs/{run_id}/events`. Unrelated to pydantic-ai migration.

---

## Test Results

```
951 passed, 1 failed, 6 skipped (119.36s)
```

- 6 skipped: benchmark tests (--benchmark-skip in pytest config)
- 1 failed: test_events_router_prefix (UI test, not migration related)
- All migration-relevant tests pass: test_pipeline, test_agent_registry_core, test_validators, test_consensus, test_token_tracking, all events/ tests

---

## Files Modified/Created by Migration

### New files (tasks 1-5):
- `llm_pipeline/agent_registry.py`
- `llm_pipeline/agent_builders.py`
- `llm_pipeline/validators.py`
- `llm_pipeline/consensus.py`
- `llm_pipeline/naming.py`
- `tests/test_agent_registry_core.py`
- `tests/test_validators.py`
- `tests/test_consensus.py`
- `tests/test_token_tracking.py`

### Modified files:
- `llm_pipeline/__init__.py` - added exports for new modules
- `llm_pipeline/pipeline.py` - execute() rewritten to use agent.run_sync(), consensus uses Strategy pattern
- `llm_pipeline/step.py` - added get_agent(), build_user_prompt()
- `llm_pipeline/strategy.py` - added agent_name, consensus_strategy fields
- `llm_pipeline/state.py` - added token fields
- `llm_pipeline/events/types.py` - added token fields to events, consensus events
- `llm_pipeline/types.py` - StepCallParams simplified (removed old fields)
- `pyproject.toml` - added pydantic-ai, otel optional deps

### Deleted files:
- `llm_pipeline/llm/provider.py`
- `llm_pipeline/llm/gemini.py`
- `llm_pipeline/llm/executor.py`
- `llm_pipeline/llm/utils.py`
- `llm_pipeline/llm/rate_limiter.py`
- `llm_pipeline/llm/schema.py`
- `llm_pipeline/llm/result.py`
- `llm_pipeline/llm/validation.py`

---

## Conclusion

Migration is structurally complete. No old patterns remain in source code. All new patterns (AgentRegistry, build_step_agent, StepDeps, ConsensusStrategy, validators, OTel) are implemented and tested. Task 6 cleanup items are: dependency classification fix, dead dep removal, stale docstring, stub subpackage deletion, __pycache__ cleanup.
