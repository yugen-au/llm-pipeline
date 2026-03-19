# Task Summary

## Work Completed

Implemented Docker-based sandbox for LLM-generated step code validation in the `llm_pipeline/creator/` package. Defense-in-depth architecture: Layer 1 is AST-based denylist scan (fast, no Docker required), Layer 2 is Docker import-check in an isolated container. `CodeValidationStep` in `steps.py` integrates sandbox results into `CodeValidationContext`. `SampleDataGenerator` auto-generates test data from `instruction_fields` specs. Graceful fallback when Docker is unavailable. Full review-fix loop completed: mutable `_TYPE_MAP` reference leak fixed, integration tests added for `CodeValidationStep` wiring, `warnings.warn` category added, stdout observability improved. Architecture review approved with zero remaining blockers.

## Files Changed

### Created

| File | Purpose |
| --- | --- |
| `llm_pipeline/creator/sandbox.py` | Three-component sandbox module: `SandboxResult` (transient Pydantic BaseModel), `CodeSecurityValidator` (AST denylist using `_SecurityVisitor`), `StepSandbox` (Docker container executor with graceful fallback) |
| `llm_pipeline/creator/sample_data.py` | `SampleDataGenerator` class that auto-generates type-appropriate test dicts from `FieldDefinition` specs; handles 8 type mappings, Optional stripping, `ast.literal_eval` defaults |
| `tests/creator/__init__.py` | Empty package marker for `tests/creator/` directory |
| `tests/creator/test_sandbox.py` | 31 unit tests across 5 classes: `TestCodeSecurityValidator` (11), `TestSandboxResult` (2), `TestStepSandbox_DockerUnavailable` (3), `TestStepSandbox_WithMockDocker` (6), `TestCodeValidationStepSandboxIntegration` (9) |
| `tests/creator/test_sample_data.py` | 12 unit tests for `SampleDataGenerator` covering all type mappings, defaults, Optional handling, JSON output, unknown type fallback |

### Modified

| File | Changes |
| --- | --- |
| `llm_pipeline/creator/schemas.py` | Added `sandbox_valid: bool = False`, `sandbox_skipped: bool = True`, `sandbox_output: str \| None = None` to `CodeValidationContext` |
| `llm_pipeline/creator/steps.py` | Added lazy import guard for `StepSandbox`/`SampleDataGenerator`; extended `CodeValidationStep.process_instructions()` to run sandbox, populate context fields, and include security issues |
| `pyproject.toml` | Added `sandbox = ["docker>=7.0"]` optional-dependency group after `creator` |

## Commits Made

Key implementation and documentation commits (chore(state) commits omitted for brevity):

| Hash | Message |
| --- | --- |
| `b3807b25` | chore(state): master-46-docker-sandbox-code-testing -> initialization |
| `cc8cf840` | docs(research-A): master-46-docker-sandbox-code-testing |
| `f4d70a1d` | docs(validate-A): master-46-docker-sandbox-code-testing |
| `f3bda095` | docs(planning-A): master-46-docker-sandbox-code-testing |
| `fc4eb209` | docs(implementation-A): master-46-docker-sandbox-code-testing (sandbox.py + sample_data.py initial) |
| `7ec2f9f4` | docs(implementation-A): master-46-docker-sandbox-code-testing (review fixes for steps 1-2) |
| `595cee2c` | docs(implementation-B): master-46-docker-sandbox-code-testing (schemas.py) |
| `1434c7ba` | docs(implementation-C): master-46-docker-sandbox-code-testing (steps.py + pyproject.toml) |
| `626191bf` | docs(implementation-D): master-46-docker-sandbox-code-testing (test_sandbox.py + test_sample_data.py initial) |
| `90788d36` | docs(fixing-review-A): master-46-docker-sandbox-code-testing (sandbox.py + sample_data.py review fixes) |
| `451fdba4` | docs(fixing-review-D): master-46-docker-sandbox-code-testing (test_sandbox.py integration tests) |
| `eb727891` | docs(review-A): master-46-docker-sandbox-code-testing (initial review) |
| `2b068672` | chore(state): master-46-docker-sandbox-code-testing -> review (re-review post-fix) |
| `6a769fe9` | docs(testing-A): master-46-docker-sandbox-code-testing (test results) |
| `592b6433` | chore(state): master-46-docker-sandbox-code-testing -> summary |

## Deviations from Plan

- `_SecurityVisitor` extracted as private inner class of `CodeSecurityValidator` rather than inline visitor methods -- improves encapsulation, no state leakage between calls. Plan implied methods directly on `CodeSecurityValidator`.
- `container.logs()` called once for combined stdout+stderr (not twice with separate flags) -- simplifies log handling; JSON parse iterates reversed lines to find last JSON entry.
- `ReadTimeout` imported inside the try block co-located with `container.wait()` rather than at module top -- keeps the transitive `requests` dependency co-located with usage.
- Broad `except Exception` used in `run()` outer catch rather than `docker.errors.DockerException` only -- container lifecycle raises `APIError`, `ImageNotFound`, and other subtypes; catching broadly ensures sandbox never crashes the pipeline.
- `warnings.warn category=UserWarning` added to all three warn call sites (review fix, not in original plan).
- `parsed` flag + "Could not parse container output" error message added to empty stdout path (review fix, not in original plan).
- `copy.deepcopy()` guard added for mutable `_TYPE_MAP` values in `generate()` (review fix, not in original plan).
- 9 `TestCodeValidationStepSandboxIntegration` tests added in fix loop (review identified missing coverage, not in original plan).

## Issues Encountered

