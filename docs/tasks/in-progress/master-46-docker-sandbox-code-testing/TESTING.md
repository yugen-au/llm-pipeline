# Testing Results

## Summary
**Status:** passed
All 34 new tests pass. 5 pre-existing failures confirmed unrelated to this task (verified by stashing changes and re-running the same 5 tests -- same failures on base branch). No regressions introduced.

## Automated Testing
### Test Scripts Created
| Script | Purpose | Location |
| --- | --- | --- |
| test_sandbox.py | CodeSecurityValidator, SandboxResult, StepSandbox (mock Docker) | tests/creator/test_sandbox.py |
| test_sample_data.py | SampleDataGenerator all type mappings and edge cases | tests/creator/test_sample_data.py |

### Test Execution
**Pass Rate:** 34/34 new tests (1084/1089 total -- 5 pre-existing failures, 6 skipped)

```
============================= test session starts =============================
platform win32 -- Python 3.13.3, pytest-9.0.2, pluggy-1.6.0
rootdir: C:\Users\SamSG\Documents\claude_projects\llm-pipeline
configfile: pyproject.toml

tests/creator/test_sample_data.py::TestSampleDataGenerator::test_str_field_generates_test_name PASSED
tests/creator/test_sample_data.py::TestSampleDataGenerator::test_int_field_generates_1 PASSED
tests/creator/test_sample_data.py::TestSampleDataGenerator::test_float_field_generates_1_0 PASSED
tests/creator/test_sample_data.py::TestSampleDataGenerator::test_bool_field_generates_true PASSED
tests/creator/test_sample_data.py::TestSampleDataGenerator::test_list_str_field PASSED
tests/creator/test_sample_data.py::TestSampleDataGenerator::test_dict_field PASSED
tests/creator/test_sample_data.py::TestSampleDataGenerator::test_optional_not_required_returns_none PASSED
tests/creator/test_sample_data.py::TestSampleDataGenerator::test_field_with_default_uses_default_string PASSED
tests/creator/test_sample_data.py::TestSampleDataGenerator::test_field_with_default_uses_default_int PASSED
tests/creator/test_sample_data.py::TestSampleDataGenerator::test_empty_fields_returns_empty_dict PASSED
tests/creator/test_sample_data.py::TestSampleDataGenerator::test_generate_json_returns_valid_json_string PASSED
tests/creator/test_sample_data.py::TestSampleDataGenerator::test_unknown_type_annotation_returns_string_fallback PASSED
tests/creator/test_sandbox.py::TestCodeSecurityValidator::test_clean_code_no_issues PASSED
tests/creator/test_sandbox.py::TestCodeSecurityValidator::test_blocked_module_os PASSED
tests/creator/test_sandbox.py::TestCodeSecurityValidator::test_blocked_module_subprocess PASSED
tests/creator/test_sandbox.py::TestCodeSecurityValidator::test_blocked_importfrom PASSED
tests/creator/test_sandbox.py::TestCodeSecurityValidator::test_blocked_builtin_eval PASSED
tests/creator/test_sandbox.py::TestCodeSecurityValidator::test_blocked_builtin_exec PASSED
tests/creator/test_sandbox.py::TestCodeSecurityValidator::test_blocked_attribute_os_system PASSED
tests/creator/test_sandbox.py::TestCodeSecurityValidator::test_empty_code_no_issues PASSED
tests/creator/test_sandbox.py::TestCodeSecurityValidator::test_normal_llm_pipeline_import_allowed PASSED
tests/creator/test_sandbox.py::TestCodeSecurityValidator::test_pydantic_import_allowed PASSED
tests/creator/test_sandbox.py::TestCodeSecurityValidator::test_multiple_issues_returned PASSED
tests/creator/test_sandbox.py::TestSandboxResult::test_default_values PASSED
tests/creator/test_sandbox.py::TestSandboxResult::test_pydantic_validation PASSED
tests/creator/test_sandbox.py::TestStepSandbox_DockerUnavailable::test_run_skips_container_when_no_docker PASSED
tests/creator/test_sandbox.py::TestStepSandbox_DockerUnavailable::test_run_still_does_ast_scan_when_no_docker PASSED
tests/creator/test_sandbox.py::TestStepSandbox_DockerUnavailable::test_validate_code_delegates_to_security_validator PASSED
tests/creator/test_sandbox.py::TestStepSandbox_WithMockDocker::test_run_creates_container_with_correct_params PASSED
tests/creator/test_sandbox.py::TestStepSandbox_WithMockDocker::test_run_parses_json_output PASSED
tests/creator/test_sandbox.py::TestStepSandbox_WithMockDocker::test_run_handles_timeout PASSED
tests/creator/test_sandbox.py::TestStepSandbox_WithMockDocker::test_run_kills_container_on_timeout PASSED
tests/creator/test_sandbox.py::TestStepSandbox_WithMockDocker::test_run_removes_container_on_success PASSED
tests/creator/test_sandbox.py::TestStepSandbox_WithMockDocker::test_run_handles_docker_exception PASSED

============================== 34 passed, 6 warnings in 1.41s ==============================

Full suite: 5 failed (pre-existing), 1084 passed, 6 skipped in 122.16s
```

