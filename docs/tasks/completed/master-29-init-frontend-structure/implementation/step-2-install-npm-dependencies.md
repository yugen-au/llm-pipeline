# IMPLEMENTATION - STEP 2: INSTALL NPM DEPENDENCIES
**Status:** completed

## Summary
Installed all npm dependencies for the frontend project on top of the Vite 7 + React 19 scaffold from step 1.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/package.json, llm_pipeline/ui/frontend/package-lock.json
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/package.json`
Added runtime and dev dependencies via three npm install commands.

```
# Before (dependencies)
"dependencies": {
  "react": "^19.2.0",
  "react-dom": "^19.2.0"
}

# After (dependencies)
"dependencies": {
  "@tailwindcss/vite": "^4.2.0",
  "@tanstack/react-query": "^5.90.21",
  "@tanstack/react-router": "^1.161.3",
  "react": "^19.2.0",
  "react-dom": "^19.2.0",
  "tailwindcss": "^4.2.0",
  "zustand": "^5.0.11"
}
```

```
# Before (devDependencies) - only scaffold defaults
"devDependencies": {
  "@eslint/js": "^9.39.1",
  "@types/node": "^24.10.1",
  "@types/react": "^19.2.7",
  "@types/react-dom": "^19.2.3",
  "@vitejs/plugin-react": "^5.1.1",
  "eslint": "^9.39.1",
  "eslint-plugin-react-hooks": "^7.0.1",
  "eslint-plugin-react-refresh": "^0.4.24",
  "globals": "^16.5.0",
  "typescript": "~5.9.3",
  "typescript-eslint": "^8.48.0",
  "vite": "^7.3.1"
}

# After (devDependencies) - added 4 new packages
"devDependencies": {
  "@eslint/js": "^9.39.1",
  "@tanstack/react-query-devtools": "^5.91.3",
  "@tanstack/router-plugin": "^1.161.3",
  "@types/node": "^24.10.1",
  "@types/react": "^19.2.7",
  "@types/react-dom": "^19.2.3",
  "@vitejs/plugin-react": "^5.1.1",
  "eslint": "^9.39.1",
  "eslint-config-prettier": "^10.1.8",
  "eslint-plugin-react-hooks": "^7.0.1",
  "eslint-plugin-react-refresh": "^0.4.24",
  "globals": "^16.5.0",
  "prettier": "^3.8.1",
  "typescript": "~5.9.3",
  "typescript-eslint": "^8.48.0",
  "vite": "^7.3.1"
}
```

## Decisions
### Skip already-installed dev deps
**Choice:** Did not re-install `@eslint/js`, `typescript-eslint`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh` since Vite 7 scaffold already included them.
**Rationale:** npm install is additive; re-installing would be a no-op but clutters the command. Only installed packages not yet present.

### Tailwind deps as runtime (not dev)
**Choice:** `tailwindcss` and `@tailwindcss/vite` installed as runtime deps (no `-D` flag), matching plan step 2.
**Rationale:** Tailwind v4 with `@tailwindcss/vite` is used as a Vite plugin at build time but npm convention for Vite plugins varies. The plan explicitly specifies `npm install` (not `npm install -D`) for these.

### No shadcn packages
**Choice:** Did not install `tw-animate-css`, `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`.
**Rationale:** These are auto-installed by `npx shadcn@latest init` in step 6 per the plan.

## Verification
[x] `@tanstack/react-router@^1.161.3` in dependencies
[x] `@tanstack/react-query@^5.90.21` in dependencies
[x] `zustand@^5.0.11` in dependencies
[x] `tailwindcss@^4.2.0` in dependencies
[x] `@tailwindcss/vite@^4.2.0` in dependencies
[x] `@tanstack/router-plugin@^1.161.3` in devDependencies
[x] `@tanstack/react-query-devtools@^5.91.3` in devDependencies
[x] `eslint-config-prettier@^10.1.8` in devDependencies
[x] `prettier@^3.8.1` in devDependencies
[x] 0 npm audit vulnerabilities
[x] No shadcn packages installed (deferred to step 6)
