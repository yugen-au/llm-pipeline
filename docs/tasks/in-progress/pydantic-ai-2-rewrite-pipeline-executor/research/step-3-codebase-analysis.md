# Step 3: Codebase Analysis - Blast Radius and Task 1 Artifact Review

## Summary
Full blast radius analysis of the functions being deleted/deprecated. Five genuine ambiguities surfaced that require CEO input before Task 2 implementation can proceed.

---

## 1. execute_llm_step

**Location:** `llm_pipeline/llm/executor.py:24`

### Call Sites (production)
| File | Line | Context |
|------|------|---------|
| `llm_pipeline/pipeline.py` | 462 | Lazy import inside `PipelineConfig.execute()` |
| `llm_pipeline/pipeline.py` | 748 | `instruction = execute_llm_step(**call_kwargs)` - main execution path |
| `llm_pipeline/pipeline.py` | 1128 | Lazy import inside `_execute_with_consensus()` |
| `llm_pipeline/pipeline.py` | 1141 | `instruction = execute_llm_step(**call_kwargs)` - consensus loop |

### Call Sites (tests)
| File | Line | Usage |
|------|------|-------|
| `tests/events/test_llm_call_events.py` | 382-383 | `__import__("llm_pipeline.llm.executor", fromlist=["execute_llm_step"]).execute_llm_step` |
| `tests/events/test_llm_call_events.py` | 390 | `monkeypatch.setattr("llm_pipeline.llm.executor.execute_llm_step", spy_execute)` |
| `llm_pipeline/extraction.py` | 229 | Docstring only - no functional usage |

### Current Signature
```python
def execute_llm_step(
    system_instruction_key: str,
    user_prompt_key: str,
    variables: Any,
    result_class: Type[T],
    provider: Optional[LLMProvider] = None,
    prompt_service: Any = None,
    context: Optional[Dict[str, Any]] = None,
    array_validation: Optional[ArrayValidationConfig] = None,
    system_variables: Optional[Any] = None,
    validation_context: Optional[ValidationContext] = None,
    event_emitter: Optional["PipelineEventEmitter"] = None,
    run_id: Optional[str] = None,
    pipeline_name: Optional[str] = None,
    step_name: Optional[str] = None,
    call_index: int = 0,
) -> T
```

### How pipeline.py builds call_kwargs (current flow)
```
# pipeline.py line 730
call_kwargs = step.create_llm_call(**params)
call_kwargs["provider"] = self._provider
call_kwargs["prompt_service"] = prompt_service
# optionally: event_emitter, run_id, pipeline_name, step_name, call_index

# pipeline.py line 748
instruction = execute_llm_step(**call_kwargs)
```

`step.create_llm_call()` (in step.py line 317) is DEPRECATED (Task 1) but still called by pipeline.py. Task 2 must remove this call.

---

## 2. call_gemini_with_structured_output

**STATUS: THIS FUNCTION DOES NOT EXIST IN THIS CODEBASE.**

No file in `llm_pipeline/` contains a function named `call_gemini_with_structured_output`. The task description references a path `core/llm/utils.py` which is also absent - this is the legacy path from the upstream `logistics-intelligence` project.

The closest equivalent in this codebase is `GeminiProvider.call_structured()` at `llm_pipeline/llm/gemini.py:69`.

**Ambiguity Q1 (see bottom): Does Task 2 delete GeminiProvider entirely, or only the listed standalone functions?**

---

## 3. format_schema_for_llm

**Location:** `llm_pipeline/llm/schema.py:56`

### Usages
| File | Line | Usage |
|------|------|-------|
| `llm_pipeline/llm/__init__.py` | 6 | Exported from `llm` subpackage |
| `llm_pipeline/llm/__init__.py` | 15 | In `__all__` |
| `llm_pipeline/llm/gemini.py` | 18, 106 | Imported and called in `GeminiProvider.call_structured()` |
| `tests/test_pipeline.py` | 200, 262 | `test_llm_imports` and `test_format_schema_for_llm` |

### Dependency chain
`format_schema_for_llm` -> `flatten_schema` (same file).

`flatten_schema` is also exported from `llm/__init__.py` and tested independently in `TestSchemaUtils.test_flatten_schema`.

