# IMPLEMENTATION - STEP 6: CREATORINPUTFORM + DRAFTPICKER
**Status:** completed

## Summary
Built DraftPicker (compact scrollable draft list with status badges and relative timestamps), CreatorInputForm (description textarea with validation, target pipeline input, extraction/transformation checkboxes, generate button), and CreatorInputColumn (Card wrapper combining both components for the 280px left column).

## Files
**Created:** `llm_pipeline/ui/frontend/src/components/creator/DraftPicker.tsx`, `llm_pipeline/ui/frontend/src/components/creator/CreatorInputForm.tsx`, `llm_pipeline/ui/frontend/src/components/creator/CreatorInputColumn.tsx`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/creator/DraftPicker.tsx`
Compact scrollable draft list component. Each item renders truncated name (font-mono text-xs), status Badge (variant mapped: secondary for draft/tested, default for accepted, destructive for error), and relative timestamp via `formatRelative` from `@/lib/time`. Selected item highlighted with `bg-accent ring-1 ring-ring/20`. "New" button (Plus icon, ghost icon-xs) at top right. Loading skeleton and empty state handled. Uses ScrollArea with `max-h-[40vh]` and thin scrollbar.

### File: `llm_pipeline/ui/frontend/src/components/creator/CreatorInputForm.tsx`
Form component with: Description Textarea (required, min 10 chars inline validation with `aria-invalid`, error message on blur), Target Pipeline Input (optional), include_extraction Checkbox (default checked by parent), include_transformation Checkbox (default unchecked by parent). Generate button: full-width, disabled when invalid/generating/disabled. Shows Loader2 + "Generating..." when active, Wand2 + "Generate" otherwise. Local `touched` state for validation-on-blur pattern.

### File: `llm_pipeline/ui/frontend/src/components/creator/CreatorInputColumn.tsx`
Card wrapper combining DraftPicker (top, shrink-0) and CreatorInputForm (bottom, flex-1 with overflow-y-auto) separated by a Separator. Designed for the 280px fixed-width left column. Passes through all props to children.

## Decisions
### Wrapping component
**Choice:** Created CreatorInputColumn as a separate composition component rather than embedding Card logic inline in the route
**Rationale:** Route component (step 8) already has significant state management. Extracting the Card + layout into its own component keeps the route clean and the column self-contained. Matches the pattern of CreatorEditor being its own component for the middle column.

### Validation strategy
**Choice:** Validation-on-blur with local `touched` state in CreatorInputForm
**Rationale:** Showing errors immediately on mount is poor UX. Blur-triggered validation gives the user a chance to type before showing errors. The Generate button still enforces min-length regardless of touched state.

### DraftPicker scrollbar
**Choice:** Used `thin` prop on ScrollArea for a more subtle scrollbar
**Rationale:** The 280px column is narrow; a standard scrollbar width would feel oversized. The thin variant is visually lighter.

## Verification
[x] TypeScript compiles with `npx tsc --noEmit` -- zero errors
[x] DraftPicker accepts DraftItem[] from creator.ts types
[x] Badge variant mapping covers all draft statuses (draft, tested, accepted, error) with fallback
[x] aria-invalid set on Textarea when validation fails
[x] Generate button disabled when description < 10 chars, isGenerating, or disabled prop
[x] Loader2 + "Generating..." shown when isGenerating
[x] ScrollArea max-h ~40% via max-h-[40vh]
[x] Both components visible simultaneously in Card (not toggled)
