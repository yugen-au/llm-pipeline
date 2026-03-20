# Architecture Review

## Overall Assessment
**Status:** complete
Solid implementation across all 9 steps. Clean component decomposition, consistent patterns with existing codebase (live.tsx, StepDetailPanel), proper React Query cache management, and correct Monaco lazy-loading. One functional bug in 409 rename error handling where suggested_name is silently lost through apiClient's detail extraction. Remaining issues are low severity (type duplication, missing deps, unsafe cast).

## Project Guidelines Compliance
**CLAUDE.md:** D:\Documents\claude-projects\llm-pipeline\CLAUDE.md
| Guideline | Status | Notes |
| --- | --- | --- |
| Python 3.11+ | pass | Uses `dict[str, str]` union syntax, match-case not used but 3.11 features compatible |
| Pydantic v2 | pass | DraftDetail, RenameRequest use BaseModel with v2 patterns |
| SQLModel / SQLAlchemy 2.0 | pass | Session(engine) pattern, select() statements, IntegrityError handling |
| Pipeline + Strategy + Step pattern | pass | Creator extends existing DraftStep model, fits within pipeline architecture |
| ReadOnlySession awareness | pass | Write endpoints correctly use Session(engine) not DBSession; read endpoints use DBSession |
| Hatchling build | n/a | No build config changes |
| Tests pass | pass | Step 1: 25 tests pass; Step 2: 16 StepDetailPanel tests pass |
| No hardcoded values | pass | MIN_DESC_LENGTH extracted as const; staleTime values match existing hooks |
| Error handling present | pass | All mutation callbacks have onError; backend has try/catch/finally in run_creator |

## Issues Found
### Critical
None

### High
None

### Medium
#### 409 rename suggested_name silently lost through apiClient
**Step:** 8
**Details:** The PATCH /drafts/{id} endpoint returns `{"detail": "name_conflict", "suggested_name": "foo_2"}` as the response body on 409. `apiClient` (client.ts) processes non-OK responses by extracting `body.detail`, which yields the string `"name_conflict"`. The `suggested_name` field is discarded. In creator.tsx handleRename (line 327), `JSON.parse(error.detail)` tries to parse `"name_conflict"` as JSON, which throws, falling through to the catch block that shows `"Name already taken"` -- the suggested name is never surfaced. Fix: either (a) restructure backend 409 to nest both fields inside `detail` (e.g., `{"detail": "{\"name_conflict\": true, \"suggested_name\": \"foo_2\"}"}`), or (b) make apiClient preserve the full response body for non-OK responses so the frontend can access `suggested_name`.

### Low
#### WorkflowState type duplicated across two files
**Step:** 5
**Details:** `CreatorEditor.tsx` (line 10-18) defines its own local `type WorkflowState` identical to the exported type in `CreatorResultsPanel.tsx` (line 15-23). The route component imports from CreatorResultsPanel. CreatorEditor should also import from there instead of re-declaring. TypeScript's structural typing prevents build failures today, but independent evolution of these two types could introduce subtle runtime bugs.

#### populateFromDraft missing from useEffect dependency array
**Step:** 8
**Details:** The stream_complete detection useEffect (creator.tsx line 85-104) calls `populateFromDraft(data)` inside the `.then()` callback but `populateFromDraft` is not listed in the dependency array `[workflowState, events, activeDraftId, refetchDraft]`. The function has a stable reference (useCallback with [] deps) so this is not a runtime bug, but ESLint's exhaustive-deps rule would flag it. Adding it to the array is a trivial fix.

#### Unsafe cast of test_results to TestResponse
**Step:** 8
**Details:** In creator.tsx line 114, `draft.test_results as unknown as TestResponse` performs a double cast. The DraftDetail type defines `test_results: Record<string, unknown> | null` while the route needs `TestResponse`. This cast bypasses all type checking. If the backend test_results shape diverges from TestResponse, the mismatch would cause runtime errors without compile-time warnings. Consider adding a runtime shape check or aligning the DraftDetail type with TestResponse.

#### Backend collision retry has no exhaustion fallback
**Step:** 1
**Details:** In `run_creator()` (creator.py line 228-247), the name collision retry loop tries candidates `[base_name, base_name_2, ..., base_name_9]`. If all 8 suffixed names are taken, the loop exits without calling `post_session.commit()` and without logging that all candidates were exhausted. The draft retains its temporary `draft_XXXXXXXX` name, which is acceptable behavior, but a log.error or explicit handling at loop exhaustion would improve debuggability.

#### EditorSkeleton uses array index as key
**Step:** 4
**Details:** `EditorSkeleton.tsx` (line 19-24) uses `key={i}` for the skeleton line list. This is acceptable here since the list is static and never reorders, but it triggers the `react/no-array-index-key` lint rule if enabled. Non-issue for this specific case.

