# IMPLEMENTATION - STEP 3: CREATOR ENDPOINT TESTS
**Status:** completed

## Summary
Created 18 tests across 4 test classes covering all 5 creator API endpoints. Tests use in-memory SQLite with seeded DraftStep rows and mock all creator module calls (StepCreatorPipeline, StepSandbox, StepIntegrator) to avoid real LLM/Docker execution.

## Files
**Created:** `tests/ui/test_creator.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `tests/ui/test_creator.py`
New test file with:
- `_make_seeded_creator_app()` helper: in-memory SQLite + StaticPool, 2 DraftStep rows (draft + tested)
- `creator_client` / `creator_app_and_client` fixtures
- `TestGenerateEndpoint` (4 tests): 202 accepted, draft row created, 422 missing model, WS broadcast
- `TestTestEndpoint` (4 tests): sandbox no overrides, code_overrides persistence, error status, 404
- `TestAcceptEndpoint` (4 tests): integrator result, pipeline_file param, 404, integrator failure 500
- `TestDraftsEndpoint` (6 tests): list all, ordering, schema, get by id (x2), 404

## Decisions
### Mock targets at source modules
**Choice:** Patch `llm_pipeline.creator.pipeline.StepCreatorPipeline`, `llm_pipeline.creator.sandbox.StepSandbox`, `llm_pipeline.creator.models.GeneratedStep.from_draft`, `llm_pipeline.creator.integrator.StepIntegrator` at their source modules rather than on the route module
**Rationale:** Route handlers use lazy `from ... import ...` inside function bodies, so the names don't exist as attributes on `llm_pipeline.ui.routes.creator` at patch time. Patching at source ensures the lazy imports pick up mocks.

### Background task handling in generate tests
**Choice:** Mock StepCreatorPipeline so background task completes cleanly (execute/save return None)
**Rationale:** TestClient flushes background tasks on context exit. Without mocking, the real pipeline runs and fails, changing PipelineRun.status to "failed". Mocking at source lets the closure's lazy import get the mock.

## Verification
[x] All 18 new tests pass
[x] No new test failures (3 pre-existing failures in test_cli.py confirmed unrelated)
[x] Tests cover all 5 endpoints: generate, test, accept, list drafts, get draft
[x] All mocked: StepCreatorPipeline, StepSandbox, StepIntegrator -- no real LLM/Docker calls
[x] DB persistence verified for code_overrides, DraftStep status, PipelineRun creation
