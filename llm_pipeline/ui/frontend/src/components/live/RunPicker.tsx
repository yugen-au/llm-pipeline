import { useState } from 'react'
import { Eye, Loader2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useRuns } from '@/api/runs'
import { useWsStore } from '@/stores/websocket'
import { subscribeToRun } from '@/api/websocket'

interface RunPickerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

function formatRelative(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const secs = Math.floor(diff / 1000)
  if (secs < 60) return `${secs}s ago`
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export function RunPicker({ open, onOpenChange }: RunPickerProps) {
  const [filter, setFilter] = useState('')
  const subscribedRuns = useWsStore((s) => s.subscribedRuns)
  const setFocusedRun = useWsStore((s) => s.setFocusedRun)

  const { data: activeData, isLoading: activeLoading } = useRuns({ status: 'running' as never })
  const { data: recentData, isLoading: recentLoading } = useRuns({ limit: 20 })

  const activeRuns = (activeData?.items ?? []).filter(
    (r) => !filter || r.pipeline_name.includes(filter) || r.run_id.includes(filter),
  )
  const recentRuns = (recentData?.items ?? [])
    .filter((r) => r.status !== 'running')
    .filter((r) => !filter || r.pipeline_name.includes(filter) || r.run_id.includes(filter))
    .slice(0, 15)

  function handleSubscribe(runId: string, pipelineName: string) {
    subscribeToRun(runId, pipelineName)
    setFocusedRun(runId)
  }

  const isLoading = activeLoading || recentLoading

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Subscribe to a run</DialogTitle>
        </DialogHeader>

        <Input
          placeholder="Filter by pipeline name or run ID..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="text-sm"
        />

        <ScrollArea className="max-h-[400px]">
          {isLoading && (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          )}

          {!isLoading && activeRuns.length > 0 && (
            <div className="space-y-1">
              <span className="text-xs font-medium text-muted-foreground px-1">Active</span>
              {activeRuns.map((run) => (
                <RunRow
                  key={run.run_id}
                  runId={run.run_id}
                  pipelineName={run.pipeline_name}
                  status={run.status}
                  startedAt={run.started_at}
                  isSubscribed={run.run_id in subscribedRuns}
                  onSubscribe={() => handleSubscribe(run.run_id, run.pipeline_name)}
                />
              ))}
            </div>
          )}

          {!isLoading && recentRuns.length > 0 && (
            <div className="space-y-1 mt-3">
              <span className="text-xs font-medium text-muted-foreground px-1">Recent</span>
              {recentRuns.map((run) => (
                <RunRow
                  key={run.run_id}
                  runId={run.run_id}
                  pipelineName={run.pipeline_name}
                  status={run.status}
                  startedAt={run.started_at}
                  isSubscribed={run.run_id in subscribedRuns}
                  onSubscribe={() => handleSubscribe(run.run_id, run.pipeline_name)}
                />
              ))}
            </div>
          )}

          {!isLoading && activeRuns.length === 0 && recentRuns.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-8">No runs found</p>
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  )
}

function RunRow({
  runId, pipelineName, status, startedAt, isSubscribed, onSubscribe,
}: {
  runId: string
  pipelineName: string
  status: string
  startedAt: string
  isSubscribed: boolean
  onSubscribe: () => void
}) {
  const statusColor =
    status === 'completed' ? 'default' as const :
    status === 'failed' ? 'destructive' as const :
    'secondary' as const

  return (
    <div className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted/50">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium truncate">{pipelineName}</span>
          <Badge variant={statusColor} className="text-[10px] px-1.5 py-0">{status}</Badge>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="font-mono">{runId.slice(0, 8)}</span>
          <span>{formatRelative(startedAt)}</span>
        </div>
      </div>
      {isSubscribed ? (
        <Badge variant="outline" className="text-[10px] shrink-0">
          <Eye className="h-3 w-3 mr-1" />
          Monitoring
        </Badge>
      ) : (
        <Button size="sm" variant="outline" className="h-7 text-xs shrink-0" onClick={onSubscribe}>
          Monitor
        </Button>
      )}
    </div>
  )
}
