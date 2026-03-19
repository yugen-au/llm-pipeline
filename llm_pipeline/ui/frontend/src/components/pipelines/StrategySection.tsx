import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { ChevronRight, ChevronDown } from 'lucide-react'
import type {
  PipelineStrategyMetadata,
  PipelineStepMetadata,
  ExtractionMetadata,
  TransformationMetadata,
} from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { JsonViewer } from '@/components/JsonViewer'

// ---------------------------------------------------------------------------
// StepRow
// ---------------------------------------------------------------------------

interface StepRowProps {
  step: PipelineStepMetadata
  pipelineName: string
}

function StepRow({ step }: StepRowProps) {
  const [expanded, setExpanded] = useState(false)

  return (
    <li className="border-b last:border-b-0">
      {/* Collapsed row header */}
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-muted/30 transition-colors"
        onClick={() => setExpanded((p) => !p)}
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
        )}
        <span className="text-sm font-medium">{step.step_name}</span>
        <span className="text-xs text-muted-foreground font-mono">
          {step.class_name}
        </span>
      </button>

      {/* Expanded detail section */}
      {expanded && (
        <div className="space-y-3 px-3 pb-3 pl-9">
          {/* Prompt keys */}
          {(step.system_key || step.user_key) && (
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">Prompt Keys</p>
              <div className="flex flex-wrap gap-2">
                {step.system_key && (
                  <Link
                    from="/pipelines"
                    to="/prompts"
                    search={{ key: step.system_key }}
                    className="font-mono text-xs text-primary underline"
                  >
                    system: {step.system_key}
                  </Link>
                )}
                {step.user_key && (
                  <Link
                    from="/pipelines"
                    to="/prompts"
                    search={{ key: step.user_key }}
                    className="font-mono text-xs text-primary underline"
                  >
                    user: {step.user_key}
                  </Link>
                )}
              </div>
            </div>
          )}

          {/* Instructions schema */}
          {step.instructions_schema && (
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">
                Instructions Schema
                {step.instructions_class && (
                  <span className="ml-1 font-mono font-normal">({step.instructions_class})</span>
                )}
              </p>
              <div className="rounded border bg-muted/20 p-2">
                <JsonViewer data={step.instructions_schema} />
              </div>
            </div>
          )}

          {/* Context schema */}
          {step.context_schema && (
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">
                Context Schema
                {step.context_class && (
                  <span className="ml-1 font-mono font-normal">({step.context_class})</span>
                )}
              </p>
              <div className="rounded border bg-muted/20 p-2">
                <JsonViewer data={step.context_schema} />
              </div>
            </div>
          )}

          {/* Extractions */}
          {step.extractions.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">Extractions</p>
              <ul className="space-y-1">
                {step.extractions.map((ext: ExtractionMetadata) => (
                  <li key={ext.class_name} className="flex items-center gap-2 text-xs font-mono">
                    <span>{ext.class_name}</span>
                    {ext.model_class && (
                      <span className="text-muted-foreground">-&gt; {ext.model_class}</span>
                    )}
                    {ext.methods.length > 0 && (
                      <span className="text-muted-foreground">
                        [{ext.methods.join(', ')}]
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Tools */}
          {step.tools && step.tools.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">Tools</p>
              <div className="flex flex-wrap gap-1.5">
                {step.tools.map((tool) => (
                  <Badge key={tool} variant="outline" className="border-cyan-500 text-cyan-600 dark:text-cyan-400 font-mono text-xs">
                    {tool}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Transformation */}
          {step.transformation && (
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">Transformation</p>
              <TransformationSummary transformation={step.transformation} />
            </div>
          )}

          {/* Action after */}
          {step.action_after && (
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">Action After</p>
              <span className="text-xs font-mono">{step.action_after}</span>
            </div>
          )}
        </div>
      )}
    </li>
  )
}

// ---------------------------------------------------------------------------
// TransformationSummary (private helper)
// ---------------------------------------------------------------------------

function TransformationSummary({ transformation }: { transformation: TransformationMetadata }) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs font-mono">
      <span>{transformation.class_name}</span>
      {transformation.input_type && (
        <span className="text-muted-foreground">{transformation.input_type}</span>
      )}
      {transformation.output_type && (
        <>
          <span className="text-muted-foreground">-&gt;</span>
          <span className="text-muted-foreground">{transformation.output_type}</span>
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// StrategySection
// ---------------------------------------------------------------------------

interface StrategySectionProps {
  strategy: PipelineStrategyMetadata
  pipelineName: string
}

export function StrategySection({ strategy, pipelineName }: StrategySectionProps) {
  return (
    <div className="space-y-2">
      {/* Strategy header */}
      <div className="flex items-center gap-2">
        <h3 className="text-base font-semibold">{strategy.display_name}</h3>
        <span className="text-xs text-muted-foreground font-mono">{strategy.class_name}</span>
        {strategy.error && <Badge variant="destructive">error</Badge>}
      </div>

      {/* Error state */}
      {strategy.error ? (
        <p className="text-sm text-destructive">{strategy.error}</p>
      ) : (
        /* Step list */
        <ol className="rounded border divide-y">
          {strategy.steps.map((step) => (
            <StepRow key={step.step_name} step={step} pipelineName={pipelineName} />
          ))}
        </ol>
      )}
    </div>
  )
}
