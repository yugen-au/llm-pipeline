# IMPLEMENTATION - STEP 6: CREATE TEST_SANDBOX.PY
**Status:** completed

## Summary
Created `tests/creator/__init__.py` (empty) and `tests/creator/test_sandbox.py` with 22 unit tests covering `CodeSecurityValidator`, `SandboxResult`, and `StepSandbox` (both Docker-unavailable and mock-Docker paths). All 22 tests pass. No real Docker daemon required.

## Files
**Created:** tests/creator/__init__.py, tests/creator/test_sandbox.py
**Modified:** none
**Deleted:** none

## Changes
### File: `tests/creator/__init__.py`
Empty package marker.

### File: `tests/creator/test_sandbox.py`
Four test classes:

**TestCodeSecurityValidator** (11 tests): validates AST-based denylist scan -- clean code, blocked `import os`, blocked `import subprocess`, blocked `from os import path`, blocked `eval()`, blocked `exec()`, blocked `os.system()` attribute chain, empty string, `llm_pipeline` import allowed, `pydantic` import allowed, multiple issues.

**TestSandboxResult** (2 tests): default field values (`import_ok=False`, `sandbox_skipped=True`, empty lists/string), pydantic field validation with explicit values.

**TestStepSandbox_DockerUnavailable** (3 tests): patches `_get_client` to return `None`; verifies `sandbox_skipped=True`, AST scan still runs and populates `security_issues`, `validate_code` delegates to `CodeSecurityValidator`.

**TestStepSandbox_WithMockDocker** (6 tests): mocks docker client/container via `unittest.mock.MagicMock` and `patch.dict("sys.modules", ...)` to inject mock `docker` module inside `run()`. Verifies container created with `network_mode='none'`, `read_only=True`, `mem_limit='512m'`; JSON stdout parsed into `SandboxResult`; `ReadTimeout` yields `import_ok=False, sandbox_skipped=False`; `container.kill()` called on timeout; `container.remove(force=True)` called on success; `DockerException` from `containers.create()` yields error result.

## Decisions
### Docker module injection
**Choice:** `patch.dict("sys.modules", {"docker": mock_docker, ...})` combined with `patch.object(sandbox, "_get_client", return_value=client)` and `patch.object(sandbox, "_discover_framework_path", return_value=None)`
**Rationale:** `run()` does `import docker; from docker.types import Mount` inside the try block after `_get_client()` succeeds. Patching sys.modules ensures those imports resolve to mocks without needing docker installed. `_get_client` patch bypasses the real ping check.

### Warnings in WithMockDocker tests
**Choice:** Warnings left unsilenced (not using `pytest.warns` or `warnings.filterwarnings`)
**Rationale:** The `UserWarning` for "Could not discover llm_pipeline package path" is expected behaviour when `_discover_framework_path` returns `None`. It does not affect test correctness. Silencing would hide legitimate warnings in other runs.

### `container.logs` mock strategy
**Choice:** `container.logs.return_value = stdout_bytes` (single return value for all calls)
**Rationale:** `run()` calls `container.logs(stdout=True, stderr=True)` for combined output and `container.logs(stdout=True, stderr=False)` for JSON parsing. Using a single return value for both is simpler and sufficient -- the JSON line is present in both, and the parse loop finds it regardless.

## Verification
[x] All 22 tests collected and pass: `pytest tests/creator/test_sandbox.py -v` -> 22 passed
[x] No Docker daemon needed: tests run in isolation with mocks
[x] Warnings are expected (framework path discovery returns None) -- not failures
[x] Test names match plan spec exactly
[x] Test classes match plan spec: TestCodeSecurityValidator, TestSandboxResult, TestStepSandbox_DockerUnavailable, TestStepSandbox_WithMockDocker
