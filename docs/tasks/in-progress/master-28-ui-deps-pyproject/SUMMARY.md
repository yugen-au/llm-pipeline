# Task Summary

## Work Completed

Updated `pyproject.toml` with the `[project.scripts]` CLI entry point and `[ui]` optional dependency group (fastapi, uvicorn[standard], python-multipart), synchronized the `[dev]` group bounds to match. Added a targeted import guard in `_run_ui()` that catches `ImportError` only for known UI packages (via `e.name` allowlist) and prints a friendly install hint to stderr before exiting with code 1; unknown `ImportError`s are re-raised. A review fix loop addressed three issues: broad catch replaced with targeted allowlist check, missing CLI guard tests added (4 tests in `TestImportGuardCli`), and loose version assertions in `TestPyprojectToml` tightened to exact strings. Final suite: 683 passed, 1 pre-existing unrelated failure.

## Files Changed

### Created
| File | Purpose |
| --- | --- |
| None | - |

### Modified
| File | Changes |
| --- | --- |
| `pyproject.toml` | Added `[project.scripts]` with `llm-pipeline = "llm_pipeline.ui.cli:main"`; updated `[ui]` deps to `fastapi>=0.115.0`, `uvicorn[standard]>=0.32.0`, `python-multipart>=0.0.9`; bumped same bounds in `[dev]` group and added `python-multipart>=0.0.9` |
| `llm_pipeline/ui/cli.py` | Wrapped `_run_ui()` body in `try/except ImportError as e`; targeted catch checks `e.name.split(".")[0]` against allowlist `{"fastapi", "uvicorn", "starlette", "multipart", "python_multipart"}`; unknown `ImportError` re-raised; known triggers stderr message + `sys.exit(1)` |
| `tests/test_ui.py` | Replaced loose `any("fastapi" in dep ...)` assertions with exact string checks; added 4 new `TestPyprojectToml` tests for `python-multipart` in `[ui]` and all 3 deps in `[dev]` (7 tests total) |
| `tests/ui/test_cli.py` | Added `TestImportGuardCli` class with 4 tests covering fastapi/uvicorn known-dep exit paths and unknown `ImportError` re-raise |

## Commits Made

| Hash | Message |
| --- | --- |
| `ae1c2e5` | `docs(implementation-A): master-28-ui-deps-pyproject` (step 1: pyproject.toml + step 2: initial import guard) |
| `b8fdcfc` | `docs(implementation-A): master-28-ui-deps-pyproject` (implementation doc updates) |
| `7681b30` | `docs(fixing-review-A): master-28-ui-deps-pyproject` (targeted guard + CLI guard tests + exact version assertions) |
| `f481e3b` | `docs(fixing-review-A): master-28-ui-deps-pyproject` (implementation doc updates for fix iteration) |

## Deviations from Plan

- The initial implementation used a bare `except ImportError` (acceptable per plan's risk table). The review identified this as medium severity and a targeted guard with `e.name` allowlist was added in the fix loop -- this was an improvement beyond the plan's original scope but within the risk mitigation strategy documented in PLAN.md.
- PLAN.md suggested "Suggest Exclusions: testing, review" but both testing and review phases ran, surfacing the three issues listed above. This was the correct outcome.

## Issues Encountered

### Broad ImportError catch masking application bugs
**Resolution:** Changed `except ImportError:` to `except ImportError as e:` with an allowlist check: `_ui_deps = {"fastapi", "uvicorn", "starlette", "multipart", "python_multipart"}`. If `e.name` root is not in the allowlist, the exception is re-raised. Covers submodule imports via `e.name.split(".")[0]`.

### No test for CLI import guard path
**Resolution:** Added `TestImportGuardCli` to `tests/ui/test_cli.py` with 4 tests: `test_missing_fastapi_exits_1`, `test_missing_fastapi_prints_install_hint`, `test_missing_uvicorn_exits_1`, `test_unknown_import_error_reraised`. Tests call `_run_ui` directly with mocked `create_app` raising `ImportError`.

### Loose version bound assertions in tests
**Resolution:** Replaced `any("fastapi" in dep for dep in ui_deps)` pattern with exact string membership: `assert "fastapi>=0.115.0" in ui_deps`. Added equivalent assertions for all 3 deps in both `[ui]` and `[dev]` groups (7 total `TestPyprojectToml` tests).

## Success Criteria

- [x] `pyproject.toml` contains `[project.scripts]` with `llm-pipeline = "llm_pipeline.ui.cli:main"` -- confirmed in file and verified by `TestPyprojectToml`
- [x] `[project.optional-dependencies].ui` contains exactly `fastapi>=0.115.0`, `uvicorn[standard]>=0.32.0`, `python-multipart>=0.0.9` -- confirmed in file and verified by 3 exact-string tests
- [x] `[project.optional-dependencies].dev` contains bumped fastapi/uvicorn bounds and `python-multipart>=0.0.9` -- confirmed in file and verified by 3 exact-string tests
- [x] `_run_ui()` prints friendly error and exits 1 when known [ui] dep missing -- verified by `TestImportGuardCli` (4 tests, all pass)
- [x] Unknown `ImportError` is re-raised, not swallowed -- verified by `test_unknown_import_error_reraised`
- [x] `llm-pipeline --help` works without [ui] deps (guard only fires inside `_run_ui`, not in `main()`) -- verified by build check, exit 0
- [x] `pip install -e .[ui]` installs without conflicts -- verified, hatchling built `llm_pipeline-0.1.0-py3-none-any.whl`
- [x] Existing tests pass without regressions -- 683 passed, 1 pre-existing unrelated failure (`test_events_router_prefix`)

## Recommendations for Follow-up

1. Fix pre-existing `test_events_router_prefix` failure (`assert '/runs/{run_id}/events' == '/events'`) -- router prefix mismatch predates this task and blocks a fully green suite.
2. Human validation of import guard in a dep-free venv: install `llm-pipeline` without `[ui]`, run `llm-pipeline ui`, confirm stderr message and exit code 1. Unit tests cover this but integration smoke test in a clean environment adds confidence.
3. Consider self-referencing `[dev]` group as `llm-pipeline[ui]` instead of duplicating dep strings -- deferred per CEO decision, but eliminates future version sync drift between `[ui]` and `[dev]`.
4. Add `[tool.hatch.build]` exclusion rules for `frontend/dist/` once task 29+ introduces frontend artifacts -- currently deferred because the directory does not exist.
