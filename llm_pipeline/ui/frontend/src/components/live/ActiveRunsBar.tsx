import { X, Plus, Loader2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useWsStore } from '@/stores/websocket'
import { unsubscribeFromRun } from '@/api/websocket'
import { cn } from '@/lib/utils'

interface ActiveRunsBarProps {
  onOpenPicker: () => void
}

export function ActiveRunsBar({ onOpenPicker }: ActiveRunsBarProps) {
  const subscribedRuns = useWsStore((s) => s.subscribedRuns)
  const focusedRunId = useWsStore((s) => s.focusedRunId)
  const setFocusedRun = useWsStore((s) => s.setFocusedRun)

  const entries = Object.entries(subscribedRuns)

  return (
    <div className="flex items-center gap-2 overflow-x-auto border-b px-3 py-2">
      <span className="text-xs text-muted-foreground shrink-0">Monitoring:</span>

      {entries.length === 0 && (
        <span className="text-xs text-muted-foreground">No runs subscribed</span>
      )}

      {entries.map(([runId, info]) => {
        const isFocused = focusedRunId === runId
        const statusColor =
          info.status === 'completed' ? 'bg-green-500' :
          info.status === 'failed' ? 'bg-red-500' :
          info.status === 'running' ? 'bg-blue-500' :
          'bg-muted-foreground'

        return (
          <button
            key={runId}
            type="button"
            className={cn(
              'flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors shrink-0',
              'hover:bg-muted/50 cursor-pointer',
              isFocused && 'ring-2 ring-ring bg-accent',
            )}
            onClick={() => setFocusedRun(runId)}
          >
            <span className={cn('h-2 w-2 rounded-full shrink-0', statusColor)} />
            <span className="font-medium truncate max-w-[120px]">{info.pipelineName}</span>
            <span className="text-muted-foreground">{runId.slice(0, 8)}</span>
            {info.isReplaying && (
              <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
            )}
            <button
              type="button"
              className="ml-0.5 rounded-full p-0.5 hover:bg-destructive/20 transition-colors"
              onClick={(e) => { e.stopPropagation(); unsubscribeFromRun(runId) }}
            >
              <X className="h-3 w-3" />
            </button>
          </button>
        )
      })}

      <Button
        variant="outline"
        size="icon"
        className="h-7 w-7 shrink-0 rounded-full"
        onClick={onOpenPicker}
      >
        <Plus className="h-3.5 w-3.5" />
      </Button>
    </div>
  )
}
