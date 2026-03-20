import { usePromptDetail } from '@/api/prompts'
import type { PromptVariant } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'

// ---------------------------------------------------------------------------
// Variable highlighting
// ---------------------------------------------------------------------------

/**
 * Split prompt content on variable placeholders and wrap matches in
 * highlighted spans. Regex matches backend extract_variables_from_content
 * pattern in llm_pipeline/prompts/loader.py (no dots).
 */
function highlightVariables(content: string): React.ReactNode[] {
  const parts = content.split(/(\{[a-zA-Z_][a-zA-Z0-9_]*\})/g)
  return parts.map((part, i) =>
    /^\{[a-zA-Z_][a-zA-Z0-9_]*\}$/.test(part) ? (
      <span key={i} className="rounded bg-primary/20 px-0.5 text-primary">
        {part}
      </span>
    ) : (
      part
    ),
  )
}

// ---------------------------------------------------------------------------
// Variant renderer
// ---------------------------------------------------------------------------

function VariantSection({ variant }: { variant: PromptVariant }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Badge variant="secondary">{variant.prompt_type}</Badge>
        <span className="text-xs text-muted-foreground">v{variant.version}</span>
      </div>

      {variant.description && (
        <p className="text-sm text-muted-foreground">{variant.description}</p>
      )}

      {variant.required_variables && variant.required_variables.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {variant.required_variables.map((v) => (
            <Badge key={v} variant="outline" className="text-xs">
              {v}
            </Badge>
          ))}
        </div>
      )}

      <pre className="whitespace-pre-wrap break-all rounded-md bg-muted p-3 font-mono text-xs">
        {highlightVariables(variant.content)}
      </pre>
    </div>
  )
}

// ---------------------------------------------------------------------------
// PromptViewer
// ---------------------------------------------------------------------------

interface PromptViewerProps {
  promptKey: string | null
}

export function PromptViewer({ promptKey }: PromptViewerProps) {
  const { data, isLoading, error } = usePromptDetail(promptKey ?? '')

  // Empty state -- nothing selected
  if (!promptKey) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-muted-foreground">Select a prompt to view details</p>
      </div>
    )
  }

  // Loading state
  if (isLoading) {
    return (
      <div className="space-y-4 p-4">
        <div className="h-7 w-48 animate-pulse rounded bg-muted" />
        <div className="h-4 w-32 animate-pulse rounded bg-muted" />
        <div className="h-40 animate-pulse rounded bg-muted" />
      </div>
    )
  }

  // Error state
  if (error) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-destructive">Failed to load prompt</p>
      </div>
    )
  }

  // No data (shouldn't happen after loading without error, but guard)
  if (!data) return null

  const { variants } = data

  // Single variant -- render directly without tabs
  if (variants.length <= 1) {
    return (
      <ScrollArea className="h-full">
        <div className="space-y-4 p-4">
          <h2 className="text-lg font-semibold">{data.prompt_key}</h2>
          {variants[0] && <VariantSection variant={variants[0]} />}
        </div>
      </ScrollArea>
    )
  }

  // Multiple variants -- wrap in tabs keyed by prompt_type
  return (
    <ScrollArea className="h-full">
      <div className="space-y-4 p-4">
        <h2 className="text-lg font-semibold">{data.prompt_key}</h2>
        <Tabs defaultValue={variants[0].prompt_type}>
          <TabsList>
            {variants.map((v) => (
              <TabsTrigger key={v.prompt_type} value={v.prompt_type}>
                {v.prompt_type}
              </TabsTrigger>
            ))}
          </TabsList>
          {variants.map((v) => (
            <TabsContent key={v.prompt_type} value={v.prompt_type}>
              <VariantSection variant={v} />
            </TabsContent>
          ))}
        </Tabs>
      </div>
    </ScrollArea>
  )
}

