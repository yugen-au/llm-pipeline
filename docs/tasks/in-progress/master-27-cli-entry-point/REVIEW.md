# Architecture Review

## Overall Assessment
**Status:** partial
Implementation is clean, well-structured, and aligns with PLAN.md architecture decisions. One functional bug in dev headless mode (reload with app instance instead of import string) prevents reload from working. All other code paths are correct. Test coverage is thorough at 34 tests across all branches.

## Project Guidelines Compliance
**CLAUDE.md:** `C:\Users\SamSG\Documents\claude_projects\llm-pipeline\CLAUDE.md`
| Guideline | Status | Notes |
| --- | --- | --- |
| Python 3.11+ | pass | No syntax below 3.11 used, `from __future__ import annotations` present |
| Pydantic v2 | pass | No Pydantic usage in CLI (correct -- CLI layer) |
| FastAPI deferred imports | pass | All FastAPI/uvicorn imports inside function bodies, only stdlib at module level |
| Hatchling build | pass | No changes to build config (out of scope per PLAN.md) |
| pytest testing | pass | 34 tests pass, pytest runner used |
| No hardcoded values | pass | Default port 8642 is an argparse default (configurable via --port), hosts are mode-appropriate constants per PLAN.md |

## Issues Found
### Critical
None

### High
#### uvicorn reload=True with app instance does not actually reload
**Step:** 1
**Details:** In `_run_dev_mode()` line 79, `uvicorn.run(app, host="127.0.0.1", port=port, reload=True)` passes the app object directly. uvicorn requires an import string (e.g., `"llm_pipeline.ui.app:create_app()"`) when `reload=True` -- otherwise it logs a warning and reload does not function. This is the headless dev mode fallback (no frontend/ dir). The fix is to pass the app as an import string, but this requires careful handling because `create_app()` needs the `db_path` argument. Options: (a) use an env var for db_path and pass a factory string, (b) skip reload when app instance is used and document the limitation, (c) construct the import string with db_path encoded. Recommend option (a) or (b) since this is a dev-only convenience path.

### Medium
#### Path.exists patch is overly broad in tests
**Step:** 2
**Details:** Multiple test classes patch `pathlib.Path.exists` globally (`patch("pathlib.Path.exists", return_value=False/True)`). This patches ALL Path.exists calls, not just the ones in cli.py. While tests currently pass, this could cause false positives if cli.py or its callees add additional Path.exists checks in the future. More precise approach: use `monkeypatch` to replace the specific path resolution, or inject the path as a parameter. Low risk given current code simplicity but fragile for maintenance.

#### No test for SIGTERM handler registration on Unix
**Step:** 2
**Details:** `_start_vite_mode()` registers a `signal.SIGTERM` handler (line 100-104) but no test verifies this registration occurs on Unix or is skipped on Windows. The `hasattr(signal, "SIGTERM")` guard is correct but untested. Low functional risk since the guard is simple.

### Low
#### Type annotation uses `object` instead of protocol or Union
**Step:** 1
**Details:** `_run_prod_mode(app: object, ...)` and `_run_dev_mode(app: object, ...)` annotate `app` as `object`, requiring `# type: ignore[union-attr]` and `# type: ignore[arg-type]` comments. A `TYPE_CHECKING`-guarded import of `FastAPI` with a conditional type annotation (e.g., `if TYPE_CHECKING: from fastapi import FastAPI`) would eliminate the ignores while maintaining deferred runtime imports. Minor polish.

#### Startup info message hardcodes "localhost" for Vite URL
**Step:** 1
**Details:** Line 107 prints `http://localhost:{vite_port}` but Vite actually binds to whatever its default is (typically localhost). This is cosmetically fine but could be misleading if Vite config changes its bind address. Very minor.

## Review Checklist
[x] Architecture patterns followed -- subparsers, deferred imports, factory pattern, clean separation of CLI from app factory
[x] Code quality and maintainability -- well-structured private functions, clear naming, docstrings on all functions
[x] Error handling present -- FileNotFoundError for npx, TimeoutExpired for cleanup, graceful fallbacks
[x] No hardcoded values -- port is configurable, hosts follow PLAN.md security policy
[x] Project conventions followed -- stdlib-only top-level, `from __future__ import annotations`, consistent style
[x] Security considerations -- shell=True only on Windows, 0.0.0.0 prod / 127.0.0.1 dev, subprocess cleanup
[x] Properly scoped (DRY, YAGNI, no over-engineering) -- no unnecessary abstractions, each function has single responsibility

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| `llm_pipeline/ui/cli.py` | pass (with 1 HIGH issue) | Clean implementation matching PLAN.md. reload=True bug needs fix. |
| `tests/ui/test_cli.py` | pass | 34 tests, all pass, comprehensive coverage of code paths |
| `llm_pipeline/ui/__init__.py` | pass | Pre-existing import guard correctly protects package |
| `llm_pipeline/ui/app.py` | pass | Factory function matches CLI's expectations (db_path param) |

