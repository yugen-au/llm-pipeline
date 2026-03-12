# Step 1: Architecture Research - Pipeline Executor

## File Path Corrections

Task description references files from original logistics-intelligence codebase. Actual locations in llm-pipeline:

| Task Description Path | Actual Path |
|---|---|
| `config.py` (PipelineConfig) | `llm_pipeline/pipeline.py` |
| `core/llm/utils.py` (execute_llm_step) | `llm_pipeline/llm/executor.py` |
| `core/llm/rate_limiter.py` | `llm_pipeline/llm/rate_limiter.py` |
| `core/llm/__init__.py` | `llm_pipeline/llm/__init__.py` |
| `schemas/pydantic_models.py` (ExecuteLLMStepParams) | `llm_pipeline/types.py` |
| `step.py` | `llm_pipeline/step.py` |
| `strategy.py` | `llm_pipeline/strategy.py` |

Additional files in scope (not listed in task but critical):
- `llm_pipeline/llm/gemini.py` - GeminiProvider (consumes all utilities being deleted)
- `llm_pipeline/llm/validation.py` - validate_structured_output, validate_array_response, check_not_found_response
- `llm_pipeline/llm/schema.py` - format_schema_for_llm, flatten_schema
- `llm_pipeline/llm/result.py` - LLMCallResult (data container)
- `llm_pipeline/llm/provider.py` - LLMProvider ABC

## Call Chain: execute() -> execute_llm_step() -> provider.call_structured()

### 1. PipelineConfig.execute() (pipeline.py L450-862)

Entry point. Orchestrates pipeline steps:

```
execute(data, initial_context, input_data, use_cache, consensus_polling)
  |
  +-- validate input_data against INPUT_DATA schema
  +-- create PipelineRun record
  +-- for step_index in range(max_steps):
  |     +-- select strategy via can_handle(context)
  |     +-- step_def.create_step(pipeline=self)
  |     +-- step.should_skip() check
  |     +-- if use_cache: _find_cached_state() -> _load_from_cache()
  |     +-- else (fresh execution):
  |     |     +-- step.prepare_calls() -> List[StepCallParams]
  |     |     +-- for each params:
  |     |     |     +-- step.create_llm_call(**params) -> call_kwargs
  |     |     |     +-- inject provider, prompt_service, event_emitter, etc.
  |     |     |     +-- if consensus: _execute_with_consensus(call_kwargs, ...)
  |     |     |     +-- else: execute_llm_step(**call_kwargs) -> instruction
  |     |     +-- store instructions, merge context, transform, extract, save state
  |     +-- step.extract_data(instructions)
  |     +-- step.process_instructions(instructions) -> context
  |     +-- step._transformation.transform() if present
  |     +-- _save_step_state()
  +-- update PipelineRun status
```

**Key pipeline.py lines for replacement:**
- L716: `call_params = step.prepare_calls()`
- L730: `call_kwargs = step.create_llm_call(**params)` -- deprecated, must replace
- L731-740: Injecting provider, prompt_service, event emitter into call_kwargs
- L742-744: `self._execute_with_consensus(call_kwargs, ...)` or
- L748: `instruction = execute_llm_step(**call_kwargs)`

### 2. execute_llm_step() (executor.py L24-195)

Bridges step config to provider call:

```
execute_llm_step(system_instruction_key, user_prompt_key, variables, result_class, provider, prompt_service, ...)
  |
  +-- Convert PromptVariables to dict (model_dump)
  +-- Resolve system instruction via prompt_service.get_system_prompt() or get_prompt()
  +-- Resolve user prompt via prompt_service.get_user_prompt()
  +-- Emit LLMCallStarting event
  +-- provider.call_structured(prompt, system_instruction, result_class, ...) -> LLMCallResult
  +-- Emit LLMCallCompleted event
  +-- if result.parsed is None: return result_class.create_failure(msg)
  +-- else: model_validate with validation_context, or result_class(**result.parsed)
  +-- return validated Pydantic instruction instance
```

**What pydantic-ai replaces here:**
- Prompt resolution -> already handled by `@agent.instructions` (system) and `build_user_prompt()` (user)
- provider.call_structured() -> `agent.run_sync()` handles LLM call + validation + retries
- Pydantic validation -> pydantic-ai validates via `output_type` natively
- Event emission -> needs decision (see Questions)

### 3. GeminiProvider.call_structured() (gemini.py L69-304)

Concrete LLM interaction with manual retry loop:

```
call_structured(prompt, system_instruction, result_class, max_retries=3, ...)
  |
  +-- rate_limiter.wait_if_needed()
  +-- genai.GenerativeModel(model_name, system_instruction)
  +-- format_schema_for_llm(result_class) -> schema string appended to prompt
  +-- model.generate_content(prompt_with_schema)
  +-- check_not_found_response() -> return None parsed
  +-- JSON extraction from response text (regex, find braces)
  +-- validate_structured_output() -> custom schema validation
  +-- validate_array_response() if array_validation config present
  +-- Pydantic model_validate() or constructor
  +-- Retry loop: 429 detection, exponential backoff, rate limit delay extraction
  +-- return LLMCallResult
```

