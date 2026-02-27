# Architecture Review

## Overall Assessment
**Status:** complete
Solid, well-scoped additive feature. Follows existing ClassVar/BaseModel/introspection patterns throughout. Clean separation of input_data from initial_context. Type guard at import time is correct. All 7 steps align with PLAN.md and VALIDATED_RESEARCH.md CEO decisions. No critical or high issues found.

## Project Guidelines Compliance
**CLAUDE.md:** C:\Users\SamSG\Documents\claude_projects\llm-pipeline\CLAUDE.md
| Guideline | Status | Notes |
| --- | --- | --- |
| Python 3.11+ | pass | Uses `str \| None` union syntax (L499) -- valid 3.10+ |
| Pydantic v2 | pass | model_validate, model_json_schema, ValidationError all v2 API |
| No hardcoded values | pass | No magic strings or hardcoded config |
| Error handling present | pass | ValueError/TypeError with contextual messages, exception chaining |
| Hatchling build | pass | No build config changes needed |
| Pipeline+Strategy+Step pattern | pass | INPUT_DATA ClassVar follows REGISTRY/STRATEGIES ClassVar pattern exactly |
| Tests pass | pass | 767/768, 1 pre-existing unrelated failure per task context |

## Issues Found
### Critical
None

### High
None

### Medium
#### _validated_input not accessible to steps
**Step:** 3
**Details:** `self._validated_input` is stored on the pipeline instance but no public property or getter exposes it to steps. Steps access pipeline data via `pipeline.context`, `pipeline.data`, `pipeline.get_data()`, etc. There is no `pipeline.validated_input` or `pipeline.get_input_data()`. This means steps cannot access the validated input object. The plan says "for potential future use" which is fine for this task scope, but the attribute is effectively dead code within this task. If intentional deferral, acceptable. If oversight, needs a property or injection into context. Severity is medium because the feature's core value (validation gate) works -- steps just can't read the validated result yet.

#### No unit tests for core PipelineInputData/INPUT_DATA behavior
**Step:** 1, 2, 3
**Details:** No dedicated test file for PipelineInputData. No tests for: (a) subclassing PipelineInputData works, (b) INPUT_DATA type guard rejects non-PipelineInputData, (c) execute() raises ValueError on missing input_data when INPUT_DATA declared, (d) execute() raises ValueError on invalid input_data, (e) execute() succeeds with valid input_data. UI route tests mock the metadata but don't test actual end-to-end INPUT_DATA integration. The introspection test_introspection.py doesn't test pipeline_input_schema key. These are core behaviors that should have direct unit coverage. The implementation docs say "tests pass" but the existing tests only cover the UI layer indirectly.

### Low
#### Empty dict rejection may surprise callers
**Step:** 3
**Details:** `if input_data is None or not input_data` treats `{}` as missing input. While documented in step-3 implementation notes and CEO-decided, a pipeline with an INPUT_DATA schema that has all-optional fields would fail on `execute(input_data={})` even though `{}` validates against such a schema. This is an edge case. The decision is documented and intentional per VALIDATED_RESEARCH.md, so severity is low. Future consumers should be aware.

#### Introspection cache not invalidated if pipeline_input_schema injected externally
**Step:** 4, 5
**Details:** The test `test_list_has_input_schema_true_with_pipeline_input_schema` patches `get_metadata` to inject `pipeline_input_schema` into the returned dict. Since introspection uses a class-identity-keyed cache (`id(cls)`), this patch mutates the cached dict in-place which could leak between tests if cache isn't cleared. The `clear_introspector_cache` fixture handles this, but the test's approach of mutating the cached dict is fragile -- if the fixture ordering changes, this could cause flaky tests. Low severity because the fixture is `autouse=True`.

## Review Checklist
[x] Architecture patterns followed -- ClassVar, __init_subclass__ guard, BaseModel inheritance all match existing codebase patterns
[x] Code quality and maintainability -- clean, readable, well-documented implementation steps
[x] Error handling present -- ValueError with pipeline name context, TypeError for type guard, exception chaining with `from e`
[x] No hardcoded values
[x] Project conventions followed -- snake_case naming, import ordering, __all__ exports
[x] Security considerations -- input validation via Pydantic schema, no user-controlled code execution
[x] Properly scoped (DRY, YAGNI, no over-engineering) -- minimal base class, no unnecessary abstractions

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| llm_pipeline/context.py | pass | PipelineInputData follows PipelineContext pattern exactly |
| llm_pipeline/pipeline.py | pass | INPUT_DATA ClassVar, type guard, execute() validation all clean |
| llm_pipeline/introspection.py | pass | Reuses _get_schema(), correct cache integration |
| llm_pipeline/ui/routes/pipelines.py | pass | has_input_schema now pipeline-level, cleaner semantic |
| llm_pipeline/ui/routes/runs.py | pass | Clean separation -- input_data as dedicated param |
| llm_pipeline/__init__.py | pass | Correct import and __all__ placement |
| tests/ui/test_pipelines.py | pass | Two new tests cover both false/true has_input_schema states |
| tests/ui/test_runs.py | pass | Spy test validates input_data threading to factory + execute |

## New Issues Introduced
- _validated_input stored but not exposed to pipeline steps (dead code for now, future task needed)
- No dedicated unit tests for PipelineInputData base class, INPUT_DATA type guard, or execute() input validation logic

## Recommendation
**Decision:** CONDITIONAL
Implementation is architecturally sound and follows all codebase conventions. Two medium issues: (1) _validated_input is stored but unreachable by steps -- acceptable if deferred to a follow-up task, needs explicit acknowledgment; (2) core INPUT_DATA behaviors lack direct unit tests -- the UI tests provide indirect coverage but dedicated tests for the type guard, missing-input error, invalid-input error, and valid-input success paths should be added before merge or tracked as immediate follow-up task.
