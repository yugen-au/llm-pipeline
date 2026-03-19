# Research Step 1: Docker SDK & Creator Integration

## 1. Docker SDK (docker-py) API Reference

### 1.1 Client Initialization

```python
import docker
from docker.errors import DockerException

# Standard: reads DOCKER_HOST, DOCKER_TLS_VERIFY, DOCKER_CERT_PATH
client = docker.from_env()

# Verify connectivity
client.ping()  # returns True or raises APIError
```

### 1.2 Container Lifecycle

```python
# Run in detached mode (non-blocking)
container = client.containers.run(
    image='python:3.11-slim',
    command='python /code/runner.py',
    detach=True,
    volumes={'/host/code': {'bind': '/code', 'mode': 'ro'}},
    network_mode='none',
    mem_limit='512m',
    cpu_period=100000,
    cpu_quota=50000,  # 50% of 1 CPU
    working_dir='/workspace',
    read_only=False,        # need /workspace writable
    auto_remove=False,      # we read logs before removing
    security_opt=['no-new-privileges'],
)

# Wait with timeout
result = container.wait(timeout=60)  # {'StatusCode': 0, 'Error': None}
exit_code = result['StatusCode']

# Capture output
stdout = container.logs(stdout=True, stderr=False).decode('utf-8')
stderr = container.logs(stdout=False, stderr=True).decode('utf-8')

# Cleanup
container.remove(force=True)
```

### 1.3 Resource Constraints (from task spec)

| Constraint | Docker SDK param | Value |
|---|---|---|
| Network isolation | `network_mode` | `'none'` |
| Memory limit | `mem_limit` | `'512m'` |
| CPU limit | `cpu_period` + `cpu_quota` | `100000` / `100000` (1 CPU equiv) |
| Timeout | `container.wait(timeout=N)` | `60` seconds |
| No privilege escalation | `security_opt` | `['no-new-privileges']` |
| Filesystem | `read_only` + writable `/workspace` | mount code as `ro` |

Note: `cpu_count` is Windows-only per docker-py docs. For cross-platform CPU limiting, use `cpu_period`/`cpu_quota` or `cpu_shares`. `cpu_period=100000, cpu_quota=100000` = 1 full CPU.

### 1.4 Volume Mounting Pattern

```python
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as tmpdir:
    code_dir = Path(tmpdir)
    (code_dir / 'runner.py').write_text(test_harness_code)
    (code_dir / 'sample_data.json').write_text(json.dumps(sample_data))

    container = client.containers.run(
        'python:3.11-slim',
        command='python /code/runner.py',
        volumes={str(code_dir): {'bind': '/code', 'mode': 'ro'}},
        detach=True,
        # ... constraints
    )
```

### 1.5 Error Hierarchy

```
DockerException (base)
  +-- APIError (server errors)
  |     +-- NotFound (404 - container/image not found)
  |     +-- ImageNotFound (404 - image specifically)
  +-- ContainerError (non-zero exit from containers.run without detach)
  +-- BuildError (image build failures)
```

Key patterns:
- `DockerException` on `from_env()` = Docker daemon not running/installed
- `ImageNotFound` on `containers.run()` = image not pulled
- `APIError` = general server-side failures
- `ContainerError` only raised in foreground mode (not detached)
- `requests.exceptions.ConnectionError` can also surface through docker-py when daemon socket unreachable

### 1.6 Timeout Handling

`container.wait(timeout=N)` raises `requests.exceptions.ReadTimeout` (or `ConnectionError`) on timeout. The container continues running - must be explicitly killed:

```python
try:
    result = container.wait(timeout=60)
except Exception:
    container.kill()
    container.wait()
    result = {'StatusCode': -1, 'Error': 'Timeout'}
finally:
    container.remove(force=True)
```

## 2. Existing Creator Package Structure

### 2.1 Package Layout (Task 45 output)

```
llm_pipeline/creator/
    __init__.py          # jinja2 ImportError guard, re-exports StepCreatorPipeline
    models.py            # FieldDefinition, ExtractionTarget, GenerationRecord (SQLModel)
    schemas.py           # 4 Instructions + 4 Context classes
    pipeline.py          # StepCreatorInputData, Registry, AgentRegistry, Strategy, Pipeline
    steps.py             # 4 @step_definition steps + GenerationRecordExtraction
    prompts.py           # 8 seed prompts + seed_prompts()
    templates/
        __init__.py      # Jinja2 Environment, render_template()
        step.py.j2
        instructions.py.j2
        extraction.py.j2
        prompts.yaml.j2
```

### 2.2 Pipeline Flow

