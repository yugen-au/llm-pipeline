# Step 3: TypeScript/Vite Configuration Research

## Scope
TypeScript 5.x + Vite 6.x configuration for React 19 frontend at `llm_pipeline/ui/frontend/`, including proxy, path aliases, ESLint/Prettier, npm scripts, .gitignore, and base path handling.

---

## 1. TypeScript Configuration

### tsconfig.json (application code)

```jsonc
{
  "compilerOptions": {
    // Language & output
    "target": "ES2022",
    "lib": ["ES2023", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",

    // Strictness
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "forceConsistentCasingInFileNames": true,
    "verbatimModuleSyntax": true,

    // Bundler interop
    "allowImportingTsExtensions": true,
    "noEmit": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "skipLibCheck": true,

    // Path aliases
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src", "vite-env.d.ts"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

### tsconfig.node.json (config files: vite.config.ts, etc.)

```jsonc
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2023"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "noEmit": true,
    "strict": true,
    "skipLibCheck": true,
    "verbatimModuleSyntax": true,
    "allowImportingTsExtensions": true
  },
  "include": ["vite.config.ts", "eslint.config.ts"]
}
```

### Key decisions
- **`"jsx": "react-jsx"`** -- React 19 automatic JSX transform; no `import React` needed.
- **`"moduleResolution": "bundler"`** -- Modern resolution for Vite; avoids Node-specific quirks.
- **`"verbatimModuleSyntax": true`** -- TS 5.x replacement for `isolatedModules`; enforces explicit `type` imports.
- **`"target": "ES2022"`** -- Safe baseline; Vite handles actual browser targeting in build via `build.target`.
- **Separate tsconfig.node.json** -- Vite config runs in Node context, different lib/module settings.
- **`"noEmit": true`** -- Vite/esbuild handles transpilation; tsc is type-checking only.

---

## 2. Vite Configuration

### vite.config.ts

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { tanstackRouter } from '@tanstack/router-plugin/vite'
import path from 'node:path'

const apiPort = process.env.VITE_API_PORT || '8642'

export default defineConfig({
  plugins: [
    tanstackRouter({
      target: 'react',
      autoCodeSplitting: true,
    }),
    react(),
  ],

  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },

  server: {
    // Port set via VITE_PORT env var from cli.py, or default for standalone
    port: parseInt(process.env.VITE_PORT || '5173', 10),
    proxy: {
      '/api': {
        target: `http://localhost:${apiPort}`,
        changeOrigin: true,
        // No rewrite -- backend expects /api prefix
      },
      '/ws': {
        target: `ws://localhost:${apiPort}`,
        ws: true,
        // No rewrite -- backend mounts ws router at root (/ws/runs/{run_id})
      },
    },
  },

  build: {
    outDir: 'dist',
    sourcemap: false, // prod; enable in dev via server.sourcemapIgnoreList
  },
})
```

### Key decisions

#### Plugin order
- **TanStack Router MUST come before React plugin** (confirmed by Context7 docs). The router plugin generates `routeTree.gen.ts` before React processes JSX.

#### Proxy configuration
- **`/api` proxy**: No `rewrite` needed. Backend FastAPI routes are mounted with `/api` prefix (`app.include_router(runs_router, prefix="/api")`). Requests from frontend like `GET /api/runs` proxy directly to `http://localhost:8642/api/runs`.
- **`/ws` proxy**: WebSocket endpoint is at `/ws/runs/{run_id}` (no `/api` prefix). Using `ws: true` enables WebSocket upgrade handling.
- **Dynamic port**: `cli.py` passes `VITE_API_PORT` env var to Vite subprocess. Config reads `process.env.VITE_API_PORT` at startup. Falls back to `8642` for standalone `npm run dev`.

#### Path aliases
- `@/` maps to `src/` via both `resolve.alias` (Vite runtime) and `tsconfig.json paths` (TS type checking). Both must be configured for full IDE + build support.

---

## 3. Base Path Handling

### Development mode
- Vite dev server runs on `localhost:{port+1}` (e.g., 8643)
- User opens Vite URL in browser
- Vite proxies `/api` and `/ws` requests to FastAPI on port 8642
- `base: '/'` (default, no change needed)

