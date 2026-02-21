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
