# PLANNING

## Summary

Add Docker-based sandbox to the `llm_pipeline/creator/` package that validates LLM-generated step code via defense-in-depth: Layer 1 is an AST-based denylist scan (fast, no Docker), Layer 2 is import-check in an isolated container (network=none, read-only FS, 512MB, no caps). `CodeValidationStep` in `steps.py` gains sandbox integration, gracefully skipping container execution when Docker is unavailable. A `SampleDataGenerator` in `sample_data.py` auto-generates test data from `instruction_fields` for future use.

## Plugin & Agents

**Plugin:** python-development, backend-development, security-scanning
**Subagents:** [available agents]
**Skills:** none

## Phases

1. **Core sandbox module**: Implement `sandbox.py` (`SandboxResult`, `CodeSecurityValidator`, `StepSandbox`) and `sample_data.py` (`SampleDataGenerator`)
2. **Integration**: Modify `steps.py` (`CodeValidationStep` calls sandbox) and `pyproject.toml` (add sandbox optional-dep)
3. **Tests**: Create `tests/creator/test_sandbox.py` and `tests/creator/test_sample_data.py`

## Architecture Decisions

### AST Denylist vs Allowlist
**Choice:** AST-based denylist using `ast.NodeVisitor` with `BLOCKED_MODULES`, `BLOCKED_BUILTINS`, `BLOCKED_ATTRIBUTES` frozensets
**Rationale:** CEO decision. ~80 lines, no false positives on comments/strings, upgradeable to allowlist. Catches obvious dangerous imports fast (~10ms) before Docker.
**Alternatives:** Allowlist (stricter but more false positives on valid generated code)

### Import-Check Only Execution Scope
**Choice:** `run_test.py` harness inside container does `__import__(module_name)` only; no method invocation
**Rationale:** CEO decision (v1 scope). Catches ImportError, SyntaxError edge cases, class definition errors, import-time side effects. No mock objects needed.
**Alternatives:** Full method execution with sample data (deferred to v2)

### Framework Mount Strategy
**Choice:** `importlib.util.find_spec('llm_pipeline')` auto-discovers package location; mount parent directory (site-packages or source root) read-only
**Rationale:** CEO decision. Zero config. Works for pip install, editable install, and source checkout. Mount entire parent so transitive deps (pydantic, sqlmodel, etc.) are also available.
**Alternatives:** Manual path config, Docker image with pre-installed deps

### Graceful Docker Fallback
**Choice:** `try: docker.from_env() except DockerException: warn + skip container` -- AST scan still runs
**Rationale:** Validated in VALIDATED_RESEARCH.md. `creator/__init__.py` pattern RAISES on missing jinja2 -- sandbox must NOT follow this; soft warn-and-continue.
**Alternatives:** Hard fail (rejected: breaks CI environments without Docker)

### Container Constraints
**Choice:** `network_mode='none'`, `read_only=True`, tmpfs `/workspace` 64MB, `cap_drop=['ALL']`, `security_opt=['no-new-privileges']`, `pids_limit=50`, `mem_limit='512m'`, `memswap_limit='512m'`, `cpu_period=100000`, `cpu_quota=100000`, timeout 60s, image `python:3.11-slim`
**Rationale:** Context7 confirms `cpu_period/cpu_quota` is cross-platform (cpu_count is Windows-only). `memswap_limit=mem_limit` prevents swap. `docker.types.Mount` required for tmpfs.
**Alternatives:** cpu_count (Windows-only, rejected)

### SandboxResult Location
**Choice:** `SandboxResult` defined in `sandbox.py` as `pydantic.BaseModel` (not SQLModel)
**Rationale:** Validated in VALIDATED_RESEARCH.md. `models.py` uses SQLModel pattern for DB-persisted records. SandboxResult is transient, in-memory only.
**Alternatives:** Add to models.py (rejected: mixes DB models with transient results)

### CodeValidationContext Extension
**Choice:** Add `sandbox_valid: bool`, `sandbox_skipped: bool`, `sandbox_output: str | None` fields to `CodeValidationContext` in `schemas.py`
**Rationale:** Downstream task 47 (StepIntegrator) reads context; sandbox result informs but does not block integration. Fields are optional/defaulted.
**Alternatives:** Separate sandbox context class (rejected: unnecessary indirection)

