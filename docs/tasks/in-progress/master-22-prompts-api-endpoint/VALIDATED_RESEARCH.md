# Research Summary

## Executive Summary

Three research files were cross-referenced against the actual codebase (db/prompt.py, prompts/loader.py, prompts/service.py, ui/routes/runs.py, ui/routes/events.py, ui/deps.py, ui/frontend/src/api/types.ts, tests/ui/conftest.py). Research findings are accurate with minor omissions. Two architectural ambiguities were resolved via CEO decisions. All assumptions now validated -- ready for planning.

## Domain Findings

### Schema Mismatch: pipeline_name Filter
**Source:** step-1, step-2, step-3

The Prompt model (db/prompt.py) has NO `pipeline_name` column. Task 22 spec explicitly uses `pipeline_name: str = None` as a query filter. Available organizational fields are `category` (Optional[str], indexed) and `step_name` (Optional[str], indexed, composite with category).

**Critical discovery not in research files:** The frontend types.ts (already committed, lines 208-215) defines `PromptListParams` with `category`, `step_name`, and `is_active` filters -- NOT `pipeline_name`. The frontend team already designed around the actual schema. If the backend implements `pipeline_name`, the frontend types are wrong. If the backend uses `category`+`step_name`, the frontend types are already correct.

Additionally, Graphiti memory confirms `PipelineStepState` tracks `pipeline_name` but the `Prompt` model does not -- these are separate domain concerns.

### Variable Extraction Strategy
**Source:** step-1, step-2

`required_variables` (JSON column, Optional[List[str]]) is auto-populated by `sync_prompts()` in loader.py via `extract_variables_from_content()`. The field can be null for manually-inserted rows or rows predating sync. PromptService in service.py never reads `required_variables` -- it works with raw content only.

Hybrid approach (stored when non-null, re-extract as fallback) is clearly correct. Satisfies task spec's "reuse extract_variables_from_content()" requirement via the fallback path, while being fast for synced rows.

### Detail Endpoint Response Shape
**Source:** step-1, step-2, step-3

UniqueConstraint `(prompt_key, prompt_type)` means one key has at most 2 rows (system + user). Task spec says "Return full prompt detail with both system and user variants."

The frontend `Prompt` interface (types.ts lines 176-191) is a flat object containing `prompt_type` as a field. There is no compound PromptDetail interface. `PromptListResponse.items` is `Prompt[]`. This indicates the frontend expects individual prompt rows, not a compound grouped object.

### API Convention Compliance
**Source:** step-1, step-3

Research accurately documents all conventions. Verified against runs.py and events.py:
- `sync def` (NOT async) -- task spec uses async, codebase uses sync
- `DBSession` from `llm_pipeline.ui.deps` (ReadOnlySession wrapper)
- Plain Pydantic BaseModel response models with explicit field mapping
- `Annotated[ParamsModel, Depends()]` for query params
- Paginated envelope: `{ items, total, offset, limit }`
- `HTTPException(status_code=404)` for not found
- Comment banner sections in file structure
- `select()` from sqlmodel, `func.count()` from sqlalchemy

### Test Infrastructure
**Source:** step-1, step-3

`tests/ui/conftest.py` verified. `_make_app()` already imports and mounts `prompts_router`. Seed data pattern uses `Session(engine)` with fixed IDs. New test file should add Prompt seed data following the same pattern. No conftest changes needed.

### Router Stub
**Source:** step-1, step-3

`llm_pipeline/ui/routes/prompts.py` confirmed as stub: `router = APIRouter(prefix="/prompts", tags=["prompts"])`. Already mounted in app.py. No app.py or conftest.py changes needed.

### Research Step-3 Stale Test Note
**Source:** step-3 (section 11)

Step-3 notes `tests/test_ui.py` line 141-143 has stale assertion about events router prefix. Not blocking but worth tracking.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| pipeline_name filter: use category+step_name instead? | CEO: Yes, use category+step_name. Matches frontend, avoids schema migration, uses existing composite index. | Filter params confirmed as category+step_name+is_active. No schema change needed. Frontend types.ts already aligned. |
| GET /prompts/{prompt_key} response: flat variants list or compound object? | CEO: Grouped wrapper format: `{ prompt_key, variants: [{type: system, ...}, {type: user, ...}] }` | Detail endpoint returns grouped wrapper. Frontend will need a PromptDetail interface with variants array. |

## Assumptions Validated
- [x] Use `sync def` endpoints (not async) -- all existing HTTP routes are sync, task spec is stale
- [x] Default `is_active=True` filter on list endpoint -- every existing Prompt query in codebase filters by is_active==True; task test strategy says "inactive prompts can be filtered" (opt-in)
- [x] Variable extraction: use stored `required_variables` when non-null, fallback to `extract_variables_from_content(content)` -- handles synced + manual rows
- [x] Response models must be plain Pydantic BaseModel, not SQLModel -- explicit convention in every existing route file
- [x] Paginated list with `{ items, total, offset, limit }` envelope -- matches runs.py and events.py pattern
- [x] Router stub exists and is mounted; no app.py changes needed
- [x] Test fixtures via `_make_app()` already include prompts_router; seed Prompt rows directly via `Session(engine)`
- [x] Frontend provisional types (Prompt, PromptListResponse, PromptListParams) exist in types.ts and should be matched/updated by backend
- [x] Filter by `category` + `step_name` (NOT pipeline_name) -- CEO confirmed, frontend already aligned, composite index exists
- [x] Detail endpoint uses grouped wrapper `{ prompt_key, variants: [...] }` -- CEO confirmed, frontend needs PromptDetail interface added

## Open Items
- Frontend types.ts needs PromptDetail interface added for grouped wrapper response; remove `@provisional` tags after backend lands
- Stale test assertion in tests/test_ui.py for events router prefix (non-blocking, separate fix)

## Recommendations for Planning
1. **Filters (confirmed):** `category` + `step_name` + `is_active` query params on GET /api/prompts. `is_active` defaults to True. No pipeline_name.
2. **Detail response (confirmed):** GET /api/prompts/{prompt_key} returns `{ prompt_key: str, variants: List[PromptVariant] }` where each variant is a flat prompt object with prompt_type, content, required_variables, etc.
3. **Variables:** Use stored `required_variables` when non-null; fallback to `extract_variables_from_content(content)` for null values.
4. **Conventions:** sync def, DBSession, plain Pydantic BaseModel responses, explicit field mapping, paginated envelope, comment banner sections.
5. **Tests:** Add Prompt seed data to conftest or new fixture. Seed both system+user variants for same prompt_key. Test list filters, detail grouping, 404, pagination.
6. **Frontend follow-up:** Add PromptDetail interface (grouped wrapper) to types.ts. Remove `@provisional` tags. Existing PromptListParams already correct.
