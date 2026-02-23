import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '@/components/ui/table'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { StatusBadge } from './StatusBadge'
import { formatRelative, formatAbsolute } from '@/lib/time'
import { useNavigate } from '@tanstack/react-router'
import type { RunListItem } from '@/api/types'

const COLUMNS = ['Run ID', 'Pipeline', 'Started', 'Status', 'Steps', 'Duration'] as const
const COLUMN_COUNT = COLUMNS.length

interface RunsTableProps {
  runs: RunListItem[]
  isLoading: boolean
  isError: boolean
}

function formatDuration(ms: number | null): string {
  if (ms == null) return '\u2014'
  return `${(ms / 1000).toFixed(1)}s`
}

function SkeletonCell({ className = 'w-20' }: { className?: string }) {
  return (
    <TableCell>
      <div className={`h-4 animate-pulse rounded bg-muted ${className}`} />
    </TableCell>
  )
}

function SkeletonRows() {
  return (
    <>
      {Array.from({ length: 5 }, (_, i) => (
        <TableRow key={i}>
          <SkeletonCell className="w-20" />
          <SkeletonCell className="w-28" />
          <SkeletonCell className="w-24" />
          <SkeletonCell className="w-16" />
          <SkeletonCell className="w-10" />
          <SkeletonCell className="w-14" />
        </TableRow>
      ))}
    </>
  )
}

export function RunsTable({ runs, isLoading, isError }: RunsTableProps) {
  const navigate = useNavigate()

  return (
    <TooltipProvider>
      <Table>
        <TableHeader>
          <TableRow>
            {COLUMNS.map((col) => (
              <TableHead key={col}>{col}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading ? (
            <SkeletonRows />
          ) : isError ? (
            <TableRow>
              <TableCell colSpan={COLUMN_COUNT} className="text-center text-destructive">
                Failed to load runs
              </TableCell>
            </TableRow>
          ) : runs.length === 0 ? (
            <TableRow>
              <TableCell colSpan={COLUMN_COUNT} className="text-center text-muted-foreground">
                No runs found
              </TableCell>
            </TableRow>
          ) : (
            runs.map((run) => (
              <TableRow
                key={run.run_id}
                className="cursor-pointer hover:bg-muted/50"
                onClick={() =>
                  navigate({
                    to: '/runs/$runId',
                    params: { runId: run.run_id },
                  })
                }
              >
                <TableCell>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <code>{run.run_id.slice(0, 8)}</code>
                    </TooltipTrigger>
                    <TooltipContent>{run.run_id}</TooltipContent>
                  </Tooltip>
                </TableCell>
                <TableCell>{run.pipeline_name}</TableCell>
                <TableCell>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span>{formatRelative(run.started_at)}</span>
                    </TooltipTrigger>
                    <TooltipContent>{formatAbsolute(run.started_at)}</TooltipContent>
                  </Tooltip>
                </TableCell>
                <TableCell>
                  <StatusBadge status={run.status} />
                </TableCell>
                <TableCell>{run.step_count ?? '\u2014'}</TableCell>
                <TableCell>{formatDuration(run.total_time_ms)}</TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </TooltipProvider>
  )
}
