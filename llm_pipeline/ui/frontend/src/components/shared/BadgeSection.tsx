import type { ReactNode } from 'react'

interface BadgeSectionProps {
  badge: ReactNode
  children: ReactNode
}

export function BadgeSection({ badge, children }: BadgeSectionProps) {
  return (
    <div className="space-y-1">
      {badge}
      {children}
    </div>
  )
}
