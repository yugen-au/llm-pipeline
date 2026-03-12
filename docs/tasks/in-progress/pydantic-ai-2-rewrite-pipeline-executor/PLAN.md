# PLANNING

## Summary

Rewrite `PipelineConfig.execute()` and `_execute_with_consensus()` in `pipeline.py` to use pydantic-ai `agent.run_sync()` instead of `execute_llm_step()`. Delete the entire legacy LLM provider abstraction layer (`gemini.py`, `provider.py`, `result.py`, `executor.py`, `schema.py`, `validation.py`, `rate_limiter.py`). Replace the `provider=` constructor param with `model: str`. Update StepDeps with two forward-compat fields. Remove `create_llm_call()` from LLMStep. Update all test files that reference deleted symbols.

## Plugin & Agents

**Plugin:** backend-development, python-development
**Subagents:** [available agents]
**Skills:** [available skills]

## Phases

1. **Delete legacy LLM layer**: Remove all 7 legacy files in `llm/` subpackage (provider, gemini, result, executor, schema, validation, rate_limiter). Rewrite `llm/__init__.py` to be minimal.
2. **Rewrite pipeline core**: Update `pipeline.py` constructor + `execute()` loop + `_execute_with_consensus()`. Delete `create_llm_call()` from `step.py` and `ExecuteLLMStepParams` from `types.py`.
3. **Update StepDeps**: Add `array_validation` + `validation_context` fields to `StepDeps` in `agent_builders.py`.
4. **Clean up exports**: Update `llm_pipeline/__init__.py`, `llm_pipeline/events/__init__.py` to remove deleted symbols.
5. **Update test suite**: Delete tests for deleted symbols, replace MockProvider pattern with model= string, rewrite step `prepare_calls()` implementations.

## Architecture Decisions

### Agent run pattern in execute()
**Choice:** Build agent once per step call via `build_step_agent()`, reuse same instance across consensus iterations. Call `agent.run_sync(user_prompt, deps=step_deps, model=self._model)` directly.
**Rationale:** CEO-decided. Per VALIDATED_RESEARCH.md Q4. Minimizes object allocation while remaining correct for consensus (same agent, different LLM samples).
**Alternatives:** Rebuild agent per consensus iteration (wasteful), pre-build all agents at pipeline init (requires model at registry time).

### LLMCallStarting rendered_system_prompt workaround
**Choice:** Resolve system prompt manually before `agent.run_sync()` using the same logic as `build_step_agent`'s `_inject_system_prompt` callback (call `prompt_service.get_system_prompt()` or `get_prompt()` directly), then emit `LLMCallStarting` with the resolved string.
**Rationale:** pydantic-ai resolves system prompts internally during `run_sync()` — unavailable before the call. Duplicating resolution for the event is the least-invasive approach. Confirmed in VALIDATED_RESEARCH.md.
**Alternatives:** Emit `LLMCallStarting` with `rendered_system_prompt=""` (inaccurate, breaks test `test_rendered_system_prompt_is_str`).

### Delete vs deprecate create_llm_call()
**Choice:** Delete entirely from `LLMStep`. Delete `ExecuteLLMStepParams` from `types.py`.
**Rationale:** CEO decision Q7. Deprecation warning already exists in Task 1; full removal in Task 2 forces migration now.
**Alternatives:** Keep with deprecation warning for one more version (CEO said no).

### StepDeps forward-compatibility fields
**Choice:** Add `array_validation: Any | None = None` and `validation_context: Any | None = None` as optional dataclass fields with defaults.
**Rationale:** CEO decision Q5. Task 3 output_validators will use these. Adding now avoids a breaking StepDeps change between tasks.
**Alternatives:** Add in Task 3 (would break StepDeps between Task 2 and Task 3 for any consumer).

