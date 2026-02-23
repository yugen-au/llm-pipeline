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

## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
[x] (LOW) formatRelative rounding edge case - Math.round can produce unexpected values at unit boundaries; replaced with Math.floor truncation toward zero
[x] (LOW) Hardcoded 'en' locale - both functions now accept optional `locale` parameter defaulting to 'en'; cached singletons reused for default locale, new instances created for non-default

### Changes Made
#### File: `llm_pipeline/ui/frontend/src/lib/time.ts`
Replaced Math.round with Math.floor for ms-to-seconds and unit division. Added optional `locale` parameter to both exports. Introduced `getRtf`/`getDtf` helper functions that return cached singleton for default 'en' locale or create new instance for other locales.
```
# Before
const diffSeconds = Math.round((then - now) / 1_000)
const value = Math.round(diffSeconds / threshold)
export function formatRelative(isoString: string): string
export function formatAbsolute(isoString: string): string

# After
const diffSeconds = Math.floor((then - now) / 1_000)
const value = diffSeconds >= 0
  ? Math.floor(diffSeconds / threshold)
  : -Math.floor(abs / threshold)
export function formatRelative(isoString: string, locale: string = 'en'): string
export function formatAbsolute(isoString: string, locale: string = 'en'): string
```

#### File: `llm_pipeline/ui/frontend/src/lib/time.test.ts`
Added 6 new tests (14 -> 20 total): boundary truncation for past (90s -> "1 minute ago") and future (90s -> "in 1 minute"), default locale equivalence for both functions, non-default locale ('de') for both functions.
```
# Before
12 formatRelative tests, 2 formatAbsolute tests

# After
16 formatRelative tests (+truncation boundary x2, +default locale, +de locale)
4 formatAbsolute tests (+default locale equivalence, +de locale)
```

### Verification
[x] `npx vitest run src/lib/time.test.ts` passes all 20 tests
[x] 90s boundary correctly truncates to "1 minute ago" (not "2 minutes ago")
[x] 90s future boundary correctly truncates to "in 1 minute"
[x] Default locale (no arg) produces same output as explicit 'en'
[x] German locale ('de') produces non-English output
