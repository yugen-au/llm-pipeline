# IMPLEMENTATION - STEP 3: STEPTIMELINE COMPONENT
**Status:** completed

## Summary
Built StepTimeline component with StepStatus type, StepTimelineItem/StepTimelineProps interfaces, deriveStepStatus utility for merging DB steps with WS events, and full loading/error/empty states following RunsTable patterns.

## Files
**Created:** llm_pipeline/ui/frontend/src/components/runs/StepTimeline.tsx
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/runs/StepTimeline.tsx`
New component file containing:
- `StepStatus` type union: 'completed' | 'running' | 'failed' | 'skipped' | 'pending'
- `StepTimelineItem` interface with step_name, step_number, status, execution_time_ms, model
- `StepTimelineProps` interface with items, isLoading, isError, selectedStepId, onSelectStep
- `deriveStepStatus(dbSteps, events)` utility: merges StepListItem[] with EventItem[] - DB steps default completed; step_started without matching step_completed/step_failed = running; step_skipped = skipped; step_failed = failed
- `SkeletonRows` - 4 rows with animate-pulse (circle badge + text bars)
- Error state: "Failed to load steps" with text-destructive
- Empty state: "No steps recorded" with text-muted-foreground
- Step rows: button elements with step number badge (rounded-full border), name (truncate), StatusBadge, formatDuration, model text. Selected = bg-muted/50, hover = bg-muted/30
- Named export `StepTimeline`

## Decisions
### Step row as button element
**Choice:** Used `<button>` for step rows instead of `<div>` with onClick
**Rationale:** Buttons are natively focusable and keyboard-accessible (Enter/Space triggers click), matching WCAG requirements without extra aria roles

### Sort by step_number in deriveStepStatus
**Choice:** Sort output array by step_number ascending
**Rationale:** Events may arrive out of order; DB steps have natural ordering. Sorting ensures consistent display regardless of event arrival sequence.

## Verification
[x] TypeScript compiles with no errors (npx tsc --noEmit)
[x] StepStatus type covers all 5 statuses from PLAN.md
[x] deriveStepStatus handles: DB-only (completed), running from events, skipped override, failed override
[x] Loading skeleton matches 4-row spec with animate-pulse
[x] Error/empty states follow RunsTable pattern
[x] Selected step uses bg-muted/50, hover uses bg-muted/30
[x] Named function export pattern matches codebase convention
[x] Imports StatusBadge from @/components/runs/StatusBadge, formatDuration from @/lib/time
