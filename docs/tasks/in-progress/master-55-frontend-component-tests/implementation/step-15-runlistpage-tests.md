# IMPLEMENTATION - STEP 15: RUNLISTPAGE TESTS
**Status:** completed

## Summary
Integration-style tests for RunListPage route component covering heading render, loading/error/data states, status filter navigation, and pagination navigation.

## Files
**Created:** `llm_pipeline/ui/frontend/src/routes/index.test.tsx`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/routes/index.test.tsx`
New test file with 6 tests for RunListPage:
- `renders "Pipeline Runs" heading`
- `shows loading skeleton when useRuns isLoading=true`
- `shows error state when useRuns isError=true`
- `renders runs table when data present` (2 RunListItem fixtures, asserts pipeline names + truncated IDs)
- `calls navigate on status filter change` (interacts with FilterBar select, verifies search fn output)
- `calls navigate on pagination change` (clicks Next, verifies search fn increments page)

## Decisions
### Mock strategy for Route.useSearch
**Choice:** Mock `createFileRoute` from `@tanstack/react-router` to return a builder that spreads options and attaches `useSearch` mock. Extract component via `Route.component`.
**Rationale:** `Route` is created by `createFileRoute('/')({...})` in the source. Mocking the factory lets us control `useSearch` while preserving the component reference. `vi.hoisted()` required for mock fns referenced inside `vi.mock` factories (Vitest hoisting).

### Zod adapter mock
**Choice:** Mock `@tanstack/zod-adapter` with stub `fallback` and `zodValidator` to avoid runtime dependency on zod schema validation during test collection.
**Rationale:** The route module calls `fallback()` and `zodValidator()` at module scope. Without mocking, test collection fails.

### Time utils mock
**Choice:** Mock `@/lib/time` with deterministic stubs matching RunsTable.test.tsx pattern.
**Rationale:** RunsTable (child component) calls formatRelative/formatAbsolute/formatDuration. Deterministic stubs prevent flaky time-dependent output.

## Verification
[x] All 6 RunListPage tests pass
[x] Full suite (206 tests across 25 files) passes with no regressions
[x] Test file co-located at `src/routes/index.test.tsx`
[x] Uses established vi.mock() pattern consistent with codebase
