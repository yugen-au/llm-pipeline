import type { PipelineListItem } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PipelineListProps {
  pipelines: PipelineListItem[]
  selectedName: string
  onSelect: (name: string) => void
  isLoading: boolean
  error: Error | null
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function SkeletonRows() {
  return (
    <div className="space-y-2 p-2">
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} className="h-12 animate-pulse rounded bg-muted" />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// PipelineList component
// ---------------------------------------------------------------------------

export function PipelineList({
  pipelines,
  selectedName,
  onSelect,
  isLoading,
  error,
}: PipelineListProps) {
  if (isLoading) {
    return (
      <ScrollArea className="min-h-0 flex-1">
        <SkeletonRows />
      </ScrollArea>
    )
  }

  if (error) {
    return (
      <p className="p-4 text-sm text-destructive">Failed to load pipelines</p>
    )
  }

  if (pipelines.length === 0) {
    return (
      <p className="p-4 text-sm text-muted-foreground">
        No pipelines found
      </p>
    )
  }

  return (
    <ScrollArea className="min-h-0 flex-1">
      <div className="space-y-1 p-2">
        {pipelines.map((pipeline) => {
          const isSelected = selectedName === pipeline.name
          return (
            <button
              key={pipeline.name}
              type="button"
              className={cn(
                'flex w-full items-center gap-3 rounded-md px-3 py-2 text-left transition-colors',
                'cursor-pointer hover:bg-muted/30',
                isSelected && 'bg-accent',
              )}
              onClick={() => onSelect(pipeline.name)}
            >
              <span className="min-w-0 flex-1 truncate text-sm font-medium">
                {pipeline.name}
              </span>
              <Badge
                variant={pipeline.status === 'published' ? 'default' : 'outline'}
                className={cn(
                  'text-[10px] px-1.5 py-0',
                  pipeline.status === 'draft' && 'text-muted-foreground',
                )}
              >
                {pipeline.status ?? 'draft'}
              </Badge>
              {pipeline.error != null ? (
                <Badge variant="destructive">error</Badge>
              ) : (
                pipeline.step_count != null && (
                  <Badge variant="outline">
                    {pipeline.step_count} {pipeline.step_count === 1 ? 'step' : 'steps'}
                  </Badge>
                )
              )}
              {pipeline.strategy_count != null && (
                <Badge variant="secondary">
                  {pipeline.strategy_count} {pipeline.strategy_count === 1 ? 'strategy' : 'strategies'}
                </Badge>
              )}
            </button>
          )
        })}
      </div>
    </ScrollArea>
  )
}
