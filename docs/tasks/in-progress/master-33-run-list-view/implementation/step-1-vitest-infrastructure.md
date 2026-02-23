# IMPLEMENTATION - STEP 1: VITEST INFRASTRUCTURE
**Status:** completed

## Summary
Set up Vitest testing infrastructure with jsdom environment, testing-library, and jest-dom matchers. All tests pass including smoke test verifying globals, jsdom DOM APIs, and custom matchers.

## Files
**Created:** `llm_pipeline/ui/frontend/vitest.config.ts`, `llm_pipeline/ui/frontend/src/test/setup.ts`, `llm_pipeline/ui/frontend/src/test/smoke.test.ts`
**Modified:** `llm_pipeline/ui/frontend/package.json`, `llm_pipeline/ui/frontend/tsconfig.app.json`, `llm_pipeline/ui/frontend/tsconfig.node.json`, `llm_pipeline/ui/frontend/package-lock.json`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/package.json`
Added test scripts and devDependencies for vitest ecosystem.
```
# Before (scripts)
"type-check": "tsc -b --noEmit"

# After (scripts)
"type-check": "tsc -b --noEmit",
"test": "vitest",
"test:coverage": "vitest run --coverage"
```
```
# Added devDependencies
"@testing-library/jest-dom": "^6.6.3"
"@testing-library/react": "^16.3.0"
"@testing-library/user-event": "^14.6.1"
"@vitest/coverage-v8": "^3.2.1"
"jsdom": "^26.1.0"
"vitest": "^3.2.1"
```

### File: `llm_pipeline/ui/frontend/vitest.config.ts`
New file. Standalone vitest config importing same vite plugins (tanstackRouter, react, tailwindcss) with jsdom environment, globals enabled, and setup file reference.

### File: `llm_pipeline/ui/frontend/src/test/setup.ts`
New file. Single import of `@testing-library/jest-dom/vitest` to extend expect matchers.

### File: `llm_pipeline/ui/frontend/src/test/smoke.test.ts`
New file. Two smoke tests verifying jsdom environment (document/window exist) and jest-dom matchers (toBeInTheDocument).

### File: `llm_pipeline/ui/frontend/tsconfig.app.json`
Added `"vitest/globals"` and `"@testing-library/jest-dom/vitest"` to `compilerOptions.types` for TypeScript type support in test files.

### File: `llm_pipeline/ui/frontend/tsconfig.node.json`
Added `"vitest.config.ts"` to `include` array so TypeScript recognizes the config file.

## Decisions
### --legacy-peer-deps for npm install
**Choice:** Used `npm install --legacy-peer-deps`
**Rationale:** Pre-existing peer dep conflict between `@tanstack/zod-adapter` (wants zod ^3.23.8) and project's zod ^4.3.6. This conflict predates vitest changes; lockfile was previously generated with legacy resolution.

### Separate vitest.config.ts (not inline in vite.config.ts)
**Choice:** Standalone `vitest.config.ts` importing plugins independently
**Rationale:** Per PLAN.md architecture decision. Avoids test globals leaking into build config. Vitest docs recommend this pattern for non-test Vite builds.

### Smoke test included
**Choice:** Added `src/test/smoke.test.ts` as infrastructure verification
**Rationale:** Verifies end-to-end: vitest globals, jsdom environment, and jest-dom matchers all work together. Provides confidence the setup is correct before downstream component tests depend on it.

## Verification
[x] `npx vitest run` passes (2/2 tests, 0 failures)
[x] jsdom environment provides document/window globals
[x] jest-dom matchers (toBeInTheDocument) work via setup file
[x] TypeScript types resolve for vitest globals and jest-dom matchers
[x] package-lock.json updated with all new dependencies
