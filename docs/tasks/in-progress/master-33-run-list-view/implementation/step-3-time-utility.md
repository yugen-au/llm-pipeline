# IMPLEMENTATION - STEP 3: TIME UTILITY
**Status:** completed

## Summary
Created time formatting utility with `formatRelative` and `formatAbsolute` functions using native `Intl` APIs. Includes 14 unit tests covering all boundary conditions, future dates, and timezone-safe absolute format checks.

## Files
**Created:** `llm_pipeline/ui/frontend/src/lib/time.ts`, `llm_pipeline/ui/frontend/src/lib/time.test.ts`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/lib/time.ts`
New file. Exports `formatRelative(isoString)` and `formatAbsolute(isoString)`.
- `formatRelative` computes elapsed seconds between now and the given ISO timestamp, picks the largest time unit (day/hour/minute/second) where abs value >= 1, formats via `Intl.RelativeTimeFormat`.
- `formatAbsolute` formats via `Intl.DateTimeFormat('en', { dateStyle: 'medium', timeStyle: 'short' })`.

### File: `llm_pipeline/ui/frontend/src/lib/time.test.ts`
New file. 14 tests across two describe blocks:
- `formatRelative`: 0s (now), 30s, 59s, 1min, 5min, 1hr, 3hr, 23hr, 1day (yesterday), 5days, future 5min, future 2hr.
- `formatAbsolute`: structure/format checks using regex to avoid timezone sensitivity.

## Decisions
### Timezone-safe test assertions
**Choice:** Assert formatAbsolute output with regex patterns (`/Feb \d{1,2}, 2026/`) instead of exact day numbers.
**Rationale:** `Intl.DateTimeFormat` uses local timezone, so UTC input "Feb 23 14:30" can render as "Feb 24" in UTC+11. Regex matching avoids flaky tests across timezones.

### Module-level Intl instances
**Choice:** Instantiate `Intl.RelativeTimeFormat` and `Intl.DateTimeFormat` at module scope (singletons).
**Rationale:** Avoids re-creating formatters on every call. These are stateless and safe to reuse.

### Rounding with Math.round
**Choice:** Use `Math.round` for both the elapsed seconds and the unit division.
**Rationale:** Provides natural rounding ("59.5 seconds ago" becomes "1 minute ago" via the minute threshold). Matches user expectations for approximate relative times.

## Verification
[x] `npx vitest run src/lib/time.test.ts` passes all 14 tests
[x] `npx vitest run src/test/smoke.test.ts src/lib/time.test.ts` passes all 16 tests
[x] formatRelative handles seconds/minutes/hours/days boundaries
[x] formatRelative handles future dates gracefully
[x] formatAbsolute returns locale-formatted date+time string
[x] No external date library used - native Intl APIs only
