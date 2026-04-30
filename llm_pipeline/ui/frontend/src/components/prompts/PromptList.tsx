import type { Prompt } from '@/api/types'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PromptListProps {
  prompts: Prompt[]
  selectedKey: string
  onSelect: (key: string) => void
  isLoading: boolean
  error: Error | null
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function SkeletonRows() {
  return (
    <div className="space-y-2 p-2">
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} className="h-12 animate-pulse rounded bg-muted" />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// PromptList component
// ---------------------------------------------------------------------------

export function PromptList({
  prompts,
  selectedKey,
  onSelect,
  isLoading,
  error,
}: PromptListProps) {
  if (isLoading) {
    return (
      <ScrollArea className="min-h-0 flex-1">
        <SkeletonRows />
      </ScrollArea>
    )
  }

  if (error) {
    return (
      <p className="p-4 text-sm text-destructive">Failed to load prompts</p>
    )
  }

  if (prompts.length === 0) {
    return (
      <p className="p-4 text-sm text-muted-foreground">
        No prompts match filters
      </p>
    )
  }

  return (
    <ScrollArea className="min-h-0 flex-1">
      <div className="space-y-1 p-2">
        {prompts.map((prompt) => {
          const isSelected = selectedKey === prompt.name
          const label = prompt.metadata.display_name ?? prompt.name
          return (
            <button
              key={prompt.name}
              type="button"
              className={cn(
                'flex w-full items-center gap-3 rounded-md px-3 py-2 text-left transition-colors',
                'cursor-pointer hover:bg-muted/30',
                isSelected && 'bg-accent',
              )}
              onClick={() => onSelect(prompt.name)}
            >
              <span className="min-w-0 flex-1 truncate text-sm font-medium">
                {label}
              </span>
            </button>
          )
        })}
      </div>
    </ScrollArea>
  )
}
