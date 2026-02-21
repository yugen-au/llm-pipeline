import { createRootRoute, Outlet } from '@tanstack/react-router'

function RootLayout() {
  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">
      <aside className="w-60 shrink-0 bg-sidebar border-r border-sidebar-border">
        <div className="p-4 text-sm text-muted-foreground">Sidebar (task 41)</div>
      </aside>
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}

export const Route = createRootRoute({
  component: RootLayout,
})
