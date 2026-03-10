# IMPLEMENTATION - STEP 4: CREATE STRATEGYSECTION & STEPROW
**Status:** completed

## Summary
Created StrategySection and StepRow sub-components that render pipeline strategies and their steps with expandable detail rows, including prompt key click-through links, JSON schema trees, extraction lists, and transformation summaries.

## Files
**Created:** `llm_pipeline/ui/frontend/src/components/pipelines/StrategySection.tsx`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/pipelines/StrategySection.tsx`
New file containing three components:

- **StepRow** -- Expandable step row with local `useState<boolean>(false)`. Collapsed: step_name + class_name + chevron. Expanded: prompt key links via `<Link from="/pipelines" to="/prompts" search={{ key }}>`, instructions/context schemas via `<JsonTree>`, extractions list, transformation summary, action_after.
- **TransformationSummary** -- Private helper rendering class_name, input_type, output_type in mono font.
- **StrategySection** -- Strategy header with display_name, class_name, error badge. If error, shows destructive text instead of steps. Otherwise renders ordered `<ol>` of StepRow.

## Decisions
### Prompt key link pattern
**Choice:** Used `from="/pipelines"` prop on Link to enable cross-route type-safe navigation
**Rationale:** Matches TanStack Router docs pattern for cross-route Links; enables proper search param typing for the target /prompts route

### StepRow in same file
**Choice:** Kept StepRow and TransformationSummary in StrategySection.tsx
**Rationale:** Plan specifies locality ("same file or separate -- keep in StrategySection.tsx for locality"); components are tightly coupled

### Border/divide pattern for step list
**Choice:** Used `<ol className="rounded border divide-y">` with `<li className="border-b last:border-b-0">`
**Rationale:** Consistent with list patterns in sibling components; provides clear visual separation between steps

## Verification
[x] TypeScript compilation passes (`npx tsc --noEmit` -- no errors)
[x] Imports resolve correctly (JsonTree, Badge, Link, chevron icons)
[x] system_key/user_key nullable handling (only renders Link when not null)
[x] strategy.error renders destructive text instead of steps
[x] Prompt key links use correct TanStack Router Link pattern with search params