### Dependency Grouping
**Choice:** `sandbox = ["docker>=7.0"]` as separate optional-dependency in pyproject.toml
**Rationale:** Follows existing pattern: `creator = ["jinja2>=3.0"]`. Users install `pip install llm-pipeline[sandbox]`. Does NOT add to `creator` group (separate concern).
**Alternatives:** Add to creator group (rejected: users who only want codegen don't need Docker)

## Implementation Steps

### Step 1: Create sandbox.py
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /docker/docker-py
**Group:** A

1. Create `llm_pipeline/creator/sandbox.py` with three components:

   **`SandboxResult(BaseModel)`:**
   - Fields: `import_ok: bool`, `security_issues: list[str]`, `sandbox_skipped: bool`, `output: str`, `errors: list[str]`, `modules_found: list[str]`

   **`CodeSecurityValidator` (internal class):**
   - Constants: `BLOCKED_MODULES: frozenset` (os, subprocess, sys, socket, ctypes, importlib, builtins, pickle, marshal, shelve, pty, tty, signal, resource, mmap, multiprocessing, threading, concurrent, asyncio, shutil, tempfile, pathlib, glob, fnmatch, linecache, tokenize, code, codeop, compileall, py_compile, dis, inspect, gc, tracemalloc, faulthandler, _thread), `BLOCKED_BUILTINS: frozenset` (eval, exec, compile, open, __import__, breakpoint), `BLOCKED_ATTRIBUTES: frozenset` (system, popen, call, Popen, run, check_output, spawn, execv, execve, fork)
   - `validate(code: str) -> list[str]` method using `ast.parse()` then `ast.NodeVisitor`
   - `visit_Import(node)` -- check `node.names` against `BLOCKED_MODULES`
   - `visit_ImportFrom(node)` -- check `node.module` against `BLOCKED_MODULES`
   - `visit_Call(node)` -- detect `eval()`, `exec()`, `__import__()` in `BLOCKED_BUILTINS`; detect dotted attribute calls like `os.system` via `_resolve_attribute_chain()`
   - `_resolve_attribute_chain(node) -> str | None` helper: recursively build `a.b.c` string from `ast.Attribute` nodes; return None if not resolvable

   **`StepSandbox`:**
   - `__init__(self, image: str = "python:3.11-slim", timeout: int = 60)` -- store config; do NOT init docker client here
   - `_get_client(self) -> docker.DockerClient | None` -- `try: client = docker.from_env(); client.ping(); return client except (DockerException, Exception): warnings.warn(...); return None`. Import `docker` inside method with try/except ImportError.
   - `_discover_framework_path(self) -> str | None` -- `importlib.util.find_spec('llm_pipeline')`, get `submodule_search_locations[0]`, return `str(Path(loc).parent)` (parent = site-packages or source root). Return None on failure.
   - `_write_files(self, tmpdir: Path, artifacts: dict[str, str], sample_data: dict | None) -> list[str]` -- write each artifact to tmpdir, write `run_test.py` harness, write `sample_data.json` if provided. Return list of artifact module names (stripped `.py`).
   - `_run_test_py` content (generated at runtime, not static file):
     ```python
     import sys, json
     results = {"import_ok": False, "errors": [], "modules_found": []}
     for module_file in sys.argv[1:]:
         module_name = module_file.replace('.py', '')
         try:
             __import__(module_name)
             results["modules_found"].append(module_name)
         except Exception as e:
             results["errors"].append(f"{module_name}: {type(e).__name__}: {e}")
     results["import_ok"] = len(results["errors"]) == 0
     print(json.dumps(results))
     sys.exit(0 if results["import_ok"] else 1)
     ```
   - `validate_code(self, code: str) -> list[str]` -- thin wrapper: `CodeSecurityValidator().validate(code)`
   - `run(self, artifacts: dict[str, str], sample_data: dict | None = None) -> SandboxResult` -- main method:
     1. Run AST security scan on all artifacts; if any issues, return early `SandboxResult(import_ok=False, security_issues=issues, sandbox_skipped=True, ...)`
     2. Get docker client; if None, return `SandboxResult(..., sandbox_skipped=True, ...)`
     3. Discover framework path; if None, warn and set `framework_path=None`
     4. Use `tempfile.TemporaryDirectory()` context for tmpdir
     5. Write files via `_write_files()`
     6. Build mounts: `[docker.types.Mount(target='/code', source=str(tmpdir), type='bind', read_only=False), docker.types.Mount(target='/workspace', type='tmpfs', tmpfs_size=67108864)]` + optional framework bind mount read-only
     7. Set `environment={'PYTHONPATH': '/code:/mounted-site-packages'}` (adjust target path based on framework_path mount target)
     8. `container = client.containers.create(image, command=['python', '/code/run_test.py', ...artifact_names], mounts=mounts, network_mode='none', read_only=True, mem_limit='512m', memswap_limit='512m', cpu_period=100000, cpu_quota=100000, cap_drop=['ALL'], security_opt=['no-new-privileges'], pids_limit=50, environment=env, auto_remove=False)`
     9. `container.start()`
     10. Try `result = container.wait(timeout=self.timeout)` -- catch `requests.exceptions.ReadTimeout`: kill container, return timeout SandboxResult
     11. Read `logs = container.logs(stdout=True, stderr=True).decode()`
     12. Parse last JSON line from stdout as results dict
     13. `container.remove(force=True)`
     14. Return `SandboxResult(import_ok=results['import_ok'], errors=results['errors'], modules_found=results['modules_found'], output=logs, sandbox_skipped=False, security_issues=[])`
     15. Wrap entire container lifecycle in try/except `docker.errors.DockerException` -- return error SandboxResult on failure

### Step 2: Create sample_data.py
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Create `llm_pipeline/creator/sample_data.py` with `SampleDataGenerator`:

   **`SampleDataGenerator`:**
   - `_TYPE_MAP: ClassVar[dict]` = `{'str': 'test_{name}', 'int': 1, 'float': 1.0, 'bool': True, 'list[str]': ['test_item'], 'dict[str, str]': {'key': 'value'}, 'list[int]': [1], 'dict[str, Any]': {'key': 'value'}}`
   - `generate(self, fields: list[FieldDefinition]) -> dict[str, Any]` -- iterate fields:
     - If `field.default` is not None: parse default (eval-safe: handle string literals like `'""'` -> `""`, numeric literals, None)
     - elif not `field.is_required`: value = `None`
     - else: look up `field.type_annotation` in `_TYPE_MAP`; handle `Optional[X]` / `X | None` by stripping to X; for str type use `f"test_{field.name}"` as value
     - Return dict mapping `field.name` -> value
   - `generate_json(self, fields: list[FieldDefinition]) -> str` -- `json.dumps(self.generate(fields), default=str)`

   Import: `from .models import FieldDefinition`

### Step 3: Modify schemas.py -- extend CodeValidationContext
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. In `llm_pipeline/creator/schemas.py`, extend `CodeValidationContext` with three new optional fields:
   ```python
   sandbox_valid: bool = False
   sandbox_skipped: bool = True
   sandbox_output: str | None = None
   ```
   These default to skipped=True/valid=False to be safe when sandbox doesn't run.

### Step 4: Modify steps.py -- integrate sandbox into CodeValidationStep
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. In `llm_pipeline/creator/steps.py`, import `StepSandbox` and `SampleDataGenerator` with lazy import guard:
   ```python
   try:
       from .sandbox import StepSandbox
       from .sample_data import SampleDataGenerator
       _SANDBOX_AVAILABLE = True
   except ImportError:
       _SANDBOX_AVAILABLE = False
   ```
   Note: `sandbox.py` itself handles docker unavailability; the ImportError guard here is only for cases where sandbox.py itself cannot be imported (unlikely but defensive).

2. In `CodeValidationStep.process_instructions()`, after building `all_artifacts` and before returning `CodeValidationContext`:
   - Get `instruction_fields` from context: `fields_raw = ctx.get("instruction_fields", [])`
   - Reconstruct `list[FieldDefinition]` from raw dicts: `fields = [FieldDefinition(**f) for f in fields_raw]`
   - Generate sample data: `sample_data = SampleDataGenerator().generate(fields) if fields else None`
   - Run sandbox: `sandbox = StepSandbox(); result = sandbox.run(artifacts=all_artifacts, sample_data=sample_data)`
   - Set sandbox fields in returned context: `sandbox_valid=result.import_ok, sandbox_skipped=result.sandbox_skipped, sandbox_output=result.output`
   - Update `is_valid`: `is_valid = syntax_valid and inst.is_valid and (result.import_ok or result.sandbox_skipped)` -- if sandbox was skipped, don't penalize validity
   - Add any `result.security_issues` to `issues` list in returned context

### Step 5: Modify pyproject.toml -- add sandbox optional-dep
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. In `pyproject.toml` under `[project.optional-dependencies]`, add:
   ```toml
   sandbox = ["docker>=7.0"]
   ```
   Place after `creator = ["jinja2>=3.0"]` line. Do NOT add to `creator` group or `dev` group.

### Step 6: Create tests/creator/test_sandbox.py
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /docker/docker-py
**Group:** D

1. Create `tests/creator/__init__.py` (empty)
2. Create `tests/creator/test_sandbox.py` with:

   **`TestCodeSecurityValidator`:**
   - `test_clean_code_no_issues` -- simple `x = 1` returns `[]`
   - `test_blocked_module_os` -- `import os` returns issue mentioning `os`
   - `test_blocked_module_subprocess` -- `import subprocess` detected
   - `test_blocked_importfrom` -- `from os import path` detected
   - `test_blocked_builtin_eval` -- `eval("x")` call detected
   - `test_blocked_builtin_exec` -- `exec("x = 1")` detected
   - `test_blocked_attribute_os_system` -- `os.system("ls")` attribute chain detected
   - `test_empty_code_no_issues` -- empty string returns `[]`
   - `test_normal_llm_pipeline_import_allowed` -- `from llm_pipeline.step import LLMStep` returns `[]`
   - `test_pydantic_import_allowed` -- `from pydantic import BaseModel` returns `[]`
   - `test_multiple_issues_returned` -- code with both `import os` and `exec("x")` returns 2 issues

   **`TestSandboxResult`:**
   - `test_default_values` -- `SandboxResult()` has `import_ok=False`, `sandbox_skipped=True`
   - `test_pydantic_validation` -- field types validated correctly

   **`TestStepSandbox_DockerUnavailable`:**
   - Patch `StepSandbox._get_client` to return None
   - `test_run_skips_container_when_no_docker` -- result has `sandbox_skipped=True`
   - `test_run_still_does_ast_scan_when_no_docker` -- code with `import os` has `security_issues` populated even when Docker unavailable
   - `test_validate_code_delegates_to_security_validator` -- `validate_code("import os")` returns non-empty list

   **`TestStepSandbox_WithMockDocker`:**
   - Use `unittest.mock.MagicMock` for docker client/container
   - `test_run_creates_container_with_correct_params` -- verify `containers.create()` called with `network_mode='none'`, `read_only=True`, `mem_limit='512m'`
   - `test_run_parses_json_output` -- mock container logs return valid JSON; verify `SandboxResult.import_ok` matches
   - `test_run_handles_timeout` -- mock `container.wait()` raises `requests.exceptions.ReadTimeout`; verify result has `import_ok=False`, `sandbox_skipped=False`
   - `test_run_kills_container_on_timeout` -- verify `container.kill()` called on timeout
   - `test_run_removes_container_on_success` -- verify `container.remove(force=True)` called
   - `test_run_handles_docker_exception` -- `containers.create()` raises `docker.errors.DockerException`; returns error SandboxResult

### Step 7: Create tests/creator/test_sample_data.py
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** D

1. Create `tests/creator/test_sample_data.py` with:

   **`TestSampleDataGenerator`:**
   - `test_str_field_generates_test_name` -- `FieldDefinition(name='sentiment', type_annotation='str', ...)` -> `{'sentiment': 'test_sentiment'}`
   - `test_int_field_generates_1` -- `type_annotation='int'` -> value is `1`
   - `test_float_field_generates_1_0` -- `type_annotation='float'` -> value is `1.0`
   - `test_bool_field_generates_true` -- `type_annotation='bool'` -> value is `True`
   - `test_list_str_field` -- `type_annotation='list[str]'` -> `['test_item']`
   - `test_dict_field` -- `type_annotation='dict[str, str]'` -> `{'key': 'value'}`
   - `test_optional_not_required_returns_none` -- `is_required=False, type_annotation='str | None'` -> `None`
   - `test_field_with_default_uses_default_string` -- `default='""', type_annotation='str'` -> `""`
   - `test_field_with_default_uses_default_int` -- `default='42'` -> `42` (or `"42"` -- verify what makes sense)
   - `test_empty_fields_returns_empty_dict` -- `generate([])` -> `{}`
   - `test_generate_json_returns_valid_json_string` -- `generate_json(fields)` is parseable JSON
   - `test_unknown_type_annotation_returns_string_fallback` -- unrecognized type returns some string value without raising

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Site-packages parent mount exposes host FS broadly | Medium | Mount is read-only; container has no network and drops all caps; tmpfs workspace for writes |
| Windows path format for docker bind mounts on Docker Desktop | Medium | Docker Desktop handles WSL2 path translation; use `str(Path(...))` which normalizes separators; test on CI |
| `requests.exceptions.ReadTimeout` import not obvious | Low | Import `requests.exceptions` explicitly in `sandbox.py`; catch broadly with `Exception` as fallback |
| TYPE_CHECKING guard imports flagged by AST denylist | Low | Rare in LLM-generated code; accepted false positive for v1; document in code comment |
| Image pull failure (`python:3.11-slim` not cached) | Medium | Catch `docker.errors.ImageNotFound` / `APIError` during `containers.create`; return error SandboxResult with clear message |
| Generated YAML file (`_prompts.py`) incorrectly named `.py` | Low | Current `all_artifacts` includes `{step_name}_prompts.py` containing YAML -- this will fail import-check. Fix: exclude non-Python artifacts from import list in `run_test.py` invocation |
| `ast.parse` edge cases (f-strings, walrus operator) | Low | `_syntax_check` in existing `steps.py` already handles this; AST denylist only scans successfully-parsed code |
| Container auto_remove=False leak if exception before remove | Medium | Use try/finally to ensure `container.remove(force=True)` always called |

## Success Criteria

- [ ] `CodeSecurityValidator` detects all 7 pattern categories (system access, dynamic execution, dynamic imports, builtin manipulation, FFI, network, resource exhaustion)
- [ ] `StepSandbox.run()` returns `sandbox_skipped=True` when Docker unavailable, with no exception raised
- [ ] `StepSandbox.run()` returns `sandbox_skipped=True` and `security_issues` populated when AST scan finds blocked code
- [ ] Container created with `network_mode='none'`, `read_only=True`, `mem_limit='512m'`, `cap_drop=['ALL']`
- [ ] `SampleDataGenerator.generate()` produces type-appropriate values for all 7 type annotations in the table
- [ ] `CodeValidationContext` has `sandbox_valid`, `sandbox_skipped`, `sandbox_output` fields
- [ ] `CodeValidationStep.process_instructions()` calls sandbox and populates context fields
- [ ] `pyproject.toml` has `sandbox = ["docker>=7.0"]` optional-dep
- [ ] Prompt YAML files excluded from import-check artifact list (only `.py` files that contain Python code passed to `run_test.py`)
- [ ] All unit tests pass with `pytest` (Docker unavailable tests use mocks)
- [ ] No Docker daemon required to run test suite

## Phase Recommendation

**Risk Level:** medium
**Reasoning:** Core logic is well-specified by validated research; main risk is the site-packages mount strategy and Windows path handling which requires runtime validation. The prompts.yaml artifact naming issue (risk row 6) needs to be handled at implementation time -- `_prompts.py` contains YAML not Python and should be excluded from the import list. These are implementation details, not architectural blockers.
**Suggested Exclusions:** review
