# Architecture Review

## Overall Assessment
**Status:** partial
Implementation is structurally sound -- clean component boundaries, proper separation of concerns, correct use of existing patterns (shadcn, pure components, factory kwargs). Two issues require attention: the 422 error mapping path is broken at runtime due to apiClient serializing Pydantic's array-typed `detail` into `[object Object]`, and there are no tests verifying input_data actually reaches the factory/execute.

## Project Guidelines Compliance
**CLAUDE.md:** C:\Users\SamSG\Documents\claude_projects\llm-pipeline\.claude\CLAUDE.md
| Guideline | Status | Notes |
| --- | --- | --- |
| Pydantic v2 | pass | TriggerRunRequest uses Pydantic BaseModel correctly |
| SQLModel / SQLAlchemy 2.0 | pass | No new DB models; existing patterns unchanged |
| Pipeline + Strategy + Step pattern | pass | execute() signature change is backwards-compatible |
| pytest testing | pass | Existing tests updated and pass; but see HIGH re: missing input_data coverage |

## Issues Found
### Critical
None

### High
#### 422 error mapping broken at runtime
**Step:** 5
**Details:** `apiClient` (client.ts L16-19) casts the response body as `{ detail?: string }` and assigns `body.detail` to a string variable. For Pydantic 422 responses, `detail` is an **array** of `{loc, msg, type}` objects, not a string. At runtime, `body.detail` is the raw array object. This array is stored in `ApiError.detail` (typed as `string` but actually an array at runtime). In live.tsx L150, `JSON.parse(error.detail)` is called, but `JSON.parse` calls `.toString()` on non-string arguments, producing `"[object Object]"` or `"[object Object],[object Object]"` -- which is not valid JSON. The parse throws, the catch block silently swallows it, and no field errors are displayed. The entire 422 per-field error feature is non-functional. Fix: either (a) `JSON.stringify` the detail in apiClient when it's not a string, or (b) check `typeof error.detail` in live.tsx and handle the case where it's already a parsed array. Option (a) is cleaner since it keeps ApiError.detail consistently a string.

#### No test coverage for input_data threading
**Step:** 2
**Details:** No tests verify that `input_data` from the HTTP body reaches the factory call or `pipeline.execute()`. Existing test factories use `**kw` which absorbs the new kwarg silently, but there is no assertion that `input_data={"foo": "bar"}` passed in the POST body actually arrives at the factory or is forwarded as `initial_context`. A regression (e.g. someone removes the kwargs from the factory call) would go undetected. Add at least one test that captures the kwargs passed to the factory and asserts `input_data` is present.

### Medium
#### usePipeline fires on every pipeline selection even when schema is always null
**Step:** 5
**Details:** `usePipeline(selectedPipeline ?? '')` triggers a GET /api/pipelines/{name} request on every pipeline selection change. Until Task 43 lands, `pipeline_input_schema` is always null, making this an unnecessary network call. The query is properly disabled when no pipeline is selected (empty string -> `enabled: false`), so there is no error -- just wasted bandwidth. Not blocking since TanStack Query caches the response and the staleTime covers repeat selections. Low urgency but worth noting for awareness.

### Low
#### Comment says "Col 1: Pipeline selector + run button + placeholder" but placeholder is gone
**Step:** 5
**Details:** live.tsx L291 comment `{/* Col 1: Pipeline selector + run button + placeholder */}` still references "placeholder" which was replaced by InputForm. Minor doc drift.

#### validateForm does not check type constraints
**Step:** 4
**Details:** `validateForm` only validates required-ness (empty/null/undefined). It does not validate type constraints (e.g. a string value in a number field). This is by design (backend Pydantic handles type validation), but the 422 mapping path is broken (see HIGH issue), so type validation errors from the backend will not display inline. Once the 422 issue is fixed, this becomes a non-issue.

## Review Checklist
[x] Architecture patterns followed -- pure component pattern, factory kwargs, clean separation
[x] Code quality and maintainability -- well-structured, consistent with codebase
[x] Error handling present -- try/catch on 422 parsing, graceful null-schema handling
[ ] No hardcoded values -- pass (no magic strings or numbers)
[x] Project conventions followed -- shadcn components, Pydantic models, TypeScript types
[ ] Security considerations -- input_data is Optional[Dict[str, Any]] which accepts arbitrary JSON; no validation beyond Pydantic type checking. Acceptable for internal tooling but noted.
[ ] Properly scoped (DRY, YAGNI, no over-engineering) -- good. No over-engineering. usePipeline call is technically YAGNI until Task 43 but enables future-proofing per plan rationale.

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| llm_pipeline/ui/routes/runs.py | pass | TriggerRunRequest extension and factory/execute threading clean |
| llm_pipeline/ui/routes/pipelines.py | pass | pipeline_input_schema field addition minimal and correct |
| llm_pipeline/pipeline.py | pass | execute() defaults backwards-compatible, None guard correct |
| llm_pipeline/ui/frontend/src/components/live/InputForm.tsx | pass | Pure component, correct null handling, validateForm helper clean |
| llm_pipeline/ui/frontend/src/components/live/FormField.tsx | pass | Type dispatch correct, accessibility (aria-invalid) good |
| llm_pipeline/ui/frontend/src/routes/live.tsx | fail | 422 mapping broken (HIGH); stale comment (LOW) |
| llm_pipeline/ui/frontend/src/api/types.ts | pass | Types match backend shapes, JsonSchema alias appropriate |
| llm_pipeline/ui/frontend/src/components/ui/input.tsx | pass | shadcn generated, no changes needed |
| llm_pipeline/ui/frontend/src/components/ui/label.tsx | pass | shadcn generated |
| llm_pipeline/ui/frontend/src/components/ui/checkbox.tsx | pass | shadcn generated |
| llm_pipeline/ui/frontend/src/components/ui/textarea.tsx | pass | shadcn generated |
| tests/ui/test_runs.py | pass | Mock execute() signatures updated to accept **kwargs |
| tests/ui/test_integration.py | pass | Factory and pipeline mocks updated consistently |

## New Issues Introduced
- 422 error mapping is non-functional due to apiClient detail serialization mismatch (HIGH - Step 5)
- No test coverage for input_data end-to-end threading (HIGH - Step 2)
- Stale comment in live.tsx L291 referencing "placeholder" (LOW - Step 5)

## Recommendation
**Decision:** CONDITIONAL
Approve once the two HIGH issues are resolved: (1) fix 422 error mapping so Pydantic validation errors display inline, and (2) add at least one test asserting input_data reaches the factory. The architecture, component design, and backend changes are solid. The 422 fix can be done in apiClient (stringify non-string detail) or in live.tsx (type-check before JSON.parse). The test gap is straightforward to fill with an assertion in TestTriggerRun.