```
StepCreatorInputData(description, target_pipeline, include_extraction, include_transformation)
  |
  v
RequirementsAnalysisStep -> RequirementsAnalysisContext(step_name, step_class_name, instruction_fields, ...)
  |
  v
CodeGenerationStep -> CodeGenerationContext(step_code, instructions_code, extraction_code)
  |
  v
PromptGenerationStep -> PromptGenerationContext(system_prompt, user_prompt_template, ...)
  |
  v
CodeValidationStep -> CodeValidationContext(is_valid, syntax_valid, llm_review_valid, issues, all_artifacts)
```

### 2.3 Current CodeValidationStep Logic

Located in `llm_pipeline/creator/steps.py` lines 234-318.

Current validation is **static only**:
1. `_syntax_check(code)` - `ast.parse(code, mode="exec")` for each artifact
2. LLM review via pydantic-ai agent (produces CodeValidationInstructions)
3. Combines: `is_valid = syntax_valid and inst.is_valid`

No runtime execution. Sandbox adds a 3rd validation dimension: actually running the code.

### 2.4 StepCreatorInputData

```python
class StepCreatorInputData(PipelineInputData):
    description: str
    target_pipeline: str | None = None
    include_extraction: bool = True
    include_transformation: bool = False
```

Note: No `sample_data` field exists. See Question 1.

### 2.5 CodeValidationContext (output)

```python
class CodeValidationContext(PipelineContext):
    is_valid: bool
    syntax_valid: bool
    llm_review_valid: bool
    issues: list[str]
    all_artifacts: dict[str, str]   # filename -> code string
```

Sandbox integration would add fields like `sandbox_valid: bool`, `sandbox_skipped: bool`, `sandbox_output: str`.

## 3. Integration Architecture

### 3.1 StepSandbox as Utility (not a pipeline step)

Per task spec: "ValidationStep calls sandbox to test generated code". Sandbox is a **service class** used by CodeValidationStep, not a 5th pipeline step.

```python
# llm_pipeline/creator/sandbox.py

class StepSandbox:
    """Execute generated Python code in isolated Docker container."""

    CONSTRAINTS = {
        'network_mode': 'none',
        'mem_limit': '512m',
        'cpu_period': 100000,
        'cpu_quota': 100000,
        'timeout': 60,
    }

    DANGEROUS_IMPORTS = [
        'os.system', 'subprocess', 'eval', 'exec',
        '__import__', 'importlib', 'builtins', 'ctypes',
    ]

    def __init__(self):
        self.client: docker.DockerClient | None = None
        self.available = False
        self._init_client()

    def _init_client(self):
        try:
            import docker
            self.client = docker.from_env()
            self.client.ping()
            self.available = True
        except Exception:
            self.available = False

    def validate_code(self, code: str) -> list[str]:
        """Pre-scan for dangerous patterns."""
        ...

    def run(self, code: str, sample_data: dict | None = None) -> SandboxResult:
        """Execute code in Docker. Graceful fallback if unavailable."""
        ...
```

### 3.2 CodeValidationStep Integration Point

In `steps.py`, `CodeValidationStep.process_instructions()` would call sandbox:

```python
def process_instructions(self, instructions):
    # ... existing AST + LLM logic ...

    # NEW: sandbox runtime validation
    sandbox = StepSandbox()
    sandbox_result = sandbox.run(step_code, sample_data=...)

    # Merge results
    is_valid = syntax_valid and inst.is_valid and sandbox_result.success
```

### 3.3 SandboxResult Model

```python
class SandboxResult(BaseModel):
    success: bool              # code ran without errors
    skipped: bool = False      # True if Docker unavailable
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    errors: list[str] = []     # pre-scan + runtime errors
    warnings: list[str] = []   # e.g. "Docker not available"
```

### 3.4 Graceful Fallback

When Docker is unavailable (not installed, daemon not running):
1. `StepSandbox.__init__()` catches DockerException, sets `self.available = False`
2. `StepSandbox.run()` returns `SandboxResult(success=True, skipped=True, warnings=["Docker not available, sandbox validation skipped"])`
3. `is_valid` in CodeValidationContext is NOT set to False (sandbox is additive, not blocking)
4. CodeValidationContext gains `sandbox_skipped: bool` field

### 3.5 Dangerous Import Detection

Pre-execution static scan. Patterns from task spec:

```python
DANGEROUS_IMPORTS = [
    'os.system', 'subprocess', 'eval', 'exec',
    '__import__', 'importlib', 'builtins', 'ctypes',
]
```

Implementation: simple string search in code (matching task spec). If any found, sandbox returns failure without running Docker. This provides security even when Docker is available.

