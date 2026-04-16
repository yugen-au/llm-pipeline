import { createFileRoute, Outlet } from '@tanstack/react-router'

export const Route = createFileRoute('/evals/$datasetId')({
  component: () => <Outlet />,
})
