# Testing Results

## Summary
**Status:** passed
All 51 new targeted tests pass. Existing test suite shows only pre-existing failures (verified present before our changes via git stash). No regressions introduced by naming.py refactor or new abstractions.

## Automated Testing
### Test Scripts Created
| Script | Purpose | Location |
| --- | --- | --- |
| test_agent_registry_core.py | naming.py, agent_registry.py, agent_builders.py, step.py, strategy.py, pipeline.py | tests/test_agent_registry_core.py |

### Test Execution
**Pass Rate:** 51/51 new tests (853/855 total - 2 pre-existing failures)

New test file run:
```
tests/test_agent_registry_core.py - 51 passed in 1.02s
```

Full suite run (with our changes):
```
FAILED tests/test_ui.py::TestRoutersIncluded::test_events_router_prefix
FAILED tests/ui/test_wal.py::TestWALMode::test_file_based_sqlite_sets_wal
2 failed, 853 passed, 6 skipped in 117.22s
```

Full suite run (without our changes, git stash):
```
FAILED tests/test_ui.py::TestRoutersIncluded::test_events_router_prefix
FAILED tests/ui/test_wal.py::TestWALMode::test_file_based_sqlite_sets_wal
2 failed, 802 passed, 6 skipped in 116.56s
```

### Failed Tests
#### test_events_router_prefix
**Step:** pre-existing (unrelated to task)
**Error:** `assert '/runs/{run_id}/events' == '/events'` - router prefix changed in prior work

#### test_file_based_sqlite_sets_wal
**Step:** pre-existing (unrelated to task)
**Error:** flaky test isolation failure - only fails in full-suite run, passes in isolation. Confirmed pre-existing via git stash.

## Build Verification
- [x] `python -m pytest tests/test_agent_registry_core.py` exits 0
- [x] All imports resolve (`from llm_pipeline.naming import to_snake_case`, `from llm_pipeline.agent_registry import AgentRegistry`, `from llm_pipeline.agent_builders import StepDeps, build_step_agent`)
- [x] pydantic-ai importable as dev dependency (`from pydantic_ai import Agent, RunContext`)
- [x] No new warnings introduced (existing DeprecationWarning from create_llm_call() in conftest.py expected)

## Success Criteria (from PLAN.md)
- [x] `llm_pipeline/naming.py` exists with `to_snake_case()` and `"HTMLParser"` -> `"html_parser"` (verified: test_consecutive_capitals_html_parser)
- [x] `LLMStep.step_name` uses `to_snake_case` and produces correct output for consecutive capitals (verified: test_step_name_snake_case)
- [x] `StepDefinition.create_step()` uses `to_snake_case` (verified: step_name property test, create_step_sets_agent_name test)
- [x] `StepKeyDict._normalize_key()` uses `to_snake_case` (verified: no inline re.sub in pipeline.py)
- [x] `llm_pipeline/agent_registry.py` exists with `AgentRegistry` ABC following Category A pattern
- [x] `AgentRegistry.__init_subclass__` raises ValueError for concrete subclass without `agents=` (verified: test_concrete_without_agents_raises)
- [x] `AgentRegistry.__init_subclass__` skips validation for `_*` named classes (verified: test_underscore_prefix_skip)
- [x] `llm_pipeline/agent_builders.py` exists with `StepDeps` dataclass (8 fields) and `build_step_agent()` factory
- [x] `StepDeps` has: session, pipeline_context, prompt_service, run_id, pipeline_name, step_name (required) + event_emitter, variable_resolver (optional None) (verified: test_field_count, test_required_field_names, test_optional_defaults_none)
- [x] `build_step_agent()` returns `Agent` with `defer_model_check=True` and `@agent.instructions` registered (verified: test_returns_agent_instance, test_defer_model_check_true, test_instructions_registered)
- [x] `StepDefinition` has `agent_name: str | None = None` field (verified: test_agent_name_default_none, test_agent_name_can_be_set)
- [x] `StepDefinition` has `step_name` property using `to_snake_case` (verified: test_step_name_property_simple, test_step_name_property_consecutive_caps)
- [x] `StepDefinition.create_step()` sets `step._agent_name` on the created step instance (verified: test_create_step_sets_agent_name_on_instance)
- [x] `LLMStep` has `get_agent(registry)` concrete method with agent_name override support (verified: test_get_agent_uses_step_name, test_get_agent_uses_override)
- [x] `LLMStep` has `build_user_prompt(variables, prompt_service, context)` concrete method (verified: test_build_user_prompt_calls_service, test_build_user_prompt_model_dump)
- [x] `LLMStep.create_llm_call()` emits `DeprecationWarning` with `stacklevel=2` (verified: test_create_llm_call_deprecation_warning, test_create_llm_call_stacklevel)
- [x] `PipelineConfig.__init_subclass__` accepts optional `agent_registry=` param and validates `{Prefix}AgentRegistry` naming (verified: test_wrong_agent_registry_name_raises)
- [x] `PipelineConfig.AGENT_REGISTRY` ClassVar added (verified: test_class_var_agent_registry_on_base_is_none, test_agent_registry_accepted_and_stored)
- [x] `pyproject.toml` has `pydantic-ai` optional dep and dev dep at `>=1.0.5` (verified: pydantic_ai imports succeed in tests)
- [x] `llm_pipeline/__init__.py` exports `AgentRegistry`, `StepDeps`, `build_step_agent` (verified: module-level imports in test file)
- [x] All existing tests pass (no regressions from naming.py refactor) (verified: same 2 pre-existing failures before and after our changes)

## Human Validation Required
None - all criteria machine-verifiable.

## Issues Found
### WAL test flaky in full-suite run
**Severity:** low
**Step:** pre-existing (unrelated)
**Details:** `tests/ui/test_wal.py::TestWALMode::test_file_based_sqlite_sets_wal` fails in full-suite run due to SQLite file lock from another test but passes in isolation. Confirmed pre-existing via git stash - exact same failure before our changes.

### pydantic-ai Agent.retries attribute
**Severity:** low
**Step:** Step 6 (build_step_agent)
**Details:** pydantic-ai v1.x does not expose a `.retries` attribute on Agent. Retries are stored as `_max_result_retries` internally. Test adjusted to verify `_max_result_retries`. If pydantic-ai changes this internal attribute name in future versions, the test will break. Not an implementation bug - build_step_agent correctly passes `retries=` to Agent constructor.

## Recommendations
1. Fix WAL test isolation (add tmp_path fixture to use unique file path per run) - separate task
2. Fix test_events_router_prefix to match new `/runs/{run_id}/events` prefix - separate task
3. Consider adding `agent.retries` as a public property request to pydantic-ai upstream if needed for testing
