# IMPLEMENTATION - STEP 2: PACKAGE.JSON BUILD
**Status:** completed

## Summary
Added `build:analyze` script and `rollup-plugin-visualizer` devDependency to frontend package.json. Ran npm install to update lockfile.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/package.json, llm_pipeline/ui/frontend/package-lock.json
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/package.json`
Added build:analyze script to scripts section and rollup-plugin-visualizer to devDependencies.

```
# Before (scripts section)
"build": "tsc -b && vite build",
"lint": "eslint .",

# After (scripts section)
"build": "tsc -b && vite build",
"build:analyze": "ANALYZE=true tsc -b && vite build",
"lint": "eslint .",
```

```
# Before (devDependencies, end)
"typescript-eslint": "^8.48.0",
"vite": "^7.3.1",

# After (devDependencies, end)
"typescript-eslint": "^8.48.0",
"rollup-plugin-visualizer": "^5.14.0",
"vite": "^7.3.1",
```

### File: `llm_pipeline/ui/frontend/package-lock.json`
Auto-updated by npm install. Added rollup-plugin-visualizer@5.14.0 and its 5 transitive dependencies.

## Decisions
None -- all choices prescribed by PLAN.md step 2.

## Verification
[x] rollup-plugin-visualizer@5.14.0 confirmed installed via `npm ls rollup-plugin-visualizer`
[x] build:analyze script present in package.json scripts section
[x] package-lock.json updated (5 packages added, 724 total audited)
[x] No breaking changes to existing scripts

## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
[x] build:analyze script env var scoping bug -- ANALYZE=true only applied to tsc -b, not vite build

### Changes Made
#### File: `llm_pipeline/ui/frontend/package.json`
Moved ANALYZE=true prefix from tsc command to vite command so the env var is in scope when vite.config.ts checks process.env.ANALYZE.

```
# Before
"build:analyze": "ANALYZE=true tsc -b && vite build",

# After
"build:analyze": "tsc -b && ANALYZE=true vite build",
```

### Verification
[x] ANALYZE=true now scopes to vite build (the command that loads vite.config.ts where visualizer plugin checks it)
[x] tsc -b does not need ANALYZE env var (type-check only)
