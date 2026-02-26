# IMPLEMENTATION - STEP 1: EXTEND API LAYER
**Status:** completed

## Summary
Added `queryKeys.prompts.detail(key)` factory and `usePromptDetail(promptKey)` hook to the existing API layer. This provides the data-fetching foundation for the PromptViewer component (Step 4).

## Files
**Created:** none
**Modified:** `llm_pipeline/ui/frontend/src/api/query-keys.ts`, `llm_pipeline/ui/frontend/src/api/prompts.ts`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/api/query-keys.ts`
Added `detail` factory to the `prompts` query key object, following the existing `runs.detail` and `pipelines.detail` pattern.

```
# Before
prompts: {
  all: ['prompts'] as const,
  list: (filters: Partial<PromptListParams>) => ['prompts', filters] as const,
},

# After
prompts: {
  all: ['prompts'] as const,
  list: (filters: Partial<PromptListParams>) => ['prompts', filters] as const,
  detail: (key: string) => ['prompts', key] as const,
},
```

### File: `llm_pipeline/ui/frontend/src/api/prompts.ts`
Added `PromptDetail` type import and `usePromptDetail` hook. Hook uses `enabled: Boolean(promptKey)` to skip fetch when no key is selected. Default 30s staleTime inherited from global QueryClient config.

```
# Before
import type { PromptListParams, PromptListResponse } from './types'
// (only usePrompts hook)

# After
import type { PromptDetail, PromptListParams, PromptListResponse } from './types'
// (usePrompts hook unchanged, plus:)

export function usePromptDetail(promptKey: string) {
  return useQuery({
    queryKey: queryKeys.prompts.detail(promptKey),
    queryFn: () => apiClient<PromptDetail>('/prompts/' + promptKey),
    enabled: Boolean(promptKey),
  })
}
```

## Decisions
None -- implementation followed plan exactly.

## Verification
[x] `detail` factory added after `list` in `queryKeys.prompts`
[x] `usePromptDetail` uses `queryKeys.prompts.detail(promptKey)` as query key
[x] `enabled: Boolean(promptKey)` disables query when key is empty
[x] No custom staleTime (inherits default 30s)
[x] `PromptDetail` type imported from `./types`
[x] ESLint passes (no semicolons, single quotes, named function)
[x] TypeScript compiles with no errors
