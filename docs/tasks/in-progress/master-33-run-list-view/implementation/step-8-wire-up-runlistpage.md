# IMPLEMENTATION - STEP 8: WIRE UP RUNLISTPAGE
**Status:** completed

## Summary
Replaced placeholder IndexPage with RunListPage that wires useRuns, useFiltersStore, FilterBar, RunsTable, and Pagination together. Merges URL search params (page, status) with Zustand filters (pipelineName, startedAfter, startedBefore) into RunListParams for the API query. Status filter changes reset page to 1.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/src/routes/index.tsx
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/routes/index.tsx`
Replaced IndexPage placeholder with full RunListPage wiring all step 3-7 components.

```
# Before
function IndexPage() {
  return (
    <div className="flex min-h-full items-center justify-center">
      <p className="text-muted-foreground">llm-pipeline ui</p>
    </div>
  )
}

# After
function RunListPage() {
  const { page, status } = Route.useSearch()
  const navigate = useNavigate()
  const { pipelineName, startedAfter, startedBefore } = useFiltersStore()

  const params: Partial<RunListParams> = {
    status: status || undefined,
    pipeline_name: pipelineName || undefined,
    started_after: startedAfter || undefined,
    started_before: startedBefore || undefined,
    offset: (page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
  }

  const { data, isLoading, isError } = useRuns(params)

  const handleStatusChange = (newStatus: string) => {
    navigate({ to: '/', search: (prev) => ({ ...prev, status: newStatus, page: 1 }) })
  }

  return (
    <div className="flex flex-col h-full p-6">
      <h1 className="text-2xl font-bold mb-4">Pipeline Runs</h1>
      <FilterBar status={status} onStatusChange={handleStatusChange} />
      <RunsTable runs={data?.items ?? []} isLoading={isLoading} isError={isError} />
      <Pagination total={data?.total ?? 0} page={page} pageSize={PAGE_SIZE} />
    </div>
  )
}
```

Added imports: useNavigate, useRuns, useFiltersStore, RunsTable, FilterBar, Pagination, RunListParams type.
Added PAGE_SIZE = 25 constant.
Changed Route component reference from IndexPage to RunListPage.

## Decisions
### Null-to-undefined conversion via `|| undefined`
**Choice:** Used `|| undefined` to convert null/empty-string filter values
**Rationale:** Zustand store uses `string | null`, URL status defaults to `''`. The `|| undefined` pattern converts both falsy cases so `toSearchParams` omits them from the API request.

### PAGE_SIZE as module-level constant
**Choice:** `const PAGE_SIZE = 25` at module level, not inside component
**Rationale:** Stable reference avoids unnecessary re-renders. Matches plan spec. Used by both offset computation and Pagination prop.

## Verification
[x] TypeScript compiles with no errors (npx tsc --noEmit)
[x] All imports resolve to existing files from steps 3-7
[x] PAGE_SIZE = 25 matches plan spec
[x] Status filter change resets page to 1
[x] data?.items and data?.total use correct response shape (RunListResponse)
[x] Route.useSearch() used for URL params, useFiltersStore() for Zustand state
