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
  promptTypes: string[]
  pipelineNames: string[]
  selectedType: string
  selectedPipeline: string
  onTypeChange: (v: string) => void
  onPipelineChange: (v: string) => void
  searchText: string
  onSearchChange: (v: string) => void
}

export function PromptFilterBar({
  promptTypes,
  pipelineNames,
  selectedType,
  selectedPipeline,
  onTypeChange,
  onPipelineChange,
  searchText,
  onSearchChange,
}: PromptFilterBarProps) {
  const typeValue = selectedType || ALL_SENTINEL
  const pipelineValue = selectedPipeline || ALL_SENTINEL

  function handleTypeChange(value: string) {
    onTypeChange(value === ALL_SENTINEL ? '' : value)
  }

  function handlePipelineChange(value: string) {
    onPipelineChange(value === ALL_SENTINEL ? '' : value)
  }

  return (
    <div className="flex flex-col gap-2 p-3">
      <Input
        placeholder="Search prompts..."
        value={searchText}
        onChange={(e) => onSearchChange(e.target.value)}
      />
      <div className="flex items-center gap-2">
        <Select value={typeValue} onValueChange={handleTypeChange}>
          <SelectTrigger className="w-full">
            <SelectValue placeholder="All types" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_SENTINEL}>All types</SelectItem>
            {promptTypes.map((type) => (
              <SelectItem key={type} value={type}>
                {type}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={pipelineValue} onValueChange={handlePipelineChange}>
          <SelectTrigger className="w-full">
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
    </div>
  )
}
