import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { fallback, zodValidator } from '@tanstack/zod-adapter'
import { z } from 'zod'
import { usePipelines } from '@/api/pipelines'
import { PipelineList } from '@/components/pipelines/PipelineList'
import { PipelineDetail } from '@/components/pipelines/PipelineDetail'

// ---------------------------------------------------------------------------
// Search params schema
// ---------------------------------------------------------------------------

const pipelinesSearchSchema = z.object({
  pipeline: fallback(z.string(), '').default(''),
})

export const Route = createFileRoute('/pipelines')({
  validateSearch: zodValidator(pipelinesSearchSchema),
  component: PipelinesPage,
})

// ---------------------------------------------------------------------------
// PipelinesPage
// ---------------------------------------------------------------------------

function PipelinesPage() {
  const { pipeline } = Route.useSearch()
  const navigate = useNavigate({ from: '/pipelines' })

  const pipelines = usePipelines()

  function handleSelect(name: string) {
    navigate({ search: { pipeline: name } })
  }

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <h1 className="text-2xl font-semibold text-card-foreground">Pipelines</h1>

      <div className="flex min-h-0 flex-1 gap-4">
        {/* Left panel: pipeline list */}
        <div className="flex w-80 shrink-0 flex-col overflow-hidden rounded-xl border">
          <PipelineList
            pipelines={pipelines.data?.pipelines ?? []}
            selectedName={pipeline}
            onSelect={handleSelect}
            isLoading={pipelines.isLoading}
            error={pipelines.error}
          />
        </div>

        {/* Right panel: pipeline detail */}
        <div className="flex-1 overflow-auto rounded-xl border">
          <PipelineDetail pipelineName={pipeline || null} />
        </div>
      </div>
    </div>
  )
}
