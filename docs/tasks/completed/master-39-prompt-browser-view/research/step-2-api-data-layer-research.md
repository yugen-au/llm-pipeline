# Step 2: API & Data Layer Research -- Prompt Browser View

## 1. Prompt Data Model

**File:** `llm_pipeline/db/prompt.py`

```
Prompt (SQLModel, table="prompts")
  id:                 int (PK)
  prompt_key:         str (max 100, indexed)
  prompt_name:        str (max 200)
  prompt_type:        str (max 50)         -- "system" | "user"
  category:           str? (max 50)        -- organizational grouping
  step_name:          str? (max 50)        -- associated pipeline step
  content:            str                  -- template text with {variable} placeholders
  required_variables: List[str]? (JSON)    -- auto-extracted or stored variable names
  description:        str?
  version:            str (default "1.0")
  is_active:          bool (default True)
  created_at:         datetime (UTC)
  updated_at:         datetime (UTC)
  created_by:         str? (max 100)

Constraints:
  UniqueConstraint('prompt_key', 'prompt_type')  -- key+type is unique
  Index("ix_prompts_category_step", "category", "step_name")
  Index("ix_prompts_active", "is_active")
```

## 2. Backend API Endpoints

### 2.1 Prompts Routes (`/api/prompts`)

**File:** `llm_pipeline/ui/routes/prompts.py`

| Method | Path | Response Model | Description |
|--------|------|---------------|-------------|
| GET | `/api/prompts` | `PromptListResponse` | Paginated list with filters |
| GET | `/api/prompts/{prompt_key}` | `PromptDetailResponse` | Grouped detail showing all variants |

**GET /api/prompts query params (PromptListParams):**
- `category: str?` -- filter by category
- `step_name: str?` -- filter by step name
- `prompt_type: str?` -- filter by type ("system"/"user")
- `is_active: bool? = True` -- filter active/inactive
- `offset: int = 0` -- pagination offset
- `limit: int = 50` (max 200) -- page size

**PromptListResponse shape:**
```json
{
  "items": [PromptItem...],
  "total": 42,
  "offset": 0,
  "limit": 50
}
```

**GET /api/prompts/{prompt_key} -- PromptDetailResponse:**
Returns all variants (system/user) for a key regardless of is_active. Groups by prompt_key.
```json
{
  "prompt_key": "step_name.system_instruction",
  "variants": [PromptItem...]
}
```

### 2.2 Pipeline Step Prompts (related)

**File:** `llm_pipeline/ui/routes/pipelines.py`

| Method | Path | Response Model | Description |
|--------|------|---------------|-------------|
| GET | `/api/pipelines/{name}/steps/{step_name}/prompts` | `StepPromptsResponse` | Prompts for a specific pipeline step |

This endpoint uses introspection to find declared prompt keys for a step within a specific pipeline, preventing cross-pipeline leakage. Returns `StepPromptItem[]` with prompt_key, prompt_type, content, required_variables, version.

## 3. Frontend API Layer (from task 31)

### 3.1 Existing Hooks

**File:** `llm_pipeline/ui/frontend/src/api/prompts.ts`
- `usePrompts(filters)` -- calls GET /api/prompts with PromptListParams
- NO `usePromptDetail` hook exists yet

**File:** `llm_pipeline/ui/frontend/src/api/pipelines.ts`
- `useStepInstructions(pipelineName, stepName)` -- calls step-level prompts endpoint

### 3.2 Existing TypeScript Types

**File:** `llm_pipeline/ui/frontend/src/api/types.ts`

All types fully defined:
- `Prompt` -- mirrors DB model fields
- `PromptListResponse` -- { items, total, offset, limit }
- `PromptVariant` -- identical to Prompt (system/user variant)
- `PromptDetail` -- { prompt_key, variants: PromptVariant[] }
- `PromptListParams` -- { prompt_type?, category?, step_name?, is_active?, offset?, limit? }

### 3.3 Query Keys

