# Research Summary

## Executive Summary

Consolidated findings from 3 domain research files covering Docker SDK integration, container isolation architecture, and code security analysis. All 4 blocking questions resolved by CEO. Key architectural decisions:

1. **Import-check only** for v1 execution scope -- run_test.py verifies generated modules can be imported
2. **AST-based denylist** for security scanning (~80 lines, Python ast module, no false positives)
3. **Auto-generate sample data** from instruction_fields spec (FieldDefinition has name, type_annotation, description, default, is_required -- sufficient for synthetic data generation)
4. **importlib auto-discovery** for framework mount -- `importlib.util.find_spec('llm_pipeline')` locates package install path, mount read-only into container. Zero config, works in dev (editable install) and prod (pip install).

Research quality is high. Remaining open items are implementation details, not architectural blockers.

## Domain Findings

### Docker SDK & Container Lifecycle
**Source:** step-1-docker-sdk-creator-integration.md, step-2-sandbox-architecture-container-isolation.md

- `docker.from_env()` for client init; `DockerException` on unavailability
- `create() + start()` preferred over `run(detach=True)` for error isolation and cleanup guarantee
- `container.wait(timeout=60)` raises `requests.exceptions.ReadTimeout` on timeout; container must be explicitly killed
- `auto_remove=False` required to read logs before cleanup
- Context7 docs confirm `cpu_period/cpu_quota` is correct cross-platform approach; task spec's `cpu_count` is Windows-only
- `docker.types.Mount` required for tmpfs support (confirmed via Context7 advanced mount examples)

### Container Isolation (6-Layer Defense-in-Depth)
**Source:** step-2-sandbox-architecture-container-isolation.md

| Layer | Parameter | Value |
|-------|-----------|-------|
| Network | `network_mode` | `'none'` |
| Filesystem | `read_only` | `True` |
| Workspace | tmpfs Mount | `/workspace`, 64MB |
| Capabilities | `cap_drop` | `['ALL']` |
| Privilege escalation | `security_opt` | `['no-new-privileges']` |
| Process limits | `pids_limit` | `50` |

Additional: `memswap_limit='512m'` (matches `mem_limit`) prevents swap usage -- good addition not in task spec.

### Code Security & Import Detection
**Source:** step-3-code-security-dangerous-import-detection.md

- 7 pattern categories (A-G): system access, dynamic execution, dynamic imports, builtin manipulation, FFI, network, resource exhaustion
- **CEO decision: AST-based denylist** (not allowlist). Use `ast.NodeVisitor` with `visit_Import`, `visit_ImportFrom`, `visit_Call` methods
- `CodeSecurityValidator` as internal class; expose `validate_code() -> list[str]` on StepSandbox per task spec
- Defense-in-depth: pre-scan catches obvious patterns fast (~10ms); Docker contains everything else
- Denylist constants: `BLOCKED_MODULES` (frozenset), `BLOCKED_BUILTINS` (frozenset), `BLOCKED_ATTRIBUTES` (frozenset)
- `_resolve_attribute_chain()` helper for dotted attribute detection (e.g., `os.system`)

### Integration Points with Creator Package
**Source:** step-1-docker-sdk-creator-integration.md, step-2-sandbox-architecture-container-isolation.md

- Sandbox is a **service class** used by `CodeValidationStep`, not a 5th pipeline step
- `CodeValidationContext` gains `sandbox_valid`, `sandbox_skipped`, `sandbox_output` fields
- `SandboxResult` is Pydantic `BaseModel` (not SQLModel), lives in `sandbox.py`
- `creator/__init__.py` has jinja2 `ImportError` guard that raises -- sandbox import guard must be SEPARATE and soft (degrade, not raise)
- Do NOT add sandbox exports to `creator/__init__.py`; import directly from `llm_pipeline.creator.sandbox`

### Framework Auto-Discovery (CEO Decision)
**Source:** CEO answer to Q4

`importlib.util.find_spec('llm_pipeline')` returns a `ModuleSpec` whose `origin` or `submodule_search_locations` reveals the package install path. This works for:
- **pip install**: `site-packages/llm_pipeline/` -- mount that directory
- **editable install** (`pip install -e .`): points to source directory
- **source checkout**: same as editable

