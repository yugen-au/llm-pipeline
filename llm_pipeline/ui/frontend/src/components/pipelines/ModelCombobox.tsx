import { useState } from 'react'
import { ChevronDown, X } from 'lucide-react'
import { useAvailableModels } from '@/api/pipelines'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'

// ---------------------------------------------------------------------------
// Provider display
// ---------------------------------------------------------------------------

const PROVIDER_LABELS: Record<string, string> = {
  'anthropic': 'Anthropic',
  'google-gla': 'Google AI',
  'google-vertex': 'Vertex AI',
  'gemini': 'Gemini',
  'groq': 'Groq',
  'mistral': 'Mistral',
  'openai': 'OpenAI',
  'deepseek': 'DeepSeek',
  'cohere': 'Cohere',
  'bedrock': 'Bedrock',
  'grok': 'Grok',
  'xai': 'Grok',
  'meta': 'Meta',
  'cerebras': 'Cerebras',
  'huggingface': 'HuggingFace',
}

/**
 * Split a "provider:name" model string into display-friendly pieces.
 * Default provider is openai when no prefix is present (matches pydantic-ai).
 */
export function formatModel(model: string) {
  const provider = model.includes(':') ? model.split(':')[0] : 'openai'
  const name = model.includes(':') ? model.split(':').slice(1).join(':') : model
  const label = PROVIDER_LABELS[provider] ?? provider
  return { provider: label, name }
}

// ---------------------------------------------------------------------------
// ModelCombobox
// ---------------------------------------------------------------------------

export interface ModelComboboxProps {
  /** Current selected model (null/empty = nothing selected). */
  value: string | null
  /** Fired when user picks a model from the list. */
  onChange: (model: string) => void
  /**
   * If provided, renders an inline X button next to the combobox that calls
   * this handler. Omit to hide the clear affordance entirely.
   */
  onClear?: () => void
  placeholder?: string
  disabled?: boolean
  className?: string
}

/**
 * Pure, controlled model picker. Fetches the available-models map internally
 * (5-minute stale cache) but does no mutations — the caller owns `value` and
 * decides what to do on change/clear.
 *
 * Extracted from the inline selector in StrategySection so it can be reused
 * from the variant editor (or any other "pick a model" UI) without dragging
 * the pipelines-specific StepModelConfig mutations along.
 */
export function ModelCombobox({
  value,
  onChange,
  onClear,
  placeholder = 'Select model...',
  disabled,
  className,
}: ModelComboboxProps) {
  const [open, setOpen] = useState(false)
  const { data: modelsMap } = useAvailableModels()

  const providers = modelsMap ? Object.keys(modelsMap).sort() : []

  return (
    <div className={`flex items-center gap-2 ${className ?? ''}`}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            role="combobox"
            aria-expanded={open}
            disabled={disabled}
            className="max-w-[380px] justify-between font-normal"
          >
            {value ? (
              <span className="flex items-center gap-1.5 truncate">
                <Badge variant="secondary" className="text-xs py-0 shrink-0">
                  {formatModel(value).provider}
                </Badge>
                <span className="font-mono text-xs truncate">
                  {formatModel(value).name}
                </span>
              </span>
            ) : (
              <span className="text-muted-foreground">{placeholder}</span>
            )}
            <ChevronDown className="ml-2 h-3.5 w-3.5 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[380px] p-0" align="start">
          <Command>
            <CommandInput placeholder="Search models..." />
            <CommandList className="max-h-[300px]">
              <CommandEmpty>No models found.</CommandEmpty>
              {providers.map((provider) => (
                <CommandGroup
                  key={provider}
                  heading={PROVIDER_LABELS[provider] ?? provider}
                >
                  {modelsMap![provider].map((model) => {
                    const name = model.includes(':')
                      ? model.split(':').slice(1).join(':')
                      : model
                    return (
                      <CommandItem
                        key={model}
                        value={model}
                        onSelect={() => {
                          onChange(model)
                          setOpen(false)
                        }}
                        className="font-mono text-xs"
                      >
                        {name}
                      </CommandItem>
                    )
                  })}
                </CommandGroup>
              ))}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
      {value && onClear && (
        <Button
          variant="ghost"
          size="sm"
          className="h-7 w-7 p-0"
          onClick={onClear}
          disabled={disabled}
          title="Clear"
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      )}
    </div>
  )
}