### model= in _execute_with_consensus
**Choice:** Pass `model=self._model` in each `agent.run_sync()` call inside the consensus loop. Agent constructed once before the loop.
**Rationale:** build_step_agent uses `defer_model_check=True`, so model can be set at run_sync time or agent construction. Passing it at run_sync time is consistent with the execute() loop and avoids constructing multiple agents.
**Alternatives:** Set model at agent construction inside build_step_agent call (also valid but requires model to be passed into build_step_agent for each call).

## Implementation Steps

### Step 1: Delete legacy llm/ files
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /pydantic/pydantic-ai
**Group:** A

1. Delete `llm_pipeline/llm/gemini.py` (entire file).
2. Delete `llm_pipeline/llm/provider.py` (entire file).
3. Delete `llm_pipeline/llm/result.py` (entire file).
4. Delete `llm_pipeline/llm/executor.py` (entire file, includes save_step_yaml dead code).
5. Delete `llm_pipeline/llm/schema.py` (entire file: format_schema_for_llm, flatten_schema).
6. Delete `llm_pipeline/llm/validation.py` (entire file: validate_structured_output, validate_array_response, check_not_found_response, strip_number_prefix).
7. Delete `llm_pipeline/llm/rate_limiter.py` (entire file: RateLimiter).
8. Rewrite `llm_pipeline/llm/__init__.py` to empty/minimal: remove all 5 exports (LLMProvider, RateLimiter, LLMCallResult, flatten_schema, format_schema_for_llm), add a single comment: "# LLM subpackage - provider abstraction removed, use pydantic-ai agents via agent_builders.py".

### Step 2: Add forward-compat fields to StepDeps
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /pydantic/pydantic-ai
**Group:** B

1. Open `llm_pipeline/agent_builders.py`.
2. Add two optional fields to the `StepDeps` dataclass after `variable_resolver`:
   - `array_validation: Any | None = None`
   - `validation_context: Any | None = None`
3. Update the docstring to note these fields are unused in Task 2, reserved for Task 3 output_validators.

### Step 3: Rewrite PipelineConfig constructor and execute() loop
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /pydantic/pydantic-ai, /pydantic/pydantic
**Group:** C

1. Open `llm_pipeline/pipeline.py`.
2. Remove `from llm_pipeline.llm.provider import LLMProvider` from `TYPE_CHECKING` block (line 52).
3. Update `__init__` signature: replace `provider: Optional["LLMProvider"] = None` with `model: str` (required positional-or-keyword parameter).
4. In `__init__` body: replace `self._provider = provider` (line 183) with `self._model = model`.
5. Update docstring: remove provider mention, add model mention.
6. In `execute()` (line 462): remove `from llm_pipeline.llm.executor import execute_llm_step` import.
7. Add imports at top of `execute()`: `from llm_pipeline.agent_builders import build_step_agent, StepDeps` and `from pydantic_ai import UnexpectedModelBehavior`.
8. Replace the provider None check (lines 466-469) with AGENT_REGISTRY validation:
   ```python
   if self.AGENT_REGISTRY is None:
       raise ValueError(
           f"{self.__class__.__name__} must specify agent_registry= parameter."
       )
   ```
9. In the per-step execution loop (lines 729-749), replace the `create_llm_call()` + `execute_llm_step()` block with new agent flow for each `params` in `call_params`:
   - Get output_type: `output_type = step.get_agent(self.AGENT_REGISTRY)`
   - Build agent once before consensus/single call: `agent = build_step_agent(step_name=step.step_name, output_type=output_type)`
   - Build StepDeps: `step_deps = StepDeps(session=self.session, pipeline_context=self._context, prompt_service=prompt_service, run_id=self.run_id, pipeline_name=self.pipeline_name, step_name=step.step_name, event_emitter=self._event_emitter, variable_resolver=self._variable_resolver)`
   - Build user_prompt: `user_prompt = step.build_user_prompt(variables=params.get("variables", {}), prompt_service=prompt_service)`
   - Resolve system prompt for event (mirror `_inject_system_prompt` logic using `prompt_service.get_prompt(system_key, prompt_type='system')` or `get_system_prompt()` if variable_resolver present).
   - Emit `LLMCallStarting` if event_emitter present.
   - Call `agent.run_sync(user_prompt, deps=step_deps, model=self._model)` wrapped in try/except `UnexpectedModelBehavior`.
   - On `UnexpectedModelBehavior`: call `output_type.create_failure(str(exc))` to produce instruction.
   - On success: `instruction = run_result.output`.
   - Emit `LLMCallCompleted` with `model_name=self._model`, `attempt_count=1`, `raw_response=None`, `parsed_result=run_result.output.model_dump() if hasattr(run_result.output, 'model_dump') else None`, `validation_errors=[]`.
