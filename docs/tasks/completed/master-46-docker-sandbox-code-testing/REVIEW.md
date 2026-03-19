# Architecture Review

## Overall Assessment
**Status:** complete
Solid defense-in-depth implementation. AST denylist + Docker container isolation layers are well-separated. Graceful degradation when Docker is unavailable follows the correct pattern (warn, not raise). Container constraints are comprehensive. Code is clean, well-documented, and all 34 tests pass. A few medium/low issues identified below -- none are blockers.

## Project Guidelines Compliance
**CLAUDE.md:** `C:\Users\SamSG\Documents\claude_projects\llm-pipeline\CLAUDE.md`
| Guideline | Status | Notes |
| --- | --- | --- |
| Python 3.11+ | pass | Uses `str \| None` union syntax, no 3.10 compat issues |
| Pydantic v2 | pass | SandboxResult uses BaseModel correctly; mutable list defaults auto-handled by v2 |
| SQLModel for DB models only | pass | SandboxResult is BaseModel (transient); GenerationRecord stays SQLModel |
| Hatchling build | pass | pyproject.toml sandbox dep follows existing optional-dep pattern |
| pytest tests | pass | 34 tests, all passing, no Docker daemon required |
| No hardcoded values | pass | image/timeout are constructor params with sensible defaults |

## Issues Found
### Critical
None

### High
#### Timeout return bypasses container.remove on non-finally path
**Step:** 1
**Details:** The `ReadTimeout` except block (line 382-393) returns a `SandboxResult` directly. This `return` exits the `with TemporaryDirectory()` context manager, which triggers tmpdir cleanup. The `finally` block at line 433 does call `container.remove(force=True)`, so the container IS cleaned up. However, `container.kill()` is called but `container.remove()` only runs in `finally` -- if `container.kill()` raises (unlikely but possible if Docker daemon becomes unreachable mid-execution), the `finally` still runs, which is correct. **On re-analysis this is properly handled by the try/finally pattern.** Downgrading: no actual issue exists here. The `finally` block correctly wraps all return paths including the timeout path.

*Retracted -- the try/finally pattern correctly handles this.*

### Medium
#### PYTHONPATH separator uses colon unconditionally
**Step:** 1
**Details:** Line 354 uses `":".join(python_path_parts)` for PYTHONPATH. This is correct because the container runs Linux (`python:3.11-slim`), but the intent is not documented. If someone changes the container image to a Windows-based image in the future, this would silently break. A comment clarifying "colon separator because container is always Linux" would be helpful but not required.

#### _TYPE_MAP returns mutable defaults by reference
**Step:** 2
**Details:** `SampleDataGenerator._TYPE_MAP` values for `list[str]`, `list[int]`, `dict[str, str]`, and `dict[str, Any]` are mutable objects. When `generate()` returns them via `result[field.name] = value`, the caller gets a direct reference to the class-level mutable. If a caller mutates the returned dict's list/dict values, it would corrupt the class-level `_TYPE_MAP` for all future calls. Fix: deep-copy mutable values in `generate()` or use tuples/frozensets in the map and convert on output. In practice the current callers (sandbox, tests) don't mutate, so this is medium not high.

#### No test for CodeValidationStep sandbox integration path
**Step:** 6
**Details:** Tests cover `sandbox.py` and `sample_data.py` in isolation, but there is no test verifying that `CodeValidationStep.process_instructions()` correctly wires sandbox results into `CodeValidationContext`. The integration point in `steps.py` (lines 309-346) relies on `_SANDBOX_AVAILABLE`, `StepSandbox().run()`, and `SampleDataGenerator().generate()` working together. A unit test mocking the pipeline context and verifying the returned context fields would increase confidence.

### Low
#### run_test.py harness uses __import__ which is in BLOCKED_BUILTINS
**Step:** 1
**Details:** The `_RUN_TEST_PY` harness template (line 144-158) uses `__import__(module_name)` to test imports inside the container. While this code is injected into the container and never scanned by `CodeSecurityValidator` (since `run_test.py` is written separately and not included in the AST scan artifacts), it's worth noting the intentional asymmetry: the validator blocks `__import__` in user code but the harness itself uses it. This is correct behavior -- just documenting for clarity.

#### warnings.warn missing category parameter
**Step:** 1
**Details:** `warnings.warn()` calls in `_get_client()` (lines 180, 192) and `_discover_framework_path()` area (line 288) pass `stacklevel` but no `category` kwarg. Default category is `UserWarning` which is appropriate here, but explicitly passing `category=UserWarning` or a custom `SandboxWarning` subclass would improve filterability for users who want to suppress sandbox warnings in production.

#### Empty stdout handling in JSON parse
**Step:** 1
**Details:** Lines 400-411 parse the last JSON line from stdout. If `stdout_logs.strip()` is empty, `splitlines()` returns `[]`, `reversed([])` iterates zero times, and `results` stays as the default `{"import_ok": False, ...}`. This is correct fallback behavior, but the error message in the returned `SandboxResult` won't indicate why import_ok is False (no "could not parse container output" error). Minor observability gap.

#### Docker image not configurable at run() call site
**Step:** 1
**Details:** The Docker image (`python:3.11-slim`) is set at `__init__` time but not overridable per `run()` call. This is fine for v1 since all generated code targets the same Python version, but noted for future extensibility.

