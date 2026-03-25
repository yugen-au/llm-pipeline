import type { ReactNode } from 'react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'

interface TabScrollAreaProps {
  children: ReactNode
  className?: string
}

export function TabScrollArea({ children, className }: TabScrollAreaProps) {
  return (
    <ScrollArea className={cn('h-[calc(100vh-220px)]', className)}>
      {children}
    </ScrollArea>
  )
}
