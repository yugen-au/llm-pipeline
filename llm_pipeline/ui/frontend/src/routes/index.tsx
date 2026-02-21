import { createFileRoute } from '@tanstack/react-router'
import { fallback, zodValidator } from '@tanstack/zod-adapter'
import { z } from 'zod'

const runListSearchSchema = z.object({
  page: fallback(z.number().int().min(1), 1).default(1),
  status: fallback(z.string(), '').default(''),
})

export const Route = createFileRoute('/')({
  validateSearch: zodValidator(runListSearchSchema),
  component: IndexPage,
})

function IndexPage() {
  return (
    <div className="flex min-h-full items-center justify-center">
      <p className="text-muted-foreground">llm-pipeline ui</p>
    </div>
  )
}
