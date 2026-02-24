import type { ContextSnapshot } from '@/api/types'
import { ScrollArea } from '@/components/ui/scroll-area'

interface ContextEvolutionProps {
  snapshots: ContextSnapshot[]
  isLoading: boolean
  isError: boolean
}

function SkeletonBlocks() {
  return (
    <div className="space-y-4 p-4">
      {Array.from({ length: 3 }, (_, i) => (
        <div key={i} className="space-y-2">
          <div className="h-5 w-32 animate-pulse rounded bg-muted" />
          <div className="h-24 animate-pulse rounded bg-muted" />
        </div>
      ))}
    </div>
  )
}

export function ContextEvolution({ snapshots, isLoading, isError }: ContextEvolutionProps) {
  if (isLoading) {
    return <SkeletonBlocks />
  }

  if (isError) {
    return (
      <p className="p-4 text-center text-destructive">Failed to load context</p>
    )
  }

  if (snapshots.length === 0) {
    return (
      <p className="p-4 text-center text-muted-foreground">No context snapshots</p>
    )
  }

  return (
    <ScrollArea className="h-full">
      <div className="space-y-0 divide-y">
        {snapshots.map((snapshot) => (
          <div key={snapshot.step_number} className="p-4">
            <h4 className="mb-2 text-sm font-semibold">
              Step {snapshot.step_number} &mdash; {snapshot.step_name}
            </h4>
            <div className="overflow-x-auto">
              <pre className="text-xs font-mono whitespace-pre-wrap break-all rounded bg-muted p-3">
                {JSON.stringify(snapshot.context_snapshot, null, 2)}
              </pre>
            </div>
          </div>
        ))}
      </div>
    </ScrollArea>
  )
}
