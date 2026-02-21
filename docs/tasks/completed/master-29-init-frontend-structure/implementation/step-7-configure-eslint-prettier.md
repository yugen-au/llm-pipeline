# IMPLEMENTATION - STEP 7: CONFIGURE ESLINT PRETTIER
**Status:** completed

## Summary
Replaced Vite scaffold's `eslint.config.js` with `eslint.config.ts` using ESLint 9 flat config via `tseslint.config()`. Created `.prettierrc` and `.prettierignore`. All configs validated: `npx eslint .` exits 0, Prettier correctly picks up settings and ignores generated files.

## Files
**Created:** `llm_pipeline/ui/frontend/eslint.config.ts`, `llm_pipeline/ui/frontend/.prettierrc`, `llm_pipeline/ui/frontend/.prettierignore`
**Modified:** none
**Deleted:** `llm_pipeline/ui/frontend/eslint.config.js` (Vite scaffold default)

## Changes
### File: `llm_pipeline/ui/frontend/eslint.config.ts`
New ESLint 9 flat config using `tseslint.config()` helper. Includes js recommended, typescript-eslint recommended, react-hooks flat recommended-latest, react-refresh vite preset, and eslint-config-prettier (applied last to disable conflicting rules). Ignores `dist/` and `src/routeTree.gen.ts`.

```typescript
import js from '@eslint/js'
import prettier from 'eslint-config-prettier'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist', 'src/routeTree.gen.ts'] },
  js.configs.recommended,
  tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    ...reactHooks.configs.flat['recommended-latest'],
  },
  {
    files: ['**/*.{ts,tsx}'],
    ...reactRefresh.configs.vite,
    rules: {
      ...reactRefresh.configs.vite.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    },
  },
  prettier,
)
```

### File: `llm_pipeline/ui/frontend/.prettierrc`
JSON config with project conventions: no semicolons, single quotes, trailing commas, 2-space indent, 100-char line width.

### File: `llm_pipeline/ui/frontend/.prettierignore`
Excludes `src/routeTree.gen.ts` (TanStack Router auto-generated) and `dist/` from formatting.

## Decisions
### tseslint.config() vs defineConfig
**Choice:** Used `tseslint.config()` instead of ESLint's `defineConfig`
**Rationale:** `tseslint.config()` provides type-safe config and properly handles spreading `tseslint.configs.recommended` (which is an array). The scaffold's `defineConfig` approach works but `tseslint.config()` is the canonical pattern from typescript-eslint docs.

### Plugin config spreading pattern
**Choice:** Spread react-hooks and react-refresh configs as top-level entries with `files` constraint rather than nesting in `extends`
**Rationale:** `tseslint.config()` validates `extends` entries strictly and rejects configs with non-standard shapes (like react-refresh's `name` + `plugins` structure). Spreading as top-level entries with explicit `files` globs works correctly.

### react-hooks recommended-latest
**Choice:** Used `reactHooks.configs.flat['recommended-latest']` instead of `reactHooks.configs.flat.recommended`
**Rationale:** `recommended-latest` is the non-legacy flat config entry point in eslint-plugin-react-hooks v7.x. Both resolve to the same rules but `recommended-latest` is the forward-compatible key.

## Verification
[x] `npx eslint .` exits 0 with no errors
[x] `.prettierrc` is valid JSON and picked up by Prettier
[x] `.prettierignore` correctly excludes `routeTree.gen.ts` and `dist/`
[x] `eslint-config-prettier` is applied last (disables style rules that conflict with Prettier)
[x] `tsconfig.node.json` already includes `eslint.config.ts` in its `include` array
