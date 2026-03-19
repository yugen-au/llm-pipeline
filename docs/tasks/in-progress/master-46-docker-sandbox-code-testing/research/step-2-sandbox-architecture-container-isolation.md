# Research Step 2: Sandbox Architecture & Container Isolation

## 1. Container Isolation Architecture

### 1.1 Defense-in-Depth Layers

The sandbox uses 6 isolation layers. Each layer provides independent protection; combined, they form a robust sandbox even if one layer is bypassed.

| Layer | Docker SDK Parameter | Value | Purpose |
|---|---|---|---|
| Network isolation | `network_mode` | `'none'` | No DNS, no outbound, no inbound. Prevents data exfiltration. |
| Filesystem read-only | `read_only` | `True` | Container root filesystem is read-only. Prevents persistent writes. |
| tmpfs workspace | `mounts` (Mount type=tmpfs) | `/workspace`, 64MB | In-memory writable area. Auto-destroyed on container removal. |
| Capability drop | `cap_drop` | `['ALL']` | Removes all Linux capabilities (NET_ADMIN, SYS_ADMIN, etc). |
| No privilege escalation | `security_opt` | `['no-new-privileges']` | Prevents setuid/setgid privilege escalation. |
| PID limit | `pids_limit` | `50` | Prevents fork bombs. Python typically uses 1-5 PIDs. |

### 1.2 Network Isolation Detail

`network_mode='none'` creates the container with no network namespace connectivity:
- No loopback interface (127.0.0.1 unavailable for socket servers)
- No DNS resolution (`socket.getaddrinfo` fails)
- No outbound HTTP/HTTPS (requests, urllib all fail)
- No inbound connections possible

This is the strongest network isolation Docker provides. No additional iptables rules or firewall configuration needed.

### 1.3 Filesystem Isolation Detail

Two-layer filesystem strategy:

**Layer 1: Read-only root** (`read_only=True`)
- Container cannot write to `/`, `/tmp`, `/var`, `/etc`, or any standard path
- `python:3.11-slim` image contents remain immutable
- Prevents malicious code from modifying Python installation or system files

**Layer 2: tmpfs workspace** (`Mount(target='/workspace', type='tmpfs', tmpfs_size='64m')`)
- In-memory filesystem, never touches host disk
- 64MB size limit (sufficient for test artifacts, prevents memory exhaustion)
- Auto-destroyed when container is removed
- Only writable location available to code

**Layer 3: Read-only code mount** (`Mount(target='/code', type='bind', source=tmpdir, read_only=True)`)
- Generated code files mounted from host temp directory
- Read-only: container cannot modify the mounted code
- Host temp directory isolated via `tempfile.TemporaryDirectory()`

### 1.4 Seccomp Profile Decision

Default Docker seccomp profile blocks ~44 dangerous syscalls including:
- `keyctl`, `ptrace`, `reboot`, `kexec_load`
- `clock_settime`, `settimeofday`
- `mount`, `umount`, `swapon`, `swapoff`
- `init_module`, `delete_module`

**Decision: Use default profile (do not specify `security_opt=['seccomp=...']`).**

Rationale: Custom seccomp profile adds operational complexity (JSON file management, cross-platform differences) with minimal security gain for Python code execution. The default profile + `cap_drop=ALL` + `no-new-privileges` already blocks all meaningful privilege escalation vectors.

### 1.5 Capability Dropping Detail

`cap_drop=['ALL']` removes all 38+ Linux capabilities:
- `NET_RAW` (raw sockets), `NET_ADMIN` (network config)
- `SYS_ADMIN` (mount, namespace), `SYS_PTRACE` (process tracing)
- `CHOWN`, `DAC_OVERRIDE`, `FOWNER`, `SETUID`, `SETGID`

No capabilities need to be added back (`cap_add=[]`). Python code execution requires zero capabilities.

## 2. Resource Constraint Architecture

### 2.1 Memory Constraints

```python
mem_limit='512m'        # Hard limit: 512MB RAM
memswap_limit='512m'    # Total memory+swap: 512MB (effectively 0 swap)
oom_kill_disable=False   # Allow OOM killer (default, do not disable)
```

Setting `memswap_limit` equal to `mem_limit` prevents swap usage. This ensures:
- Deterministic memory behavior (no swap thrashing)
- OOM killer triggers at exactly 512MB
- Container is killed cleanly on memory exhaustion

### 2.2 CPU Constraints

