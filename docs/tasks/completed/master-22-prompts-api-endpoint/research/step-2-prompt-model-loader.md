# Research Step 2: Prompt Model & Loader

## Prompt SQLModel (`llm_pipeline/db/prompt.py`)

### Table: `prompts`

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | `int` | PK, auto-increment | - |
| `prompt_key` | `str(100)` | indexed | Lookup key (e.g. `classify_line_items`, `classify_line_items.dhl`) |
| `prompt_name` | `str(200)` | required | Human-readable name |
| `prompt_type` | `str(50)` | required | `system` or `user` |
| `category` | `str(50)` | optional, composite index w/ step_name | Organizational grouping |
| `step_name` | `str(50)` | optional, composite index w/ category | Pipeline step association |
| `content` | `str` (text) | required | Template text with `{variable}` placeholders |
| `required_variables` | `JSON (List[str])` | optional | Auto-extracted from content during sync |
| `description` | `str` | optional | - |
| `version` | `str(20)` | default `"1.0"` | Semantic version for sync comparisons |
| `is_active` | `bool` | default `True`, indexed | Soft-delete flag |
| `created_at` | `datetime` | auto UTC | - |
| `updated_at` | `datetime` | auto UTC | - |
| `created_by` | `str(100)` | optional | - |

### Constraints & Indexes

- **UniqueConstraint**: `(prompt_key, prompt_type)` -- a key can have both system and user variants
- **Index**: `(category, step_name)` -- composite for organizational queries
- **Index**: `(is_active)` -- for filtering active prompts
- **Index**: `(prompt_key)` -- field-level index

### CRITICAL: No `pipeline_name` Field

Task 22 specifies filtering by `pipeline_name`, but the Prompt model has **no such field**. The closest organizational fields are:
- `category` -- general grouping (e.g. step category)
- `step_name` -- associates prompt with a pipeline step

This is a **schema mismatch** between the task spec and the actual model.

---

## Prompt Loader (`llm_pipeline/prompts/loader.py`)

### `extract_variables_from_content(content: str) -> List[str]`

- Regex: `r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}'`
- Returns unique variable names, preserving first-occurrence order
- Exported in `__all__`
- Import path: `from llm_pipeline.prompts.loader import extract_variables_from_content`

### `sync_prompts(bind, prompts_dir, force) -> Dict[str, int]`

- Loads YAML files from `prompts_dir` (env `PROMPTS_DIR` or `./prompts`)
- Inserts new prompts, updates if version increased (or force=True)
- **Auto-populates `required_variables`** from content during sync
- YAML required fields: `prompt_key`, `name`, `type`, `category`, `step`, `version`, `content`

### `load_prompt(yaml_path) -> Dict[str, Any]`

- Loads single YAML file, validates required fields
- YAML field `name` maps to DB `prompt_name`, `step` maps to `step_name`, `type` maps to `prompt_type`

---

## PromptService (`llm_pipeline/prompts/service.py`)

Existing service class used by pipeline internals:

### Key Methods

| Method | Filters | Returns |
|--------|---------|---------|
| `get_prompt(key, type, context)` | `prompt_key`, `prompt_type`, `is_active=True` | `str` (content) |
| `get_system_prompt(key, variables)` | system type | formatted content |
| `get_user_prompt(key, variables)` | user type | formatted content |
| `prompt_exists(key)` | `prompt_key`, `is_active=True` | `bool` |

### Query Patterns

All existing queries consistently filter by `is_active == True`. Example from `strategy.py`:
```python
select(Prompt).where(
    Prompt.prompt_key == strategy_key,
    Prompt.prompt_type == 'system',
    Prompt.is_active == True
)
```

---

## Variable Extraction: Stored vs Runtime

The `required_variables` JSON field is populated during `sync_prompts()`. Two options for API:

1. **Use stored `required_variables`** -- fast, no regex at query time; stale if DB edited outside sync
2. **Re-extract via `extract_variables_from_content()`** -- always fresh; minor compute cost per row

Recommendation: Use stored `required_variables` when present, fall back to `extract_variables_from_content(content)` if null. This covers both synced prompts and manually-inserted rows.

---

## Existing Usage Patterns in Codebase

### Prompt Resolution Order (from `strategy.py`)

1. Strategy-level: `prompt_key = "{step_name}.{strategy_name}"` + `prompt_type` + `is_active`
2. Step-level fallback: `prompt_key = "{step_name}"` + `prompt_type` + `is_active`

### Prompt Key Conventions

- Simple: `classify_line_items`
- Strategy-scoped: `classify_line_items.dhl`
- System instruction: `classify_line_items.system_instruction`
- Guidance: `classify_line_items.guidance.{table_type}`

---

## Implications for API Endpoints

### GET /prompts (list)

- Filter by `prompt_type` -- direct field match, no issues
- Filter by `pipeline_name` -- **NO corresponding field** (see question below)
- Default: `is_active == True` (consistent with all existing queries)
- Response should include: `prompt_key`, `prompt_type`, `prompt_name`, `content` (or truncated), `required_variables`, `category`, `step_name`, `version`, `is_active`

### GET /prompts/{prompt_key} (detail)

- Query by `prompt_key` with no `prompt_type` filter to get both system and user variants
- Return full content with extracted variables
- 404 if no matching prompts found

### Pagination

- Runs/events routes use offset+limit pagination
- Prompt table likely has far fewer rows (tens to low hundreds), so pagination may be optional but should follow convention
