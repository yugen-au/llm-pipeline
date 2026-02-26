import type { RunStatus } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

type BadgeConfig = { variant: 'outline'; className: string }

const statusConfig: Record<string, BadgeConfig> = {
  running: {
    variant: 'outline',
    className: 'border-status-running text-status-running',
  },
  completed: {
    variant: 'outline',
    className: 'border-status-completed text-status-completed',
  },
  failed: {
    variant: 'outline',
    className: 'border-status-failed text-status-failed',
  },
  skipped: {
    variant: 'outline',
    className: 'border-status-skipped text-status-skipped',
  },
  pending: {
    variant: 'outline',
    className: 'border-status-pending text-status-pending',
  },
}

interface StatusBadgeProps {
  /** Known statuses get compile-time checking; unknown strings still render via fallback. */
  status: RunStatus | (string & {})
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const config = statusConfig[status] as BadgeConfig | undefined

  if (!config) {
    return <Badge variant="secondary">{status}</Badge>
  }

  return (
    <Badge variant={config.variant} className={cn(config.className)}>
      {status}
    </Badge>
  )
}
