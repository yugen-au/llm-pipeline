# IMPLEMENTATION - STEP 3: UPDATE MAIN.TSX THEME
**Status:** completed

## Summary
Removed hardcoded `document.documentElement.classList.add('dark')` from main.tsx and replaced it with a side-effect import of the ui store module (`import '@/stores/ui'`). The store's `onRehydrateStorage` callback now handles theme class application from persisted localStorage before first render.

## Files
**Created:** none
**Modified:** `llm_pipeline/ui/frontend/src/main.tsx`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/main.tsx`
Removed hardcoded dark theme class; added side-effect import of ui store for theme hydration.

```
# Before
import './index.css'

const ReactQueryDevtools = import.meta.env.DEV
...
document.documentElement.classList.add('dark')

createRoot(document.getElementById('root')!).render(

# After
import './index.css'
import '@/stores/ui'

const ReactQueryDevtools = import.meta.env.DEV
...
createRoot(document.getElementById('root')!).render(
```

## Decisions
### Side-effect import vs named import
**Choice:** `import '@/stores/ui'` (bare side-effect import) instead of `import { useUIStore } from '@/stores/ui'`
**Rationale:** main.tsx doesn't use any exports from the store -- it only needs the module to execute so `create()` runs and `onRehydrateStorage` fires. A bare import avoids an unused-import lint warning and communicates intent clearly.

## Verification
[x] `document.documentElement.classList.add('dark')` line removed from main.tsx
[x] `import '@/stores/ui'` present at top of main.tsx (after CSS import)
[x] `tsc -b --noEmit` passes with no type errors
[x] No other changes to main.tsx
