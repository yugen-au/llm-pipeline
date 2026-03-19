# IMPLEMENTATION - STEP 1: CREATE SANDBOX.PY
**Status:** completed

## Summary
Created `llm_pipeline/creator/sandbox.py` with three components: `SandboxResult` (Pydantic BaseModel), `CodeSecurityValidator` (AST-based denylist), and `StepSandbox` (Docker container executor with graceful fallback).

## Files
**Created:** `llm_pipeline/creator/sandbox.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/creator/sandbox.py`
New file with three components:

**SandboxResult(BaseModel)** - Transient result model with fields: `import_ok`, `security_issues`, `sandbox_skipped`, `output`, `errors`, `modules_found`. Defaults to `import_ok=False`, `sandbox_skipped=True`.

**CodeSecurityValidator** - Uses internal `_SecurityVisitor(ast.NodeVisitor)` with:
- `BLOCKED_MODULES`: 36-entry frozenset (os, subprocess, sys, socket, ctypes, etc.)
- `BLOCKED_BUILTINS`: 6-entry frozenset (eval, exec, compile, open, __import__, breakpoint)
- `BLOCKED_ATTRIBUTES`: 10-entry frozenset (system, popen, call, Popen, run, check_output, spawn, execv, execve, fork)
- `visit_Import`, `visit_ImportFrom`, `visit_Call` methods
- `_resolve_attribute_chain` static helper for dotted attribute resolution

**StepSandbox** - Docker container executor with:
- `__init__(image, timeout)` stores config only
- `_get_client()` imports docker inside method, returns None on ImportError or DockerException
- `_discover_framework_path()` uses `importlib.util.find_spec('llm_pipeline')`
- `_write_files()` writes artifacts + run_test.py harness + sample_data.json; excludes `_prompts.py` from import list
- `validate_code()` thin wrapper to CodeSecurityValidator
- `run()` performs AST scan then Docker import-check with full container constraints

Container constraints applied: `network_mode='none'`, `read_only=True`, tmpfs `/workspace` 64MB, `cap_drop=['ALL']`, `security_opt=['no-new-privileges']`, `pids_limit=50`, `mem_limit='512m'`, `memswap_limit='512m'`, `cpu_period=100000`, `cpu_quota=100000`.

## Decisions
### _SecurityVisitor as internal class
**Choice:** Made `_SecurityVisitor` a private internal class, `CodeSecurityValidator` as public API
**Rationale:** Keeps the visitor implementation detail hidden; public API is `CodeSecurityValidator.validate(code)` which creates a fresh visitor per call (no state leakage)

### Prompt file exclusion strategy
**Choice:** Exclude files ending with `_prompts.py` from both AST scan and import-check list
**Rationale:** `{step_name}_prompts.py` contains YAML content (not Python); attempting to import or AST-parse it would fail. Identified in PLAN.md risk table row 6.

### ReadTimeout import location
**Choice:** Import `requests.exceptions.ReadTimeout` inside the try block where `container.wait()` is called
**Rationale:** `requests` is a transitive dependency of `docker`; importing at method level keeps it co-located with usage and avoids top-level dep on requests.

### Broad exception catch in run()
**Choice:** Outer try/except catches `Exception` (not just `docker.errors.DockerException`)
**Rationale:** Container lifecycle can raise various exceptions (APIError, ImageNotFound, etc.). Catching broadly ensures the sandbox never crashes the pipeline. All errors are logged and returned in SandboxResult.

## Verification
[x] SandboxResult defaults: import_ok=False, sandbox_skipped=True
[x] CodeSecurityValidator detects blocked imports (os, subprocess)
[x] CodeSecurityValidator detects blocked from-imports (from os import path)
[x] CodeSecurityValidator detects blocked builtins (eval, exec)
[x] CodeSecurityValidator detects blocked attributes (os.system)
[x] CodeSecurityValidator allows safe imports (pydantic, llm_pipeline)
[x] CodeSecurityValidator returns multiple issues for multiple violations
[x] Empty code returns no issues
[x] StepSandbox.validate_code delegates to CodeSecurityValidator
[x] Docker unavailable -> sandbox_skipped=True, no exception raised
[x] Security issues -> early return with sandbox_skipped=True
[x] Prompt YAML files excluded from import-check artifact list
[x] try/finally ensures container.remove(force=True) always called
[x] Module imports and loads without Docker installed
[x] Syntax validation passes (ast.parse)
