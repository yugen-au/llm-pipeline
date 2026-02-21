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
