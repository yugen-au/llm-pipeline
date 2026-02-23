import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { fallback, zodValidator } from '@tanstack/zod-adapter'
import { z } from 'zod'
import { useRuns } from '@/api/runs'
import { useFiltersStore } from '@/stores/filters'
import { RunsTable } from '@/components/runs/RunsTable'
import { FilterBar } from '@/components/runs/FilterBar'
import { Pagination } from '@/components/runs/Pagination'
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
    <div className="flex flex-col h-full p-6">
      <h1 className="text-2xl font-bold mb-4">Pipeline Runs</h1>
      <FilterBar status={status} onStatusChange={handleStatusChange} />
      <RunsTable
        runs={data?.items ?? []}
        isLoading={isLoading}
        isError={isError}
      />
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
