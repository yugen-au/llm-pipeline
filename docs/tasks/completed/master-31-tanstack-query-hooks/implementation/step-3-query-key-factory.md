# IMPLEMENTATION - STEP 3: QUERY KEY FACTORY
**Status:** completed

## Summary
Created centralized query key factory with hierarchical keys for targeted cache invalidation, plus isTerminalStatus helper for dynamic staleTime in downstream hooks.

## Files
**Created:** `llm_pipeline/ui/frontend/src/api/query-keys.ts`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/api/query-keys.ts`
New file. Exports `queryKeys` const object with nested factory functions per resource (runs, prompts, pipelines) and `isTerminalStatus` helper.

```typescript
// queryKeys structure:
// runs: all, list(filters), detail(runId), context(runId), steps(runId), step(runId, stepNumber), events(runId, filters)
// prompts: all, list(filters)
// pipelines: all, detail(name)

// isTerminalStatus returns true for 'completed' | 'failed'
```

## Decisions
### Type-only import for types.ts dependency
**Choice:** Used `import type` for RunListParams, EventListParams, PromptListParams, RunStatus
**Rationale:** `verbatimModuleSyntax: true` in tsconfig requires type-only imports. Since Step 1 (types.ts) runs in parallel (Group A), using `import type` ensures the import is erased at compile time and creates no runtime dependency ordering issue.

### Outer `as const` on queryKeys object
**Choice:** Applied `as const` both on individual return tuples and on the outer object
**Rationale:** Outer `as const` ensures the `all` properties (which are not functions) get readonly tuple types. Inner `as const` on function returns ensures factory function return types are narrow tuples, not `string[]`.

## Verification
[x] All 12 factory entries from PLAN.md Step 3 implemented
[x] isTerminalStatus helper exported with correct logic
[x] No semicolons, single quotes throughout (Prettier config)
[x] `import type` used for all type imports (verbatimModuleSyntax compliance)
[x] All factory functions return `as const` tuples
[x] Hierarchical key structure enables prefix-based invalidation
