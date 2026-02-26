# IMPLEMENTATION - STEP 3: FONTSOURCE INSTALL
**Status:** completed

## Summary
Installed @fontsource-variable/jetbrains-mono and imported it at top of main.tsx. Added type declaration for the module.

## Files
**Created:** llm_pipeline/ui/frontend/src/fontsource.d.ts
**Modified:** llm_pipeline/ui/frontend/src/main.tsx, llm_pipeline/ui/frontend/package.json, llm_pipeline/ui/frontend/package-lock.json
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/package.json`
Added @fontsource-variable/jetbrains-mono dependency via npm install.
```
# Before
(no fontsource dependency)

# After
"@fontsource-variable/jetbrains-mono": "^5.2.8",
```

### File: `llm_pipeline/ui/frontend/src/main.tsx`
Added fontsource import as first line, before all other imports.
```
# Before
import { lazy, StrictMode, Suspense } from 'react'

# After
import '@fontsource-variable/jetbrains-mono'
import { lazy, StrictMode, Suspense } from 'react'
```

### File: `llm_pipeline/ui/frontend/src/fontsource.d.ts`
Created type declaration to resolve TS2307 for the CSS-only fontsource package.
```
# Before
(file did not exist)

# After
declare module '@fontsource-variable/jetbrains-mono'
```

## Decisions
### Type declaration file
**Choice:** Created src/fontsource.d.ts with module declaration
**Rationale:** @fontsource-variable/jetbrains-mono exports only CSS (no .d.ts). TypeScript cannot resolve the module without a declaration. vite/client types handle *.css imports but not bare package specifiers that resolve to CSS via package.json exports.

## Verification
[x] npm install succeeded (package in package.json dependencies)
[x] Import added as first line in main.tsx
[x] tsc --noEmit passes with zero errors
[x] Variable package used (full weight range)
