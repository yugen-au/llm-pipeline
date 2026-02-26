# IMPLEMENTATION - STEP 2: BUILD PROMPTFILTERBAR
**Status:** completed

## Summary
Created PromptFilterBar component with text search input, prompt type dropdown, and pipeline name dropdown. Follows existing FilterBar.tsx ALL_SENTINEL pattern for Radix Select compatibility.

## Files
**Created:** llm_pipeline/ui/frontend/src/components/prompts/PromptFilterBar.tsx
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/prompts/PromptFilterBar.tsx`
New component with:
- `Input` for text search (placeholder "Search prompts...")
- Two `Select` dropdowns using `ALL_SENTINEL = '__all'` pattern (prompt type, pipeline name)
- Controlled component: all state managed via props
- Named function component, no semicolons, single quotes (ESLint compliant)

## Decisions
### Layout: vertical stacking with horizontal dropdown row
**Choice:** Input on top, two selects side-by-side below in a flex row
**Rationale:** Fits naturally in the narrow left sidebar (w-80) defined in PLAN.md Step 5. Horizontal stacking of all three controls would overflow at that width.

### No cn() usage
**Choice:** Did not import cn() since no conditional/merged classes needed
**Rationale:** All classes are static. Adding cn() import for no dynamic merging would be unnecessary.

## Verification
[x] ESLint passes with zero errors
[x] No semicolons used
[x] Single quotes for imports
[x] Named function component (not arrow/default)
[x] ALL_SENTINEL pattern matches FilterBar.tsx
[x] Props match PLAN.md Step 2 specification exactly
[x] shadcn imports from @/components/ui/

## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
[x] No accessibility labels on Select dropdowns and search Input

### Changes Made
#### File: `llm_pipeline/ui/frontend/src/components/prompts/PromptFilterBar.tsx`
Added aria-label attributes to all interactive controls.
```
# Before
<Input placeholder="Search prompts..." .../>
<SelectTrigger className="w-full">  <!-- type -->
<SelectTrigger className="w-full">  <!-- pipeline -->

# After
<Input aria-label="Search prompts" placeholder="Search prompts..." .../>
<SelectTrigger aria-label="Filter by prompt type" className="w-full">
<SelectTrigger aria-label="Filter by pipeline" className="w-full">
```

### Verification
[x] ESLint passes with zero errors
[x] aria-label on search Input
[x] aria-label on prompt type SelectTrigger
[x] aria-label on pipeline SelectTrigger
