import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

/** Radix Select requires non-empty string values; sentinel maps to '' externally */
const ALL_SENTINEL = '__all'

interface PromptFilterBarProps {
  pipelineNames: string[]
  selectedPipeline: string
  onPipelineChange: (v: string) => void
  searchText: string
  onSearchChange: (v: string) => void
}

export function PromptFilterBar({
  pipelineNames,
  selectedPipeline,
  onPipelineChange,
  searchText,
  onSearchChange,
}: PromptFilterBarProps) {
  const pipelineValue = selectedPipeline || ALL_SENTINEL

  function handlePipelineChange(value: string) {
    onPipelineChange(value === ALL_SENTINEL ? '' : value)
  }

  return (
    <div className="flex flex-col gap-2 p-3">
      <Input
        aria-label="Search prompts"
        placeholder="Search prompts..."
        value={searchText}
        onChange={(e) => onSearchChange(e.target.value)}
      />
      <Select value={pipelineValue} onValueChange={handlePipelineChange}>
        <SelectTrigger aria-label="Filter by pipeline" className="w-full">
          <SelectValue placeholder="All pipelines" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL_SENTINEL}>All pipelines</SelectItem>
          {pipelineNames.map((name) => (
            <SelectItem key={name} value={name}>
              {name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
