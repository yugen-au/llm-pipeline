# IMPLEMENTATION - STEP 2: PURE FUNCTION TESTS
**Status:** completed

## Summary
Unit tests for toSearchParams, ApiError (api/types.ts), and validateForm (components/live/InputForm.tsx). 25 tests, all passing.

## Files
**Created:** llm_pipeline/ui/frontend/src/api/types.test.ts, llm_pipeline/ui/frontend/src/components/live/validateForm.test.ts
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/api/types.test.ts`
9 tests for toSearchParams (empty obj, single param, multiple params, null omission, undefined omission, all null/undefined, number conversion, boolean conversion, special char encoding) and 6 tests for ApiError (name, status, detail, message, instanceof Error, instanceof ApiError).

### File: `llm_pipeline/ui/frontend/src/components/live/validateForm.test.ts`
10 tests for validateForm: null schema, no required fields, missing required (undefined/null/empty string), title fallback to field key, all present, multiple missing, truthy non-string values (0/false accepted), no properties in schema.

## Decisions
### validateForm test file placement
**Choice:** Separate validateForm.test.ts co-located in components/live/ rather than inside InputForm.test.tsx
**Rationale:** validateForm is a pure function export tested independently of React rendering. Keeps Step 4's InputForm.test.tsx focused on component rendering tests.

### No integer type validation tests
**Choice:** Omitted "type validation for integer with non-numeric -> error" from plan
**Rationale:** validateForm only validates required field presence (null/undefined/empty string). It does not perform type-specific validation. Tests reflect actual behavior.

## Verification
[x] npx vitest run types.test.ts validateForm.test.ts -- 25/25 passing
[x] No new dependencies added
[x] Co-located test files next to source
[x] No QueryClientProvider usage