### Production mode
- `cli.py` `_run_prod_mode()` mounts `frontend/dist/` via `StaticFiles(directory=dist_dir, html=True)` at `/`
- `html=True` enables SPA fallback (returns index.html for unknown routes)
- API routes registered before static mount, so `/api/*` and `/ws/*` take priority
- `base: '/'` works correctly -- all asset paths are relative to root

### No special base path needed
Both dev and prod serve from root. No `base` override required in vite.config.ts.

---

## 4. ESLint + Prettier Configuration

### ESLint 9 flat config (eslint.config.ts)

```typescript
import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import prettier from 'eslint-config-prettier'

export default tseslint.config(
  { ignores: ['dist', 'src/routeTree.gen.ts'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],
    },
  },
  prettier, // Must be last to disable conflicting rules
)
```

### .prettierrc

```json
{
  "semi": false,
  "singleQuote": true,
  "trailingComma": "all",
  "tabWidth": 2,
  "printWidth": 100
}
```

### Key decisions
- **ESLint 9 flat config** -- current standard; `.eslintrc` is legacy.
- **eslint.config.ts** (not .js) -- project is TypeScript; config should match.
- **`eslint-config-prettier`** as last in extends -- disables ESLint rules that conflict with Prettier.
- **Ignore `routeTree.gen.ts`** -- auto-generated by TanStack Router plugin, should not be linted.
- **`react-refresh` plugin** -- warns about non-component exports that break HMR.

### ESLint dev dependencies
```
@eslint/js
eslint
eslint-config-prettier
eslint-plugin-react-hooks
eslint-plugin-react-refresh
globals
prettier
typescript-eslint
```

---

## 5. package.json Scripts

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "lint": "eslint .",
    "lint:fix": "eslint . --fix",
    "type-check": "tsc --noEmit",
    "format": "prettier --write \"src/**/*.{ts,tsx,css}\"",
    "format:check": "prettier --check \"src/**/*.{ts,tsx,css}\""
  }
}
```

### Script details
- **`dev`**: `vite` starts dev server. When launched by `cli.py`, `VITE_PORT` and `VITE_API_PORT` env vars are set automatically. Standalone: uses defaults (5173, proxy to 8642).
- **`build`**: Runs `tsc -b` (project references build) then `vite build`. Ensures type errors caught before bundling. Output to `dist/`.
- **`preview`**: Serves built `dist/` locally for testing production build.
- **`lint`**: ESLint flat config scans all files (ignores configured in eslint.config.ts).
- **`type-check`**: `tsc --noEmit` for CI/pre-commit type verification without producing output.
- **`format`/`format:check`**: Prettier for consistent code style.

---

## 6. .gitignore Patterns

### Frontend-specific .gitignore (llm_pipeline/ui/frontend/.gitignore)

```gitignore
# Dependencies
node_modules/

# Build output
dist/

# Vite cache
.vite/

# TypeScript build info
*.tsbuildinfo

# Generated route tree (optional: some teams commit this)
# src/routeTree.gen.ts

# Environment
.env.local
.env.*.local