**File:** `llm_pipeline/ui/frontend/src/api/query-keys.ts`
- `queryKeys.prompts.all` -- `['prompts']`
- `queryKeys.prompts.list(filters)` -- `['prompts', filters]`
- NO `queryKeys.prompts.detail(key)` factory exists

### 3.4 API Client

**File:** `llm_pipeline/ui/frontend/src/api/client.ts`
- `apiClient<T>(path, options?)` -- prefixes `/api`, throws `ApiError` on non-OK

## 4. Prompt-Pipeline Relationship

Prompts relate to pipelines indirectly:
```
Pipeline (introspection_registry)
  -> Strategy
    -> Step (has system_key, user_key)
      -> Prompt (DB, matched by prompt_key)
```

- `PipelineStepState` stores `prompt_system_key`, `prompt_user_key`, `prompt_version` per executed step
- Pipeline introspection metadata exposes `system_key` and `user_key` per step definition
- Prompt DB model has `step_name` and `category` but NO `pipeline_name` field

## 5. Prompt Loading & Variable Extraction

**File:** `llm_pipeline/prompts/loader.py`
- `extract_variables_from_content(content)` -- regex `\{([a-zA-Z_][a-zA-Z0-9_]*)\}`, returns unique ordered list
- `sync_prompts(bind, prompts_dir, force)` -- YAML-to-DB sync (insert/update/skip by version)
- YAML format requires: prompt_key, name, type, category, step, version, content

**File:** `llm_pipeline/prompts/service.py`
- `PromptService` -- runtime service for retrieving and formatting prompts
- `get_system_prompt(key, variables)` / `get_user_prompt(key, variables)` -- template rendering via `str.format(**variables)`

**File:** `llm_pipeline/prompts/variables.py`
- `VariableResolver` protocol -- host projects implement to provide variable class resolution

## 6. Backend Architecture Patterns

All API routes follow consistent patterns:
- **Router pattern:** `APIRouter(prefix="/...", tags=["..."])`, mounted in `app.py` under `/api`
- **DB access:** `DBSession` (Annotated ReadOnlySession via Depends) -- prevents writes from API layer
- **Response models:** Plain Pydantic BaseModel (not SQLModel) for API responses
- **Query params:** Pydantic BaseModel with `Query()` defaults, injected via `Annotated[..., Depends()]`
- **Pagination:** Offset-based with total count, consistent `{ items, total, offset, limit }` shape
- **Filtering:** `_apply_filters(stmt, params)` helper appends `.where()` for non-None params
- **Sync endpoints:** All `def` (not async) -- SQLite is sync, FastAPI wraps in threadpool

## 7. Gaps for Prompt Browser Implementation

### Must Create (frontend)
1. **`usePromptDetail(promptKey)` hook** -- GET /api/prompts/{prompt_key}, enabled when key truthy
2. **`queryKeys.prompts.detail(key)` factory** -- e.g. `['prompts', key]`

### Existing & Sufficient (no changes needed)
- Backend GET /api/prompts (list with filters) -- fully functional
- Backend GET /api/prompts/{prompt_key} (detail with variants) -- fully functional
- All TypeScript types (Prompt, PromptDetail, PromptListParams, etc.) -- fully defined
- `usePrompts(filters)` hook -- already works
- Variable extraction logic -- available server-side; client can also regex `{var}` for highlighting

### Design Note: "Pipeline" Filter
Task 39 description references filtering by "pipeline" but the Prompt model has no `pipeline_name` field. Options for implementation:
- **Option A:** Use `category` filter as pipeline proxy (if categories map to pipeline names)
- **Option B:** Use `step_name` filter (prompts are associated with steps)
- **Option C:** Fetch pipeline introspection data to get prompt keys, then filter client-side
- **Recommendation:** Use `category` as the primary grouping/filter, supplemented by `step_name`. The pipeline introspection endpoint can provide category-to-pipeline mapping if needed. No backend changes required.
