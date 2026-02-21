import { createFileRoute } from '@tanstack/react-router'
import { fallback, zodValidator } from '@tanstack/zod-adapter'
import { z } from 'zod'

const runDetailSearchSchema = z.object({
  tab: fallback(z.string(), 'steps').default('steps'),
})

export const Route = createFileRoute('/runs/$runId')({
  validateSearch: zodValidator(runDetailSearchSchema),
  component: RunDetailPage,
})

function RunDetailPage() {
  const { runId } = Route.useParams()
  const { tab } = Route.useSearch()

  return (
    <div className="bg-card text-card-foreground rounded-lg border p-6">
      <h1 className="text-2xl font-semibold">Run Detail</h1>
      <p className="text-muted-foreground mt-1">Run ID: {runId}</p>
      <p className="text-muted-foreground mt-1">Active tab: {tab}</p>
    </div>
  )
}
