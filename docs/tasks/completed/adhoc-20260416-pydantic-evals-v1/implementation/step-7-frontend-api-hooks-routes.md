# IMPLEMENTATION - STEP 7: FRONTEND API HOOKS + ROUTES
**Status:** completed

## Summary
Created TanStack Query hooks for the evals feature: 13 TypeScript interfaces, 5 query hooks, 7 mutation hooks, and centralized query keys. Mirrors reviews.ts patterns.

## Files
**Created:** `llm_pipeline/ui/frontend/src/api/evals.ts`
**Modified:** `llm_pipeline/ui/frontend/src/api/query-keys.ts`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/api/query-keys.ts`
Added `evals` key namespace with `all`, `list`, `detail`, `runs`, `run`, `schema` factories.

### File: `llm_pipeline/ui/frontend/src/api/evals.ts`
New file with:
- 13 interfaces (DatasetListItem, DatasetListResponse, DatasetDetail, CaseItem, RunListItem, RunDetail, CaseResultItem, SchemaResponse, DatasetCreateRequest, DatasetUpdateRequest, CaseCreateRequest, CaseUpdateRequest, TriggerRunRequest, DatasetListParams)
- 5 query hooks: useDatasets, useDataset, useEvalRuns, useEvalRun, useInputSchema
- 7 mutation hooks: useCreateDataset, useUpdateDataset, useDeleteDataset, useCreateCase, useUpdateCase, useDeleteCase, useTriggerEvalRun
- All mutations invalidate relevant query keys and show toast on success
- useUpdateCase accepts `{ caseId, ...fields }` to avoid separate hook per case
- useDeleteCase accepts `caseId: number` as mutation arg

## Decisions
### DatasetUpdateRequest as separate interface
**Choice:** Separate DatasetUpdateRequest (partial name/description) from DatasetCreateRequest
**Rationale:** PUT typically accepts partial updates; avoids requiring target_type/target_name on update

### useUpdateCase mutation arg shape
**Choice:** `{ caseId, ...req }` destructured in mutationFn
**Rationale:** Avoids needing a separate hook instance per case ID while keeping a single mutation hook per dataset

## Verification
[x] tsc --noEmit passes with zero errors
[x] All hooks follow reviews.ts patterns (useQuery/useMutation, toast, invalidation)
[x] apiClient paths use `/evals` (client prepends `/api`)
[x] Query keys added to centralized query-keys.ts
[x] All interfaces match SCOPE specification
