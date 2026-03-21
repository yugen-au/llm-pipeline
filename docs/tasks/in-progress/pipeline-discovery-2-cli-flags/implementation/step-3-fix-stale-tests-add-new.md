# IMPLEMENTATION - STEP 3: FIX STALE TESTS & ADD NEW
**Status:** completed

## Summary
Fixed 5 stale test assertions and 1 broken test in `tests/ui/test_cli.py`, added 4 new test classes (11 test methods) covering --model flag, --pipelines flag, dev mode env var bridge, and _create_dev_app parameter passing.

## Files
**Created:** none
**Modified:** `tests/ui/test_cli.py`
**Deleted:** none

## Changes
### File: `tests/ui/test_cli.py`

**Stale assertion fixes (5):**

1. `TestDbFlag::test_db_path_passed_to_create_app` -- replaced `assert_called_once_with(db_path=...)` with individual kwarg check
2. `TestDbFlag::test_db_none_by_default` -- same pattern
3. `TestCreateDevApp::test_reads_env_var_and_passes_to_create_app` -- same pattern
4. `TestCreateDevApp::test_passes_none_when_env_var_absent` -- same pattern
5. `TestDevModeWithFrontend::test_uvicorn_no_reload_in_vite_mode` -- renamed to `test_uvicorn_reload_in_vite_mode`, assertion changed from `assert not kwargs.get("reload", False)` to `assert kwargs.get("reload") is True`

**Broken test fix (1):**

6. `TestImportGuardCli::test_missing_uvicorn_exits_1` -- added `args.model = None` and `args.pipelines = None` to MagicMock args; without these, `_run_dev_mode` tried to set `os.environ["LLM_PIPELINE_MODEL"] = MagicMock()` which raises TypeError

**New test classes (4, 11 methods):**

7. `TestModelFlag` (2 tests) -- `--model gemini-2.0-flash` passes `default_model` to `create_app`; default is None
8. `TestPipelinesFlag` (4 tests) -- single module, repeatable `--pipelines a --pipelines b`, default None, ValueError causes `sys.exit(1)`
9. `TestDevModeEnvBridge` (2 tests) -- `--model x` sets `LLM_PIPELINE_MODEL` env var; `--pipelines a --pipelines b` sets `LLM_PIPELINE_PIPELINES=a,b`
10. `TestCreateDevAppPipelinesModel` (3 tests) -- `LLM_PIPELINE_PIPELINES=a,b` splits to list; `LLM_PIPELINE_MODEL=x` passes through; absent vars give None

```
# Before (stale assertion example)
mock_ca.assert_called_once_with(db_path="/tmp/test.db")

# After (resilient kwarg check)
mock_ca.assert_called_once()
assert mock_ca.call_args.kwargs["db_path"] == "/tmp/test.db"
```

## Decisions
### Assertion Style
**Choice:** `mock.call_args.kwargs["key"]` for expected-present kwargs, `.get("key")` for expected-None
**Rationale:** Resilient to future param additions; `.get()` avoids KeyError when param may not be passed explicitly

### test_missing_uvicorn_exits_1 Fix
**Choice:** Added `args.model = None` and `args.pipelines = None` to the MagicMock
**Rationale:** cli.py now accesses `args.model` and `args.pipelines` in `_run_dev_mode`; MagicMock auto-creates truthy attributes causing `os.environ["..."] = MagicMock()` which raises TypeError

## Verification
[x] All 57 tests in test_cli.py pass
[x] Full suite: 1250 passed, 1 pre-existing failure (unrelated test_agent_registry_core), 6 skipped
[x] No regressions from changes
[x] 5 stale assertions fixed
[x] 4 new test classes added (11 methods)