10. Update `model_name` at line 792: replace `getattr(self._provider, 'model_name', None)` with `self._model`.

### Step 4: Rewrite _execute_with_consensus()
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /pydantic/pydantic-ai
**Group:** C

1. Change `_execute_with_consensus` signature from `(self, call_kwargs, consensus_threshold, maximum_step_calls, current_step_name)` to `(self, agent, user_prompt, step_deps, output_type, consensus_threshold, maximum_step_calls, current_step_name)`.
2. Remove `from llm_pipeline.llm.executor import execute_llm_step` import inside the method (line 1128).
3. Add `from pydantic_ai import UnexpectedModelBehavior` import inside method (or move to module-level import).
4. Replace `instruction = execute_llm_step(**call_kwargs)` (line 1141) with:
   ```python
   try:
       run_result = agent.run_sync(user_prompt, deps=step_deps, model=self._model)
       instruction = run_result.output
   except UnexpectedModelBehavior as exc:
       instruction = output_type.create_failure(str(exc))
   ```
5. Update the call site in `execute()` (Step 3 above): pass `agent`, `user_prompt`, `step_deps`, `output_type` instead of `call_kwargs` when calling `_execute_with_consensus`.

### Step 5: Delete create_llm_call() from LLMStep and ExecuteLLMStepParams from types.py
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. Open `llm_pipeline/step.py`.
2. Remove `import warnings` (line 10) if only used by `create_llm_call()` deprecation warning.
3. Remove `from llm_pipeline.types import ExecuteLLMStepParams` from the `TYPE_CHECKING` block (line 32).
4. Delete the entire `create_llm_call()` method (lines 317-359) from `LLMStep`.
5. Open `llm_pipeline/types.py`.
6. Delete the `ExecuteLLMStepParams` class definition (lines 74-89).
7. Remove `"ExecuteLLMStepParams"` from `__all__` (line 96).

### Step 6: Clean up exports in __init__.py files
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** D

1. Open `llm_pipeline/__init__.py`:
   - Remove `from llm_pipeline.llm.result import LLMCallResult` (line 31).
   - Remove `"LLMCallResult"` from `__all__` (line 66).
   - Update docstring (lines 8-9): remove `from llm_pipeline.llm import LLMProvider` and `from llm_pipeline.llm.gemini import GeminiProvider` lines.
   - Update docstring (line 13): remove `from llm_pipeline import LLMCallResult` from usage example.
2. Open `llm_pipeline/events/__init__.py`:
   - Remove `from llm_pipeline.llm.result import LLMCallResult` (line 83).
   - Remove `"LLMCallResult"` from `__all__` (line 103).
   - Update module docstring to remove LLMCallResult reference.

### Step 7: Update tests - delete tests for deleted symbols
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** E

1. Delete `tests/test_llm_call_result.py` entirely (tests LLMCallResult which is deleted).
2. Delete `tests/events/test_retry_ratelimit_events.py` entirely (tests GeminiProvider retry loop which is deleted).
3. In `tests/test_pipeline.py`:
   - Delete `class TestImports: test_llm_imports` test method (imports LLMProvider, RateLimiter, format_schema_for_llm — all deleted).
   - Delete `class TestSchemaUtils` entirely (tests format_schema_for_llm, flatten_schema — deleted).
   - Delete `class TestValidation` entirely (tests validate_structured_output — deleted).
   - Delete `class TestRateLimiter` entirely (tests RateLimiter — deleted).
   - Delete `class TestStripNumberPrefix` entirely (tests strip_number_prefix — deleted).
