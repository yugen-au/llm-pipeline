# PRD: pydantic.ai Migration for LLM Pipeline

## Overview

Replace the custom LLM provider layer (`call_gemini_with_structured_output`, `execute_llm_step`, `RateLimiter`, custom validation/retry) with pydantic.ai `Agent` instances. The pipeline framework (steps, strategies, extractions, transformations) remains unchanged -- only the LLM call interface changes.

### Reference Implementation

`logistics_intelligence/core/llm/agentic_extraction/agent.py` already uses pydantic.ai successfully in this codebase. Pattern: `Agent("google-gla:gemini-2.5-flash", deps_type=..., output_type=..., instructions=...)` with `@agent.tool` decorators and `agent.run_sync()`.

### Current Call Chain

```
PipelineConfig.execute()
  -> step.prepare_calls() -> [{variables: User(...)}]
  -> step.create_llm_call() -> ExecuteLLMStepParams dict
  -> execute_llm_step(**params)
       -> PromptService.get_prompt() (DB lookup + variable templating)
       -> call_gemini_with_structured_output()
            -> gemini_rate_limiter.wait_if_needed()
            -> google.generativeai (raw SDK)
            -> JSON extraction from markdown
            -> validate_structured_output() + validate_array_response()
            -> Pydantic model_validate()
            -> retry loop (3 retries, exponential backoff on 429)
       -> returns instruction instance or create_failure()
```

### Target Call Chain

```
PipelineConfig.execute()
  -> step.prepare_calls() -> [{variables: User(...)}]
  -> step.get_agent() -> Agent from AgentRegistry
  -> agent.run_sync(user_prompt, deps=step_deps)
       -> pydantic.ai handles: model call, structured output, retries, 429s
       -> output validators handle: not_found checks, array validation
       -> returns RunResult.output (instruction instance)
```

---

## Task 1: AgentRegistry + Core Abstractions

### Goal

Create `AgentRegistry` that maps step names to pydantic.ai `Agent` instances. Establish the new step-to-agent contract. All agents are `Agent` instances (simple ones just have no tools).

### Requirements

1. **Create `AgentRegistry` class** in `logistics_intelligence/core/schemas/pipeline/agent_registry.py`
   - Follow `PipelineDatabaseRegistry.__init_subclass__` pattern from `registry.py`
   - Subclasses declare agents via class-level dict or `__init_subclass__` params
   - Each agent entry: name (str) -> `Agent` instance
   - A single agent definition can be shared across multiple steps
   - Registry validates all referenced step names exist at class definition time

2. **Create `StepDeps` dataclass** for agent dependencies
   - Contains: `session` (ReadOnlySession), `pipeline_context` (dict), `prompt_service` (PromptService), `validation_context` (ValidationContext | None)
   - Passed as `deps=` to `agent.run_sync()`
   - Accessible in tools/validators via `RunContext[StepDeps]`

3. **Create agent builder utilities** in `logistics_intelligence/core/schemas/pipeline/agent_builders.py`
   - `build_step_agent(name, output_type, model, instructions_fn, validators, retries)` factory
   - `output_type` = the step's `LLMResultMixin` subclass (e.g., `TableTypeDetectionInstructions`)
   - `instructions_fn` = callback that receives `StepDeps` and returns system prompt string (fetched from DB via PromptService)
   - Use `@agent.instructions` decorator for dynamic prompt injection from DB

4. **Add `agent_name` field to `StepDefinition`** in `strategy.py`
   - Optional field, defaults to step's snake_case name
   - Used to look up agent from registry
   - Allows multiple steps to share one agent

5. **Update `LLMStep` base class** in `step.py`
   - Add `get_agent(registry) -> Agent` method that resolves agent from registry by name
   - Keep `prepare_calls()` contract (returns variable dicts for user prompt construction)
   - Add `build_user_prompt(variables) -> str` method -- formats user prompt from variables + DB template
   - Deprecate `create_llm_call()` (keep for backward compat, mark with warnings.warn)

### Affected Files

