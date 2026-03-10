# IMPLEMENTATION - STEP 6: REPLACE STUB PIPELINES.TSX
**Status:** completed

## Summary
Replaced the stub pipelines.tsx route with the full Pipeline Structure View wiring PipelineList and PipelineDetail sub-components with URL search params (?pipeline=name) and the left-right panel layout matching prompts.tsx.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/src/routes/pipelines.tsx
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/routes/pipelines.tsx`
Replaced entire stub with full implementation: zodValidator search schema, usePipelines hook, handleSelect navigation, flex h-full left-right panel layout with PipelineList (w-80) and PipelineDetail (flex-1).

```
# Before
import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/pipelines')({
  component: PipelinesPage,
})

function PipelinesPage() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold text-card-foreground">Pipelines</h1>
      <p className="mt-2 text-muted-foreground">Pipeline configuration</p>
    </div>
  )
}

# After
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { fallback, zodValidator } from '@tanstack/zod-adapter'
import { z } from 'zod'
import { usePipelines } from '@/api/pipelines'
import { PipelineList } from '@/components/pipelines/PipelineList'
import { PipelineDetail } from '@/components/pipelines/PipelineDetail'

const pipelinesSearchSchema = z.object({
  pipeline: fallback(z.string(), '').default(''),
})

export const Route = createFileRoute('/pipelines')({
  validateSearch: zodValidator(pipelinesSearchSchema),
  component: PipelinesPage,
})

function PipelinesPage() {
  const { pipeline } = Route.useSearch()
  const navigate = useNavigate({ from: '/pipelines' })
  const pipelines = usePipelines()

  function handleSelect(name: string) {
    navigate({ search: { pipeline: name } })
  }

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <h1 className="text-2xl font-semibold text-card-foreground">Pipelines</h1>
      <div className="flex min-h-0 flex-1 gap-4">
        <div className="flex w-80 shrink-0 flex-col overflow-hidden rounded-xl border">
          <PipelineList ... />
        </div>
        <div className="flex-1 overflow-auto rounded-xl border">
          <PipelineDetail pipelineName={pipeline || null} />
        </div>
      </div>
    </div>
  )
}
```

## Decisions
None -- followed prompts.tsx pattern exactly as specified in plan.

## Verification
[x] TypeScript compiles with no errors (npx tsc --noEmit)
[x] Import patterns match prompts.tsx (createFileRoute, useNavigate, fallback, zodValidator, z)
[x] zodValidator search schema uses fallback + default pattern
[x] usePipelines().data?.pipelines ?? [] matches hook return type
[x] Left-right panel layout matches prompts.tsx structure
[x] PipelineList props match component interface (pipelines, selectedName, onSelect, isLoading, error)
[x] PipelineDetail props match component interface (pipelineName: string | null)
