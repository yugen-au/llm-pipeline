# IMPLEMENTATION - STEP 3: CREATOR API LAYER
**Status:** completed

## Summary
Added creator query keys to the centralized query key factory and created the full `src/api/creator.ts` module with TypeScript interfaces matching all backend Pydantic models and 6 React Query hooks (3 mutations, 1 rename mutation, 2 queries).

## Files
**Created:** `llm_pipeline/ui/frontend/src/api/creator.ts`
**Modified:** `llm_pipeline/ui/frontend/src/api/query-keys.ts`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/api/query-keys.ts`
Added `creator` section to queryKeys object with hierarchical keys for cache invalidation.
```
# Before
  pipelines: { ... },
} as const

# After
  pipelines: { ... },
  creator: {
    all: ['creator'] as const,
    drafts: () => ['creator', 'drafts'] as const,
    draft: (id: number) => ['creator', 'drafts', id] as const,
  },
} as const
```

### File: `llm_pipeline/ui/frontend/src/api/creator.ts`
New file with:
- 10 TypeScript interfaces: GenerateRequest, GenerateResponse, TestRequest, TestResponse, AcceptRequest, AcceptResponse, DraftItem, DraftDetail, DraftListResponse, RenameRequest
- `useGenerateStep()` mutation: POST /creator/generate, invalidates drafts list
- `useTestDraft(draftId)` mutation: POST /creator/test/{draftId}, invalidates draft detail
- `useAcceptDraft(draftId)` mutation: POST /creator/accept/{draftId}, invalidates drafts + draft detail
- `useRenameDraft()` mutation: PATCH /creator/drafts/{draftId}, invalidates draft + drafts, uses `satisfies RenameRequest` for type safety
- `useDrafts()` query: GET /creator/drafts, staleTime 30_000
- `useDraft(draftId)` query: GET /creator/drafts/{draftId}, enabled when draftId != null, dynamic staleTime (Infinity for accepted, 10s for active)

## Decisions
### Mutation variable shape for useRenameDraft
**Choice:** Combined `{ draftId: number; name: string }` variable object instead of separate draftId param + body
**Rationale:** useMutation only accepts a single argument to mutationFn. Combining draftId and name into one object allows the onSuccess handler to access draftId for cache invalidation via the `variables` param.

### DraftDetail.generated_code type
**Choice:** `Record<string, string>` (not `dict` / `Record<string, unknown>`)
**Rationale:** Backend stores artifact filenames as keys and Python source code as string values. Using `string` value type gives downstream editor components correct types without casting.

## Verification
[x] TypeScript compilation passes (`npx tsc --noEmit` - zero errors)
[x] All 6 hooks match backend endpoint signatures in creator.py
[x] Query key hierarchy follows existing pattern (runs, prompts, pipelines)
[x] Cache invalidation patterns match existing codebase (useCreateRun pattern)
[x] apiClient usage matches existing hooks (client.ts fetch wrapper)
[x] staleTime/enabled patterns match existing hooks (useDraft mirrors useRun dynamic staleTime)

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] 409 rename suggested_name silently lost through apiClient (MEDIUM)

### Changes Made
#### File: `llm_pipeline/ui/frontend/src/api/types.ts`
Added `RenameConflictError` subclass of `ApiError` that carries `suggestedName`.
```
# Before
(only ApiError class)

# After
export class RenameConflictError extends ApiError {
  readonly suggestedName: string
  constructor(detail: string, suggestedName: string) {
    super(409, detail)
    this.name = 'RenameConflictError'
    this.suggestedName = suggestedName
  }
}
```

#### File: `llm_pipeline/ui/frontend/src/api/creator.ts`
Replaced `useRenameDraft` mutationFn: uses raw `fetch` instead of `apiClient` to intercept 409 before the response body is stripped. On 409, parses full JSON body and throws `RenameConflictError` with `suggested_name`. Non-409 errors still throw `ApiError` for consistency.
```
# Before
mutationFn: (vars) => apiClient<DraftDetail>('/creator/drafts/' + vars.draftId, { method: 'PATCH', ... })

# After
mutationFn: async (vars) => {
  const response = await fetch('/api/creator/drafts/' + vars.draftId, { method: 'PATCH', ... })
  if (response.status === 409) {
    const body = await response.json()
    throw new RenameConflictError(body.detail ?? 'name_conflict', body.suggested_name ?? vars.name)
  }
  if (!response.ok) { ... throw new ApiError(...) }
  return response.json()
}
```

#### File: `llm_pipeline/ui/frontend/src/routes/creator.tsx`
Replaced `handleRename` onError: uses `instanceof RenameConflictError` instead of broken `JSON.parse(error.detail)` approach.
```
# Before
if (error instanceof ApiError && error.status === 409) {
  try { const body = JSON.parse(error.detail) ... } catch { setRenameError('Name already taken') }
}

# After
if (error instanceof RenameConflictError) {
  setRenameError(`Name conflict. Suggested: ${error.suggestedName}`)
}
```

### Verification
[x] TypeScript compilation passes (`npx tsc --noEmit` - zero errors)
[x] RenameConflictError extends ApiError (existing `instanceof ApiError` checks still match)
[x] 409 response body preserved: both `detail` and `suggested_name` fields accessible
[x] Non-409 errors still throw ApiError via fallback path in mutationFn
[x] creator.tsx handleRename uses clean `instanceof` check instead of fragile JSON.parse
