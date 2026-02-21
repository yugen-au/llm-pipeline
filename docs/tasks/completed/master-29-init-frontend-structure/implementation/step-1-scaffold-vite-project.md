# IMPLEMENTATION - STEP 1: SCAFFOLD VITE PROJECT
**Status:** completed

## Summary
Scaffolded Vite 7.3.1 + React 19.2.0 + TypeScript 5.9.3 project at `llm_pipeline/ui/frontend/` using `npm create vite@latest` with `react-ts` template (create-vite v8.3.0). Installed dependencies, deleted placeholder files, created `.gitignore`, and added `minimatch` override to resolve upstream audit vulnerabilities.

## Files
**Created:** `llm_pipeline/ui/frontend/` (entire scaffold: package.json, index.html, vite.config.ts, tsconfig.json, tsconfig.app.json, tsconfig.node.json, eslint.config.js, src/main.tsx, src/index.css, README.md, public/, .gitignore)
**Modified:** `llm_pipeline/ui/frontend/.gitignore` (replaced scaffold default with plan-specified entries)
**Deleted:** `llm_pipeline/ui/frontend/src/App.css`, `llm_pipeline/ui/frontend/src/App.tsx`, `llm_pipeline/ui/frontend/src/assets/react.svg`, `llm_pipeline/ui/frontend/public/vite.svg`

## Changes
### File: `llm_pipeline/ui/frontend/.gitignore`
Replaced Vite scaffold default .gitignore with minimal plan-specified entries.
```
# Before (scaffold default)
# Logs
logs
*.log
npm-debug.log*
yarn-debug.log*
yarn-error.log*
pnpm-debug.log*
lerna-debug.log*

node_modules
dist
dist-ssr
*.local

# Editor directories and files
.vscode/*
!.vscode/extensions.json
.idea
.DS_Store
*.suo
*.ntvs*
*.njsproj
*.sln
*.sw?

# After
dist/
node_modules/
.vite/
*.tsbuildinfo
.env.local
.env.*.local
```

### Deleted scaffold placeholders
- `src/App.css` - default CSS not needed (Tailwind v4 in later step)
- `src/App.tsx` - default component not needed (TanStack Router in later step)
- `src/assets/react.svg` - React logo placeholder
- `public/vite.svg` - Vite logo placeholder

## Decisions
### create-vite version
**Choice:** Used create-vite v8.3.0 (latest as of 2026-02-21)
**Rationale:** `npm create vite@latest` automatically pulled the latest version. This scaffolded Vite ^7.3.1, React ^19.2.0, TypeScript ~5.9.3 which meets all requirements.

### Scaffold eslint.config.js retained
**Choice:** Kept scaffold-generated `eslint.config.js` for now
**Rationale:** Step 7 will replace it with the full flat config (`eslint.config.ts`). No point modifying it in this step.

### Scaffold main.tsx and index.css retained
**Choice:** Kept `src/main.tsx` and `src/index.css` from scaffold
**Rationale:** Step 5 (Tailwind CSS) and Step 8 (entry files) will replace these. They are valid placeholders until then.

### minimatch override added
**Choice:** Added `"overrides": {"minimatch": "^10.2.1"}` to package.json
**Rationale:** Scaffold eslint ^9.39.1 and typescript-eslint ^8.48.0 depend transitively on minimatch <10.2.1 which has a ReDoS vulnerability (GHSA-3ppc-4f35-3m26). The only npm-suggested fix was eslint@10 (breaking, incompatible with eslint-plugin-react-hooks@7). npm overrides force minimatch to a patched version across all transitive deps, resolving all 10 high-severity findings with 0 breaking changes.

## Verification
[x] `npm create vite@latest frontend -- --template react-ts` succeeded
[x] `npm install` completed (226 packages)
[x] Vite version is ^7.3.1 (Vite 7)
[x] React version is ^19.2.0 (React 19)
[x] TypeScript version is ~5.9.3
[x] `src/App.css` deleted
[x] `src/App.tsx` deleted
[x] `src/assets/` directory deleted (contained react.svg)
[x] `public/vite.svg` deleted
[x] `.gitignore` contains: dist/, node_modules/, .vite/, *.tsbuildinfo, .env.local, .env.*.local
[x] `package.json` has correct scripts (dev, build, lint, preview)
[x] `npm audit` reports 0 vulnerabilities (minimatch override applied)
[x] `package.json` contains `overrides.minimatch: "^10.2.1"`

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] Broken favicon reference - index.html referenced href="/vite.svg" but public/vite.svg was deleted. Removed the `<link rel="icon">` tag entirely.
[x] Scaffold title - changed `<title>frontend</title>` to `<title>llm-pipeline</title>`.

### Changes Made
#### File: `llm_pipeline/ui/frontend/index.html`
Removed broken favicon link tag and updated title to project name.
```
# Before
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>frontend</title>

# After
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>llm-pipeline</title>
```

### Verification
[x] No `<link rel="icon">` tag in index.html (no 404 in dev mode)
[x] `<title>` is `llm-pipeline`