| Action | File | What Changes |
|--------|------|--------------|
| CREATE | `schemas/pipeline/agent_registry.py` | New AgentRegistry base class |
| CREATE | `schemas/pipeline/agent_builders.py` | Agent factory utilities, StepDeps |
| MODIFY | `schemas/pipeline/strategy.py` | Add `agent_name` to StepDefinition |
| MODIFY | `schemas/pipeline/step.py` | Add `get_agent()`, `build_user_prompt()`, deprecate `create_llm_call()` |
| MODIFY | `schemas/pipeline/__init__.py` | Export new classes |
| MODIFY | `schemas/pydantic_models.py` | Add StepDeps TypedDict/dataclass |

### Acceptance Criteria

- [ ] `AgentRegistry` subclass can declare agents with `__init_subclass__` pattern
- [ ] `StepDeps` dataclass passes type checking and works with `RunContext[StepDeps]`
- [ ] Agent builder creates valid `Agent` instances with dynamic instructions from DB prompts
- [ ] `LLMStep.get_agent()` resolves from registry
- [ ] `LLMStep.build_user_prompt()` produces same prompt text as current `execute_llm_step()` prompt resolution
- [ ] Existing `create_llm_call()` still works (deprecated but functional)
- [ ] Unit tests for registry, builder, and step changes

---

## Task 2: Executor Rewrite

### Goal

Rewrite `PipelineConfig.execute()` to use pydantic.ai agents instead of `execute_llm_step()`. Keep caching, state saving, extraction, and transformation logic intact.

### Requirements

1. **Update `PipelineConfig.execute()` in `config.py`**
   - Replace `execute_llm_step(**call_kwargs)` call with `agent.run_sync(user_prompt, deps=step_deps)`
   - Build `StepDeps` from pipeline state (session, context, prompt_service)
   - Extract result via `run_result.output` (replaces raw dict -> Pydantic validation)
   - Keep step iteration, caching, state saving, extraction, transformation unchanged
   - Keep consensus path (calls agent multiple times, uses `_instructions_match()`)
   - Emit existing events (Prepared, Starting, Completed) at same points

2. **Update `LLMStep.create_llm_call()` callers**
   - `execute()` currently calls `step.create_llm_call()` to get `ExecuteLLMStepParams`
   - Replace with: `step.get_agent(registry)` + `step.build_user_prompt(variables)`
   - Pass to `agent.run_sync(user_prompt, deps=step_deps)`

3. **Handle failure cases**
   - `create_failure()` currently returned on LLM errors -- map `UnexpectedModelBehavior` to `create_failure()`
   - `check_not_found_response()` moves to output validator (Task 3), but executor must handle the result

4. **Update `_execute_with_consensus()`**
   - Same logic: run agent N times, compare via `_instructions_match()`
   - Use `agent.run_sync()` in loop instead of `execute_llm_step()`
   - Token usage from `run_result.usage()` for logging

5. **Delete `execute_llm_step()` and `call_gemini_with_structured_output()`** from `utils.py`
   - Move remaining utility functions (`flatten_schema`, `save_step_yaml`) if still needed
   - Delete `format_schema_for_llm()`, `validate_structured_output()`, `validate_array_response()` (pydantic.ai handles structured output natively)
   - Keep `check_not_found_response()` temporarily (used by output validator in Task 3)

6. **Delete `RateLimiter`** from `rate_limiter.py`
   - pydantic.ai's HTTP transport handles 429 retry with backoff
   - Delete `gemini_rate_limiter` global instance
   - Remove import from `__init__.py`

### Affected Files

| Action | File | What Changes |
|--------|------|--------------|
| MODIFY | `schemas/pipeline/config.py` | Rewrite execute() and _execute_with_consensus() |
| MODIFY | `core/llm/utils.py` | Delete execute_llm_step, call_gemini, format_schema, validate_structured_output, validate_array_response |
| DELETE | `core/llm/rate_limiter.py` | Entire file |
| MODIFY | `core/llm/__init__.py` | Remove rate_limiter exports, update utils exports |
| MODIFY | `schemas/pydantic_models.py` | Deprecate ExecuteLLMStepParams (keep StepCallParams if still used) |

