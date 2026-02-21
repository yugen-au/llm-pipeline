# IMPLEMENTATION - STEP 4: INDEX SEARCH PARAMS
**Status:** completed

## Summary
Added Zod search param validation to index.tsx with page/status schema using zodValidator from @tanstack/zod-adapter.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/src/routes/index.tsx
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/routes/index.tsx`
Added zod imports, defined runListSearchSchema with page (int, min 1, fallback 1) and status (string, fallback ''), wired validateSearch, added Route.useSearch() placeholder.

```
# Before
import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/')({
  component: IndexPage,
})

function IndexPage() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-muted-foreground">llm-pipeline ui</p>
    </div>
  )
}

# After
import { createFileRoute } from '@tanstack/react-router'
import { fallback, zodValidator } from '@tanstack/zod-adapter'
import { z } from 'zod'

const runListSearchSchema = z.object({
  page: fallback(z.number().int().min(1), 1).optional(),
  status: fallback(z.string(), '').optional(),
})

export const Route = createFileRoute('/')({
  validateSearch: zodValidator(runListSearchSchema),
  component: IndexPage,
})

function IndexPage() {
  const search = Route.useSearch()

  return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-muted-foreground">llm-pipeline ui</p>
    </div>
  )
}
```

## Decisions
### Schema shape matches plan exactly
**Choice:** Used `fallback(z.number().int().min(1), 1).optional()` and `fallback(z.string(), '').optional()` as specified in PLAN.md
**Rationale:** Plan explicitly defines this shape. Context7 docs show `.default()` as alternative but plan takes precedence. Task 31+ will refine schema when API shapes are known.

### Route.useSearch() as placeholder
**Choice:** Added `const search = Route.useSearch()` without destructuring or usage
**Rationale:** Plan says "add as placeholder"; task 31 will consume the search values when implementing the run list API hook.

## Verification
[x] File uses no semicolons
[x] File uses single quotes
[x] Named function component (IndexPage)
[x] Imports: z from 'zod', fallback and zodValidator from '@tanstack/zod-adapter'
[x] Schema defined as runListSearchSchema with page and status fields
[x] validateSearch wired to zodValidator(runListSearchSchema)
[x] Route.useSearch() called in component
[x] Existing component body preserved

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] `fallback().optional()` changed to `fallback().default()` for consistency with `$runId.tsx` and Context7 docs
[x] `min-h-screen` replaced with `min-h-full` since root layout uses `h-screen` with `overflow-auto` on `<main>`

### Changes Made
#### File: `llm_pipeline/ui/frontend/src/routes/index.tsx`
Two fixes applied: schema uses `.default()` instead of `.optional()`, container uses `min-h-full` instead of `min-h-screen`.

```
# Before
  page: fallback(z.number().int().min(1), 1).optional(),
  status: fallback(z.string(), '').optional(),
...
    <div className="flex min-h-screen items-center justify-center">

# After
  page: fallback(z.number().int().min(1), 1).default(1),
  status: fallback(z.string(), '').default(''),
...
    <div className="flex min-h-full items-center justify-center">
```

### Verification
[x] Schema uses `.default()` pattern matching Context7 docs and `$runId.tsx`
[x] Container uses `min-h-full` compatible with root layout overflow model
[x] Route.useSearch() placeholder re-added (was missing)
[x] No semicolons, single quotes, named function preserved

## Review Fix Iteration 1
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] Removed unused `const search = Route.useSearch()` that caused TS6133 (declared but never used)

### Changes Made
#### File: `llm_pipeline/ui/frontend/src/routes/index.tsx`
Removed placeholder `Route.useSearch()` call. Task 31 will add actual usage when building run list UI.

```
# Before
function IndexPage() {
  const search = Route.useSearch()

  return (

# After
function IndexPage() {
  return (
```

### Verification
[x] `npx tsc --noEmit` passes with no errors
[x] No unused variables remain
