# IMPLEMENTATION - STEP 2: SHARED COMPONENT LIBRARY
**Status:** completed

## Summary
Extracted 5 reusable visual patterns from StepDetailPanel.tsx into a new shared component library at src/components/shared/. Refactored StepDetailPanel to import and use these components. All 16 existing tests pass with no regression.

## Files
**Created:**
- llm_pipeline/ui/frontend/src/components/shared/LabeledPre.tsx
- llm_pipeline/ui/frontend/src/components/shared/BadgeSection.tsx
- llm_pipeline/ui/frontend/src/components/shared/TabScrollArea.tsx
- llm_pipeline/ui/frontend/src/components/shared/LoadingSkeleton.tsx
- llm_pipeline/ui/frontend/src/components/shared/EmptyState.tsx
- llm_pipeline/ui/frontend/src/components/shared/index.ts

**Modified:**
- llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.tsx

**Deleted:** none

## Changes
### File: `src/components/shared/LabeledPre.tsx`
New component. Props: label, content, className. Wraps the repeated pattern of text-xs font-medium label + whitespace-pre-wrap bg-muted pre block inside a space-y-1 div.

### File: `src/components/shared/BadgeSection.tsx`
New component. Props: badge (ReactNode), children (ReactNode). Wraps Badge + content block in space-y-1 div.

### File: `src/components/shared/TabScrollArea.tsx`
New component. Props: children, className. Wraps ScrollArea with h-[calc(100vh-220px)] default height, composable via cn().

### File: `src/components/shared/LoadingSkeleton.tsx`
New component. Exports SkeletonLine (h-4 animate-pulse, optional width prop via style) and SkeletonBlock (h-20 animate-pulse). Both accept className for override.

### File: `src/components/shared/EmptyState.tsx`
New component. Props: message. Renders text-sm text-muted-foreground paragraph.

### File: `src/components/shared/index.ts`
Barrel export for all 6 exports (LabeledPre, BadgeSection, TabScrollArea, SkeletonLine, SkeletonBlock, EmptyState).

### File: `src/components/runs/StepDetailPanel.tsx`
Replaced inline patterns with shared component imports:
```
# Before
import { ScrollArea } from '@/components/ui/scroll-area'
# ...inline <p className="text-sm text-muted-foreground">msg</p>
# ...inline <ScrollArea className="h-[calc(100vh-220px)]">
# ...inline <div className="h-24 animate-pulse rounded bg-muted" />
# ...inline <div className="h-5 w-40 animate-pulse rounded bg-muted" />

# After
import { EmptyState, TabScrollArea, LabeledPre, BadgeSection, SkeletonLine, SkeletonBlock } from '@/components/shared'
# ScrollArea import removed (used via TabScrollArea)
# EmptyState replaces 6 inline empty-state paragraphs
# TabScrollArea replaces 7 inline ScrollArea wrappers
# LabeledPre replaces ResponseTab "Raw Response" label+pre pattern
# BadgeSection replaces PromptsTab badge+content wrapper
# SkeletonLine/SkeletonBlock replace inline animate-pulse divs
```

## Decisions
### SkeletonLine width via style prop
**Choice:** Use style={{ width }} instead of className for width on SkeletonLine
**Rationale:** Arbitrary pixel/rem widths like "10rem" or "6rem" are cleaner as inline style than Tailwind arbitrary values. className still available for h-5 overrides.

### LabeledPre wraps in space-y-1 div
**Choice:** LabeledPre includes the space-y-1 wrapper div (label + pre)
**Rationale:** Every usage of the label+pre pattern had a space-y-1 parent div. Including it in the component avoids consumers needing to wrap.

### Kept Parsed Result column inline
**Choice:** Did not use LabeledPre for the "Parsed Result" column in ResponseTab
**Rationale:** Parsed Result renders JsonViewer or a span, not a pre block. LabeledPre is specifically for text content in a pre element.

## Verification
[x] All 16 StepDetailPanel.test.tsx tests pass
[x] No ScrollArea direct import remains in StepDetailPanel (uses TabScrollArea)
[x] All 6 EmptyState patterns replaced
[x] All 7 TabScrollArea patterns replaced
[x] Loading skeletons replaced with SkeletonLine/SkeletonBlock
[x] ResponseTab uses LabeledPre for Raw Response
[x] PromptsTab uses BadgeSection for prompt entries
[x] index.ts barrel exports all components
