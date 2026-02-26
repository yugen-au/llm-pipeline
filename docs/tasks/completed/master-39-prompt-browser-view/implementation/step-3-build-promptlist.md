# IMPLEMENTATION - STEP 3: BUILD PROMPTLIST
**Status:** completed

## Summary
Created PromptList component -- scrollable list of prompt items with selection highlighting, loading skeletons, error/empty states. Follows StepTimeline pattern for consistency.

## Files
**Created:** `llm_pipeline/ui/frontend/src/components/prompts/PromptList.tsx`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/prompts/PromptList.tsx`
New component with:
- `PromptListProps` interface: `prompts`, `selectedKey`, `onSelect`, `isLoading`, `error`
- `SkeletonRows` helper: 6x `h-12 animate-pulse rounded bg-muted` divs inside `ScrollArea`
- Error state: `text-sm text-destructive` paragraph
- Empty state: `text-sm text-muted-foreground` paragraph
- List: `ScrollArea` wrapping buttons with `prompt.prompt_name` + `Badge` for `prompt.prompt_type`. Selected item gets `bg-accent`. Click calls `onSelect(prompt.prompt_key)`.

## Decisions
### Selection highlight class
**Choice:** `bg-accent` for selected item
**Rationale:** Plan specifies `bg-accent` as primary option. Matches shadcn conventions for interactive selection states.

### Button styling pattern
**Choice:** Followed `StepTimeline` button pattern (`w-full`, `text-left`, `rounded-md`, `transition-colors`)
**Rationale:** Consistent with existing codebase list-item buttons. Adds `hover:bg-muted/30` for hover feedback.

## Verification
[x] ESLint passes (no semicolons, single quotes, named function component)
[x] Imports resolve: `Prompt` from `@/api/types`, `Badge` from `@/components/ui/badge`, `ScrollArea` from `@/components/ui/scroll-area`, `cn` from `@/lib/utils`
[x] Loading state renders 6 skeleton rows inside ScrollArea
[x] Error state renders destructive text
[x] Empty state renders muted-foreground text
[x] Selected item highlighted with `bg-accent`
[x] Click calls `onSelect(prompt.prompt_key)`