### Failed Tests
None (all new tests pass; 5 failures are pre-existing and unrelated to this task)

Pre-existing failures for reference:
- tests/test_agent_registry_core.py::TestStepDepsFields::test_field_count
- tests/ui/test_cli.py::TestCreateDevApp::test_reads_env_var_and_passes_to_create_app
- tests/ui/test_cli.py::TestCreateDevApp::test_passes_none_when_env_var_absent
- tests/ui/test_cli.py::TestDevModeWithFrontend::test_uvicorn_no_reload_in_vite_mode
- tests/ui/test_runs.py::TestTriggerRun::test_returns_422_when_no_model_configured

Confirmed pre-existing by git stash + re-run on base commit (b3807b25).

## Build Verification
- [x] `python -m pytest` collects without import errors
- [x] `llm_pipeline/creator/sandbox.py` imports cleanly (no docker required)
- [x] `llm_pipeline/creator/sample_data.py` imports cleanly
- [x] `llm_pipeline/creator/schemas.py` loads with new fields
- [x] `llm_pipeline/creator/steps.py` loads with sandbox integration
- [x] `pyproject.toml` has `sandbox = ["docker>=7.0"]` optional-dep
- [x] No Docker daemon required to run test suite (all container tests use mocks)

## Success Criteria (from PLAN.md)
- [x] `CodeSecurityValidator` detects blocked patterns -- test_blocked_module_os, test_blocked_module_subprocess, test_blocked_importfrom, test_blocked_builtin_eval, test_blocked_builtin_exec, test_blocked_attribute_os_system all pass
- [x] `StepSandbox.run()` returns `sandbox_skipped=True` when Docker unavailable -- test_run_skips_container_when_no_docker passes
- [x] `StepSandbox.run()` returns `sandbox_skipped=True` and `security_issues` populated when AST scan blocked -- test_run_still_does_ast_scan_when_no_docker passes
- [x] Container created with correct security params -- test_run_creates_container_with_correct_params verifies `network_mode='none'`, `read_only=True`, `mem_limit='512m'`
- [x] `SampleDataGenerator.generate()` produces type-appropriate values -- 8 type-specific tests pass
- [x] `CodeValidationContext` has `sandbox_valid`, `sandbox_skipped`, `sandbox_output` fields -- confirmed in schemas.py lines 178-180
- [x] `CodeValidationStep.process_instructions()` calls sandbox and populates context fields -- confirmed in steps.py lines 310-346
- [x] `pyproject.toml` has `sandbox = ["docker>=7.0"]` optional-dep -- confirmed line 30
- [x] Prompt YAML files excluded from import-check artifact list -- steps.py filters to only `.py` files before passing to sandbox
- [x] All unit tests pass with `pytest` (Docker unavailable tests use mocks) -- 34/34 pass
- [x] No Docker daemon required to run test suite -- confirmed, all container tests patch `_get_client`

## Human Validation Required
### Live Docker Sandbox Execution
**Step:** Step 1 (sandbox.py) and Step 4 (steps.py integration)
**Instructions:** On a machine with Docker Desktop running, run `pytest tests/creator/test_sandbox.py -v` then run a full CodeValidationStep pipeline with a real LLM-generated artifact and verify `sandbox_valid=True` appears in the returned context.
**Expected Result:** Container spins up with python:3.11-slim, imports the generated step module, returns `import_ok=True`, and CodeValidationContext shows `sandbox_valid=True, sandbox_skipped=False`.

### Framework Mount Path (Windows)
**Step:** Step 1 (sandbox.py `_discover_framework_path`)
**Instructions:** With Docker Desktop on Windows, trigger a sandbox run and check the docker container logs to confirm `/mounted-site-packages` is mounted and PYTHONPATH is set correctly.
**Expected Result:** No `ModuleNotFoundError: No module named 'llm_pipeline'` in container logs.

## Issues Found
### UserWarning: Could not discover llm_pipeline package path
**Severity:** low
**Step:** Step 1 (sandbox.py `_discover_framework_path`)
**Details:** In mock Docker tests, `importlib.util.find_spec('llm_pipeline')` returns None in the test environment (package not installed in editable mode with spec available), triggering the warning. This is expected behavior -- the warning is correct and the test still passes. Not a bug. Will not appear in production where package is installed.

## Recommendations
1. Run live Docker validation (human validation above) before merging to dev -- the mock tests are comprehensive but cannot verify actual container startup, image pull, and Python import within the container.
2. Pre-pull `python:3.11-slim` on CI agents (`docker pull python:3.11-slim`) to avoid image pull timeout on first sandbox run.
3. Consider suppressing the `_discover_framework_path` UserWarning in tests with `pytest.warns` or `warnings.filterwarnings` to keep test output clean.
