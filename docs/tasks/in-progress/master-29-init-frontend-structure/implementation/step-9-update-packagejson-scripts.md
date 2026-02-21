# IMPLEMENTATION - STEP 9: UPDATE PACKAGE.JSON SCRIPTS
**Status:** completed

## Summary
Added missing `type-check` script to package.json. The other four required scripts (`dev`, `build`, `lint`, `preview`) were already present from prior steps.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/package.json
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/package.json`
Added `type-check` script to the scripts section.

```
# Before
"scripts": {
  "dev": "vite",
  "build": "tsc -b && vite build",
  "lint": "eslint .",
  "preview": "vite preview"
}

# After
"scripts": {
  "dev": "vite",
  "build": "tsc -b && vite build",
  "lint": "eslint .",
  "preview": "vite preview",
  "type-check": "tsc -b --noEmit"
}
```

## Decisions
None

## Verification
[x] All 5 required scripts present: dev, build, preview, lint, type-check
[x] `dev` runs vite dev server
[x] `build` type-checks then bundles via `tsc -b && vite build`
[x] `preview` serves production build
[x] `lint` runs eslint flat config
[x] `type-check` uses project references (`-b`) with `--noEmit` for check-only