### Acceptance Criteria

- [ ] `PipelineConfig.execute()` runs steps via `agent.run_sync()` instead of `execute_llm_step()`
- [ ] Consensus polling still works (N runs, matching comparison)
- [ ] Caching, state saving, extraction, transformation unchanged
- [ ] Pipeline events (Prepared, Starting, Completed) still emitted
- [ ] `RateLimiter` deleted, 429s handled by pydantic.ai
- [ ] `execute_llm_step()`, `call_gemini_with_structured_output()` deleted
- [ ] All existing pipeline tests pass (adapted for new call pattern)
- [ ] Rate card parser end-to-end test passes

---

## Task 3: Validation Port to Output Validators

### Goal

Port custom validation logic (`not_found_indicators`, `ArrayValidationConfig`, schema validation) to pydantic.ai `@agent.output_validator` decorators. Delete `validation.py`.

### Requirements

1. **Create validator factories** in `logistics_intelligence/core/schemas/pipeline/validators.py`

   ```python
   def not_found_validator(indicators: list[str]):
       """Factory: returns output validator that checks for not-found responses."""
       def validator(ctx: RunContext[StepDeps], data: T) -> T:
           # Check string fields for indicator phrases
           # Raise ModelRetry if found (tells LLM to try again)
           # Or return create_failure() -- decision: use ModelRetry for retry,
           # but if max retries exhausted, catch UnexpectedModelBehavior in executor
           # and call create_failure()
           ...
       return validator

   def array_length_validator(expected_length: int, match_field: str):
       """Factory: validates output array length matches input array."""
       def validator(ctx: RunContext[StepDeps], data: T) -> T:
           # Access expected_length from closure or ctx.deps
           # Raise ModelRetry('Expected {n} items, got {m}') on mismatch
           ...
       return validator
   ```

2. **Port `check_not_found_response()` logic**
   - Current: checks string fields for phrases like "not found", "unable to determine", "no data"
   - New: `@agent.output_validator` that inspects output model fields
   - Raise `ModelRetry` to give LLM another chance, or return `create_failure()` for genuine not-found

3. **Port `validate_array_response()` logic**
   - Current: validates array length, order, reordering support, number prefix stripping
   - New: output validator that checks array fields against expected input
   - `ArrayValidationConfig` data moves to `StepDeps` (accessible via `RunContext`)
   - `strip_number_prefix` and `allow_reordering` logic preserved

4. **Port `ValidationContext` usage**
   - Current: passed as `context=` to `model_validate()` for `@model_validator` access
   - New: use pydantic.ai's `validation_context` param on Agent constructor
   - Or pass via `StepDeps` and access in output validators via `ctx.deps`

5. **Update agent builders** to accept validator lists
   - `build_step_agent(..., validators=[not_found_validator([...]), array_length_validator(...)])`
   - Each validator registered via `@agent.output_validator`

6. **Delete `validation.py`** after porting
   - `ArrayValidationConfig` moves to `validators.py` or `StepDeps`
   - `ValidationContext` usage replaced by `StepDeps` + `RunContext`

7. **Drop `strict_types`** -- pydantic.ai validates output against Pydantic model natively

### Affected Files

| Action | File | What Changes |
|--------|------|--------------|
| CREATE | `schemas/pipeline/validators.py` | Validator factories (not_found, array_length) |
| DELETE | `schemas/validation.py` | Entire file (after porting) |
| MODIFY | `schemas/pipeline/agent_builders.py` | Accept and register validators |
| MODIFY | `core/llm/utils.py` | Delete check_not_found_response, validate_array_response |
| MODIFY | Step files using ArrayValidationConfig | Update to pass config via StepDeps |

### Acceptance Criteria

