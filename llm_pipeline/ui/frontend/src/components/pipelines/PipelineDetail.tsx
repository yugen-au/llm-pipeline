import { usePipeline } from '@/api/pipelines'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { JsonViewer } from '@/components/JsonViewer'
import { StrategySection } from '@/components/pipelines/StrategySection'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PipelineDetailProps {
  pipelineName: string | null
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function DetailSkeleton() {
  return (
    <div className="space-y-4 p-4">
      <div className="h-7 w-48 animate-pulse rounded bg-muted" />
      <div className="h-4 w-32 animate-pulse rounded bg-muted" />
      <div className="h-40 animate-pulse rounded bg-muted" />
    </div>
  )
}

// ---------------------------------------------------------------------------
// PipelineDetail component
// ---------------------------------------------------------------------------

export function PipelineDetail({ pipelineName }: PipelineDetailProps) {
  const { data, isLoading, error } = usePipeline(pipelineName ?? '')

  // Empty state -- no pipeline selected
  if (!pipelineName) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-muted-foreground">Select a pipeline to view details</p>
      </div>
    )
  }

  if (isLoading) {
    return (
      <ScrollArea className="h-full">
        <DetailSkeleton />
      </ScrollArea>
    )
  }

  if (error || !data) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-destructive">Failed to load pipeline</p>
      </div>
    )
  }

  return (
    <ScrollArea className="h-full">
      <div className="space-y-6 p-4">
        {/* Header */}
        <div className="space-y-3">
          <h2 className="text-xl font-semibold">{data.pipeline_name}</h2>

          {/* Registry models */}
          {data.registry_models.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-muted-foreground">Models:</span>
              {data.registry_models.map((model) => (
                <Badge key={model} variant="secondary">
                  {model}
                </Badge>
              ))}
            </div>
          )}

          {/* Execution order */}
          {data.execution_order.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-muted-foreground">Execution order:</span>
              {data.execution_order.map((name, i) => (
                <Badge key={name} variant="outline">
                  {i + 1}. {name}
                </Badge>
              ))}
            </div>
          )}

          {/* Pipeline input schema */}
          {data.pipeline_input_schema && (
            <div className="space-y-1">
              <span className="text-xs font-medium text-muted-foreground">
                Input Schema
              </span>
              <div className="rounded border p-2">
                <JsonViewer data={data.pipeline_input_schema} />
              </div>
            </div>
          )}
        </div>

        {/* Strategies */}
        <div className="space-y-6">
          {data.strategies.map((strategy) => (
            <StrategySection
              key={strategy.name}
              strategy={strategy}
              pipelineName={data.pipeline_name}
            />
          ))}
        </div>
      </div>
    </ScrollArea>
  )
}
