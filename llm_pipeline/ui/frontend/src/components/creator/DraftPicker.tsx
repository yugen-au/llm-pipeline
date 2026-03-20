import { Plus } from 'lucide-react'
import type { DraftItem } from '@/api/creator'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import { formatRelative } from '@/lib/time'

interface DraftPickerProps {
  drafts: DraftItem[]
  isLoading: boolean
  selectedDraftId: number | null
  onSelect: (draft: DraftItem) => void
  onNew: () => void
}

const STATUS_VARIANT: Record<string, 'secondary' | 'default' | 'destructive'> = {
  draft: 'secondary',
  tested: 'secondary',
  accepted: 'default',
  error: 'destructive',
}

function statusVariant(status: string) {
  return STATUS_VARIANT[status] ?? 'secondary'
}

export function DraftPicker({
  drafts,
  isLoading,
  selectedDraftId,
  onSelect,
  onNew,
}: DraftPickerProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between px-1">
        <span className="text-xs font-medium text-muted-foreground">
          Drafts
        </span>
        <Button variant="ghost" size="icon-xs" onClick={onNew} title="New draft">
          <Plus className="size-3" />
        </Button>
      </div>

      <ScrollArea className="max-h-[40vh]" thin>
        {isLoading && drafts.length === 0 ? (
          <div className="space-y-1.5 px-1">
            {Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="h-10 animate-pulse rounded-md bg-muted"
              />
            ))}
          </div>
        ) : drafts.length === 0 ? (
          <p className="px-1 py-2 text-xs text-muted-foreground">
            No drafts yet
          </p>
        ) : (
          <div className="space-y-0.5 px-0.5">
            {drafts.map((draft) => (
              <button
                key={draft.id}
                type="button"
                onClick={() => onSelect(draft)}
                className={cn(
                  'flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left transition-colors',
                  'hover:bg-accent',
                  selectedDraftId === draft.id &&
                    'bg-accent ring-1 ring-ring/20',
                )}
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate font-mono text-xs">{draft.name}</p>
                  <p className="text-[10px] text-muted-foreground">
                    {formatRelative(draft.updated_at)}
                  </p>
                </div>
                <Badge
                  variant={statusVariant(draft.status)}
                  className="shrink-0 text-[10px] px-1.5 py-0"
                >
                  {draft.status}
                </Badge>
              </button>
            ))}
          </div>
        )}
      </ScrollArea>
    </div>
  )
}
