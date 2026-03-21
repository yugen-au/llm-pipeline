# Testing Results

## Summary
**Status:** passed
All implementation changes verified. 57/57 tests pass in `tests/ui/test_cli.py`. Full suite: 1250 passed, 1 pre-existing failure unrelated to this task, 6 skipped. No regressions introduced.

---

## Round 2 — Review Fix Verification (2026-03-21)

**Status:** passed
Review fixes verified. 68/68 pass across `tests/ui/test_cli.py` and new `tests/ui/test_load_pipeline_modules.py`. Full suite: 1261 passed (+11 new tests), same 1 pre-existing failure, 6 skipped. No regressions.

### Test Scripts Created (Round 2)
| Script | Purpose | Location |
| --- | --- | --- |
| test_load_pipeline_modules.py | Unit tests for `_load_pipeline_modules` with fixture modules — success scan, import failure, no-subclass error, re-export guard | tests/ui/test_load_pipeline_modules.py |

### Test Execution (Round 2)
**Pass Rate:** 1261/1262 (1 pre-existing failure; 6 skipped)

`tests/ui/test_load_pipeline_modules.py` + `tests/ui/test_cli.py` isolated run:
```
68 passed in 0.43s
```

Full suite run:
```
1 failed, 1261 passed, 6 skipped, 10 warnings in 32.59s

FAILED tests/test_agent_registry_core.py::TestStepDepsFields::test_field_count
AssertionError: assert 11 == 10  (pre-existing, confirmed in Round 1)
```

### Review Fix Coverage
- [x] `cls.__module__` guard in `_load_pipeline_modules` — `TestReexportGuard::test_reexport_only_module_raises` (PASSED), `TestReexportGuard::test_mixed_module_registers_only_local` (PASSED)
- [x] `seed_prompts` failure isolation — `TestSuccessfulScan::test_seed_prompts_failure_does_not_unregister` (PASSED)
- [x] Multiple module paths — `TestSuccessfulScan::test_multiple_modules` (PASSED)
- [x] Import error chained cause — `TestImportFailure::test_chained_from_import_error` (PASSED)
- [x] Unused `mock_app` removed from `test_cli.py` — no fixture warnings in output
- [x] Env var restoration comment present in `test_cli.py` — no behavioral change, verified by `TestDevModeEnvBridge` (2 PASSED), `TestCreateDevAppPipelinesModel` (3 PASSED)

---

## Automated Testing
### Test Scripts Created
| Script | Purpose | Location |
| --- | --- | --- |
| N/A | Tests added to existing file in Step 3 | tests/ui/test_cli.py |

### Test Execution
**Pass Rate:** 1250/1251 (1 pre-existing failure unrelated to this task; 6 skipped)

`tests/ui/test_cli.py` isolated run:
```
57 passed in 0.21s
```

Full suite run:
```
1 failed, 1250 passed, 6 skipped, 10 warnings in 34.48s

FAILED tests/test_agent_registry_core.py::TestStepDepsFields::test_field_count
AssertionError: assert 11 == 10
  +  where 11 = len(dc_fields(StepDeps))
```

### Failed Tests
#### TestStepDepsFields::test_field_count
**Step:** N/A (pre-existing failure, not in scope)
**Error:** `assert 11 == 10` — `StepDeps` has 11 dataclass fields; test expects 10. Confirmed pre-existing by running test on stashed (pre-implementation) state and observing identical failure.

## Build Verification
- [x] Python import succeeds: `from llm_pipeline.ui.app import _load_pipeline_modules, create_app`
- [x] Python import succeeds: `from llm_pipeline.ui.cli import main`
- [x] No syntax errors in modified files (ast.parse verified in implementation steps)
- [x] No new import errors introduced

## Success Criteria (from PLAN.md)
- [x] `--model` passes `default_model` to `create_app` — verified by `TestModelFlag::test_model_passed_to_create_app` (PASSED)
- [x] `--pipelines my.module` imports module, scans for `PipelineConfig` subclasses, registers them — `_load_pipeline_modules` implemented in Step 1; `TestPipelinesFlag::test_single_pipeline_module` (PASSED)
- [x] `--pipelines bad.module` exits with code 1 and prints ERROR to stderr — `TestPipelinesFlag::test_value_error_causes_exit_1` (PASSED)
- [x] `--pipelines my.module --pipelines other.module` registers from both modules — `TestPipelinesFlag::test_repeatable_pipelines` (PASSED)
- [x] Dev mode `--model` and `--pipelines` set env vars; `_create_dev_app` reads them and passes to `create_app` — `TestDevModeEnvBridge` (2 tests PASSED), `TestCreateDevAppPipelinesModel` (3 tests PASSED)
- [x] 3 previously-failing `test_cli.py` tests now pass — `TestDbFlag::test_db_path_passed_to_create_app`, `TestDbFlag::test_db_none_by_default`, `TestCreateDevApp::test_reads_env_var_and_passes_to_create_app` all PASSED
- [x] All new test classes from Step 3 pass — `TestModelFlag` (2), `TestPipelinesFlag` (4), `TestCreateDevAppPipelinesModel` (3), `TestDevModeEnvBridge` (2): all PASSED
- [x] No existing passing tests regressed — 1250 pass, 1 pre-existing failure confirmed via stash test
- [x] `pytest` exits 0 for `tests/ui/test_cli.py` — confirmed

## Human Validation Required
### CLI smoke test with real module
**Step:** Step 1, Step 2
**Instructions:** Run `llm-pipeline ui --pipelines <your_module_path>` where the module contains a concrete `PipelineConfig` subclass. Also run with a non-existent module path.
**Expected Result:** Valid module: server starts and pipeline is registered in `/api/pipelines`. Invalid module: exits immediately with `ERROR: Failed to import pipeline module '...': ...` printed to stderr and exit code 1.

### Dev mode env bridge smoke test
**Step:** Step 2
**Instructions:** Run `llm-pipeline ui dev --model google-gla:gemini-2.0-flash-lite --pipelines my.module`. Check that `LLM_PIPELINE_MODEL` and `LLM_PIPELINE_PIPELINES` are set in the uvicorn process env before `_create_dev_app` is called.
**Expected Result:** Env vars set; `create_app` receives `default_model="google-gla:gemini-2.0-flash-lite"` and `pipeline_modules=["my.module"]`.

## Issues Found
None

## Recommendations
1. Fix pre-existing `TestStepDepsFields::test_field_count` failure in a separate task — `StepDeps` has grown to 11 fields but test still asserts 10.
