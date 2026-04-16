# IMPLEMENTATION - STEP 9: FRONTEND RUN DETAIL + SIDEBAR
**Status:** completed

## Summary
Created eval run detail page with pass/fail grid per evaluator per case, expandable rows for output/error inspection, and aggregate stat cards. Added Evals nav entry to sidebar with FlaskConical icon. Created placeholder evals.$datasetId route for back-link resolution. Updated routeTree.gen.ts with all three evals routes.

## Files
**Created:** llm_pipeline/ui/frontend/src/routes/evals.$datasetId.runs.$runId.tsx, llm_pipeline/ui/frontend/src/routes/evals.$datasetId.tsx
**Modified:** llm_pipeline/ui/frontend/src/components/Sidebar.tsx, llm_pipeline/ui/frontend/src/routeTree.gen.ts
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.runs.$runId.tsx`
New run detail page with:
- Header: breadcrumb back to dataset, status badge (color-coded), timestamps
- Stat cards: total/passed/failed/errored counts
- Results table: rows=cases, columns=evaluator names (extracted from first result's evaluator_scores keys) + overall
- Cell rendering: bool->green check/red X, float->colored number (green>=0.8, yellow>=0.5, red<0.5), null->grey dash
- Overall column uses backend `passed` field
- Expandable rows: click to show output_data (JsonViewer) and error_message

### File: `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.tsx`
Placeholder route for dataset detail (step 14 scope). Minimal component so back-link from run detail type-checks.

### File: `llm_pipeline/ui/frontend/src/components/Sidebar.tsx`
Added FlaskConical import, added `{ to: '/evals', label: 'Evals', icon: FlaskConical }` after Reviews in navItems.

### File: `llm_pipeline/ui/frontend/src/routeTree.gen.ts`
Added /evals, /evals/$datasetId, /evals/$datasetId/runs/$runId routes to all type interfaces and route tree.

## Decisions
### Placeholder evals.$datasetId route
**Choice:** Created minimal placeholder since step 14 (dataset detail) is out of scope
**Rationale:** Run detail page links back to /evals/$datasetId; route must exist for type-safe Link to compile

### Score rendering thresholds
**Choice:** green>=0.8, yellow>=0.5, red<0.5 for numeric evaluator scores
**Rationale:** Common convention for pass/warn/fail thresholds; scannable at a glance

### Overall column uses backend `passed` field
**Choice:** Use CaseResultItem.passed directly instead of re-deriving from evaluator_scores
**Rationale:** Backend already computes this; avoids client-side logic drift

## Verification
[x] tsc --noEmit passes with zero errors
[x] Sidebar includes Evals entry after Reviews
[x] Run detail route registered at /evals/$datasetId/runs/$runId
[x] All evals routes in routeTree.gen.ts type interfaces