**If GeminiProvider is deleted, format_schema_for_llm becomes dead code and can be deleted. If GeminiProvider is kept, it cannot be deleted without breaking gemini.py.**

---

## 4. validate_structured_output

**Location:** `llm_pipeline/llm/validation.py:110`

### Usages
| File | Line | Usage |
|------|------|-------|
| `llm_pipeline/llm/validation.py` | 237 | Recursive call (nested schema validation) |
| `llm_pipeline/llm/gemini.py` | 20, 170 | Imported and called in `GeminiProvider.call_structured()` |
| `llm_pipeline/llm/validation.py` | 383 | In `__all__` |
| `tests/test_pipeline.py` | 270, 278 | `TestValidation` - direct unit tests |

Only production caller is `GeminiProvider.call_structured()`. Direct test coverage in `test_pipeline.py`.

---

## 5. validate_array_response

**Location:** `llm_pipeline/llm/validation.py:291`

### Usages
| File | Line | Usage |
|------|------|-------|
| `llm_pipeline/llm/gemini.py` | 21, 192 | Imported and called in `GeminiProvider.call_structured()` |
| `llm_pipeline/llm/validation.py` | 384 | In `__all__` |

Only production caller is `GeminiProvider.call_structured()`. No direct unit tests (tested via GeminiProvider integration).

---

## 6. RateLimiter

**Location:** `llm_pipeline/llm/rate_limiter.py:10`

### Usages
| File | Line | Usage |
|------|------|-------|
| `llm_pipeline/llm/__init__.py` | 4, 10 | Exported from `llm` subpackage and in `__all__` |
| `llm_pipeline/llm/gemini.py` | 16, 45, 49, 99 | Used in `GeminiProvider.__init__` (parameter + default instance) and `call_structured()` |
| `tests/test_pipeline.py` | 199, 293, 299 | `test_llm_imports` and `TestRateLimiter` class |

`TestRateLimiter` (test_pipeline.py lines 291-303) directly instantiates and tests `RateLimiter`. Deleting it kills these tests.

**If GeminiProvider is deleted, RateLimiter can be deleted. If GeminiProvider is kept, it cannot.**

---

## 7. ExecuteLLMStepParams

**Location:** `llm_pipeline/types.py:74`

### Usages
| File | Line | Usage |
|------|------|-------|
| `llm_pipeline/step.py` | 32 | `TYPE_CHECKING` import only (not runtime) |
| `llm_pipeline/step.py` | 324 | Return type annotation for `create_llm_call()` |
| `llm_pipeline/types.py` | 96 | In `__all__` |

Task 2 says "deprecate", not delete. It's already only used at type-check time. Safe to deprecate with a comment; full deletion can wait until `create_llm_call()` is removed.

---

## 8. create_llm_call (being deprecated)

**Location:** `llm_pipeline/step.py:317` (already emits `DeprecationWarning` as of Task 1)

### Usages - STILL ACTIVE in production code
| File | Line | Usage |
|------|------|-------|
| `llm_pipeline/pipeline.py` | 730 | `call_kwargs = step.create_llm_call(**params)` - live production path |

### Usages in tests (all use `create_llm_call` in step implementations)
| File | Step class | Usage |
|------|-----------|-------|
| `tests/events/conftest.py` | `SimpleStep`, `SkippableStep`, `ItemDetectionStep`, `TransformationStep` | `self.create_llm_call(variables=...)` in `prepare_calls()` |
| `tests/events/test_ctx_state_events.py` | local step | `self.create_llm_call(variables=...)` |
| `tests/events/test_extraction_events.py` | `FailingItemDetectionStep` | `self.create_llm_call(variables=...)` |
| `tests/test_introspection.py` | `WidgetDetectionStep`, `ScanDetectionStep`, `GadgetDetectionStep` | `self.create_llm_call(...)` |
| `tests/test_pipeline.py` | `WidgetDetectionStep` | `self.create_llm_call(...)` |
| `tests/test_pipeline_run_tracking.py` | `GadgetStep` | `self.create_llm_call(...)` |

**Task 2 must remove the `pipeline.py line 730` call to `create_llm_call()`. All test steps that use it need updating - but the question is whether tests are updated in Task 2 or Task 6.**

---

## 9. Task 1 Artifacts Analysis