Mount discovered path as read-only bind mount at `/usr/local/lib/python3.11/site-packages/llm_pipeline/` (or equivalent) inside container. The generated step code's `from llm_pipeline.step import LLMStep` resolves naturally.

Key implementation detail: must also mount pydantic, sqlmodel, sqlalchemy, pyyaml (llm_pipeline's core deps) or mount the entire `site-packages` directory. Mounting just `llm_pipeline/` is insufficient -- the framework imports its own deps.

### Sample Data Auto-Generation (CEO Decision)
**Source:** CEO answer to Q3, FieldDefinition model in models.py

`FieldDefinition` has: `name`, `type_annotation`, `description`, `default`, `is_required`. Auto-generation strategy:

| type_annotation | Generated value |
|-----------------|----------------|
| `str` | `"test_{name}"` or `description[:50]` |
| `int` | `1` |
| `float` | `1.0` |
| `bool` | `True` |
| `list[str]` | `["test_item"]` |
| `dict[str, str]` | `{"key": "value"}` |
| `Optional[X]` / `X \| None` | `None` if not required, else default for X |

If `default` is set on FieldDefinition, use that. Otherwise generate from type_annotation.

This data feeds into the run_test.py harness as `sample_data.json`, used to verify the import-check passes with realistic field shapes even if methods aren't called in v1.

### Dependency Management
**Source:** step-1-docker-sdk-creator-integration.md, pyproject.toml analysis

- Existing pattern: `creator = ["jinja2>=3.0"]` as separate optional-dependency
- `sandbox = ["docker>=7.0"]` follows same pattern
- Import guard in `sandbox.py` degrades gracefully (unlike `creator/__init__.py` which raises)

### run() Method Signature (Resolved)
**Source:** Step-1 vs Step-2 inconsistency, resolved by analysis

Use `run(self, artifacts: dict[str, str], sample_data: dict | None = None) -> SandboxResult`:
- `artifacts` aligns with `CodeValidationContext.all_artifacts` (dict of filename -> code)
- `sample_data` is auto-generated from instruction_fields by the caller (CodeValidationStep) before passing to sandbox
- Step-1's `code: str` signature is discarded

### run_test.py Harness (Resolved)
**Source:** CEO answer to Q1 -- import-check only

```python
# run_test.py (generated into tmpdir, executed inside container)
import sys
import json

results = {"import_ok": False, "errors": [], "modules_found": []}

# Attempt to import each artifact module
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

Container command: `python /code/run_test.py step_code instructions_code extraction_code`

This catches:
- Missing framework imports (ImportError)
- Syntax errors missed by ast.parse edge cases
- Class definition errors (metaclass conflicts, invalid bases)
- Import-time side effects that crash

Does NOT test (deferred to future versions):
- Runtime behavior of prepare_calls / process_instructions
- Data flow correctness with sample data
- Method-level logic errors

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| Q1: What should run_test.py do? | Import-check only -- verify module loads | Simplest harness. Framework must be in container (see Q4). No mock objects needed. |
| Q2: Security scanning approach? | AST-based denylist using Python ast module | ~80 lines. No false positives on comments/strings. BLOCKED_MODULES + BLOCKED_BUILTINS + BLOCKED_ATTRIBUTES as frozensets. Can upgrade to allowlist later. |
| Q3: Sample data source? | Auto-generate from instruction_fields spec | FieldDefinition has name, type_annotation, default, is_required. Generate type-appropriate synthetic values. No changes to StepCreatorInputData schema. |
| Q4: Framework availability in container? | importlib auto-discovery + read-only mount | `importlib.util.find_spec('llm_pipeline')` locates package. Mount into container. Zero config. Works for pip install, editable install, source. |

## Assumptions Validated

- [x] Docker SDK `docker.from_env()` + `ping()` is the correct connectivity check pattern (confirmed via Context7 docs)
- [x] `cpu_period/cpu_quota` (not `cpu_count`) for cross-platform CPU limiting (Context7: cpu_count is Windows containers only)
- [x] `docker.types.Mount` over legacy volumes dict -- required for tmpfs support (confirmed via Context7 docs)
- [x] `container.wait(timeout=N)` raises `requests.exceptions.ReadTimeout` on timeout (confirmed via Context7 API docs)
- [x] Task 45 completed with all creator files in place; `CodeValidationStep` does AST syntax check + LLM review; no runtime execution (confirmed via codebase inspection)
- [x] `CodeValidationContext.all_artifacts` contains `dict[str, str]` mapping filename to code (confirmed in schemas.py and steps.py)
- [x] Task 47 (StepIntegrator) reads `all_artifacts` from context -- sandbox result informs but does not block integration (confirmed from task 47 description)
- [x] `creator/__init__.py` raises ImportError on missing jinja2 -- sandbox must NOT follow this pattern (confirmed in __init__.py)
- [x] `SandboxResult` belongs in `sandbox.py` not `models.py` -- it's Pydantic BaseModel, not SQLModel (models.py uses SQLModel pattern)
- [x] Separate `sandbox = ["docker>=7.0"]` extra is correct dependency grouping (follows existing pyproject.toml pattern)
- [x] FieldDefinition model has sufficient fields (name, type_annotation, description, default, is_required) for synthetic data generation (confirmed in models.py)
- [x] `importlib.util.find_spec()` works for pip install, editable install, and source checkout (standard Python mechanism)
- [x] Generated step code has `from llm_pipeline.step import LLMStep, step_definition` -- framework MUST be available in container for import-check (confirmed in step.py.j2 template and CodeGenerationInstructions.example)

## Open Items

- **Site-packages mount scope**: Mounting just `llm_pipeline/` is insufficient since the framework imports pydantic, sqlmodel, etc. Need to either mount entire site-packages or discover and mount each transitive dependency. Implementation detail for planning phase.
- **TYPE_CHECKING guard awareness**: Imports inside `if TYPE_CHECKING:` blocks never execute at runtime. AST denylist will flag them as errors. Decision: accept false positives on these (rare in generated code) or add special handling. Low priority.
- **Image pull timeout/failure handling**: Lazy pull of `python:3.11-slim` needs timeout and clear error in SandboxResult when pull fails (e.g., no network). Implementation detail.
- **run_test.py PYTHONPATH setup**: Container needs `/code` on PYTHONPATH so `__import__('step_code')` works. Also needs the mounted site-packages on PYTHONPATH. Set via `environment` param in container config.
- **Cross-platform path normalization for importlib**: `find_spec().submodule_search_locations` may return Windows paths on Windows host. Docker Desktop handles Windows-to-WSL2 path translation for bind mounts, but verify behavior with edge cases.
- **Artifact filename normalization**: `all_artifacts` keys like `sentiment_analysis_step.py` need to map to importable module names (`sentiment_analysis_step`). The harness strips `.py` suffix.

## Recommendations for Planning

1. **Use `artifacts: dict[str, str]` as run() parameter** -- aligns with `CodeValidationContext.all_artifacts`.
2. **AST-based denylist with `BLOCKED_MODULES`, `BLOCKED_BUILTINS`, `BLOCKED_ATTRIBUTES` frozensets** -- `CodeSecurityValidator` internal class, `validate_code() -> list[str]` external API.
3. **importlib auto-discovery** for framework mount -- `find_spec('llm_pipeline')` then mount the parent directory (site-packages or source root) as read-only. Consider mounting all of site-packages for simplicity (deps included).
4. **Auto-generate sample data from instruction_fields** -- build a `_generate_sample_data(fields: list[FieldDefinition]) -> dict` utility. Map type_annotation strings to synthetic values. Write as `sample_data.json` in tmpdir even if not consumed by import-check harness (ready for future execution-scope upgrades).
5. **Include `memswap_limit='512m'` and `pids_limit=50`** despite not being in task spec -- low-cost, high-value security additions.
6. **Do NOT add sandbox to `creator/__init__.py`** -- import directly from `llm_pipeline.creator.sandbox`.
7. **Container environment setup**: Set `PYTHONPATH=/code:/mounted-site-packages` so both generated code and framework are importable.
8. **Plan for 3 files in sandbox.py**: `SandboxResult` (model), `CodeSecurityValidator` (AST scanner), `StepSandbox` (orchestrator). Single module, ~250-300 lines estimated.
9. **run_test.py is generated at runtime** -- written into tmpdir by `StepSandbox._write_files()`, not a static file in the package. Content is the import-check harness from the harness section above.
10. **Test strategy**: Unit tests mock docker client. Integration tests (optional, needs Docker) run real containers. Security validator tests use known-bad code snippets against AST scanner.
