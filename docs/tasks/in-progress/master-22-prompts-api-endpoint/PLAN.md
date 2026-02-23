# PLANNING

## Summary

Implement two REST endpoints in the existing prompts router stub (`llm_pipeline/ui/routes/prompts.py`): `GET /api/prompts` (paginated list with category/step_name/is_active/prompt_type filters) and `GET /api/prompts/{prompt_key}` (grouped detail returning `{ prompt_key, variants: [...] }`). Add a companion test file. Update frontend `types.ts` to add the `PromptDetail` interface and remove `@provisional` tags from prompt types.

## Plugin & Agents

**Plugin:** backend-development
**Subagents:** [available agents]
**Skills:** none

## Phases

1. **Implementation**: Add endpoints, response models, query params model, helper filter function to `prompts.py`
2. **Tests**: Add `tests/ui/test_prompts.py` with seed data and full coverage
3. **Frontend types**: Add `PromptDetail` interface and remove `@provisional` tags from `types.ts`

## Architecture Decisions

### Filter Parameters

**Choice:** `category`, `step_name`, `is_active` (default True), `prompt_type` query params -- no `pipeline_name`
**Rationale:** `Prompt` model has no `pipeline_name` column. Frontend `PromptListParams` in `types.ts` (lines 208-215) already uses `category`/`step_name`/`is_active`. Composite index `ix_prompts_category_step` exists. CEO confirmed this approach.
**Alternatives:** `pipeline_name` filter (rejected -- no column, would require schema migration)

### Detail Endpoint Response Shape

**Choice:** Grouped wrapper `{ prompt_key: str, variants: List[PromptVariant] }` where each variant is a flat prompt object with `prompt_type`, `content`, `required_variables`, etc.
**Rationale:** CEO confirmed grouped wrapper format. `UniqueConstraint(prompt_key, prompt_type)` guarantees at most two rows (system + user) per key, making grouping cheap (max 2 DB rows). Frontend will add a `PromptDetail` interface.
**Alternatives:** Flat list response identical to list endpoint items (rejected -- CEO decision)

### Variable Extraction Strategy

**Choice:** Return stored `required_variables` field when non-null; call `extract_variables_from_content(content)` as fallback when null
**Rationale:** `required_variables` is auto-populated by `sync_prompts()` via `extract_variables_from_content()` (loader.py line 107). Manually-inserted or pre-sync rows may have null. Hybrid approach satisfies task spec requirement to "reuse extract_variables_from_content()" via the fallback path while being fast for synced rows.
**Alternatives:** Always re-extract (slower, unnecessary for synced rows); always use stored (fails for null rows)

### Sync vs Async Endpoints

**Choice:** `sync def` endpoints
**Rationale:** All existing HTTP route handlers in runs.py, steps.py, events.py are `sync def`. SQLite is sync. FastAPI wraps sync handlers in a threadpool automatically. Task spec using `async def` is stale.
**Alternatives:** `async def` (rejected -- inconsistent with codebase, SQLModel session is not async)

### Test Fixtures

**Choice:** Add a new `seeded_prompts_client` fixture to `tests/ui/conftest.py` that seeds `Prompt` rows; `app_client` reused for empty-DB tests
**Rationale:** `_make_app()` already imports and mounts `prompts_router` (conftest.py line 26). Seed data pattern uses `Session(engine)` with fixed IDs matching existing fixtures. No structural conftest changes needed -- only additive fixture.
**Alternatives:** Inline seeding per test (rejected -- inconsistent with established pattern)

## Implementation Steps

### Step 1: Implement prompts.py endpoints and response models

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /tiangolo/fastapi, /pydantic/pydantic
**Group:** A

1. Open `llm_pipeline/ui/routes/prompts.py` (currently 4-line stub)
2. Add imports: `Annotated, List, Optional, datetime` from typing/datetime; `APIRouter, Depends, HTTPException, Query` from fastapi; `BaseModel` from pydantic; `func` from sqlalchemy; `select` from sqlmodel; `DBSession` from `llm_pipeline.ui.deps`; `Prompt` from `llm_pipeline.db.prompt`; `extract_variables_from_content` from `llm_pipeline.prompts.loader`
3. Add response model section with comment banner `# Response models (plain Pydantic, NOT SQLModel)`:
   - `PromptItem(BaseModel)`: fields `id: int`, `prompt_key: str`, `prompt_name: str`, `prompt_type: str`, `category: Optional[str]`, `step_name: Optional[str]`, `content: str`, `required_variables: Optional[List[str]]`, `description: Optional[str]`, `version: str`, `is_active: bool`, `created_at: datetime`, `updated_at: datetime`, `created_by: Optional[str]`
   - `PromptListResponse(BaseModel)`: fields `items: List[PromptItem]`, `total: int`, `offset: int`, `limit: int`
   - `PromptVariant(BaseModel)`: same fields as `PromptItem` (system or user variant in grouped detail)
   - `PromptDetailResponse(BaseModel)`: fields `prompt_key: str`, `variants: List[PromptVariant]`
