# Task Summary

## Work Completed

Fixed data mapping across three tabs in `StepDetailPanel` UI. The root cause was a swap between what the Instructions and Prompts tabs were displaying, plus a hardcoded `raw_response=None` on the backend that prevented the Response tab from ever showing content.

- **Instructions tab**: Rewired from `useStepInstructions` (prompt templates) to `usePipeline` (Pydantic output model JSON schema from `/api/pipelines/{name}`). Rewritten to render `instructions_class` label above a `<pre>` JSON schema block with a "No schema available" empty state.
- **Prompts tab**: Rewired from `llm_call_starting` event data (rendered/variable-injected prompts) to `useStepInstructions` (prompt templates with `{variable}` placeholders). Rendering logic moved from old InstructionsTab.
- **Response tab**: Backend `_extract_raw_response()` helper added to `pipeline.py`. Extracts last `ModelResponse` from `run_result.new_messages()`; serializes `ToolCallPart.args` to JSON string (structured output case) or uses `TextPart.content` (text output case). Populated at both emission sites (normal path and consensus path) instead of hardcoded `None`.
- **Review fixes**: Added type annotation to `_extract_raw_response`, updated `usePipeline` to accept `string | undefined`, added inline comments explaining mock pattern in tests.

## Files Changed

### Created
| File | Purpose |
| --- | --- |
| `tests/test_raw_response.py` | 7 unit tests for `_extract_raw_response`: ToolCallPart, TextPart, no-response, multi-part, last-response-wins, exception fallback, non-serializable fallback |

### Modified
| File | Changes |
| --- | --- |
| `llm_pipeline/pipeline.py` | Added `_extract_raw_response(run_result: Any) -> str \| None` helper (module level); replaced `raw_response=None` with `raw_response=_extract_raw_response(run_result)` at normal path (~L869) and consensus path (~L1293) |
| `llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.tsx` | Rewired `InstructionsTab` to receive `instructionsSchema`/`instructionsClass` props from `usePipeline`; rewired `PromptsTab` to receive `StepPromptItem[]` from `useStepInstructions`; removed rendered-prompt event filtering; updated `StepContent` to call `usePipeline(step?.pipeline_name)` and derive step metadata |
| `llm_pipeline/ui/frontend/src/api/pipelines.ts` | Updated `usePipeline` hook signature from `name: string` to `name: string \| undefined`; added `Boolean(name)` enabled guard; call site passes `step?.pipeline_name` directly without `?? ''` fallback |
| `llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.test.tsx` | Added `usePipeline` mock returning pipeline metadata with `instructions_schema` and `instructions_class`; updated InstructionsTab assertions to check JSON schema rendering; updated PromptsTab assertions to check prompt template items; added loading/error state tests; total tests 16 (up from 10) |

## Commits Made

| Hash | Message |
| --- | --- |
| `c9d9cf4e` | docs(implementation-A): adhoc-20260316-step-input-output-tabs (frontend tab rewire + StepDetailPanel.tsx) |
| `322a1536` | docs(implementation-A): adhoc-20260316-step-input-output-tabs (backend raw_response + pipeline.py) |
| `5103dea5` | docs(implementation-B): adhoc-20260316-step-input-output-tabs (test updates: test_raw_response.py + StepDetailPanel.test.tsx) |
| `6a767d90` | docs(fixing-review-A): adhoc-20260316-step-input-output-tabs (usePipeline undefined signature + StepDetailPanel call site) |
| `00a81cef` | docs(fixing-review-B): adhoc-20260316-step-input-output-tabs (type annotation + test comments) |

## Deviations from Plan

- None. All three implementation steps and four review fixes executed as planned. The only minor deviation was adding two extra loading/error state tests in StepDetailPanel.test.tsx during the review-fix pass (not in original plan), which increased the test count from 14 to 16 without removing any planned coverage.

## Issues Encountered

### Pre-existing WAL mode test failure on Windows
**Resolution:** Not resolved -- pre-existing failure (`tests/ui/test_wal.py::TestWALMode::test_file_based_sqlite_sets_wal`) introduced in commit `fff9f38d` (Feb 2026) before this task. SQLite on this Windows environment returns `'delete'` instead of `'wal'` after WAL PRAGMA. Not caused by this task; tracked as a follow-up recommendation.

### MagicMock isinstance() fragility for pydantic-ai types
**Resolution:** Used `mock.__class__ = ModelResponse` override pattern (known workaround when `MagicMock(spec=...)` alone does not satisfy `isinstance()` checks). Added docstring to `_model_response()` helper and inline references from `_tool_call_part()` and `_text_part()` explaining the pattern.

## Success Criteria

- [x] Instructions tab shows `instructions_schema` JSON for a step with a defined output type -- covered by `InstructionsTab renders JSON schema from usePipeline metadata` (frontend test passes)
- [x] Instructions tab shows `instructions_class` label above the schema -- covered by same test
- [x] Instructions tab shows "No schema available" empty state for steps without instructions schema -- covered by `InstructionsTab shows empty state when no pipeline schema available` (passes)
- [x] Prompts tab shows prompt templates with `{variable}` placeholders, not rendered/injected prompts -- covered by `PromptsTab renders prompt templates from useStepInstructions` (passes)
- [ ] Response tab shows non-null `raw_response` after a real pipeline run -- requires human validation (live run needed)
- [x] For structured output steps, `raw_response` is JSON string of args dict -- covered by `test_tool_call_part_returns_json_args` (passes)
- [x] For text output steps, `raw_response` is raw text string -- covered by `test_text_part_returns_content` (passes)
- [x] All existing StepDetailPanel tests pass -- 10 pre-existing + 6 new = 16 total, all pass
- [x] New backend unit tests for `_extract_raw_response` pass -- 7/7 pass
- [ ] No regressions in other tabs (Input, Context Diff, Extractions, Meta) -- requires human validation

## Recommendations for Follow-up

1. Run human validation for Response tab: trigger a real pipeline run (structured output step), open the run, click a step, click the Response tab -- expected non-null JSON string of LLM tool-call args.
2. Fix or skip `tests/ui/test_wal.py::TestWALMode::test_file_based_sqlite_sets_wal` on Windows -- mark `@pytest.mark.skipif(sys.platform == 'win32', ...)` or investigate why `init_pipeline_db` WAL PRAGMA does not take effect in this environment.
3. Consider adding type annotation `run_result: RunResult[Any]` (instead of bare `Any`) once a clean import path for `RunResult` is established without breaking the lazy-import pattern in `pipeline.py`.
4. Consider whether rendered (variable-injected) prompts should be surfaced somewhere in the UI in a future iteration -- currently this data is captured in `llm_call_starting` events but not displayed in any tab after the Prompts tab swap.
5. Consider an interactive JSON tree viewer for the Instructions tab schema display in a future polish pass -- the current `<pre>` block is functional but a tree viewer would improve navigability for large schemas.
