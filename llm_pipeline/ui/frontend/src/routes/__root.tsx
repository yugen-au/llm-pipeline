import { createRootRoute, Outlet } from '@tanstack/react-router'
import { Toaster } from 'sonner'
import { Sidebar } from '@/components/Sidebar'
import { useGlobalWebSocket } from '@/api/websocket'

function RootLayout() {
  useGlobalWebSocket()

  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
      <Toaster richColors position="bottom-right" />
    </div>
  )
}

export const Route = createRootRoute({
  component: RootLayout,
})