4. Add query params section with comment banner `# Query params model`:
   - `PromptListParams(BaseModel)`: `category: Optional[str] = None`, `step_name: Optional[str] = None`, `prompt_type: Optional[str] = None`, `is_active: Optional[bool] = True`, `offset: int = Query(default=0, ge=0)`, `limit: int = Query(default=50, ge=1, le=200)`
5. Add helpers section with comment banner `# Helpers`:
   - `_resolve_variables(prompt: Prompt) -> Optional[List[str]]`: returns `prompt.required_variables` if not None, else `extract_variables_from_content(prompt.content)` (returns empty list if content has none)
   - `_to_prompt_item(prompt: Prompt) -> PromptItem`: maps all fields using `_resolve_variables(prompt)` for `required_variables`
   - `_apply_filters(stmt, params: PromptListParams)`: applies `.where()` for each non-None param (`category`, `step_name`, `prompt_type`, `is_active`)
6. Add endpoints section with comment banner `# Endpoints (all sync def -- SQLite is sync, FastAPI wraps in threadpool)`:
   - `GET ""` mapped to `list_prompts(params: Annotated[PromptListParams, Depends()], db: DBSession) -> PromptListResponse`: count query with filters, data query with filters + `order_by(Prompt.prompt_key, Prompt.prompt_type)` + offset/limit, return `PromptListResponse`
   - `GET "/{prompt_key}"` mapped to `get_prompt(prompt_key: str, db: DBSession) -> PromptDetailResponse`: query all rows where `Prompt.prompt_key == prompt_key`, 404 if none found, map to `PromptVariant` list sorted by `prompt_type`, return `PromptDetailResponse(prompt_key=prompt_key, variants=[...])`

### Step 2: Add test file tests/ui/test_prompts.py

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /pytest-dev/pytest
**Group:** B

1. Create `tests/ui/test_prompts.py`
2. Import: `pytest`, `Session` from sqlmodel, `TestClient` from starlette, conftest helpers `_make_app` and `_utc` (import directly from `tests.ui.conftest`), `Prompt` from `llm_pipeline.db.prompt`
3. Define constants: `KEY_CLASSIFY = "classify_shipment"`, `KEY_EXTRACT = "extract_fields"` for two distinct prompt keys used in seed data
4. Add `seeded_prompts_client` fixture: call `_make_app()`, get engine, seed with `Session(engine)` -- create:
   - `Prompt(prompt_key=KEY_CLASSIFY, prompt_type="system", category="logistics", step_name="classify", content="You are {role}. Classify {input}.", required_variables=["role", "input"], is_active=True, prompt_name="Classify System", version="1.0")`
   - `Prompt(prompt_key=KEY_CLASSIFY, prompt_type="user", category="logistics", step_name="classify", content="Item: {item}", required_variables=["item"], is_active=True, prompt_name="Classify User", version="1.0")`
   - `Prompt(prompt_key=KEY_EXTRACT, prompt_type="system", category="extraction", step_name="extract", content="Extract data.", required_variables=None, is_active=False, prompt_name="Extract System", version="2.0")`
   - Yield `TestClient(app)`
5. `class TestListPrompts`:
   - `test_empty_db_returns_200_empty(app_client)`: GET /api/prompts, assert 200, items==[], total==0
   - `test_returns_active_by_default(seeded_prompts_client)`: GET /api/prompts, assert total==2 (only active rows), all items have is_active==True
   - `test_category_filter(seeded_prompts_client)`: GET /api/prompts?category=logistics, assert total==2, all category=="logistics"
   - `test_step_name_filter(seeded_prompts_client)`: GET /api/prompts?step_name=classify, assert total==2
   - `test_prompt_type_filter(seeded_prompts_client)`: GET /api/prompts?prompt_type=system, assert total==1 (active system prompt only -- KEY_CLASSIFY system, KEY_EXTRACT system is inactive)
   - `test_is_active_false_returns_inactive(seeded_prompts_client)`: GET /api/prompts?is_active=false, assert total==1, items[0]["prompt_key"]==KEY_EXTRACT
   - `test_required_variables_fallback(seeded_prompts_client)`: GET /api/prompts?is_active=false, assert items[0]["required_variables"]==[] (fallback extraction from "Extract data." has no variables)
   - `test_pagination_limit(seeded_prompts_client)`: GET /api/prompts?limit=1, assert len(items)==1, total==2
   - `test_pagination_offset(seeded_prompts_client)`: GET /api/prompts?offset=1, assert len(items)==1
   - `test_combined_category_step_filter(seeded_prompts_client)`: GET /api/prompts?category=logistics&step_name=classify, assert total==2
   - `test_no_match_returns_empty(seeded_prompts_client)`: GET /api/prompts?category=nonexistent, assert total==0, items==[]