```python
cpu_period=100000    # CFS period: 100ms (default)
cpu_quota=100000     # CFS quota: 100ms per period = 1 full CPU
```

**Why `cpu_period/cpu_quota` instead of `cpu_count`:**
- `cpu_count` is Windows containers only (Hyper-V isolation)
- `cpu_period/cpu_quota` works on all platforms (Linux, WSL2, Docker Desktop)
- `cpu_shares` is relative (only meaningful with contention) -- not suitable for hard limits
- `nano_cpus=1000000000` (1e9) is equivalent but less readable

### 2.3 Execution Timeout

```python
TIMEOUT_SECONDS = 60  # from task spec
```

Timeout is enforced at the Docker SDK level via `container.wait(timeout=60)`, NOT at the container level. This means:
- The container itself has no internal timeout mechanism
- If `container.wait()` times out, the container continues running until explicitly killed
- The kill sequence is: `container.kill()` (SIGKILL) -> `container.wait()` -> `container.remove(force=True)`

### 2.4 Combined Constraint Configuration

```python
CONTAINER_CONFIG = {
    'image': 'python:3.11-slim',
    'network_mode': 'none',
    'mem_limit': '512m',
    'memswap_limit': '512m',
    'cpu_period': 100000,
    'cpu_quota': 100000,
    'pids_limit': 50,
    'read_only': True,
    'cap_drop': ['ALL'],
    'security_opt': ['no-new-privileges'],
    'auto_remove': False,     # must be False to read logs before cleanup
    'stdin_open': False,
    'tty': False,
}
```

**`auto_remove=False` rationale:** We need to read `container.logs()` and potentially `container.get_archive()` after the container exits. With `auto_remove=True`, the container is deleted immediately on exit, making log retrieval race-prone.

## 3. Container Lifecycle Architecture

### 3.1 Lifecycle State Machine

```
INIT -> PREPARE -> CREATE -> START -> WAIT -> COLLECT -> CLEANUP -> DONE
  |       |          |         |        |        |          |
  |       |          |         |     timeout     |          |
  |       |          |         |        v        |          |
  |       |          |         +-> KILL -> COLLECT_TIMEOUT -> CLEANUP -> DONE
  |       |          |
  |       |       create_error
  |       |          v
  |       +--- CLEANUP_PARTIAL -> DONE (error result)
  |
  docker_unavailable
  v
  SKIP -> DONE (skipped result)
```

### 3.2 Detailed Lifecycle Implementation

```python
def run(self, artifacts: dict[str, str], sample_data: dict | None = None) -> SandboxResult:
    """Execute generated code in Docker sandbox."""
    start_time = time.monotonic()

    # Phase 0: Pre-scan
    all_code = '\n'.join(artifacts.values())
    errors = self.validate_code(all_code)
    if errors:
        return SandboxResult(success=False, errors=errors)

    # Phase 1: Docker availability check
    if not self.available:
        return SandboxResult(success=True, skipped=True,
                             warnings=["Docker unavailable, sandbox skipped"])

    container = None
    try:
        with tempfile.TemporaryDirectory(prefix='llm_sandbox_') as tmpdir:
            # Phase 2: Prepare temp directory
            self._write_files(tmpdir, artifacts, sample_data)

            # Phase 3: Create container
            mounts = [
                Mount(target='/code', source=str(tmpdir), type='bind', read_only=True),
                Mount(target='/workspace', source='', type='tmpfs', tmpfs_size='64m'),
            ]
            container = self.client.containers.create(
                command='python /code/run_test.py',
                mounts=mounts,
                working_dir='/workspace',
                **self.CONTAINER_CONFIG,
            )

            # Phase 4: Start container
            container.start()

            # Phase 5: Wait with timeout
            timed_out = False
            try:
                result = container.wait(timeout=self.CONSTRAINTS['timeout'])
                exit_code = result.get('StatusCode', -1)
            except Exception:
                container.kill()
                container.wait()
                exit_code = -1
                timed_out = True

            # Phase 6: Collect output
            stdout = container.logs(stdout=True, stderr=False).decode('utf-8', errors='replace')
            stderr = container.logs(stdout=False, stderr=True).decode('utf-8', errors='replace')

            duration = time.monotonic() - start_time

            return SandboxResult(
                success=(exit_code == 0 and not timed_out),
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                timed_out=timed_out,
                duration_seconds=round(duration, 2),
            )
    except Exception as exc:
        return SandboxResult(
            success=False,
            errors=[f"Sandbox error: {exc}"],
            duration_seconds=round(time.monotonic() - start_time, 2),
        )
    finally:
        # Phase 7: Cleanup container
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass  # container may already be removed or never created
```

