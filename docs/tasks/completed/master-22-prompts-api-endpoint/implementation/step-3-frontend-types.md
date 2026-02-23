# IMPLEMENTATION - STEP 3: FRONTEND TYPES
**Status:** completed

## Summary
Updated frontend TypeScript types to add PromptVariant/PromptDetail interfaces and removed all @provisional tags from prompt types now that backend endpoints are implemented.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/src/api/types.ts
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/api/types.ts`

**1. File header comment** -- removed prompts from provisional list (only pipelines remain provisional).

```
# Before
 * llm_pipeline/ui/routes/. Provisional types (prompts, pipelines)
 * are typed against existing DB/introspection models but their
 * endpoints do not exist yet (tasks 22, 24).

# After
 * llm_pipeline/ui/routes/. Provisional types (pipelines) are typed
 * against existing DB/introspection models but their endpoints do
 * not exist yet (task 24).
```

**2. Prompts section header** -- removed `@provisional` annotation.

```
# Before
// Prompts (@provisional - endpoints do not exist until task 22)

# After
// Prompts
```

**3. Prompt interface JSDoc** -- removed @provisional tag, "Will 404 until task 22 lands" wording, "Shape may change" warning.

```
# Before
/**
 * Prompt entity matching llm_pipeline/db/prompt.py SQLModel fields.
 *
 * @provisional - backend endpoint (GET /api/prompts) does not exist yet.
 * Will 404 until task 22 lands. Shape may change; update this type first.
 */

# After
/** Prompt entity matching llm_pipeline/db/prompt.py SQLModel fields. */
```

**4. PromptListResponse JSDoc** -- replaced @provisional with proper endpoint reference.

```
# Before
/**
 * @provisional - backend endpoint does not exist until task 22.
 */

# After
/** GET /api/prompts response body. */
```

**5. PromptListParams JSDoc** -- replaced @provisional with standard query params doc.

```
# Before
/**
 * Query params for GET /api/prompts (anticipated shape).
 *
 * @provisional - backend endpoint does not exist until task 22.
 */

# After
/** Query params for GET /api/prompts. All fields optional for partial filtering. */
```

**6. Added PromptVariant interface** (after PromptListResponse, line ~196) -- mirrors PromptItem/PromptVariant response model from backend prompts.py.

Fields: id, prompt_key, prompt_name, prompt_type, category, step_name, content, required_variables, description, version, is_active, created_at, updated_at, created_by.

**7. Added PromptDetail interface** (after PromptVariant, line ~214) -- mirrors PromptDetailResponse from backend. Grouped wrapper: `{ prompt_key: string, variants: PromptVariant[] }`.

## Decisions
None -- all decisions were pre-specified in the plan (Step 3). Interface shapes match backend response models exactly.

## Verification
[x] PromptVariant fields match PromptItem/PromptVariant response model in prompts.py
[x] PromptDetail fields match PromptDetailResponse in prompts.py
[x] All @provisional tags removed from Prompt, PromptListResponse, PromptListParams
[x] "Will 404 until task 22 lands" wording removed
[x] File header updated to exclude prompts from provisional list
[x] Existing Prompt interface unchanged (fields intact)
[x] Pipeline @provisional tags left untouched (task 24 not yet done)
