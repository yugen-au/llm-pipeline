# Task Summary

## Work Completed

Implemented two REST endpoints in `llm_pipeline/ui/routes/prompts.py` (previously a 4-line stub):

- `GET /api/prompts` - paginated list with `category`, `step_name`, `prompt_type`, `is_active` (default True), `offset`, `limit` filters
- `GET /api/prompts/{prompt_key}` - grouped detail returning `{ prompt_key, variants: [...] }`

Response models added: `PromptItem`, `PromptListResponse`, `PromptVariant` (type alias for `PromptItem`), `PromptDetailResponse`. Variable resolution uses stored `required_variables` when non-null, falling back to `extract_variables_from_content(content)`.

17 tests written covering all filter combinations, pagination, 404 behaviour, variable fallback, and grouped variant response.

Frontend `types.ts` updated: `PromptVariant` and `PromptDetail` interfaces added; `@provisional` tags removed from `Prompt`, `PromptListResponse`, `PromptListParams`.

DRY fix applied post-review: `get_prompt` now delegates to `_to_prompt_item` helper; `PromptVariant` is a type alias rather than a duplicate class.

## Files Changed

### Created
| File | Purpose |
| --- | --- |
| `tests/ui/test_prompts.py` | 17 tests for GET /api/prompts and GET /api/prompts/{prompt_key} |

### Modified
| File | Changes |
| --- | --- |
| `llm_pipeline/ui/routes/prompts.py` | Full implementation replacing stub: response models, query params model, `_resolve_variables`, `_to_prompt_item`, `_apply_filters` helpers, `list_prompts` and `get_prompt` endpoints |
| `llm_pipeline/ui/frontend/src/api/types.ts` | Added `PromptVariant` and `PromptDetail` interfaces; removed `@provisional` tags from `Prompt`, `PromptListResponse`, `PromptListParams` |

## Commits Made

| Hash | Message |
| --- | --- |
| `971d439` | docs(implementation-A): master-22-prompts-api-endpoint |
| `aa1bb1c` | docs(implementation-B): master-22-prompts-api-endpoint |
| `be91791` | docs(fixing-review-A): master-22-prompts-api-endpoint |

State/docs housekeeping commits omitted (chore/docs commits for task framework state machine).

## Deviations from Plan

- `PromptVariant` implemented as a type alias (`PromptVariant = PromptItem`) rather than a duplicate Pydantic class. Review identified the original class as a DRY violation; alias is cleaner and functionally identical.
- `get_prompt` detail endpoint reuses `_to_prompt_item` for mapping (post-review fix) rather than inline field construction as originally specified in Step 1.

## Issues Encountered

### DRY violation in get_prompt
`get_prompt` originally duplicated all 14 field mappings inline instead of reusing `_to_prompt_item`. Identified during architecture review as medium-severity.
**Resolution:** `PromptVariant` changed to a type alias (`PromptVariant = PromptItem`). `get_prompt` changed to `variants=[_to_prompt_item(r) for r in rows]`. All 17 tests passed after fix with no regressions.

### Pre-existing test failure
`tests/test_ui.py::TestRoutersIncluded::test_events_router_prefix` fails with `assert '/runs/{run_id}/events' == '/events'`. Confirmed pre-existing via stash; predates this branch.
**Resolution:** Not fixed (out of scope). Documented in TESTING.md for a separate task.

## Success Criteria

- [x] GET /api/prompts returns 200 with `{ items, total, offset, limit }` envelope -- verified by `test_empty_db_returns_200_empty`, `test_returns_active_by_default`
- [x] GET /api/prompts defaults to is_active=True -- verified by `test_returns_active_by_default` (total==2, only active rows returned)
- [x] category/step_name/prompt_type filters work -- verified by `test_category_filter`, `test_step_name_filter`, `test_prompt_type_filter`
- [x] GET /api/prompts/{prompt_key} returns `{ prompt_key, variants: [...] }` grouped response -- verified by `test_returns_grouped_variants`
- [x] GET /api/prompts/unknown_key returns 404 -- verified by `test_404_for_unknown_key`
- [x] required_variables: stored value when non-null, fallback to extract_variables_from_content when null -- verified by `test_required_variables_populated`, `test_required_variables_fallback`, `test_required_variables_fallback_in_detail`
- [x] 17/17 new tests pass
- [x] No regressions: test_runs.py, test_steps.py, test_events.py all pass; 1 failure is pre-existing in test_ui.py unrelated to task
- [x] Frontend types.ts has PromptDetail and PromptVariant interfaces; @provisional tags removed

## Recommendations for Follow-up

1. Fix pre-existing `test_events_router_prefix` failure -- update assertion from `/events` to `/runs/{run_id}/events` to match actual router mount prefix.
2. Add `= None` defaults to optional fields in `PromptItem` (`category`, `step_name`, `description`, `created_by`) to match `runs.py` style convention -- cosmetic only, non-blocking.
3. Consider adding `prompt_type` to the frontend `PromptListParams` interface in `types.ts` -- backend accepts it, frontend currently does not send it.
4. Human validation step: start UI server (`uv run python -m llm_pipeline.ui`) and verify `curl http://localhost:8000/api/prompts` returns `{"items":[],"total":0,"offset":0,"limit":50}`.
