import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { usePipelines } from '@/api/pipelines'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface PipelineSelectorProps {
  selectedPipeline: string | null
  onSelect: (name: string) => void
  disabled?: boolean
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function SelectorSkeleton() {
  return (
    <div className="space-y-1.5">
      <div className="h-4 w-16 animate-pulse rounded bg-muted" />
      <div className="h-9 w-full animate-pulse rounded-md bg-muted" />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PipelineSelector({
  selectedPipeline,
  onSelect,
  disabled = false,
}: PipelineSelectorProps) {
  const { data, isLoading, isError } = usePipelines()

  if (isLoading) {
    return <SelectorSkeleton />
  }

  if (isError) {
    return (
      <p className="text-sm text-destructive">
        Failed to load pipelines.
      </p>
    )
  }

  const pipelines = data?.pipelines ?? []

  if (pipelines.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No pipelines registered
      </p>
    )
  }

  return (
    <div className="space-y-1.5">
      <label htmlFor="pipeline-select" className="text-sm font-medium">
        Pipeline
      </label>
      <Select
        value={selectedPipeline ?? undefined}
        onValueChange={onSelect}
        disabled={disabled}
      >
        <SelectTrigger id="pipeline-select" className="w-full">
          <SelectValue placeholder="Select a pipeline" />
        </SelectTrigger>
        <SelectContent>
          {pipelines.map((p) => (
            <SelectItem key={p.name} value={p.name}>
              {p.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
