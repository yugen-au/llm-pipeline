# IMPLEMENTATION - STEP 4: STATUSBADGE COMPONENT
**Status:** completed

## Summary
Created StatusBadge component that color-codes pipeline run statuses using shadcn Badge. Three known statuses (running, completed, failed) map to distinct visual treatments; unknown statuses fall back to secondary/gray.

## Files
**Created:** `llm_pipeline/ui/frontend/src/components/runs/StatusBadge.tsx`, `llm_pipeline/ui/frontend/src/components/runs/StatusBadge.test.tsx`
**Modified:** `llm_pipeline/ui/frontend/package.json` (added @testing-library/dom peer dep)
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/runs/StatusBadge.tsx`
New component. Uses a `statusConfig` lookup map keyed by status string. Each entry specifies a Badge `variant` and optional `className` overrides via `cn()`.

- `running` -> `outline` variant + `border-amber-500 text-amber-600 dark:text-amber-400`
- `completed` -> `outline` variant + `border-green-500 text-green-600 dark:text-green-400`
- `failed` -> `destructive` variant (built-in red styling, no overrides needed)
- fallback -> `secondary` variant, label = raw status string

### File: `llm_pipeline/ui/frontend/src/components/runs/StatusBadge.test.tsx`
5 tests covering:
1. Running status renders with amber outline classes
2. Completed status renders with green outline classes
3. Failed status uses destructive variant (checked via `data-variant`)
4. Unknown status falls back to secondary variant
5. All three known statuses display their raw string as label text

### File: `llm_pipeline/ui/frontend/package.json`
Added `@testing-library/dom` as devDependency -- missing peer dep of `@testing-library/react` that caused test runner failure.

## Decisions
### Badge variant strategy for running/completed
**Choice:** Use `outline` variant + Tailwind color class overrides via `cn()`
**Rationale:** shadcn Badge only ships default/secondary/destructive/outline/ghost/link variants. No built-in amber or green. Using `outline` as base provides the border styling, then color overrides via Tailwind classes for text and border color. Includes dark mode variants.

### Failed status uses built-in destructive
**Choice:** Use `destructive` variant directly with no className overrides
**Rationale:** destructive is already red-styled in the shadcn theme (bg-destructive text-white). No need for custom classes.

### @testing-library/dom installation
**Choice:** Added as devDependency
**Rationale:** Required peer dependency of @testing-library/react that was missing from step 1 install. Tests fail without it.

## Verification
[x] StatusBadge renders correct text for running, completed, failed
[x] StatusBadge renders fallback for unknown status
[x] CSS classes applied correctly for each status
[x] All 5 tests pass via `npx vitest run`
[x] Component uses Badge from @/components/ui/badge (step 2 output)
[x] Component uses cn() from @/lib/utils

## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
[x] (MEDIUM) Status type looseness -- StatusBadge accepts `status: string` but `RunStatus` union type exists. No compile-time protection for known statuses.

### Changes Made
#### File: `llm_pipeline/ui/frontend/src/components/runs/StatusBadge.tsx`
Imported `RunStatus` from `@/api/types`. Changed `statusConfig` key type from `Record<string, ...>` to `Record<RunStatus, ...>` so adding/removing backend statuses forces a compile error if the config map is out of sync. Changed prop type to `RunStatus | (string & {})` -- known statuses get autocomplete and compile-time checking, unknown strings still render via the fallback path. Lookup uses `as RunStatus` cast with `as BadgeConfig | undefined` to preserve the runtime fallback for unknown values.

```
# Before
status: string
statusConfig: Record<string, { variant: ...; className: string }>
const config = statusConfig[status]

# After
status: RunStatus | (string & {})
statusConfig: Record<RunStatus, BadgeConfig>
const config = statusConfig[status as RunStatus] as BadgeConfig | undefined
```

### Verification
[x] All 5 StatusBadge tests pass
[x] `tsc -b --noEmit` clean (no type errors)
[x] Unknown status fallback still works at runtime (tested via "unknown-state" test case)
[x] Known statuses get IDE autocomplete from RunStatus union