### 3.3 Why `create + start` Instead of `run`

`client.containers.run(detach=True)` combines create + start + optional pull. Using separate `create()` + `start()`:

1. **Error isolation**: Creation errors (bad config, missing image) are distinct from runtime errors
2. **Mount validation**: Can inspect container config after creation before starting
3. **Cleanup guarantee**: Container ID is known after create, even if start fails
4. **Image pull control**: Can pre-pull image separately (see section 5)

### 3.4 Timeout Kill Sequence

When `container.wait(timeout=60)` times out:

```
wait() raises exception
  -> container.kill()         # sends SIGKILL (immediate, not SIGTERM)
  -> container.wait()         # blocks until container fully stops (fast after SIGKILL)
  -> proceed to log collection
```

Using SIGKILL (via `container.kill()`) rather than `container.stop()` (which sends SIGTERM first, then SIGKILL after grace period) because:
- Code has already exceeded timeout -- no need for graceful shutdown
- SIGKILL is immediate -- avoids additional delay
- Python processes don't need cleanup on test abort

## 4. Volume Mounting Architecture

### 4.1 Mount Strategy

```python
from docker.types import Mount

mounts = [
    # Code: read-only bind mount from host temp dir
    Mount(
        target='/code',
        source=str(tmpdir),    # host path
        type='bind',
        read_only=True,
    ),
    # Workspace: writable in-memory tmpfs
    Mount(
        target='/workspace',
        source='',             # no source for tmpfs
        type='tmpfs',
        tmpfs_size='64m',      # 64MB limit
    ),
]
```

### 4.2 Why `docker.types.Mount` Over `volumes` Dict

Docker SDK supports two volume specification formats:
- `volumes={'/host/path': {'bind': '/container/path', 'mode': 'ro'}}` -- legacy dict format
- `mounts=[Mount(...)]` -- modern Mount objects

Mount objects are preferred because:
- Support tmpfs mounts (volumes dict does not)
- Explicit type field (`bind`, `volume`, `tmpfs`)
- Better IDE autocomplete and type checking
- Docker SDK docs recommend Mount for new code

### 4.3 Temp Directory File Layout

```
{tmpdir}/
    run_test.py          # test harness entry point
    step_code.py         # generated step artifact
    instructions_code.py # generated instructions artifact
    extraction_code.py   # generated extraction artifact (optional)
    sample_data.json     # test data (optional)
```

Files are written by `StepSandbox._write_files()` before container creation. The temp directory path is resolved to absolute path for Docker bind mount compatibility.

### 4.4 Cross-Platform Path Considerations

Docker bind mounts require absolute paths. On Windows with Docker Desktop (WSL2 backend):
- `tempfile.TemporaryDirectory()` returns Windows paths (e.g., `C:\Users\...\Temp\llm_sandbox_xyz`)
- Docker Desktop auto-translates Windows paths to WSL2 paths for bind mounts
- `pathlib.Path` handles path separator normalization
- No special handling needed for the source path in `Mount(source=str(tmpdir))`

## 5. Result Extraction Architecture

### 5.1 SandboxResult Model

```python
from pydantic import BaseModel

class SandboxResult(BaseModel):
    """Result of sandbox code execution."""

    success: bool                        # True if code ran without errors
    skipped: bool = False                # True if Docker unavailable
    exit_code: int = 0                   # Container exit code (0=success)
    stdout: str = ""                     # Container stdout
    stderr: str = ""                     # Container stderr
    timed_out: bool = False              # True if execution exceeded timeout
    duration_seconds: float = 0.0        # Wall-clock execution time
    errors: list[str] = []              # Pre-scan + runtime errors
    warnings: list[str] = []            # Non-blocking warnings
```

### 5.2 Output Capture Strategy

Docker SDK captures stdout/stderr separately via `container.logs()`:

```python
stdout = container.logs(stdout=True, stderr=False).decode('utf-8', errors='replace')
stderr = container.logs(stdout=False, stderr=True).decode('utf-8', errors='replace')
```

Using `errors='replace'` for decode because:
- Generated code may print non-UTF-8 bytes
- Container may produce binary output on error
- Replacement character is safe for result display

### 5.3 Structured Output from Test Harness

The `run_test.py` harness writes structured JSON to stdout:

```json
{
  "import_ok": true,
  "syntax_ok": true,
  "sample_data_ok": true,
  "errors": [],
  "warnings": []
}
```