**What pydantic-ai replaces here:**
- Rate limiting -> pydantic-ai handles 429 retries internally
- Schema formatting -> pydantic-ai sends structured output natively
- JSON extraction -> pydantic-ai parses structured output natively
- validate_structured_output() -> pydantic-ai output_type validation
- validate_array_response() -> Task 3 output_validator
- check_not_found_response() -> Task 3 output_validator
- Retry loop -> pydantic-ai retries parameter

## Consensus Mechanism: _execute_with_consensus() (pipeline.py L1127-1185)

```python
def _execute_with_consensus(self, call_kwargs, consensus_threshold, maximum_step_calls, current_step_name):
    results = []
    result_groups = []
    for attempt in range(maximum_step_calls):
        instruction = execute_llm_step(**call_kwargs)  # <-- REPLACE THIS
        results.append(instruction)
        # Group by structural match
        matched_group = None
        for group in result_groups:
            if self._instructions_match(instruction, group[0]):
                group.append(instruction)
                matched_group = group
                break
        if matched_group is None:
            result_groups.append([instruction])
            matched_group = result_groups[-1]
        # Check threshold
        if len(matched_group) >= consensus_threshold:
            return matched_group[0]
    # Fallback: largest group
    largest_group = max(result_groups, key=len)
    return largest_group[0]
```

**_instructions_match()** (L1121-1125): Compares two instructions using `_smart_compare()`.

**_smart_compare()** (L1094-1118): Structural comparison that:
- Ignores LLMResultMixin fields (confidence_score, notes)
- Treats all string and None values as matching (always returns True)
- Only compares numbers, bools, lists, and dicts structurally
- Recursive for nested structures

**Consensus migration**: Change inner `execute_llm_step(**call_kwargs)` to `agent.run_sync(user_prompt, deps=step_deps).output`. Comparison logic (_smart_compare, _instructions_match) stays unchanged -- it operates on instruction model instances regardless of source. Signature changes: consensus now receives agent+prompt+deps instead of flat call_kwargs.

## Wrapper Logic (Unchanged in Task 2)

### Caching (_find_cached_state, _load_from_cache, _save_step_state)
- Input hash computed from `step.prepare_calls()` output (L897-903)
- Cache lookup by pipeline_name + step_name + input_hash + prompt_version
- Cache stores serialized instructions as JSON list
- **No changes needed**: operates on instruction objects, not LLM call mechanism

### State Saving (_save_step_state, L978-1029)
- Saves serialized instructions, context snapshot, prompt keys, execution time, model name
- `model_name` currently from `getattr(self._provider, 'model_name', None)` (L792)
- **Change needed**: get model_name from agent.run_sync() result.usage() or agent model string

### Extraction (step.extract_data, L378-439 in step.py)
- Iterates extraction classes, calls extract(instructions)
- Stores instances in pipeline via store_extractions()
- **No changes needed**: operates on instruction objects

### Transformation (step._transformation.transform())
- Transforms current data using instructions
- **No changes needed**: operates on instruction objects

### Context Merging (step.process_instructions -> _validate_and_merge_context)
- Processes instructions to produce context dict
- Validates against expected PipelineContext type if declared
- **No changes needed**: operates on instruction objects

## Functions to Delete (Task 2 Scope)

### From llm_pipeline/llm/executor.py:
- `execute_llm_step()` -- replaced by agent.run_sync()
- `save_step_yaml()` -- utility, check if used elsewhere (only defined in executor.py, not imported elsewhere)

### From llm_pipeline/llm/rate_limiter.py:
- `RateLimiter` class -- pydantic-ai handles retries/rate limiting internally

### From llm_pipeline/llm/__init__.py:
- Remove `RateLimiter` export
- Keep `LLMProvider`, `LLMCallResult`, `flatten_schema`, `format_schema_for_llm` (if GeminiProvider kept)

### From llm_pipeline/types.py:
- `ExecuteLLMStepParams` -- no longer used after executor.py deletion
- Keep `StepCallParams` -- still used by prepare_calls() return type
- Keep `ArrayValidationConfig` -- still used (Task 3 scope for migration)
- Keep `ValidationContext` -- still used (Task 3 scope for migration)

## Task 1 Artifacts Available

From completed Task 1, these are ready for Task 2 use:
- `AgentRegistry` (agent_registry.py) -- step_name -> output_type mapping
- `StepDeps` (agent_builders.py) -- dependency container with 8 fields
- `build_step_agent()` (agent_builders.py) -- factory with @agent.instructions for system prompt
- `LLMStep.get_agent(registry)` -- returns output_type from registry
- `LLMStep.build_user_prompt(variables, prompt_service, context)` -- renders user prompt
- `StepDefinition.agent_name` -- optional override for step naming
- `PipelineConfig.AGENT_REGISTRY` -- ClassVar for agent registry class

