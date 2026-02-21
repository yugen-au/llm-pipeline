import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/prompts')({
  component: PromptsPage,
})

function PromptsPage() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold text-card-foreground">Prompts</h1>
      <p className="mt-2 text-muted-foreground">Prompt management</p>
    </div>
  )
}