6. `class TestGetPrompt`:
   - `test_404_for_unknown_key(app_client)`: GET /api/prompts/no_such_key, assert 404
   - `test_returns_grouped_variants(seeded_prompts_client)`: GET /api/prompts/classify_shipment, assert 200, body["prompt_key"]==KEY_CLASSIFY, len(body["variants"])==2
   - `test_variants_contain_prompt_type_field(seeded_prompts_client)`: GET /api/prompts/classify_shipment, assert set of prompt_type values == {"system", "user"}
   - `test_single_variant_key(seeded_prompts_client)`: GET /api/prompts/extract_fields, assert 200 (404 not raised -- row exists even if inactive), len(body["variants"])==1
   - `test_required_variables_populated(seeded_prompts_client)`: GET /api/prompts/classify_shipment, find system variant, assert required_variables==["role", "input"]
   - `test_required_variables_fallback_in_detail(seeded_prompts_client)`: GET /api/prompts/extract_fields, assert variants[0]["required_variables"]==[] (null stored, fallback extracts none)

### Step 3: Update frontend types.ts

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. Open `llm_pipeline/ui/frontend/src/api/types.ts`
2. After `PromptListResponse` interface (line ~201), insert new `PromptDetail` interface:
   ```
   export interface PromptVariant {
     id: number
     prompt_key: string
     prompt_name: string
     prompt_type: string
     category: string | null
     step_name: string | null
     content: string
     required_variables: string[] | null
     description: string | null
     version: string
     is_active: boolean
     created_at: string
     updated_at: string
     created_by: string | null
   }

   export interface PromptDetail {
     prompt_key: string
     variants: PromptVariant[]
   }
   ```
3. Remove `@provisional` JSDoc tags from `Prompt`, `PromptListResponse`, `PromptListParams` interfaces (keep description lines, remove `@provisional - backend endpoint does not exist until task 22` lines)
4. Update comment blocks to remove "Will 404 until task 22 lands" wording

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| `extract_variables_from_content` import creates circular dependency (prompts.loader imports db.prompt, routes.prompts imports both) | Medium | Verify import chain: loader.py imports Prompt inside function body (`from llm_pipeline.db.prompt import Prompt` at line 95), not at module level -- no circular risk |
| `GET /{prompt_key}` returns variants regardless of `is_active` (no filter applied) -- could expose inactive prompts unexpectedly | Low | This is intentional: detail endpoint shows all variants for a key; list endpoint defaults is_active=True for browsing. Document in docstring. |
| `required_variables` fallback returns empty list `[]` for prompts with no `{var}` patterns -- callers may conflate null (stored) vs empty list (extracted none) | Low | Consistent: both stored `[]` and extracted `[]` mean "no variables required". Return `[]` not None in fallback case. |
| Frontend `PromptListParams` has `prompt_type` field but original frontend types.ts does not -- mismatch if frontend doesn't send it | Low | Backend accepts it as optional; frontend can add it later. No breaking change. |

## Success Criteria

- [ ] GET /api/prompts returns 200 with `{ items, total, offset, limit }` envelope
- [ ] GET /api/prompts default filters to is_active=True (inactive prompts not returned unless is_active=false passed)
- [ ] GET /api/prompts?category=X filters by category; ?step_name=X filters by step_name; ?prompt_type=X filters by type
- [ ] GET /api/prompts/{prompt_key} returns `{ prompt_key, variants: [...] }` grouped response
- [ ] GET /api/prompts/unknown_key returns 404
- [ ] required_variables returns stored value when non-null; fallback to extract_variables_from_content when null
- [ ] All new tests in tests/ui/test_prompts.py pass with pytest
- [ ] No regressions in existing tests (tests/ui/test_runs.py, test_steps.py, test_events.py)
- [ ] Frontend types.ts has PromptDetail and PromptVariant interfaces; @provisional tags removed from prompt types

## Phase Recommendation

**Risk Level:** low
**Reasoning:** Router stub is already mounted in app and test conftest. No schema changes needed. Two endpoints with standard patterns (identical to runs.py). Only risk is the extract_variables_from_content import, verified safe. All architectural decisions confirmed by CEO.
**Suggested Exclusions:** testing, review
