import { cn } from '@/lib/utils'

interface SkeletonLineProps {
  width?: string
  className?: string
}

export function SkeletonLine({ width, className }: SkeletonLineProps) {
  return (
    <div
      className={cn('h-4 animate-pulse rounded bg-muted', className)}
      style={width ? { width } : undefined}
    />
  )
}

interface SkeletonBlockProps {
  className?: string
}

export function SkeletonBlock({ className }: SkeletonBlockProps) {
  return (
    <div className={cn('h-20 animate-pulse rounded bg-muted', className)} />
  )
}
