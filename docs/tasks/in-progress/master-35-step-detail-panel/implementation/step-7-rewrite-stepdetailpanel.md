# IMPLEMENTATION - STEP 7: REWRITE STEPDETAILPANEL
**Status:** completed

## Summary
Rewrote StepDetailPanel from a div-based panel with manual a11y (focus trap, Escape handler, backdrop) to shadcn/ui Sheet + Tabs with 7 tab content sections. Added useRunContext mock to test file to fix QueryClientProvider errors from the new hook dependency.

## Files
**Created:** none
**Modified:** `llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.tsx`, `llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.test.tsx`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.tsx`
Full rewrite. Removed ~50 lines of manual a11y code (focus trap, Escape handler, backdrop div, panelRef, closeBtnRef). Replaced with Sheet component from shadcn/ui providing all a11y via Radix Dialog primitive.

Key structural changes:
- `Sheet open={visible} onOpenChange={(o) => !o && onClose()}` replaces manual state management
- `SheetContent className="w-[600px]"` replaces fixed-width div panel with custom translate animation
- `SheetHeader` with sr-only title/description for Radix a11y requirements
- `StepContent` now fetches 4 data sources: `useStep`, `useStepEvents`, `useStepInstructions`, `useRunContext`
- `Tabs defaultValue="meta"` with 7 TabsTrigger values and corresponding TabsContent
- 7 private tab content components: InputTab, PromptsTab, ResponseTab, InstructionsTab, ContextDiffTab, ExtractionsTab, MetaTab

Data flow:
- InputTab uses useRunContext snapshots to find previous step's context_snapshot
- PromptsTab/ResponseTab filter step events by llm_call_starting/llm_call_completed
- InstructionsTab uses useStepInstructions (fetches from /pipelines/{name}/steps/{step}/prompts)
- ContextDiffTab shows before/after snapshots side-by-side with new_keys badges
- ExtractionsTab filters extraction_completed and extraction_error events
- MetaTab aggregates step metadata + event-derived data (cache status, validation errors, strategy)

### File: `llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.test.tsx`
Added mock for `useRunContext` from `@/api/runs` (new hook dependency introduced by rewrite). Added reset and default return value in beforeEach. Fixed `screen.getByText('extract')` assertion to use `getAllByText` since step_name now appears in both header and Meta tab.

## Decisions
### useRunContext for Input/Context tabs instead of separate event fetching
**Choice:** Call `useRunContext(runId)` inside StepContent for Input and ContextDiff tab data
**Rationale:** TanStack Query deduplicates -- the parent RunDetailPage already calls useRunContext for the same runId, so this hits cache. Avoids needing to fetch unfiltered events or pass context snapshots via props.

### SheetHeader as sr-only
**Choice:** Render SheetHeader with sr-only class containing SheetTitle and SheetDescription
**Rationale:** Radix Dialog requires aria-labelledby/aria-describedby. The step header inside StepContent provides the visual title. Using sr-only satisfies Radix without duplicate visual headers.

### showCloseButton kept as default (true)
**Choice:** Use Sheet's built-in close button (X icon with sr-only "Close" text)
**Rationale:** Existing tests expect a close button with name /close/i. The Sheet component provides this by default via Radix Dialog Close primitive.

## Verification
[x] TypeScript compiles without errors (npx tsc --noEmit)
[x] All 10 StepDetailPanel tests pass
[x] All 90 frontend tests pass (9 test files)
[x] Sheet replaces manual focus-trap, Escape handler, backdrop code
[x] Panel width is w-[600px] per spec
[x] 7 tabs render: meta, input, prompts, response, instructions, context, extractions
[x] StepDetailPanelProps interface unchanged
[x] StepContent child component pattern preserved