### AgentRegistry (`llm_pipeline/agent_registry.py`)
- ABC with `__init_subclass__` enforcing `agents=` parameter
- `AGENTS: ClassVar[dict[str, Type[BaseModel]]]` - maps step_name to output BaseModel type
- `get_output_type(step_name) -> Type[BaseModel]` - returns the class, not an Agent instance
- Exported from top-level `llm_pipeline/__init__.py`
- Tested in `tests/test_agent_registry_core.py`
- **Status: Complete and correct**

### StepDeps (`llm_pipeline/agent_builders.py`)
```python
@dataclass
class StepDeps:
    session: Any          # Session
    pipeline_context: dict[str, Any]
    prompt_service: Any   # PromptService
    run_id: str
    pipeline_name: str
    step_name: str
    event_emitter: Any | None = None
    variable_resolver: Any | None = None
```
- **MISSING**: `validation_context` field (needed for Task 3 validators)
- Task 3 description says validators access `ArrayValidationConfig` via `StepDeps` - currently absent
- Task 2 note: `validation_context` will be needed once Task 3 runs. Task 2 may need to add this field to StepDeps even if not yet used, to avoid a second round of refactoring.

### build_step_agent (`llm_pipeline/agent_builders.py`)
```python
def build_step_agent(
    step_name: str,
    output_type: type,
    model: str | None = None,
    system_instruction_key: str | None = None,
    retries: int = 3,
    model_settings: Any | None = None,
) -> Agent[StepDeps, Any]
```
- Creates `Agent` with `defer_model_check=True` (model can be None at class definition time)
- Registers `@agent.instructions` callback that resolves system prompt from `deps.prompt_service`
- Returns a fully configured `Agent` instance (not just an output type)
- **Status: Complete and ready for Task 2 use**

### LLMStep.get_agent() (`llm_pipeline/step.py:265`)
```python
def get_agent(self, registry: 'AgentRegistry') -> type:
    agent_name = getattr(self, '_agent_name', None) or self.step_name
    return registry.get_output_type(agent_name)
```
- Returns output_type (BaseModel class), NOT an Agent instance
- Docstring says "Task 2 will provide the full Agent instance via build_step_agent()"
- This method returns only the output type; Task 2 needs to call `build_step_agent()` to get the actual agent

### LLMStep.build_user_prompt() (`llm_pipeline/step.py:284`)
```python
def build_user_prompt(self, variables, prompt_service, context=None) -> str
```
- Calls `prompt_service.get_user_prompt(self.user_prompt_key, variables=..., variable_instance=..., context=...)`
- Ready for use as the `user_prompt` argument to `agent.run_sync()`
- **Status: Complete and ready for Task 2 use**

### StepDefinition (`llm_pipeline/strategy.py:38`)
- Has `agent_name: str | None = None` field (added in Task 1)
- `_agent_name` is set on step instance via `create_step()` to route `get_agent()` lookups

---

## 10. Test Files Affected by Deletions

### Tests directly testing symbols being deleted
| Test File | Affected Tests | Symbol |
|-----------|---------------|--------|
| `tests/test_pipeline.py` | `TestImports.test_llm_imports` | `RateLimiter`, `format_schema_for_llm` |
| `tests/test_pipeline.py` | `TestSchemaUtils.test_format_schema_for_llm` | `format_schema_for_llm` |
| `tests/test_pipeline.py` | `TestValidation.test_validate_structured_output_valid/missing_field` | `validate_structured_output` |
| `tests/test_pipeline.py` | `TestRateLimiter.test_basic_usage/test_reset` | `RateLimiter` |
| `tests/events/test_llm_call_events.py` | `test_no_event_params_in_call_kwargs` | `execute_llm_step` monkeypatch |

### Tests referencing GeminiProvider (affected if deleted)
- `tests/events/test_retry_ratelimit_events.py` - entire file tests GeminiProvider retry/rate-limit event emission
- These tests also patch `llm_pipeline.llm.gemini.extract_retry_delay_from_error`

### Tests using create_llm_call in step implementations
- `tests/events/conftest.py` (4 step classes)
- `tests/events/test_ctx_state_events.py`
- `tests/events/test_extraction_events.py`
- `tests/test_introspection.py` (3 step classes)
- `tests/test_pipeline.py`
- `tests/test_pipeline_run_tracking.py`

