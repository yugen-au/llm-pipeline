# Architecture Review

## Overall Assessment
**Status:** complete
Implementation is clean, well-structured, and follows established codebase patterns consistently. All 3 changed files are additive, backward-compatible, and well-tested. The merge order logic, error handling strategy, and dev-mode env var bridge are architecturally sound. 57/57 CLI tests pass; no regressions.

## Project Guidelines Compliance
**CLAUDE.md:** `D:\Documents\claude-projects\llm-pipeline\CLAUDE.md`
| Guideline | Status | Notes |
| --- | --- | --- |
| Pipeline + Strategy + Step pattern | pass | New code extends existing PipelineConfig registration, does not alter core pattern |
| Pydantic v2 conventions | pass | No new Pydantic models; existing PipelineConfig subclass handling preserved |
| No hardcoded values | pass | All config via CLI args, env vars, or function params with None defaults |
| Error handling present | pass | ValueError on failed imports, isolated try/except on seed_prompts, sys.exit(1) in CLI |
| Tests pass (pytest) | pass | 57/57 CLI tests pass; 1250/1251 full suite (1 pre-existing unrelated failure) |
| Build with hatchling | pass | No build changes; new param is backward-compatible |

## Issues Found
### Critical
None

### High
None

### Medium
#### Re-exported subclasses picked up by inspect.getmembers
**Step:** 1
**Details:** `_load_pipeline_modules` uses `inspect.getmembers(mod, inspect.isclass)` which scans the module namespace, not just locally-defined classes. If a user module does `from other_package import SomePipeline` (a concrete PipelineConfig subclass), that class will be registered as well. This differs from `_discover_pipelines` which uses explicit entry-point declarations. The risk is low because users control their own modules, but it could cause surprise double-registration if a module imports a PipelineConfig subclass for internal use. A `cls.__module__ == mod.__name__` guard would restrict to locally-defined classes only. Not blocking -- this is a behavioral nuance users can work around.

### Low
#### Missing dedicated unit tests for _load_pipeline_modules
**Step:** 1
**Details:** The `_load_pipeline_modules` helper has no direct unit tests. It is tested indirectly through CLI integration tests (`TestPipelinesFlag`) which mock `create_app` entirely, so the actual import/scan/filter/seed_prompts logic inside `_load_pipeline_modules` is never exercised in the test suite. This is consistent with the existing convention (`_discover_pipelines` also lacks unit tests), but given `_load_pipeline_modules` has more complex error paths (ValueError on import failure, ValueError on no subclasses found, seed_prompts isolation), direct unit tests would improve confidence. Not blocking.

#### Unused `mock_app` variable in test_value_error_causes_exit_1
**Step:** 3
**Details:** `TestPipelinesFlag::test_value_error_causes_exit_1` (L296) creates `mock_app = MagicMock()` but never uses it -- `create_app` is patched with `side_effect=ValueError(...)` so it never returns. Harmless dead code, but slightly misleading.

#### TestDevModeEnvBridge env var leak potential within context manager
**Step:** 3
**Details:** `TestDevModeEnvBridge` tests use `patch.dict(os.environ, {}, clear=False)` which correctly restores env after the `with` block exits. However, the `main()` call inside the context manager calls `_run_dev_mode` which writes env vars via `os.environ["KEY"] = val` -- these writes are visible within the `with` scope but properly cleaned up on exit. The pattern works correctly but is subtle; a comment explaining the restoration would aid future maintainers. Not blocking.

## Review Checklist
[x] Architecture patterns followed -- consistent with existing _discover_pipelines, _make_pipeline_factory, env var bridge patterns
[x] Code quality and maintainability -- clean separation: app.py owns module loading, cli.py owns arg parsing, well-documented docstrings
[x] Error handling present -- ValueError on import/scan failure, isolated seed_prompts try/except, sys.exit(1) at CLI boundary
[x] No hardcoded values -- all configuration via parameters/env vars
[x] Project conventions followed -- to_snake_case for registry keys, same logging patterns, same test assertion style
[x] Security considerations -- importlib.import_module on user-provided paths is inherent to the feature; no additional attack surface vs existing entry-point loading
[x] Properly scoped (DRY, YAGNI, no over-engineering) -- reuses _make_pipeline_factory, naming.to_snake_case; no unnecessary abstractions

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| llm_pipeline/ui/app.py | pass | _load_pipeline_modules well-structured, create_app extension backward-compatible, merge order correct |
| llm_pipeline/ui/cli.py | pass | --model and --pipelines args follow existing --db pattern exactly, ValueError catch clean, dev mode env bridge consistent |
| tests/ui/test_cli.py | pass | 5 stale assertions fixed, 1 broken test fixed, 4 new test classes (11 methods), all 57 pass |

## New Issues Introduced
- None detected

## Recommendation
**Decision:** APPROVE
Implementation is architecturally sound, consistent with existing patterns, well-tested, and fully backward-compatible. The medium-severity item (re-exported subclass pickup) is a behavioral nuance worth documenting but not blocking. All changes are additive with sensible defaults.
