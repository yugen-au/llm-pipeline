import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

/** Radix Select requires non-empty string values; sentinel maps to '' externally */
const ALL_SENTINEL = '__all'

const STATUS_OPTIONS = [
  { value: ALL_SENTINEL, label: 'All' },
  { value: 'running', label: 'Running' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
] as const

interface FilterBarProps {
  status: string
  onStatusChange: (status: string) => void
}

export function FilterBar({ status, onStatusChange }: FilterBarProps) {
  const selectValue = status || ALL_SENTINEL

  function handleChange(value: string) {
    onStatusChange(value === ALL_SENTINEL ? '' : value)
  }

  return (
    <div className="flex items-center gap-3">
      <label htmlFor="status-filter" className="text-sm font-medium">
        Status
      </label>
      <Select value={selectValue} onValueChange={handleChange}>
        <SelectTrigger id="status-filter" className="w-[160px]">
          <SelectValue placeholder="All" />
        </SelectTrigger>
        <SelectContent>
          {STATUS_OPTIONS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
