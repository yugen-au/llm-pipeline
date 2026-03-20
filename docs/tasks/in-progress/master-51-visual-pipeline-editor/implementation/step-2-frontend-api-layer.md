# IMPLEMENTATION - STEP 2: FRONTEND API LAYER
**Status:** completed

## Summary
Created TypeScript interfaces matching all backend Pydantic models from editor.py and implemented 7 TanStack Query hooks (3 queries + 4 mutations) in src/api/editor.ts. Added editor query key section to query-keys.ts.

## Files
**Created:** llm_pipeline/ui/frontend/src/api/editor.ts
**Modified:** llm_pipeline/ui/frontend/src/api/query-keys.ts
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/api/query-keys.ts`
Added editor section to queryKeys factory with keys for availableSteps, drafts, and draft(id).

```
# Before
  creator: {
    all: ['creator'] as const,
    drafts: () => ['creator', 'drafts'] as const,
    draft: (id: number) => ['creator', 'drafts', id] as const,
  },
} as const

# After
  creator: { ... },
  editor: {
    all: ['editor'] as const,
    availableSteps: () => ['editor', 'available-steps'] as const,
    drafts: () => ['editor', 'drafts'] as const,
    draft: (id: number) => ['editor', 'drafts', id] as const,
  },
} as const
```

### File: `llm_pipeline/ui/frontend/src/api/editor.ts`
New file with 11 exported TypeScript interfaces and 7 exported hooks:

**Interfaces:** EditorStep, EditorStrategy, CompileRequest, CompileError, CompileResponse, AvailableStep, AvailableStepsResponse, DraftPipelineItem, DraftPipelineDetail, DraftPipelineListResponse, CreateDraftPipelineRequest, UpdateDraftPipelineRequest

**Query hooks:**
- `useAvailableSteps()` - GET /editor/available-steps, staleTime 30s
- `useDraftPipelines()` - GET /editor/drafts, staleTime 30s
- `useDraftPipeline(id)` - GET /editor/drafts/{id}, enabled when id != null

**Mutation hooks:**
- `useCompilePipeline()` - POST /editor/compile, no cache invalidation
- `useCreateDraftPipeline()` - POST /editor/drafts, invalidates drafts list
- `useUpdateDraftPipeline()` - PATCH /editor/drafts/{id}, invalidates draft detail + list
- `useDeleteDraftPipeline()` - DELETE /editor/drafts/{id}, invalidates drafts list

## Decisions
### DELETE mutation uses raw fetch instead of apiClient
**Choice:** useDeleteDraftPipeline uses raw fetch() instead of apiClient wrapper
**Rationale:** Backend returns 204 No Content with empty body. apiClient unconditionally calls response.json() which throws on empty bodies. Raw fetch matches the pattern used by useRenameDraft in creator.ts for special response handling. ApiError is imported from types.ts for error consistency.

### datetime fields typed as string
**Choice:** created_at and updated_at typed as `string` not `Date`
**Rationale:** Matches existing pattern in creator.ts (DraftItem uses string for dates). JSON serialization from backend produces ISO strings; parsing to Date is a presentation concern, not an API layer concern.

### UpdateDraftPipelineRequest mutation vars include id
**Choice:** mutationFn accepts `{ id: number } & UpdateDraftPipelineRequest` intersection
**Rationale:** The id is needed for both the URL path and for onSuccess cache invalidation (via vars.id). Intersection type keeps the API clean -- callers pass a single object with id + optional name/structure.

## Verification
[x] TypeScript compiles with zero errors (npx tsc --noEmit)
[x] All 12 interfaces match backend Pydantic models in editor.py
[x] All 7 hooks match PLAN.md Step 2 specification
[x] Query keys follow existing hierarchical pattern from query-keys.ts
[x] Mutation cache invalidation targets correct query keys per PLAN.md
[x] staleTime 30s on queries per PLAN.md spec
[x] useDraftPipeline disabled when id is null per PLAN.md spec
[x] useCompilePipeline has no cache invalidation per PLAN.md spec (compile is ephemeral)
[x] DELETE handles 204 No Content correctly (raw fetch, no response.json())
[x] Follows existing codebase patterns from creator.ts and pipelines.ts
