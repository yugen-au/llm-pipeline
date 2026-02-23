import type { RunStatus } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

type BadgeConfig = { variant: 'outline' | 'destructive' | 'secondary'; className: string }

const statusConfig: Record<RunStatus, BadgeConfig> = {
  running: {
    variant: 'outline',
    className: 'border-amber-500 text-amber-600 dark:text-amber-400',
  },
  completed: {
    variant: 'outline',
    className: 'border-green-500 text-green-600 dark:text-green-400',
  },
  failed: {
    variant: 'destructive',
    className: '',
  },
}

interface StatusBadgeProps {
  /** Known statuses get compile-time checking; unknown strings still render via fallback. */
  status: RunStatus | (string & {})
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const config = statusConfig[status as RunStatus] as BadgeConfig | undefined

  if (!config) {
    return <Badge variant="secondary">{status}</Badge>
  }

  return (
    <Badge variant={config.variant} className={cn(config.className)}>
      {status}
    </Badge>
  )
}