## Review Checklist
[x] Architecture patterns followed -- component decomposition matches existing codebase (live.tsx 3-column pattern, shared component extraction, React Query hooks)
[x] Code quality and maintainability -- clean separation of concerns, proper TypeScript interfaces, barrel exports
[x] Error handling present -- all mutations have onError callbacks, backend has comprehensive try/catch in background task
[x] No hardcoded values -- constants extracted (MIN_DESC_LENGTH, EDITOR_OPTIONS, TABS, STATUS_VARIANT, LINE_WIDTHS)
[x] Project conventions followed -- import patterns, file structure, naming conventions match existing code
[x] Security considerations -- no credentials exposed, ReadOnlySession used for read endpoints, writable Session for writes
[x] Properly scoped (DRY, YAGNI, no over-engineering) -- shared components extracted only where patterns exist, no Zustand for page-local state

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| llm_pipeline/ui/routes/creator.py | pass | DraftDetail model, PATCH rename, collision retry all correctly implemented. Minor: no exhaustion fallback in retry loop |
| llm_pipeline/ui/frontend/src/components/shared/LabeledPre.tsx | pass | Clean, composable via className, space-y-1 wrapper included |
| llm_pipeline/ui/frontend/src/components/shared/BadgeSection.tsx | pass | Minimal, correct |
| llm_pipeline/ui/frontend/src/components/shared/TabScrollArea.tsx | pass | Wraps ScrollArea with cn() for composability |
| llm_pipeline/ui/frontend/src/components/shared/LoadingSkeleton.tsx | pass | SkeletonLine width via inline style is pragmatic |
| llm_pipeline/ui/frontend/src/components/shared/EmptyState.tsx | pass | Minimal, correct |
| llm_pipeline/ui/frontend/src/components/shared/index.ts | pass | Barrel export for all 6 exports |
| llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.tsx | pass | Clean refactor, imports shared components, no behavior change |
| llm_pipeline/ui/frontend/src/api/query-keys.ts | pass | Creator section follows existing hierarchical pattern |
| llm_pipeline/ui/frontend/src/api/creator.ts | pass | All 6 hooks match backend endpoints, cache invalidation correct, dynamic staleTime for terminal drafts |
| llm_pipeline/ui/frontend/src/components/creator/EditorSkeleton.tsx | pass | Static list, varying widths, correct |
| llm_pipeline/ui/frontend/src/components/creator/CreatorEditor.tsx | pass | Monaco lazy-loaded, path-based tab switching, workflow-aware buttons. Minor: local WorkflowState type should import from shared location |
| llm_pipeline/ui/frontend/src/components/creator/CreatorInputForm.tsx | pass | Validation-on-blur pattern, aria-invalid, min-length enforcement |
| llm_pipeline/ui/frontend/src/components/creator/DraftPicker.tsx | pass | Status badge variants, selected highlight, loading/empty states |
| llm_pipeline/ui/frontend/src/components/creator/CreatorInputColumn.tsx | pass | Composition wrapper, clean prop forwarding |
| llm_pipeline/ui/frontend/src/components/creator/TestResultsCard.tsx | pass | Uses shared components, handles security issues, modules, errors |
| llm_pipeline/ui/frontend/src/components/creator/AcceptResultsCard.tsx | pass | Uses LabeledPre for files_written, correct |
| llm_pipeline/ui/frontend/src/components/creator/CreatorResultsPanel.tsx | pass | Exhaustive switch with never check, exports WorkflowState |
| llm_pipeline/ui/frontend/src/routes/creator.tsx | pass | Full state machine, WS integration, 3-column + mobile tabs. Medium: 409 handling bug loses suggested_name |
| llm_pipeline/ui/frontend/src/components/Sidebar.tsx | pass | Wand2 icon, /creator nav item added correctly, type-safe via FileRoutesByTo |
| llm_pipeline/ui/frontend/vite.config.ts | pass | Monaco manualChunk placed before react-dom check |

## New Issues Introduced
- MEDIUM: 409 rename conflict response's suggested_name field is silently discarded by apiClient, making the collision suggestion feature non-functional (Step 8)
- LOW: WorkflowState type defined in two files independently (Step 5, Step 7)

## Recommendation
**Decision:** CONDITIONAL
Approve contingent on fixing the MEDIUM issue: 409 rename suggested_name data loss. This is a planned feature (collision handling with suggestion) that silently fails. The fix is small -- either restructure the backend 409 response to nest suggested_name inside the `detail` field (which apiClient preserves), or modify the frontend to handle the 409 differently. All other issues are LOW severity and can be addressed in a follow-up.