- [ ] `not_found_validator` factory produces working `@agent.output_validator`
- [ ] `array_length_validator` factory validates array output length/order
- [ ] `ModelRetry` triggers LLM retry on validation failure
- [ ] `ValidationContext` replaced by `StepDeps` or pydantic.ai `validation_context`
- [ ] `validation.py` deleted
- [ ] `strict_types` dropped (pydantic.ai native validation sufficient)
- [ ] All steps that used custom validation still work correctly
- [ ] Unit tests for each validator factory

---

## Task 4: OTel Integration + Event Cleanup

### Goal

Enable pydantic.ai's OpenTelemetry instrumentation for operational observability (retries, token usage, latency). Add pipeline-level event emission for real-time UI. Log token usage per step.

### Requirements

1. **Enable OTel instrumentation on all pipeline agents**
   - Use `Agent.instrument_all()` or per-agent `instrument=InstrumentationSettings(...)` in agent builder
   - Configure: `include_content=True` (for debugging), use global TracerProvider
   - This gives automatic spans for: model requests, token usage, retry attempts, latency

2. **Create pipeline event system** for real-time UI streaming
   - Define event types: `StepPrepared`, `StepStarting`, `StepCompleted` (dataclasses or Pydantic models)
   - Emit from executor at appropriate points in `execute()` loop
   - Event channel: callback function passed to `PipelineConfig.execute()`, or async generator pattern
   - Note: no existing event system to deprecate -- the current executor has no event emission

3. **Add token usage logging** from `RunResult.usage()`
   - After each `agent.run_sync()`, log `result.usage().request_tokens`, `response_tokens`, `total_tokens`
   - Store in `PipelineStepState` or new fields for audit trail
   - Useful for cost tracking per step

4. **Configure OTel export** (documentation/setup only)
   - Document how to configure TracerProvider for different backends (Jaeger, OTLP, console)
   - No hardcoded exporter -- rely on standard OTel env vars (`OTEL_EXPORTER_OTLP_ENDPOINT`)

### Affected Files

| Action | File | What Changes |
|--------|------|--------------|
| MODIFY | `schemas/pipeline/agent_builders.py` | Add `instrument=` param to agent construction |
| MODIFY | `schemas/pipeline/config.py` | Emit events during execute(), log token usage from RunResult |
| CREATE | `schemas/pipeline/events.py` | Pipeline event types (StepPrepared, StepStarting, StepCompleted) |
| MODIFY | `schemas/pipeline/state.py` | Add token usage fields to PipelineStepState |
| CREATE | `docs/observability.md` | OTel setup documentation |

### Acceptance Criteria

- [ ] All pipeline agents have OTel instrumentation enabled
- [ ] OTel spans generated for model requests (visible in configured exporter)
- [ ] Pipeline events (Prepared, Starting, Completed) defined and emitted by executor
- [ ] Token usage logged per step from `RunResult.usage()`
- [ ] Token usage stored in PipelineStepState for audit trail
- [ ] OTel setup documented with env var configuration

---

## Task 5: Consensus Enhancement

### Goal

Replace naive consensus (run N times, pick most common) with a `ConsensusStrategy` abstraction supporting research-backed strategies: Self-Consistency, CISC confidence-weighted, Adaptive, Soft voting.

### Requirements

1. **Create `ConsensusStrategy` ABC** in `logistics_intelligence/core/schemas/pipeline/consensus.py`

   ```python
   class ConsensusStrategy(ABC):
       @abstractmethod
       def should_continue(self, results: list[RunResult], target: int) -> bool:
           """Whether to keep polling for more results."""

       @abstractmethod
       def select(self, results: list[RunResult]) -> ConsensusResult:
           """Select final result from collected results."""

   @dataclass
   class ConsensusResult:
       output: Any              # selected instruction instance
       confidence: float        # consensus confidence score
       strategy_name: str       # which strategy was used
       num_samples: int         # how many LLM calls made
       agreement_ratio: float   # fraction of results that matched
   ```

