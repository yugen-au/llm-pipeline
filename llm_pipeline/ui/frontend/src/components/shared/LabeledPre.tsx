import { cn } from '@/lib/utils'

interface LabeledPreProps {
  label: string
  content: string
  className?: string
}

export function LabeledPre({ label, content, className }: LabeledPreProps) {
  return (
    <div className={cn('space-y-1', className)}>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <pre className="whitespace-pre-wrap break-all rounded-md bg-muted p-3 text-xs">
        {content}
      </pre>
    </div>
  )
}