## New Issues Introduced
- `uvicorn.run(app_instance, reload=True)` does not enable actual file-watching reload (HIGH, Step 1)
- Global `Path.exists` patching in tests is fragile (MEDIUM, Step 2)
- No SIGTERM handler test coverage (MEDIUM, Step 2)

## Recommendation
**Decision:** CONDITIONAL
Approve after fixing the HIGH issue: `reload=True` with an app instance object does not work in uvicorn. The headless dev mode path (`_run_dev_mode` without frontend/) will log a uvicorn warning and not actually reload on file changes, defeating the purpose of `--dev` mode. All other aspects of the implementation are solid and well-aligned with the plan.

---

# Architecture Re-Review (Post-Fix: commit 4700ac6)

## Overall Assessment
**Status:** complete
The HIGH issue (uvicorn reload with app instance) is fully resolved. The fix uses `factory=True` with an import string to `_create_dev_app`, passing `db_path` through `LLM_PIPELINE_DB` env var. All 34 tests pass. Implementation is architecturally sound.

## Fix Verification

### HIGH - uvicorn reload=True with app instance: RESOLVED
**Commit:** 4700ac6
**Changes reviewed:**
1. `_run_dev_mode` signature changed from `(app, port)` to `(args)` -- correct, headless path no longer pre-creates app
2. `_run_ui` now only calls `create_app` in prod path; dev path passes full `args` namespace
3. Headless dev path sets `LLM_PIPELINE_DB` env var when `args.db` is provided, then calls `uvicorn.run("llm_pipeline.ui.cli:_create_dev_app", factory=True, ...)`
4. New `_create_dev_app()` factory reads `LLM_PIPELINE_DB` from env and delegates to `create_app(db_path=...)`
5. Verified `_create_dev_app` is importable from module path and returns a valid `FastAPI` instance

**Assessment:** Clean fix. Env var approach aligns with existing `create_app` contract (which already documents `LLM_PIPELINE_DB` env var). The `factory=True` parameter tells uvicorn to call the function on each reload, which is correct.

## Remaining Issues (unchanged from initial review)

### Medium
#### Path.exists patch is overly broad in tests
**Step:** 2
**Details:** Unchanged. Global `pathlib.Path.exists` patching is fragile but functional. Low risk.

#### No test for SIGTERM handler registration on Unix
**Step:** 2
**Details:** Unchanged. Simple guard, low risk.

### Low
#### No test coverage for `_create_dev_app` factory or `factory=True` kwarg
**Step:** 1 (fix)
**Details:** The new `_create_dev_app()` function has no dedicated unit test. The headless dev tests (`TestDevModeNoFrontend`) verify `reload=True` is passed to `uvicorn.run` but do not assert that the first positional arg is the import string `"llm_pipeline.ui.cli:_create_dev_app"` or that `factory=True` is passed. The function itself is trivial (2 lines), so risk is low.

#### Type annotation uses `object` instead of protocol or Union
**Step:** 1
**Details:** Unchanged. Minor polish item.

#### Startup info message hardcodes "localhost" for Vite URL
**Step:** 1
**Details:** Unchanged. Very minor.

## Review Checklist
[x] Architecture patterns followed -- factory pattern for uvicorn reload, env var for config passthrough, clean separation maintained
[x] Code quality and maintainability -- new factory function is minimal and well-documented
[x] Error handling present -- all pre-existing error handling intact
[x] No hardcoded values -- env var name `LLM_PIPELINE_DB` matches existing project convention
[x] Project conventions followed -- stdlib-only top-level imports preserved
[x] Security considerations -- no new security surface introduced
[x] Properly scoped (DRY, YAGNI, no over-engineering) -- minimal fix, no unnecessary abstractions

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| `llm_pipeline/ui/cli.py` | pass | HIGH issue resolved. Import string + factory=True pattern is correct. |
| `tests/ui/test_cli.py` | pass | 34 tests pass. Missing _create_dev_app coverage (LOW). |

## New Issues Introduced
- No test for `_create_dev_app` factory or `factory=True` kwarg (LOW, Step 1)

## Recommendation
**Decision:** APPROVE
The HIGH issue is resolved correctly. Remaining issues are MEDIUM and LOW severity, none blocking. The implementation is clean, well-structured, and aligned with project architecture. The factory pattern for uvicorn reload is the standard approach and works correctly.