### Prompt YAML artifact incorrectly named `.py`
`CodeValidationStep` builds `all_artifacts` including `{step_name}_prompts.py` which contains YAML, not Python. Passing it to the import-check harness would fail AST parse and import-check.

**Resolution:** `_write_files()` filters artifact keys to exclude those ending with `_prompts.py` before writing the import list passed to `run_test.py`. Only Python source artifacts are import-checked.

### `cpu_count` is Windows-only in Docker SDK
Task spec referenced `cpu_count` for CPU limiting. Context7 docs confirmed `cpu_count` is Windows containers only and not cross-platform.

**Resolution:** Used `cpu_period=100000, cpu_quota=100000` (1 CPU equivalent) which is the cross-platform approach for Linux containers.

### `docker.types.Mount` required for tmpfs
Legacy volumes dict does not support `type='tmpfs'` in recent Docker SDK versions.

**Resolution:** Used `docker.types.Mount(target='/workspace', type='tmpfs', tmpfs_size=67108864)` as confirmed by Context7 docs.

### Framework path mount scope insufficient
Mounting only `llm_pipeline/` into the container would cause `ModuleNotFoundError` for pydantic, sqlmodel, and other framework deps that generated code imports transitively.

**Resolution:** `_discover_framework_path()` returns the parent of the `llm_pipeline` package directory (i.e., `site-packages` or source root), which is mounted at `/mounted-site-packages`. This makes all transitive dependencies available.

### Mock Docker injection in tests
`run()` imports `docker` and `docker.types.Mount` inside the try block after `_get_client()` returns a client. Standard `patch('docker.from_env')` does not intercept these in-method imports.

**Resolution:** `patch.dict("sys.modules", {"docker": mock_docker, "docker.types": mock_docker_types, "docker.errors": mock_docker_errors})` combined with `patch.object(sandbox, "_get_client", return_value=client)` and `patch.object(sandbox, "_discover_framework_path", return_value=None)` to inject the full mock module tree.

### Mutable `_TYPE_MAP` reference leak
`SampleDataGenerator._TYPE_MAP` holds mutable list and dict values. `generate()` returned direct references to class-level objects; a caller mutating the returned value would corrupt `_TYPE_MAP` for all future calls.

**Resolution:** Added `elif isinstance(value, (list, dict)): value = copy.deepcopy(value)` guard in `generate()` before assigning to result.

## Success Criteria

- [x] `CodeSecurityValidator` detects all blocked pattern categories -- `test_blocked_module_os`, `test_blocked_module_subprocess`, `test_blocked_importfrom`, `test_blocked_builtin_eval`, `test_blocked_builtin_exec`, `test_blocked_attribute_os_system` all pass
- [x] `StepSandbox.run()` returns `sandbox_skipped=True` when Docker unavailable with no exception -- `test_run_skips_container_when_no_docker` passes
- [x] `StepSandbox.run()` returns `sandbox_skipped=True` and `security_issues` populated when AST blocked -- `test_run_still_does_ast_scan_when_no_docker` passes
- [x] Container created with `network_mode='none'`, `read_only=True`, `mem_limit='512m'`, `cap_drop=['ALL']` -- `test_run_creates_container_with_correct_params` passes
- [x] `SampleDataGenerator.generate()` produces type-appropriate values for all 8 type annotations -- 8 type-specific tests pass
- [x] `CodeValidationContext` has `sandbox_valid`, `sandbox_skipped`, `sandbox_output` fields -- confirmed in `schemas.py`
- [x] `CodeValidationStep.process_instructions()` calls sandbox and populates context fields -- 9 integration tests pass
- [x] `pyproject.toml` has `sandbox = ["docker>=7.0"]` optional-dep -- confirmed
- [x] Prompt YAML files excluded from import-check artifact list -- `_write_files()` filters `_prompts.py` keys
- [x] All 43 new unit tests pass -- 43/43 (1093/1098 total; 5 pre-existing failures unrelated to this task)
- [x] No Docker daemon required to run test suite -- all container tests patch `_get_client`

## Recommendations for Follow-up

1. Run live Docker validation before merging to `dev`: on a machine with Docker Desktop running, trigger a full `CodeValidationStep` pipeline with a real LLM-generated artifact and verify `sandbox_valid=True, sandbox_skipped=False` in the returned `CodeValidationContext`.
2. Pre-pull `python:3.11-slim` on CI agents (`docker pull python:3.11-slim`) to avoid image pull timeout on the first sandbox run in CI.
3. Add `@pytest.mark.filterwarnings("ignore::UserWarning")` or patch `_discover_framework_path` in `TestStepSandbox_WithMockDocker` tests to suppress the 6 cosmetic `UserWarning` emissions in test output (LOW issue from re-review, still open).
4. Task 47 (StepIntegrator): reads `CodeValidationContext.all_artifacts` -- can now also read `sandbox_valid`, `sandbox_skipped`, `sandbox_output` to inform integration decisions. Consider gating integration on `sandbox_valid=True or sandbox_skipped=True`.
5. v2 scope: upgrade from import-check-only to full method execution with sample data. `SampleDataGenerator` and `sample_data.json` are already written to the container tmpdir; the harness just needs to call `prepare_calls()` / `process_instructions()` with the generated data.
6. Consider a custom `SandboxWarning(UserWarning)` subclass for filterability -- users who want to suppress sandbox warnings in production could use `warnings.filterwarnings("ignore", category=SandboxWarning)` without suppressing all `UserWarning` emissions.
7. Windows Docker Desktop path handling: verify bind mount path translation from Windows host paths to WSL2 paths works correctly in a real Docker Desktop environment. The `str(Path(...))` normalization is expected to work, but has not been validated on a live Windows+Docker Desktop system.
