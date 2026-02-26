# IMPLEMENTATION - STEP 4: BUILD PROMPTVIEWER
**Status:** completed

## Summary
Built PromptViewer component that displays prompt details with variable highlighting, variant tabs, and metadata for a selected prompt key.

## Files
**Created:** `llm_pipeline/ui/frontend/src/components/prompts/PromptViewer.tsx`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/prompts/PromptViewer.tsx`
New component with:
- `PromptViewer` -- main component, props: `{ promptKey: string | null }`
- `highlightVariables` -- splits content on `{var_name}` regex, wraps matches in blue highlight spans
- `VariantSection` -- renders single variant: prompt_type badge, version, description, required_variables badges, highlighted content in monospace `<pre>`
- Empty state (no key): centered muted text
- Loading state: skeleton placeholders (h-7, h-4, h-40)
- Error state: centered destructive text
- Single variant: renders directly without tabs
- Multiple variants: wraps in shadcn `Tabs` keyed by `prompt_type`

## Decisions
### Export only component
**Choice:** Export only `PromptViewer`, not `highlightVariables` or `PromptViewerProps`
**Rationale:** ESLint `react-refresh/only-export-components` warns when non-component exports are mixed with components. `highlightVariables` is internal. Props type can be inferred by consumers if needed.

### Variable regex without dots
**Choice:** `/(\{[a-zA-Z_][a-zA-Z0-9_]*\})/g` (no dot support)
**Rationale:** Matches backend `extract_variables_from_content` in `llm_pipeline/prompts/loader.py` which uses `r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}'`. Consistency over flexibility.

## Verification
[x] TypeScript compiles with no errors (`tsc --noEmit`)
[x] ESLint passes with no errors or warnings
[x] No semicolons, single quotes, named function components
[x] Variable highlighting uses React elements (not dangerouslySetInnerHTML)
[x] Empty/loading/error states all handled
[x] Tabs conditional on variants.length > 1
[x] Imports from established API layer and shadcn components

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] MEDIUM - Export style inconsistency: changed from `function PromptViewer` + bottom `export { PromptViewer }` to `export function PromptViewer` at declaration site, matching codebase convention
[x] LOW - Variable highlighting hardcoded dark theme colors: replaced `bg-blue-900/30 text-blue-400` with semantic tokens `bg-primary/20 text-primary`

### Changes Made
#### File: `llm_pipeline/ui/frontend/src/components/prompts/PromptViewer.tsx`
Two fixes applied:

```
# Before (issue 1)
function PromptViewer({ promptKey }: PromptViewerProps) {
...
export { PromptViewer }

# After (issue 1)
export function PromptViewer({ promptKey }: PromptViewerProps) {
// bottom export statement removed
```

```
# Before (issue 2)
<span key={i} className="rounded bg-blue-900/30 px-0.5 text-blue-400">

# After (issue 2)
<span key={i} className="rounded bg-primary/20 px-0.5 text-primary">
```

### Verification
[x] ESLint passes with no errors or warnings
[x] Export style matches codebase convention (`export function` at declaration)
[x] Highlight colors use semantic design tokens for theme compatibility