Task 1 deviations relevant to Task 2:
- `get_agent()` returns output_type (Type[BaseModel]), NOT an Agent instance. Task 2 needs to build the Agent via `build_step_agent()` separately.
- `build_step_agent()` uses `defer_model_check=True` -- model must be set at run-time
- pydantic-ai is lazy-imported inside `build_step_agent()` to honour optional dependency contract

## Downstream Task Boundaries (OUT OF SCOPE)

- **Task 3**: Migrate not_found_indicators/check_not_found_response and ArrayValidationConfig/validate_array_response to @agent.output_validator. Task 2 should NOT touch these validators -- just pass array_validation/validation_context through if present in prepare_calls() output.
- **Task 4**: OTel instrumentation, pipeline event system, token usage logging. Task 2 should NOT add OTel. Should make minimal event adjustments only.
- **Task 5**: Refactor consensus with ConsensusStrategy pattern. Task 2 should update consensus to use agent.run_sync() but NOT restructure the consensus mechanism.
- **Task 6**: Final cleanup, remove all deprecated code, end-to-end testing. Task 2 deprecations are cleaned up here.

## References Used by Deleted Code

### execute_llm_step references:
- `llm_pipeline/pipeline.py` (2 imports: L462, L1128)
- `tests/events/test_llm_call_events.py`
- Not directly imported elsewhere

### RateLimiter references:
- `llm_pipeline/llm/gemini.py` (import + usage in __init__)
- `llm_pipeline/llm/__init__.py` (re-export)
- `tests/test_pipeline.py`

### format_schema_for_llm references:
- `llm_pipeline/llm/gemini.py` (import + usage)
- `llm_pipeline/llm/__init__.py` (re-export)
- `llm_pipeline/llm/schema.py` (definition)

### validate_structured_output references:
- `llm_pipeline/llm/gemini.py` (import + usage)
- `llm_pipeline/llm/validation.py` (definition)
- `tests/test_pipeline.py`

### validate_array_response references:
- `llm_pipeline/llm/gemini.py` (import + usage)
- `llm_pipeline/llm/validation.py` (definition)
- `tests/test_pipeline.py`

### check_not_found_response references:
- `llm_pipeline/llm/gemini.py` (import + usage)
- `llm_pipeline/llm/validation.py` (definition)

## Questions Requiring CEO Input

### Q1: Model string source
pydantic-ai uses model strings (e.g., 'google-gla:gemini-2.0-flash-lite'). PipelineConfig constructor currently takes `provider: LLMProvider`. How should the model string be provided?
- (a) Replace `provider=` with `model: str` parameter on PipelineConfig
- (b) Keep `provider=` for backward compat, add `model: str` alongside
- (c) Environment variable (e.g., PYDANTIC_AI_MODEL)
- (d) Per-step model via StepDefinition field
- (e) Combination

### Q2: GeminiProvider and LLMProvider fate
Task 2 deletes utilities GeminiProvider depends on (format_schema_for_llm, validate_structured_output, validate_array_response, check_not_found_response, RateLimiter). GeminiProvider becomes broken/unused.
- (a) Delete GeminiProvider + LLMProvider + LLMCallResult entirely
- (b) Keep but accept broken imports (defer to Task 6)
- (c) Keep functional by inlining deleted dependencies

### Q3: LLM call event emission
Current flow emits LLMCallStarting, LLMCallCompleted, LLMCallRetry, LLMCallFailed, LLMCallRateLimited from executor.py and GeminiProvider. With those deleted:
- (a) Emit simplified LLMCallStarting/Completed around agent.run_sync() in pipeline.py
- (b) Drop all LLM call events entirely, defer to Task 4 OTel
- (c) Use pydantic-ai message callbacks for event emission

### Q4: prepare_calls() and array_validation/validation_context passthrough
prepare_calls() returns StepCallParams with optional array_validation and validation_context. Task 3 migrates these to output_validators. Should Task 2:
- (a) Add array_validation and validation_context fields to StepDeps now (forward-compatible for Task 3)
- (b) Ignore them in Task 2 (silently dropped), Task 3 will add to StepDeps
- (c) Pass through as extra kwargs

### Q5: create_llm_call() removal
Deprecated in Task 1, still called in executor (pipeline.py L730). Should Task 2:
- (a) Remove create_llm_call() method entirely from LLMStep
- (b) Keep deprecated method, just remove executor's usage
- (c) Defer removal to Task 6 cleanup

### Q6: Agent construction and caching
build_step_agent() creates a new Agent per call. For consensus with up to 5 calls, that's 5 Agent constructions. pydantic-ai Agents are designed to be reused.
- (a) Build agent once per step, reuse for consensus iterations
- (b) Build agent once per pipeline execution, cache by step_name
- (c) Keep per-call construction (simple, no caching complexity)
