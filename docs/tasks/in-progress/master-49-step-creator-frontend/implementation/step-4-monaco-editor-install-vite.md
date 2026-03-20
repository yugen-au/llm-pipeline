# IMPLEMENTATION - STEP 4: MONACO EDITOR INSTALL + VITE
**Status:** completed

## Summary
Installed @monaco-editor/react, configured Vite manualChunks for Monaco code splitting, and created EditorSkeleton fallback component for Suspense lazy-loading.

## Files
**Created:** llm_pipeline/ui/frontend/src/components/creator/EditorSkeleton.tsx
**Modified:** llm_pipeline/ui/frontend/package.json, llm_pipeline/ui/frontend/package-lock.json, llm_pipeline/ui/frontend/vite.config.ts
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/package.json`
Added @monaco-editor/react ^4.7.0 to dependencies. Fixed pre-existing audit vulnerabilities (flatted, hono) via npm audit fix.

### File: `llm_pipeline/ui/frontend/vite.config.ts`
Added monaco-editor manualChunk before existing react-dom check.
```
# Before
manualChunks(id) {
  if (id.includes('node_modules/react-dom/') || id.includes('node_modules/react/')) {

# After
manualChunks(id) {
  if (id.includes('node_modules/monaco-editor/')) {
    return 'monaco'
  }
  if (id.includes('node_modules/react-dom/') || id.includes('node_modules/react/')) {
```

### File: `llm_pipeline/ui/frontend/src/components/creator/EditorSkeleton.tsx`
New component. Renders 12 animated skeleton lines with varying widths (w-1/2 through w-full) inside a bg-muted container. Each line uses h-4 animate-pulse rounded bg-muted-foreground/10. Used as Suspense fallback when lazy-loading Monaco.

## Decisions
### Skeleton line width distribution
**Choice:** 12 lines with widths: 3/4, full, 5/6, 2/3, full, 4/5, 1/2, full, 3/5, 5/6, 2/3, 3/4
**Rationale:** Mimics realistic code line lengths. Avoids uniform appearance that looks artificial. 12 lines fills a reasonable viewport area without being excessive.

## Verification
[x] @monaco-editor/react ^4.7.0 present in package.json dependencies
[x] vite.config.ts manualChunks catches monaco-editor before react-dom
[x] EditorSkeleton.tsx renders 12 animated lines with varying widths
[x] src/components/creator/ directory created
[x] TypeScript type-check passes clean
[x] npm audit shows 0 vulnerabilities after fix
