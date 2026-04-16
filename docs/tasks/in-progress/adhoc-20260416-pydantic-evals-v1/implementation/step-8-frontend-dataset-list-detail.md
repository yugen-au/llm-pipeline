# IMPLEMENTATION - STEP 8: FRONTEND DATASET LIST + DETAIL
**Status:** completed

## Summary
Created Evals dataset list page and dataset detail page with tabular case editor, run history tab, and schema-driven typed form fields.

## Files
**Created:** none (files already existed as placeholders from Step 7)
**Modified:**
- llm_pipeline/ui/frontend/src/routes/evals.tsx
- llm_pipeline/ui/frontend/src/routes/evals.$datasetId.tsx
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/routes/evals.tsx`
Replaced placeholder with full dataset list page: table with Name/Target/Cases/Last Run columns, pass rate badge (green >80%, yellow >50%, red <=50%, grey null), New Dataset dialog with name/target_type/target_name fields, row click navigates to detail.

### File: `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.tsx`
Replaced placeholder with full detail page: header with back nav + delete, tabbed layout (Cases + Run History). Cases tab has schema-driven editable table via useInputSchema hook - renders typed fields per JSON Schema property type (string->Input, number->Input[number], boolean->Checkbox, object/array->Textarea). Falls back to raw JSON textarea cards when schema unavailable. Add/save/delete case rows. Run History tab lists runs with status/pass/fail/error counts, Run Evals trigger button.

## Decisions
### Schema field extraction
**Choice:** Extract fields from `schema.json_schema.properties` matching SchemaResponse shape from API hooks
**Rationale:** Matches backend GET /evals/schema response shape defined in Step 7 api/evals.ts

### Case editor state management
**Choice:** Custom useCaseEditor hook with Map<id, CaseRowState> for local edit state, dirty tracking, temp IDs for new rows
**Rationale:** Avoids unnecessary re-renders from global state; supports mixed persisted + unsaved rows; dirty flag enables per-row save buttons

### JSON fallback mode
**Choice:** When schema fetch fails or returns no properties, render each case as a Card with JSON textareas for inputs/expected_output
**Rationale:** Matches PLAN risk mitigation for schema introspection failures

## Verification
[x] tsc --noEmit passes with zero errors
[x] Both routes export createFileRoute with correct paths
[x] All imports reference existing shadcn components and api/evals hooks
[x] Sidebar already had /evals nav item (from Step 7)
[x] Pass rate badge colors match spec: green >80%, yellow >50%, red <=50%, grey null