4. In `tests/events/test_llm_call_events.py`:
   - Delete `test_no_event_params_in_call_kwargs` method (monkeypatches `execute_llm_step` which is deleted).
   - The test at line 368-402 in class `TestNoEmitterZeroOverhead` must be removed. The other test in that class (`test_no_events_without_emitter`) stays but needs MockProvider removal (covered in Step 8).

### Step 8: Update tests - replace MockProvider with model= string
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /pydantic/pydantic-ai
**Group:** F

In each file below, the approach is:
- Remove `from llm_pipeline.llm.provider import LLMProvider` import.
- Remove `from llm_pipeline.llm.result import LLMCallResult` import.
- Delete the `MockProvider(LLMProvider)` class definition.
- Replace `provider=MockProvider(...)` in pipeline constructor calls with `model="mock-model"`.
- Because `agent.run_sync()` will actually be called, the test pipeline must also declare an `AGENT_REGISTRY`. Since these are integration tests that previously used MockProvider to return fake data, they need a mock pydantic-ai approach. Use `pytest-mock` or `unittest.mock.patch` on `pydantic_ai.Agent.run_sync` to return a mock `AgentRunResult` with `.output` set to the test instruction instance.

Files to update:
1. `tests/test_pipeline.py`: Remove MockProvider class (lines 38-61). Add AgentRegistry to TestPipeline. Patch `Agent.run_sync` in fixtures to return pre-defined instruction objects.
2. `tests/test_pipeline_run_tracking.py`: Remove MockProvider (lines 133+). Add AgentRegistry. Patch `Agent.run_sync`.
3. `tests/test_pipeline_input_data.py`: Remove MockProvider (line 204+). Add AgentRegistry. Patch `Agent.run_sync`.
4. `tests/events/conftest.py`: Remove MockProvider (lines 32-58). Add AgentRegistry to SuccessPipeline, FailurePipeline, etc. Patch `Agent.run_sync` in fixtures.
5. `tests/benchmarks/conftest.py`: Remove `_BenchmarkMockProvider(LLMProvider)` (line 38). Add AgentRegistry. Patch `Agent.run_sync`.

### Step 9: Update tests - rewrite step prepare_calls() to not use create_llm_call()
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** G

In each step class that calls `self.create_llm_call(...)`, replace the body of `prepare_calls()` with the new pattern. Since `prepare_calls()` now just needs to return a list of `StepCallParams` dicts (the variables to pass to `build_user_prompt`), simplify each to:

```python
def prepare_calls(self) -> List[StepCallParams]:
    return [{"variables": {"data": "test"}}]
```

The actual prompt building and agent invocation happens in `execute()`. `StepCallParams` is a TypedDict with `variables` and optional fields. Check `types.py` for current definition: `StepCallParams` has `variables`, `array_validation`, `validation_context`. Update prepare_calls() to return plain dicts or `StepCallParams`-compatible dicts with just `variables`.