### 3.6 File Layout for sandbox.py

```
llm_pipeline/creator/
    sandbox.py     # NEW: StepSandbox, SandboxResult
    models.py      # SandboxResult could go here instead (same pattern as GenerationRecord)
    schemas.py     # CodeValidationContext gains sandbox fields
    steps.py       # CodeValidationStep.process_instructions() calls sandbox
```

## 4. Dependency Management

### 4.1 Optional Dependency Pattern

Following the `creator = ["jinja2>=3.0"]` pattern in pyproject.toml:

Option A: Separate extra
```toml
sandbox = ["docker>=7.0"]
```

Option B: Merge into creator
```toml
creator = ["jinja2>=3.0", "docker>=7.0"]
```

Option C: Combined extra
```toml
creator = ["jinja2>=3.0"]
creator-sandbox = ["jinja2>=3.0", "docker>=7.0"]
```

Recommendation: Option A is cleanest. Sandbox can be used independently of creator templates. Import guard in sandbox.py is soft (degrades gracefully instead of raising).

### 4.2 Import Guard Pattern

```python
# sandbox.py
_has_docker = False
try:
    import docker
    from docker.errors import DockerException, APIError, ImageNotFound
    _has_docker = True
except ImportError:
    pass
```

Unlike creator/__init__.py which raises ImportError, sandbox degrades gracefully.

## 5. Docker Container Execution Flow

```
StepSandbox.run(code, sample_data)
  |
  +-- validate_code(code) -> pre-scan for dangerous imports
  |     |-- if errors: return SandboxResult(success=False, errors=...)
  |
  +-- if not self.available: return SandboxResult(skipped=True)
  |
  +-- Create tempdir
  |     +-- Write runner.py (test harness wrapping generated code)
  |     +-- Write sample_data.json
  |
  +-- client.containers.run(
  |       image='python:3.11-slim',
  |       command='python /code/runner.py',
  |       volumes={tmpdir: {bind: '/code', mode: 'ro'}},
  |       network_mode='none',
  |       mem_limit='512m',
  |       detach=True,
  |   )
  |
  +-- container.wait(timeout=60)
  |     |-- on timeout: container.kill(), return SandboxResult(timed_out=True)
  |
  +-- Read logs (stdout, stderr)
  +-- container.remove(force=True)
  +-- Return SandboxResult(success=exit_code==0, ...)
```

## 6. Context Updates Required

### 6.1 CodeValidationContext Changes

```python
class CodeValidationContext(PipelineContext):
    is_valid: bool
    syntax_valid: bool
    llm_review_valid: bool
    sandbox_valid: bool          # NEW
    sandbox_skipped: bool        # NEW
    sandbox_output: str          # NEW (stdout from container)
    issues: list[str]
    all_artifacts: dict[str, str]
```

### 6.2 StepCreatorInputData Changes (pending CEO decision)

```python
class StepCreatorInputData(PipelineInputData):
    description: str
    target_pipeline: str | None = None
    include_extraction: bool = True
    include_transformation: bool = False
    sample_data: dict | None = None   # NEW (pending Q1)
```

## 7. Unresolved Questions

### Q1: Sample Data Source
Where does `sample_data` come from for sandbox execution?
- **Option A**: Add `sample_data: dict | None = None` to `StepCreatorInputData` - user provides it
- **Option B**: Auto-generate synthetic test data from instruction_fields spec during CodeValidationStep
- **Option C**: Both - use provided if available, generate if not

Impact: Option A is simpler but requires user effort. Option B is more automated but adds complexity. Option C is most flexible.

### Q2: Execution Scope
What code does the sandbox actually run?
- **Option A**: Full rendered module (step.py artifact) - requires `llm-pipeline` installed in Docker container (slow, ~30s pip install per run, or pre-built image)
- **Option B**: Method body snippets only (prepare_calls_body, process_instructions_body) - wrap in minimal test harness with mock objects, no framework dependency needed
- **Option C**: Import-check only - verify the module can be imported without error (needs framework in container)

Impact: Option A is most thorough but has significant cold-start cost. Option B is fast and practical for catching runtime errors in generated logic. Option C is middle ground.

### Q3: Dependency Grouping
How should docker be packaged?
- **Option A**: `sandbox = ["docker>=7.0"]` - separate optional extra
- **Option B**: Merge into `creator = ["jinja2>=3.0", "docker>=7.0"]` - always available with creator
- **Option C**: `creator-sandbox = ["jinja2>=3.0", "docker>=7.0"]` - combined extra

Impact: Option A keeps dependencies minimal (Docker is heavy). Option B simplifies install but forces Docker on all creator users. Option C is confusing naming.