Parsing strategy:
1. If exit_code == 0, try `json.loads(stdout)` for structured result
2. If JSON parse fails, treat raw stdout as text output (still success if exit_code == 0)
3. If exit_code != 0, stderr contains the error traceback

### 5.4 Artifact Collection (Optional)

For advanced use cases, `container.get_archive('/workspace')` can retrieve files written by the code:

```python
bits, stat = container.get_archive('/workspace')
tar_stream = b''.join(bits)
# Extract tar to inspect output files
```

**Decision: Not implemented in initial version.** Stdout/stderr + exit code is sufficient for pass/fail validation. Artifact collection adds complexity (tar parsing, file extraction) without clear value for the code-validation use case.

## 6. Image Management

### 6.1 Image Pull Strategy

The sandbox uses `python:3.11-slim`. This image must be available locally. Two approaches:

**Lazy pull (on first run):**
```python
try:
    self.client.images.get('python:3.11-slim')
except docker.errors.ImageNotFound:
    self.client.images.pull('python:3.11-slim')
```
Drawback: First run is slow (~30s to pull ~150MB image). Network required.

**Eager pull (on init):**
```python
def _init_client(self):
    self.client = docker.from_env()
    self.client.ping()
    # Ensure image exists
    try:
        self.client.images.get('python:3.11-slim')
    except ImageNotFound:
        self.client.images.pull('python:3.11-slim')
```
Drawback: Init is slow if image not cached.

**Recommended: Lazy pull with availability check.**
- `__init__` checks Docker connectivity only (`ping()`)
- `run()` checks for image before creating container
- Pull only if missing, with timeout
- Report in SandboxResult.warnings if pull was needed

### 6.2 Image Version Pinning

`python:3.11-slim` tracks the latest 3.11.x patch. For deterministic builds:
- Option A: Pin digest `python:3.11-slim@sha256:...` -- most deterministic but requires manual updates
- Option B: Use `python:3.11-slim` (current) -- auto-gets security patches
- Option C: Make image configurable via class attribute

**Recommended: Option C.** Default to `python:3.11-slim` but allow override:

```python
class StepSandbox:
    IMAGE = 'python:3.11-slim'
    # Can be overridden: StepSandbox.IMAGE = 'custom-sandbox:latest'
```

## 7. Error Handling Architecture

### 7.1 Error Categories

| Category | Cause | SandboxResult |
|---|---|---|
| Pre-scan failure | Dangerous imports detected | `success=False, errors=[...]` |
| Docker unavailable | Daemon not running, docker not installed | `success=True, skipped=True, warnings=[...]` |
| Image not found | `python:3.11-slim` not pulled, pull fails | `success=False, errors=["Image not found: ..."]` |
| Creation error | Invalid Docker config | `success=False, errors=["Container creation failed: ..."]` |
| Runtime error | Code throws exception | `success=False, exit_code=1, stderr="Traceback..."` |
| Timeout | Code exceeds 60s | `success=False, timed_out=True` |
| OOM kill | Code exceeds 512MB | `success=False, exit_code=137` (SIGKILL by OOM) |

### 7.2 Exit Code Interpretation

| Exit Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Python exception (unhandled) |
| 2 | Python usage error (bad args) |
| 137 | SIGKILL (OOM kill or manual kill) |
| 139 | SIGSEGV (segmentation fault) |
| -1 | Timeout (set by sandbox, not Docker) |

### 7.3 Exception Handling Strategy

All exceptions in the sandbox lifecycle are caught and converted to SandboxResult. The sandbox NEVER raises exceptions to the caller. This ensures:
- CodeValidationStep always receives a result
- Pipeline execution is never interrupted by Docker errors
- All error information is captured in the result model

## 8. Determinism and Reproducibility

### 8.1 Sources of Non-Determinism

| Source | Mitigation |
|---|---|
| Image version drift | Pin `IMAGE` class attribute, allow override |
| Network timing | `network_mode='none'` eliminates network dependencies |
| Random data | Test harness uses deterministic sample data (JSON input) |
| Filesystem ordering | tmpfs is clean on each run, no prior state |
| CPU scheduling | Not mitigated -- execution time may vary but correctness doesn't |
| OOM timing | Memory limit is deterministic; OOM behavior depends on allocation pattern |

### 8.2 Reproducibility Guarantees