Files to update:
1. `tests/events/conftest.py`: SimpleStep, SkippableStep, ItemDetectionStep, TransformationStep — replace `self.create_llm_call(variables={"data": "test"})` with `{"variables": {"data": "test"}}`.
2. `tests/events/test_ctx_state_events.py`: local step — same replacement.
3. `tests/events/test_extraction_events.py`: FailingItemDetectionStep — same replacement.
4. `tests/test_introspection.py`: WidgetDetectionStep, ScanDetectionStep, GadgetDetectionStep — same replacement (use `{"variables": {"data": self.pipeline.get_sanitized_data()}}` where applicable).
5. `tests/test_pipeline.py`: WidgetDetectionStep — replace `self.create_llm_call(variables={"data": self.pipeline.get_sanitized_data()})` with `{"variables": {"data": self.pipeline.get_sanitized_data()}}`.
6. `tests/test_pipeline_run_tracking.py`: GadgetStep — same replacement.
7. `tests/test_agent_registry_core.py`: step that calls create_llm_call (used to test deprecation warning) — delete the 3 test methods `test_create_llm_call_deprecation_warning`, `test_create_llm_call_stacklevel`, `test_create_llm_call_still_works` since the method is gone.

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| `test_rendered_system_prompt_is_str` fails if system prompt resolution logic differs from what `_inject_system_prompt` does internally | Medium | Mirror exact logic: check `variable_resolver`, call `get_system_prompt()` vs `get_prompt()` as appropriate — verified in executor.py L95-107 |
| Agent.run_sync mock in tests may be complex to set up correctly for all test scenarios | Medium | Use `unittest.mock.patch('pydantic_ai.Agent.run_sync')` returning `MagicMock(output=instruction_instance)` — consistent across all test files |
| Steps in test files use `AGENT_REGISTRY` but no existing registry declares test step names | High | Each test pipeline that mocks agent.run_sync needs a matching AgentRegistry with step names. Since run_sync is patched, the registry only needs to return a valid output_type — use a simple `MyAgentRegistry(AgentRegistry, agents={"simple": SimpleInstructions, ...})` |
| Consensus test (`test_consensus_events.py`) may break if `_execute_with_consensus` signature changed | Medium | Update call site in execute() to pass new params; consensus tests do not call `_execute_with_consensus` directly |
| LLMCallCompleted.attempt_count: pydantic-ai's `run_result.usage()` returns token counts, not attempt count | Low | Set `attempt_count=1` for initial calls; pydantic-ai handles retries internally. VALIDATED_RESEARCH.md confirmed this approach |
| Removing `save_step_yaml` from executor may break unknown callers | Low | VALIDATED_RESEARCH.md confirmed no external callers; verified via grep |
| `tests/events/test_llm_call_events.py` tests for `rendered_system_prompt` content rely on exact prompt text | Medium | Existing test seeds prompts into DB; resolved system prompt will match since same PromptService logic is used |

## Success Criteria

- [ ] `llm_pipeline/llm/` contains only `__init__.py` with empty/minimal content (7 files deleted)
- [ ] `pipeline.py` constructor takes `model: str` (not `provider=`)
- [ ] `PipelineConfig.execute()` calls `agent.run_sync()` instead of `execute_llm_step()`
- [ ] `_execute_with_consensus()` accepts `agent, user_prompt, step_deps, output_type` params
- [ ] `LLMCallStarting` and `LLMCallCompleted` events emitted around `agent.run_sync()` calls
- [ ] `UnexpectedModelBehavior` mapped to `create_failure()` in both execute() and consensus
- [ ] `create_llm_call()` method absent from `LLMStep` class
- [ ] `ExecuteLLMStepParams` absent from `types.py` and `__all__`
- [ ] `StepDeps` has `array_validation` and `validation_context` optional fields
- [ ] `LLMCallResult` not exported from `llm_pipeline/__init__.py` or `llm_pipeline/events/__init__.py`
- [ ] `pytest` passes with no import errors from deleted symbols
- [ ] All 14 test files that referenced deleted symbols are updated
- [ ] `model_name` in `_save_step_state` call uses `self._model` (not `self._provider`)

## Phase Recommendation

**Risk Level:** high
**Reasoning:** Large blast radius: 7 files deleted, 5 test conftest/fixture files changed, 14 total test files affected, constructor API breaking change. The test mocking pattern for pydantic-ai Agent.run_sync is not yet established in the codebase — first time this pattern appears. Consensus rewrite and event emission for rendered_system_prompt both have subtle correctness requirements. High risk warrants full code + testing + review phases.
**Suggested Exclusions:** none
