# IMPLEMENTATION - STEP 1: INSTALL DEPENDENCIES
**Status:** completed

## Summary
Installed `zod` and `@tanstack/zod-adapter` as production dependencies in `llm_pipeline/ui/frontend/`.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/package.json, llm_pipeline/ui/frontend/package-lock.json
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/package.json`
Added two production dependencies.
```
# Before (dependencies section, partial)
    "tailwindcss": "^4.2.0",
    "zustand": "^5.0.11"

# After (dependencies section, partial)
    "@tanstack/zod-adapter": "^1.161.3",
    ...
    "tailwindcss": "^4.2.0",
    "zod": "^4.3.6",
    "zustand": "^5.0.11"
```

## Decisions
### Zod 4 vs Zod 3
**Choice:** Accepted npm's resolution of zod@4.3.6 (latest)
**Rationale:** `@tanstack/zod-adapter@1.161.3` declares peer dep `zod@^3.23.8`, but npm overrode it to install zod 4. Zod 4 ships a `zod/v3` compat layer and the core `z.object()`, `z.string()`, `z.number()` APIs used in this task are unchanged. The adapter loaded without error in Node. If issues arise in later steps, can pin to `zod@^3.24` as fallback.

## Verification
[x] `zod` appears in `package.json` under `dependencies` (^4.3.6)
[x] `@tanstack/zod-adapter` appears in `package.json` under `dependencies` (^1.161.3)
[x] Neither appears in `devDependencies`
[x] Both packages resolve correctly via `require()` in Node
