import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

const statusConfig: Record<string, { variant: 'outline' | 'destructive' | 'secondary'; className: string }> = {
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
  status: string
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const config = statusConfig[status]

  if (!config) {
    return <Badge variant="secondary">{status}</Badge>
  }

  return (
    <Badge variant={config.variant} className={cn(config.className)}>
      {status}
    </Badge>
  )
}
