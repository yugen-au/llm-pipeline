import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { fallback, zodValidator } from '@tanstack/zod-adapter'
import { z } from 'zod'
import { useRuns } from '@/api/runs'
import { useFiltersStore } from '@/stores/filters'
import { RunsTable } from '@/components/runs/RunsTable'
import { FilterBar } from '@/components/runs/FilterBar'
import { Pagination } from '@/components/runs/Pagination'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { RunListParams } from '@/api/types'

const PAGE_SIZE = 25

const runListSearchSchema = z.object({
  page: fallback(z.number().int().min(1), 1).default(1),
  status: fallback(z.string(), '').default(''),
})

export const Route = createFileRoute('/')({
  validateSearch: zodValidator(runListSearchSchema),
  component: RunListPage,
})

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
    <div className="flex flex-col gap-4 h-full p-6">
      <h1 className="shrink-0 text-2xl font-bold">Pipeline Runs</h1>
      <div className="shrink-0">
        <FilterBar status={status} onStatusChange={handleStatusChange} />
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <RunsTable
          runs={data?.items ?? []}
          isLoading={isLoading}
          isError={isError}
        />
      </ScrollArea>
      <Pagination
        total={data?.total ?? 0}
        page={page}
        pageSize={PAGE_SIZE}
        onPageChange={(newPage) =>
          navigate({ to: '/', search: (prev) => ({ ...prev, page: newPage }) })
        }
      />
    </div>
  )
}