# Editor
*.sw?
```

### Root .gitignore interaction
- Root `.gitignore` already has `node_modules/` and `dist/` patterns -- these apply recursively to `llm_pipeline/ui/frontend/` too.
- A frontend-specific `.gitignore` is still recommended for clarity and for patterns unique to the frontend (`.vite/`, `*.tsbuildinfo`).
- **`dist/` is correctly gitignored**. The hatchling wheel build reads from disk at build time; `dist/` does not need to be committed. CI/build pipelines must run `npm run build` in the frontend directory before `pip wheel` or `hatch build`.

### routeTree.gen.ts
TanStack Router plugin auto-generates `src/routeTree.gen.ts`. Two options:
1. **Commit it** (recommended by TanStack): deterministic, no generation step needed in CI.
2. **Gitignore it**: cleaner git history but requires plugin/CLI run in CI.

Recommendation: **Commit it**. Keeps CI simpler and matches TanStack Router's default behavior. The eslint config already ignores it for linting.

---

## 7. Subdirectory-Specific Considerations

### Project root isolation
- `package.json`, `tsconfig.json`, `vite.config.ts`, `eslint.config.ts`, `.prettierrc` all live in `llm_pipeline/ui/frontend/`.
- No root-level `package.json` or Node config needed.
- IDE (VS Code) may need `typescript.tsdk` setting pointed at `llm_pipeline/ui/frontend/node_modules/typescript/lib` for best DX, but this is optional.

### cli.py integration points
The existing `cli.py` (already implemented in task 28) has these integration points:
1. `_start_vite()` runs `npx vite --port {vite_port}` with `cwd=frontend_dir`
2. Passes `VITE_PORT` and `VITE_API_PORT` env vars
3. `_run_prod_mode()` mounts `frontend/dist/` as static files at `/`

The vite.config.ts must honor these env vars (see section 2).

### hatchling wheel inclusion
`pyproject.toml` already has:
```toml
[tool.hatch.build.targets.wheel.shared-data]
"llm_pipeline/ui/frontend/dist" = "llm_pipeline/ui/frontend/dist"
```
This includes the built `dist/` in the Python wheel. Users install via `pip install llm-pipeline[ui]` and the CLI serves the bundled frontend.

---

## 8. Version Recommendations

| Package | Version | Rationale |
|---------|---------|-----------|
| vite | ^6.0.0 | Contract specifies 6.x; stable, well-supported |
| @vitejs/plugin-react | ^4.4.0 | Compatible with Vite 6 and React 19 |
| typescript | ~5.7.0 | Latest 5.x stable; supports verbatimModuleSyntax |
| react | ^19.0.0 | React 19 (contract requirement) |
| react-dom | ^19.0.0 | Must match React version |
| @tanstack/react-router | ^1.114.0 | Latest stable with file-based routing |
| @tanstack/router-plugin | ^1.114.0 | Vite plugin for route generation |
| @tanstack/react-query | ^5.0.0 | Server state management |
| tailwindcss | ^4.0.0 | TW v4 (CSS-first config, no tailwind.config needed for basics) |
| eslint | ^9.0.0 | Flat config support |
| prettier | ^3.0.0 | Current stable |

**Note on Vite 7**: Context7 shows Vite 7.0.0 is available. `npm create vite@latest` may scaffold with Vite 7. If so, the config patterns above remain compatible (Vite 7 is backward-compatible with 6.x config). However, contract scope says 6.x, so pin to `^6.0.0` explicitly in package.json.

**Note on Tailwind v4**: Tailwind CSS v4 uses a CSS-first configuration approach (`@import "tailwindcss"` in CSS) instead of `tailwind.config.ts`. This affects task 42 (theme/colors). If task 42 expects `tailwind.config.ts`, either use Tailwind v3 or adapt to v4's `@theme` CSS directive. This is OUT OF SCOPE for this research step but noted for downstream awareness.

---

## 9. Deviations from Task 29 Details

| Task 29 says | Actual recommendation | Reason |
|---|---|---|
| `TanStackRouterVite` import | `tanstackRouter` from `@tanstack/router-plugin/vite` | API renamed in current version (confirmed by Context7) |
| `npm install tailwindcss postcss autoprefixer @shadcn/ui` | Tailwind v4 no longer needs postcss/autoprefixer separately | Tailwind v4 bundles its own PostCSS plugin; v3 syntax if v3 chosen |
| Static proxy target `'http://localhost:8642'` | Dynamic via `process.env.VITE_API_PORT` | cli.py passes VITE_API_PORT; config should honor it |
| No mention of eslint flat config | eslint.config.ts with flat config | ESLint 9 default; .eslintrc is legacy |

---

## 10. Summary of Files to Create

```
llm_pipeline/ui/frontend/
  package.json          -- deps, scripts
  tsconfig.json         -- app TS config with path aliases
  tsconfig.node.json    -- config file TS config
  vite.config.ts        -- plugins, proxy, aliases, build
  eslint.config.ts      -- flat config with React/TS rules
  .prettierrc           -- formatting rules
  .gitignore            -- frontend-specific ignores
  vite-env.d.ts         -- Vite client type declarations
  index.html            -- Vite entry point HTML
  src/
    main.tsx            -- React entry point
    vite-env.d.ts       -- (alternative location)
```
