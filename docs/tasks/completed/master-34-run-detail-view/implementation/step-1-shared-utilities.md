# IMPLEMENTATION - STEP 1: SHARED UTILITIES
**Status:** completed

## Summary
Extracted formatDuration to shared time.ts utility, extended StatusBadge with step-specific statuses (skipped, pending), updated RunsTable to import from shared utility, fixed RunsTable test mock.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/src/lib/time.ts, llm_pipeline/ui/frontend/src/lib/time.test.ts, llm_pipeline/ui/frontend/src/components/runs/RunsTable.tsx, llm_pipeline/ui/frontend/src/components/runs/RunsTable.test.tsx, llm_pipeline/ui/frontend/src/components/runs/StatusBadge.tsx
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/lib/time.ts`
Added exported formatDuration function at end of file.
```
# Before
(no formatDuration)

# After
export function formatDuration(ms: number | null): string {
  if (ms == null) return '\u2014'
  return `${(ms / 1000).toFixed(1)}s`
}
```

### File: `llm_pipeline/ui/frontend/src/lib/time.test.ts`
Added formatDuration describe block with 4 test cases: null, 0, 1500, 60000.

### File: `llm_pipeline/ui/frontend/src/components/runs/RunsTable.tsx`
Removed private formatDuration function, added formatDuration to import from @/lib/time.

### File: `llm_pipeline/ui/frontend/src/components/runs/RunsTable.test.tsx`
Updated @/lib/time mock to use importOriginal pattern so formatDuration uses real implementation while formatRelative/formatAbsolute remain mocked.

### File: `llm_pipeline/ui/frontend/src/components/runs/StatusBadge.tsx`
Changed statusConfig type from Record<RunStatus, BadgeConfig> to Record<string, BadgeConfig>. Added skipped and pending entries (secondary variant, text-muted-foreground). Removed unnecessary `as RunStatus` cast on config lookup.

## Decisions
### RunsTable test mock strategy
**Choice:** Use importOriginal to pass through formatDuration while keeping formatRelative/formatAbsolute mocked
**Rationale:** formatDuration is pure (no time dependency), so real implementation works in tests. Existing duration assertion ('1.5s') validates the real function.

## Verification
[x] time.test.ts: 24 tests pass (including 4 new formatDuration tests)
[x] RunsTable.test.tsx: 12 tests pass
[x] StatusBadge.test.tsx: 5 tests pass
[x] TypeScript compiles with no errors
[x] All 35 runs component tests pass
