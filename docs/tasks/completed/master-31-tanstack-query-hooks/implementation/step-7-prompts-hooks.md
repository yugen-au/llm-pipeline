# IMPLEMENTATION - STEP 7: PROMPTS HOOKS
**Status:** completed

## Summary
Created `src/api/prompts.ts` with a `usePrompts` hook targeting the provisional `/api/prompts` endpoint (task 22). Uses default 30s staleTime since prompts are static reference data. Follows the same pattern as `events.ts` for URLSearchParams building.

## Files
**Created:** `llm_pipeline/ui/frontend/src/api/prompts.ts`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/api/prompts.ts`
New file. Exports `usePrompts(filters)` hook with file-level TSDoc noting 404 until task 22 lands. Imports from `./client`, `./query-keys`, `./types`. Includes `buildPromptParams` helper that omits undefined/null filter values before serializing to URLSearchParams.

## Decisions
### No staleTime override
**Choice:** Use global 30s default from QueryClient config
**Rationale:** Prompts are static reference data per PLAN.md -- no polling or custom staleTime needed

### Followed events.ts pattern for URLSearchParams
**Choice:** Extracted `buildPromptParams` helper matching `buildEventParams` in events.ts
**Rationale:** Consistent pattern across hook files; filters out null/undefined values before serialization

## Verification
[x] TypeScript compilation passes (`npx tsc --noEmit` - no errors)
[x] No semicolons, single quotes throughout
[x] File-level TSDoc with @remarks about 404 until task 22
[x] Imports use `import type` for type-only imports per verbatimModuleSyntax
[x] Hook exported for task 39 (Prompt Browser) consumption
[x] Uses queryKeys.prompts.list(filters) from query-keys.ts

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] URLSearchParams dedup: replace local `buildPromptParams` with shared `toSearchParams` from `./types`

### Changes Made
No changes needed -- the Step 1 agent already refactored `prompts.ts` to import `toSearchParams` from `./types` (line 11) and removed the local `buildPromptParams` helper. The file currently has no local params builder function.

### Verification
[x] `prompts.ts` imports `toSearchParams` from `./types` (line 11)
[x] No local `buildPromptParams` or equivalent function exists in `prompts.ts`
[x] `toSearchParams` used correctly on line 29: `'/prompts' + toSearchParams(filters)`
[x] TypeScript compilation passes (`npx tsc --noEmit` - no errors)
