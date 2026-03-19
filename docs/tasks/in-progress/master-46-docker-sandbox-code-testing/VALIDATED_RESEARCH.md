# Research Summary

## Executive Summary

Consolidated findings from 3 domain research files covering Docker SDK integration, container isolation architecture, and code security analysis. Research quality is high overall, with thorough Docker SDK coverage and well-reasoned security layering. However, several critical hidden assumptions were identified that block planning:

1. The **test harness (`run_test.py`) is entirely unspecified** -- all 3 research files reference it but none define its contents
2. The **run() method signature is inconsistent** between Step-1 (`code: str`) and Step-2 (`artifacts: dict[str, str]`)
3. Generated step code **imports from llm_pipeline framework** -- cannot run in bare `python:3.11-slim` without the framework present
4. The **security approach** (AST allowlist vs task-spec string denylist) represents significant scope difference needing CEO decision

Four questions require CEO input before planning can proceed (see Q&A History).

## Domain Findings

### Docker SDK & Container Lifecycle
**Source:** step-1-docker-sdk-creator-integration.md, step-2-sandbox-architecture-container-isolation.md

- `docker.from_env()` for client init; `DockerException` on unavailability
- `create() + start()` preferred over `run(detach=True)` for error isolation and cleanup guarantee
- `container.wait(timeout=60)` raises `requests.exceptions.ReadTimeout` on timeout; container must be explicitly killed
- `auto_remove=False` required to read logs before cleanup
- Context7 docs confirm `cpu_period/cpu_quota` is correct cross-platform approach; task spec's `cpu_count` is Windows-only

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

- 7 pattern categories identified (A-G): system access, dynamic execution, dynamic imports, builtin manipulation, FFI, network, resource exhaustion
- AST-based analysis recommended over string matching -- no false positives from comments/strings/variable names
- Allowlist approach recommended for generated code (well-defined narrow scope)
- `CodeSecurityValidator` proposed as separate class with `SecurityIssue` dataclass
- Defense-in-depth: pre-scan catches obvious patterns fast; Docker contains everything else

### Integration Points with Creator Package
**Source:** step-1-docker-sdk-creator-integration.md, step-2-sandbox-architecture-container-isolation.md

- Sandbox is a **service class** used by `CodeValidationStep`, not a 5th pipeline step
- `CodeValidationContext` gains `sandbox_valid`, `sandbox_skipped`, `sandbox_output` fields
- `SandboxResult` is Pydantic `BaseModel` (not SQLModel), lives in `sandbox.py`
- `creator/__init__.py` has jinja2 `ImportError` guard that raises -- sandbox import guard must be SEPARATE and soft (degrade, not raise)

### Dependency Management
**Source:** step-1-docker-sdk-creator-integration.md, pyproject.toml analysis

- Existing pattern: `creator = ["jinja2>=3.0"]` as separate optional-dependency
- `sandbox = ["docker>=7.0"]` follows same pattern
- Import guard in `sandbox.py` degrades gracefully (unlike `creator/__init__.py` which raises)

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| Q1: What should run_test.py actually do? Import-only, instantiate classes, or call methods with mock data? | PENDING | Determines harness complexity, whether framework must be in container, and sample_data requirements |
| Q2: Should security scanning use simple string matching (per task spec) or AST-based analysis (per research)? | PENDING | ~5 lines vs ~80 lines implementation difference; false positive/negative tradeoffs |
| Q3: Where does sample_data come from? User-provided, auto-generated from instruction_fields, or skip in v1? | PENDING | Affects StepCreatorInputData schema and test harness design |
| Q4: Does the container need llm-pipeline installed to test generated code? (Generated code has `from llm_pipeline.step import LLMStep, step_definition`) | PENDING | Determines Docker image strategy: bare python:3.11-slim vs pre-built image vs source mount |

## Assumptions Validated

- [x] Docker SDK `docker.from_env()` + `ping()` is the correct connectivity check pattern (confirmed via Context7 docs)
- [x] `cpu_period/cpu_quota` (not `cpu_count`) for cross-platform CPU limiting (Context7: cpu_count is Windows containers only)
- [x] `docker.types.Mount` over legacy volumes dict -- required for tmpfs support (confirmed via Context7 docs)
- [x] `container.wait(timeout=N)` raises `requests.exceptions.ReadTimeout` on timeout (confirmed via Context7 API docs)
- [x] Task 45 completed with all creator files in place; `CodeValidationStep` does AST syntax check + LLM review; no runtime execution (confirmed via codebase inspection)
- [x] `CodeValidationContext.all_artifacts` contains `dict[str, str]` mapping filename to code (confirmed in schemas.py and steps.py)
- [x] Task 47 (StepIntegrator) reads `all_artifacts` from context and writes files -- sandbox result informs but does not block integration (confirmed from task 47 description)
- [x] `creator/__init__.py` raises ImportError on missing jinja2 -- sandbox must NOT follow this pattern (confirmed in __init__.py)
- [x] `SandboxResult` belongs in `sandbox.py` not `models.py` -- it's Pydantic BaseModel, not SQLModel (models.py uses SQLModel pattern)
- [x] Separate `sandbox = ["docker>=7.0"]` extra is correct dependency grouping (follows existing pyproject.toml pattern)

## Open Items

- **run_test.py harness content**: Completely unspecified. All 3 research files reference it but none define what it executes. This is the single biggest gap in the research.
- **run() method signature inconsistency**: Step-1 uses `run(self, code: str, sample_data)`, Step-2 uses `run(self, artifacts: dict[str, str], sample_data)`. Step-2's `artifacts` dict aligns better with `CodeValidationContext.all_artifacts` but needs explicit resolution.
- **Framework availability in container**: Generated step code has hard imports like `from llm_pipeline.step import LLMStep`. If the harness tries to import the module, the framework must be available. Options: pre-built image, source mount, or snippet-only testing.
- **Scope of CodeSecurityValidator**: Research proposes a separate class with `SecurityIssue` dataclass -- more complex than task spec's `validate_code() -> list[str]`. Acceptable as internal implementation detail if external API stays `list[str]`.
- **TYPE_CHECKING guard awareness**: Research notes imports inside `if TYPE_CHECKING:` blocks are flagged by AST scan but never execute. Decision on whether to skip/downgrade these is deferred.
- **Image pull timeout/failure handling**: Step-2 recommends lazy pull but doesn't specify timeout or behavior when pull fails (e.g., no network). Should produce clear error in SandboxResult.

## Recommendations for Planning

1. **Resolve execution scope before planning** -- the answer to "what does run_test.py do" cascades into image strategy, sample data needs, and harness complexity. Recommend starting with import-check-only in v1.
2. **Use `artifacts: dict[str, str]` as run() parameter** -- aligns with `CodeValidationContext.all_artifacts` which is the natural caller input.
3. **Use AST-based denylist (not allowlist) for v1 security** -- provides the robustness benefits of AST (no false positives on comments/strings) without the restrictiveness of allowlist. Can upgrade to allowlist later.
4. **Keep `CodeSecurityValidator` as internal class** -- expose `validate_code() -> list[str]` on StepSandbox per task spec; use structured `SecurityIssue` internally for extensibility.
5. **Do NOT add sandbox exports to `creator/__init__.py`** -- sandbox has its own import guard pattern (soft degrade). Import directly from `llm_pipeline.creator.sandbox`.
6. **`memswap_limit='512m'` and `pids_limit=50` should be included** despite not being in task spec -- they are low-cost additions that close real attack vectors.
7. **Pin run() signature early in planning** to avoid rework across harness, tests, and integration code.