---

## 11. Pipeline Execution Flow - Current vs Target

### Current flow (pipeline.py lines 729-748)
```python
for idx, params in enumerate(call_params):
    call_kwargs = step.create_llm_call(**params)          # DEPRECATED
    call_kwargs["provider"] = self._provider
    call_kwargs["prompt_service"] = prompt_service
    # inject event_emitter, run_id, etc.
    instruction = execute_llm_step(**call_kwargs)          # TO DELETE
    instructions.append(instruction)
```

### Target flow (Task 2)
```python
for idx, params in enumerate(call_params):
    user_prompt = step.build_user_prompt(params["variables"], prompt_service)
    agent = build_step_agent(
        step_name=step.step_name,
        output_type=step.get_agent(registry),
        model=self._model_string,   # replaces self._provider
        system_instruction_key=step.system_instruction_key,
    )
    step_deps = StepDeps(
        session=self._real_session,
        pipeline_context=self._context,
        prompt_service=prompt_service,
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
        step_name=step.step_name,
        event_emitter=self._event_emitter,
        variable_resolver=self._variable_resolver,
    )
    run_result = agent.run_sync(user_prompt, deps=step_deps)
    instruction = run_result.output
    instructions.append(instruction)
```

Note: `PipelineConfig` currently requires `provider=` (LLMProvider instance) in constructor. After Task 2, this becomes `model=` (model string like `"google-gla:gemini-2.0-flash-lite"`). This is a **breaking constructor API change**.

### UnexpectedModelBehavior mapping
```python
from pydantic_ai.exceptions import UnexpectedModelBehavior
try:
    run_result = agent.run_sync(user_prompt, deps=step_deps)
    instruction = run_result.output
except UnexpectedModelBehavior as e:
    instruction = result_class.create_failure(str(e))
```

---

## 12. Unresolved Ambiguities (Need CEO Input)

**Q1: call_gemini_with_structured_output doesn't exist.**
`call_gemini_with_structured_output` is absent from this codebase. Does "delete it" mean:
- (a) Delete the entire `GeminiProvider` class (it was refactored from that standalone function), OR
- (b) It's a naming error - nothing to delete for this specific item?

**Q2: GeminiProvider fate.**
If GeminiProvider is deleted in Task 2:
- `format_schema_for_llm`, `validate_structured_output`, `validate_array_response`, `RateLimiter` all become deletable (their only production caller is gone)
- `tests/events/test_retry_ratelimit_events.py` (the entire file) needs deletion/rewrite
If GeminiProvider is kept:
- Cannot delete `format_schema_for_llm`, `validate_structured_output`, `validate_array_response`, `RateLimiter` without breaking it
- Need to understand when/if GeminiProvider is ever deprecated

**Q3: PipelineConfig constructor API change.**
Currently: `PipelineConfig(provider=GeminiProvider(), ...)`
After Task 2: presumably `PipelineConfig(model="google-gla:gemini-2.0-flash-lite", ...)`
Is this the correct API change for Task 2? Or does the AgentRegistry carry the model string and `provider=` is removed/deprecated separately?

**Q4: Test update scope for Task 2.**
All test files using `create_llm_call()` in step `prepare_calls()` methods will still work (since `create_llm_call()` is deprecated but not deleted). However, the pipeline executor no longer calls `create_llm_call()` in Task 2. Are tests expected to be updated to the new pattern in Task 2, or only in Task 6?

**Q5: save_step_yaml.**
`save_step_yaml` is in `executor.py` (same file as `execute_llm_step`) and in `executor.__all__`. If `executor.py` is deleted, `save_step_yaml` is lost. Is it being kept (moved) or deleted?

---

## 13. Confirmed Safe Deletion Targets (no ambiguity)

The following can be deleted in Task 2 regardless of GeminiProvider decision:
- `execute_llm_step` from `llm_pipeline/llm/executor.py` (after replacing both pipeline.py call sites)
- The `create_llm_call()` call in `pipeline.py` line 730 (replace with new agent flow)
- The import of `execute_llm_step` in `pipeline.py` lines 462 and 1128

The following tests need updating in Task 2:
- `tests/events/test_llm_call_events.py:369-391` - monkeypatch must be rewritten