Given identical inputs (code artifacts + sample data), the sandbox guarantees:
- Same pass/fail result (deterministic code + deterministic data)
- Same exit code
- Similar but not identical stdout/stderr (timing-dependent log lines may vary)
- Similar but not identical duration_seconds

### 8.3 Container Cleanup Guarantee

```python
finally:
    if container is not None:
        try:
            container.remove(force=True)
        except Exception:
            pass
```

`container.remove(force=True)` combines stop + remove. The `force=True` flag:
- Kills running container (if still running after timeout kill failed)
- Removes container and its writable layer
- Releases all tmpfs memory
- Idempotent: does not error if container already removed

Combined with `tempfile.TemporaryDirectory()` context manager, all resources are cleaned up even on exceptions.

## 9. Integration Points with Creator Package

### 9.1 sandbox.py Location

```
llm_pipeline/creator/sandbox.py
```

New file in the existing creator package. Contains:
- `SandboxResult` (Pydantic BaseModel)
- `StepSandbox` (main class)

### 9.2 Module Exports

```python
# sandbox.py
__all__ = ["StepSandbox", "SandboxResult"]
```

```python
# creator/__init__.py -- add:
from llm_pipeline.creator.sandbox import StepSandbox, SandboxResult
```

### 9.3 Relationship to CodeValidationStep

Step-1 research (section 3.2) identified the integration point: `CodeValidationStep.process_instructions()` calls `StepSandbox.run()`. The sandbox result augments the existing AST + LLM validation.

Sandbox does NOT block validation when Docker is unavailable. The `skipped=True` result allows `is_valid` to be determined by AST + LLM review alone.

### 9.4 Relationship to Task 47 (Downstream)

Task 47 (StepIntegrator) receives `CodeValidationContext.all_artifacts` and writes files to disk. The sandbox result (`sandbox_valid`, `sandbox_skipped`) informs the integrator whether runtime validation was performed.

If `sandbox_valid=False`, the integrator could:
- Refuse to integrate (strict mode)
- Integrate with warning (lenient mode)
- This is Task 47's decision -- out of scope for sandbox design.

## 10. Architectural Decisions

### Decision 1: Use `docker.types.Mount` over legacy volumes dict
**Choice:** Mount objects.
**Rationale:** Required for tmpfs support. Better type safety. Docker SDK recommended.

### Decision 2: Default seccomp profile (no custom)
**Choice:** Do not specify custom seccomp profile.
**Rationale:** Default blocks dangerous syscalls. Custom profile adds operational complexity without meaningful security gain for Python code.

### Decision 3: `cap_drop=['ALL']` with no `cap_add`
**Choice:** Drop all capabilities, add none back.
**Rationale:** Python code execution requires zero Linux capabilities. Maximum restriction.

### Decision 4: SIGKILL on timeout (not SIGTERM)
**Choice:** `container.kill()` (SIGKILL) instead of `container.stop()` (SIGTERM + grace).
**Rationale:** Code exceeded timeout -- no need for graceful shutdown. Immediate termination.

### Decision 5: `auto_remove=False`
**Choice:** Manual removal after log collection.
**Rationale:** `auto_remove=True` races with `container.logs()`. Manual removal in `finally` block is deterministic.

### Decision 6: Sandbox never raises exceptions
**Choice:** All errors converted to SandboxResult.
**Rationale:** Pipeline must never crash due to Docker issues. Caller always gets a structured result.

### Decision 7: 64MB tmpfs workspace
**Choice:** 64MB tmpfs at `/workspace`.
**Rationale:** Sufficient for test artifacts. Prevents memory exhaustion (separate from 512MB container limit). Auto-cleaned.

## 11. Cross-Reference with Step-1 Research

| Topic | Step-1 Coverage | Step-2 Addition |
|---|---|---|
| Docker SDK API | Basic lifecycle, error hierarchy | -- (no duplication) |
| Resource constraints | Table of params | Memory swap, OOM behavior, cross-platform CPU |
| Container lifecycle | Linear flow diagram | State machine, error branches, kill sequence |
| Volume mounting | Legacy dict syntax example | Mount objects, tmpfs, cross-platform paths |
| Isolation layers | network_mode, security_opt | Full 6-layer defense-in-depth, seccomp analysis, capabilities |
| Result extraction | Basic stdout/stderr | Structured JSON harness, exit code interpretation, artifact collection analysis |
| Image management | Not covered | Pull strategy, version pinning, configurability |
| Error handling | Error hierarchy | Error categories table, exception-free guarantee |
| Determinism | Not covered | Non-determinism sources, reproducibility guarantees |
