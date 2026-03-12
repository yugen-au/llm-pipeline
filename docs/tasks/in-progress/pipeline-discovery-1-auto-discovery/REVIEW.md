# Architecture Review

## Overall Assessment
**Status:** complete

Implementation is clean, minimal, and well-aligned with the PLAN.md decisions and VALIDATED_RESEARCH conclusions. Discovery logic is correctly isolated as private helpers, merge order is correct, seed_prompts is properly isolated, and the model guard is placed at the right execution boundary. All 191 UI tests pass. Two medium issues and two low issues found.

## Project Guidelines Compliance
**CLAUDE.md:** C:\Users\SamSG\Documents\claude_projects\llm-pipeline\CLAUDE.md (project), C:\Users\SamSG\.claude\CLAUDE.md (global)

| Guideline | Status | Notes |
| --- | --- | --- |
| No hardcoded values | pass | Model fallback uses param > env > None, no hardcoded default |
| Error handling present | pass | Broad except+warning for ep.load(), separate except for seed_prompts, 422 guard |
| Tests pass | pass | 191 passed, 0 failures |
| Warnings fixed | pass | No new warnings observed |
| Project conventions (logging) | pass | Uses `logging.getLogger(__name__)` per codebase pattern |
| Backward compatibility | pass | All 3 CLI call sites (cli.py L46, L82, L109) unaffected -- new params have defaults |

## Issues Found

### Critical

None

### High

None

### Medium

#### Missing test for HTTP 422 model guard
**Step:** 2
**Details:** No test verifies that `trigger_run` returns 422 when `default_model` is None but the pipeline exists in the registry. The two existing 404 tests (`test_returns_404_for_unregistered_pipeline`, `test_returns_404_when_registry_empty`) implicitly prove 404 fires before the model guard, but the 422 path itself is untested. A test like `create_app(db_path=":memory:", pipeline_registry={"p": factory})` (no `default_model`) followed by `POST /api/runs {"pipeline_name": "p"}` asserting 422 is needed. Without it, the guard could be removed or broken without detection.

#### conftest _make_app missing introspection_registry on app.state
**Step:** 1
**Details:** The `_make_app()` fixture in `tests/ui/conftest.py` sets `app.state.pipeline_registry` and `app.state.default_model` but does not set `app.state.introspection_registry`. The pipelines route (`list_pipelines`, `get_pipeline`) uses `getattr(request.app.state, "introspection_registry", {})` which safely defaults to `{}`, so this is not a runtime error. However, it means the test fixture does not match the contract that `create_app()` establishes (which always sets both registries). If any future test uses the `seeded_app_client` or `app_client` fixture to test pipeline introspection endpoints, it would silently get an empty registry. This was pre-existing (not introduced by this task), but the addition of `default_model` without also adding `introspection_registry` makes the gap more visible.

### Low

#### Factory closure passes model=None to PipelineConfig.__init__ if guard is bypassed
**Step:** 1
**Details:** The factory closure created by `_make_pipeline_factory` captures `model: Optional[str]` and passes it directly to `cls(model=model, ...)`. `PipelineConfig.__init__` declares `model: str` (no default). The 422 guard in `trigger_run` prevents this path at runtime, but if a consumer calls the factory directly (outside the HTTP layer), they get a Pydantic/TypeError at `__init__` time rather than a clear "no model configured" message. This is an acceptable tradeoff per the PLAN rationale ("guard at execution boundary"), but worth documenting that the factory is only safe to call when a model is configured.

#### Startup warning fires on every test that omits default_model
**Step:** 1
**Details:** The two 404 tests in `test_runs.py` call `create_app(db_path=":memory:")` without `default_model`, which triggers the `logger.warning("No default model configured...")` on every test run. This is noise in test output. Consider either (a) adding `default_model="test-model"` to those calls (they test 404 behavior, not model behavior) or (b) suppressing the warning via `auto_discover=False, default_model="x"` for cleaner test logs. Not functionally broken.

## Review Checklist
[x] Architecture patterns followed -- private helpers, factory pattern, entry-point discovery
[x] Code quality and maintainability -- clean separation, good docstrings, consistent style
[x] Error handling present -- broad except on ep.load(), isolated seed_prompts except, 422 guard
[x] No hardcoded values -- model resolution uses param > env > None
[x] Project conventions followed -- logging.getLogger(__name__), logger.warning for load errors
[x] Security considerations -- no new attack surface; entry points are publisher-controlled
[x] Properly scoped (DRY, YAGNI, no over-engineering) -- inline in app.py, no premature extraction

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| llm_pipeline/ui/app.py | pass | Discovery logic, factory closure, model resolution, merge order all correct |
| llm_pipeline/ui/routes/runs.py | pass | Model guard placed correctly after 404, before execution |
| tests/ui/conftest.py | pass | default_model added; missing introspection_registry is pre-existing |
| tests/ui/test_runs.py | pass | All create_app calls updated; missing 422 guard test noted |
| llm_pipeline/ui/cli.py | pass | 3 call sites backward-compatible with new defaults |
| llm_pipeline/ui/routes/pipelines.py | pass | Uses getattr for introspection_registry; unmodified, compatible |

## New Issues Introduced
- Missing test coverage for the 422 model guard path (MEDIUM, Step 2)
- Startup warning noise in 404 tests that omit default_model (LOW, Step 1)

## Recommendation
**Decision:** CONDITIONAL

Approve pending addition of one test for the 422 model guard path. The missing test is the only gap that could allow a regression in the core new behavior (model None guard). All other issues are low severity or pre-existing. The implementation is architecturally sound, well-documented, and correctly follows all PLAN.md decisions and CEO directives from VALIDATED_RESEARCH.

Required before merge:
1. Add test: `trigger_run` returns 422 when pipeline exists but `default_model` is None

Recommended (not blocking):
1. Add `app.state.introspection_registry = {}` to conftest `_make_app()` for fixture consistency
2. Pass `default_model="test-model"` to the two 404 test `create_app()` calls to suppress warning noise

---

# Re-Review (post-fix)

## Fix Verified
The previously required change -- "Add test: `trigger_run` returns 422 when pipeline exists but `default_model` is None" -- has been addressed by `test_returns_422_when_no_model_configured` in `tests/ui/test_runs.py`.

**Test correctness:** The new test (1) creates an app with a registered pipeline but `default_model=None`, (2) POSTs to trigger that pipeline, (3) asserts HTTP 422, and (4) verifies the detail message contains both "No model configured" and "LLM_PIPELINE_MODEL". This covers the exact gap identified: the 422 guard path is now exercised and regression-protected. All 25 tests in `test_runs.py` pass.

## Remaining Issues Assessment

### conftest _make_app missing introspection_registry (previously MEDIUM)
**Disposition:** Out of scope. This is pre-existing behavior not introduced by this task. The route safely defaults via `getattr(request.app.state, "introspection_registry", {})`. No runtime risk. Can be tracked as a separate cleanup item.

### Factory closure model=None bypass (previously LOW)
**Disposition:** Accepted. The 422 guard now has test coverage confirming it blocks the path. Risk is mitigated.

### Startup warning noise in 404 tests (previously LOW)
**Disposition:** Accepted. Cosmetic only, no functional impact. The new 422 test intentionally relies on `default_model=None` so the warning is expected there.

## Updated Recommendation
**Decision:** APPROVE

All required changes addressed. The 422 model guard has test coverage. Implementation is architecturally sound, backward-compatible, and aligned with PLAN.md. Remaining issues are pre-existing (conftest) or cosmetic (warning noise) -- neither blocks merge. No new issues introduced by the fix.
