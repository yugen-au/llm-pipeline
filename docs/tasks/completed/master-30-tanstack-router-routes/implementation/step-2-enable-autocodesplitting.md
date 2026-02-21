# IMPLEMENTATION - STEP 2: ENABLE AUTOCODESPLITTING
**Status:** completed

## Summary
Enabled `autoCodeSplitting: true` in the TanStack Router Vite plugin config. Route components will now be automatically lazy-loaded without manual `.lazy.tsx` files.

## Files
**Created:** none
**Modified:** `llm_pipeline/ui/frontend/vite.config.ts`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/vite.config.ts`
Added `autoCodeSplitting: true` option to the `tanstackRouter()` plugin call on line 11.

```
# Before
plugins: [tanstackRouter(), react(), tailwindcss()],

# After
plugins: [tanstackRouter({ autoCodeSplitting: true }), react(), tailwindcss()],
```

## Decisions
None

## Verification
- [x] `tanstackRouter({ autoCodeSplitting: true })` present in vite.config.ts line 11
- [x] No semicolons, single quotes maintained per .prettierrc
- [x] No other lines in vite.config.ts changed