2. **Implement strategy variants**

   - **`MajorityVoteStrategy`** (current behavior, default)
     - Run N times, group by `_instructions_match()`, pick largest group
     - `should_continue`: stop when any group reaches target count
     - Based on: Self-Consistency (Wang et al., 2022)

   - **`ConfidenceWeightedStrategy`**
     - Weight votes by `confidence_score` from `LLMResultMixin`
     - Higher confidence responses count more in voting
     - Based on: CISC (2025)

   - **`AdaptiveStrategy`**
     - Start with fewer samples, increase if disagreement detected
     - `should_continue`: adaptive based on current agreement level
     - Based on: Adaptive Consistency (Aggarwal et al., 2023)

   - **`SoftVoteStrategy`**
     - Probabilistic: merge fields weighted by confidence rather than selecting one response
     - Works best with numeric/categorical fields
     - Based on: Soft Self-Consistency (Wang et al., 2024)

3. **Update `PipelineConfig._execute_with_consensus()`**
   - Accept `ConsensusStrategy` parameter (default: `MajorityVoteStrategy`)
   - Use `strategy.should_continue()` to control polling loop
   - Use `strategy.select()` to pick final result
   - Return `ConsensusResult` with metadata

4. **Add consensus config to pipeline/step level**
   - `StepDefinition` gains optional `consensus_strategy: ConsensusStrategy | None`
   - Pipeline-level default, overridable per step
   - Backward compatible: no consensus config = no consensus (current default)

5. **Keep `_smart_compare()` and `_instructions_match()`** as utilities
   - Used by `MajorityVoteStrategy` and potentially others for grouping
   - Move from `PipelineConfig` to `consensus.py` module level

### Affected Files

| Action | File | What Changes |
|--------|------|--------------|
| CREATE | `schemas/pipeline/consensus.py` | ConsensusStrategy ABC + 4 implementations |
| MODIFY | `schemas/pipeline/config.py` | Update _execute_with_consensus to use strategy, move _smart_compare/_instructions_match |
| MODIFY | `schemas/pipeline/strategy.py` | Add consensus_strategy to StepDefinition |
| MODIFY | `schemas/pipeline/__init__.py` | Export consensus classes |

### Acceptance Criteria

- [ ] `ConsensusStrategy` ABC defined with `should_continue()` and `select()`
- [ ] `MajorityVoteStrategy` reproduces current consensus behavior exactly
- [ ] `ConfidenceWeightedStrategy` weights by LLMResultMixin.confidence_score
- [ ] `AdaptiveStrategy` adjusts sample count based on agreement level
- [ ] `SoftVoteStrategy` merges numeric/categorical fields by confidence weight
- [ ] `_execute_with_consensus()` uses strategy pattern
- [ ] `_smart_compare()` and `_instructions_match()` moved to consensus module
- [ ] Default behavior unchanged (MajorityVote when consensus enabled)
- [ ] ConsensusResult includes metadata (confidence, strategy, samples, agreement)
- [ ] Unit tests for each strategy with known input/output
- [ ] Integration test: pipeline with consensus still produces correct results

---

## Migration Notes

### Backward Compatibility

- Phase 1-2 are breaking for internal API only (no external consumers)
- `create_llm_call()` deprecated but kept through Phase 2
- Custom events deprecated in Phase 4, not deleted
- All pipeline subclasses (RateCardParser, TableExtraction, InvoiceParser) work without changes to their step/strategy/extraction code

### Model Configuration

- Current: hardcoded `gemini-2.0-flash-lite` in `call_gemini_with_structured_output()`
- New: model specified per-agent in registry, default `google-gla:gemini-2.0-flash-lite`
- Allows different models per step (e.g., harder steps get `gemini-2.5-flash`)

### Prompt System

- DB-stored prompts (system + user) remain the source of truth
- System prompts injected via `@agent.instructions` dynamic decorator (queries DB at runtime)
- User prompts passed as `input=` to `agent.run_sync()`
- Variable templating (`PromptService.format()`) unchanged

### Testing Strategy

- Each phase has unit tests for new/changed components
- Integration test: full rate card parse end-to-end after each phase
- Use `PYDANTIC_AI_DEFER_MODEL_CHECK=True` in tests to avoid model initialization
