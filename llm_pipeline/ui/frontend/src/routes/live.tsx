import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/live')({
  component: LivePage,
})

function LivePage() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold text-card-foreground">Live</h1>
      <p className="mt-2 text-muted-foreground">Live pipeline monitoring</p>
    </div>
  )
}