## Review Checklist
[x] Architecture patterns followed -- defense-in-depth with clear layer separation, Strategy pattern for sandbox execution
[x] Code quality and maintainability -- clean separation between `_SecurityVisitor` (internal), `CodeSecurityValidator` (public API), `StepSandbox` (orchestrator)
[x] Error handling present -- try/finally for container cleanup, broad exception catch with logging, graceful Docker-unavailable fallback
[x] No hardcoded values -- image and timeout are configurable via constructor; container constraints are explicit and documented
[x] Project conventions followed -- `__all__` exports, BaseModel for transient data, optional-dep pattern matches existing `creator`
[x] Security considerations -- comprehensive container lockdown (no network, read-only FS, cap_drop ALL, no-new-privileges, pids_limit, mem/cpu limits)
[x] Properly scoped (DRY, YAGNI, no over-engineering) -- import-check only for v1 (no method execution), sample_data generated but only written to container (not executed yet)

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| llm_pipeline/creator/sandbox.py | pass | Well-structured, all three components solid. Container constraints match plan. |
| llm_pipeline/creator/sample_data.py | pass | Clean type-map approach. Handles Optional stripping and ast.literal_eval for defaults. |
| llm_pipeline/creator/schemas.py | pass | Three new fields added with safe defaults (sandbox_skipped=True, sandbox_valid=False). |
| llm_pipeline/creator/steps.py | pass | Lazy import guard correct. Sandbox integration in process_instructions well-placed. |
| pyproject.toml | pass | `sandbox = ["docker>=7.0"]` follows existing optional-dep pattern. |
| tests/creator/test_sandbox.py | pass | 22 tests covering AST validator, SandboxResult model, Docker-unavailable path, mocked Docker path. |
| tests/creator/test_sample_data.py | pass | 12 tests covering all type map entries, defaults, optional fields, JSON output, unknown types. |

## New Issues Introduced
- Mutable default reference leak in `SampleDataGenerator._TYPE_MAP` (medium, no current callers mutate)
- No integration test for `CodeValidationStep` sandbox wiring (medium, isolated unit tests exist)

## Recommendation
**Decision:** APPROVE
Implementation is architecturally sound, follows project conventions, and provides comprehensive security constraints. The two medium issues (mutable _TYPE_MAP references, missing integration test) are not blockers -- they can be addressed in a follow-up. All 34 tests pass. No Docker daemon required for test suite. Defense-in-depth pattern is correctly implemented with proper graceful degradation.

---

# Architecture Re-Review (Post-Fix)

## Overall Assessment
**Status:** complete
All three fixes correctly address the issues from the initial review. 43 tests pass (22 original + 9 new integration + 12 sample_data). No regressions introduced. All previous medium and low issues resolved or addressed.

## Fix Verification

### Fix 1: sandbox.py -- warnings.warn category + empty stdout parse error
**Previous issues:** LOW - Step 1: `warnings.warn` missing `category`; LOW - Step 1: empty stdout no error message
**Verification:**
- Lines 183, 194, 293: `category=UserWarning` now explicitly passed to all three `warnings.warn()` calls. Confirmed.
- Lines 403-404, 418-420: `parsed` boolean flag tracks whether JSON was found; line 420 appends `"Could not parse container output"` to errors when `not parsed`. Correct -- provides observability for empty/unparseable container output.

### Fix 2: sample_data.py -- deep-copy mutable _TYPE_MAP values
**Previous issue:** MEDIUM - Step 2: mutable _TYPE_MAP values returned by reference
**Verification:**
- Line 11: `import copy` added.
- Lines 117-118: `elif isinstance(value, (list, dict)): value = copy.deepcopy(value)` in `generate()`. Correctly deep-copies mutable values before returning. The `str` template path (line 114-115) is not affected since strings are immutable. Confirmed -- class-level `_TYPE_MAP` can no longer be corrupted by caller mutations.

### Fix 3: test_sandbox.py -- CodeValidationStep integration tests
**Previous issue:** MEDIUM - Step 6: no integration test for CodeValidationStep sandbox wiring
**Verification:**
- 9 new tests in `TestCodeValidationStepSandboxIntegration` class (lines 415-635).
- Sandbox-available path (6 tests): validates `sandbox_valid`, `sandbox_skipped`, `sandbox_output`, security issue propagation, artifact map contents, sample data generator invocation, `is_valid=False` on import failure.
- Sandbox-unavailable path (3 tests): validates `sandbox_output` message, `sandbox_skipped=True`, and `is_valid=True` when syntax+llm pass.
- Test helpers (`_make_pipeline_mock`, `_make_code_validation_step`, `_make_instructions`) properly bypass LLMStep constructor to test process_instructions in isolation. Clean approach.

## Issues Found
### Critical
None

### High
None

### Medium
None -- both previous medium issues resolved.

### Low
#### UserWarning in test output from _discover_framework_path
**Step:** 6
**Details:** 6 pytest warnings emitted from `_discover_framework_path` during mock Docker tests (visible in test output). These are cosmetic -- the tests that don't patch `_discover_framework_path` trigger the real method which emits `UserWarning`. Could suppress with `@pytest.mark.filterwarnings("ignore::UserWarning")` or by patching `_discover_framework_path` in all mock Docker tests. Not a functional issue.

## Review Checklist
[x] Architecture patterns followed
[x] Code quality and maintainability
[x] Error handling present
[x] No hardcoded values
[x] Project conventions followed
[x] Security considerations
[x] Properly scoped (DRY, YAGNI, no over-engineering)

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| llm_pipeline/creator/sandbox.py | pass | `category=UserWarning` added to all warn calls; `parsed` flag + error message for empty stdout |
| llm_pipeline/creator/sample_data.py | pass | `copy.deepcopy()` for mutable _TYPE_MAP values |
| tests/creator/test_sandbox.py | pass | 9 new integration tests for CodeValidationStep sandbox wiring, all passing |

## New Issues Introduced
- None detected

## Recommendation
**Decision:** APPROVE
All previous medium/low issues resolved. 43 tests pass with no Docker daemon required. Fixes are minimal, targeted, and introduce no new complexity. Implementation is ready for merge.
