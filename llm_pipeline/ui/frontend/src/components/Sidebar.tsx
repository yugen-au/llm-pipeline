import { Link } from '@tanstack/react-router'
import {
  List,
  Play,
  FileText,
  Box,
  PanelLeftClose,
  PanelLeftOpen,
  Menu,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import { cn } from '@/lib/utils'
import { useUIStore } from '@/stores/ui'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
  TooltipProvider,
} from '@/components/ui/tooltip'
import {
  Sheet,
  SheetContent,
  SheetTrigger,
  SheetTitle,
} from '@/components/ui/sheet'
import type { FileRoutesByTo } from '@/routeTree.gen'

interface NavItem {
  to: keyof FileRoutesByTo
  label: string
  icon: LucideIcon
}

const navItems: NavItem[] = [
  { to: '/', label: 'Runs', icon: List },
  { to: '/live', label: 'Live', icon: Play },
  { to: '/prompts', label: 'Prompts', icon: FileText },
  { to: '/pipelines', label: 'Pipelines', icon: Box },
]

const activeLinkClasses =
  'bg-sidebar-accent text-sidebar-accent-foreground border-l-2 border-sidebar-primary font-medium'
const inactiveLinkClasses =
  'text-sidebar-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground border-l-2 border-transparent'
const baseLinkClasses = 'flex items-center gap-3 px-3 py-2 rounded-md text-sm w-full'

function NavLinks({
  collapsed,
  responsiveCollapse = false,
}: {
  collapsed: boolean
  responsiveCollapse?: boolean
}) {
  return (
    <ul role="list" className="flex flex-col gap-1 px-2">
      {navItems.map((item) => {
        const Icon = item.icon
        const linkContent = (
          <>
            <Icon aria-hidden="true" className="size-5 shrink-0" />
            <span
              className={cn(
                collapsed && 'sr-only',
                responsiveCollapse && 'max-lg:sr-only',
              )}
            >
              {item.label}
            </span>
          </>
        )

        if (collapsed) {
          return (
            <li key={item.to}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Link
                    to={item.to}
                    className={baseLinkClasses}
                    activeProps={{
                      'aria-current': 'page' as const,
                      className: activeLinkClasses,
                    }}
                    inactiveProps={{ className: inactiveLinkClasses }}
                  >
                    {linkContent}
                  </Link>
                </TooltipTrigger>
                <TooltipContent side="right" sideOffset={8}>
                  {item.label}
                </TooltipContent>
              </Tooltip>
            </li>
          )
        }

        return (
          <li key={item.to}>
            <Link
              to={item.to}
              className={baseLinkClasses}
              activeProps={{
                'aria-current': 'page' as const,
                className: activeLinkClasses,
              }}
              inactiveProps={{ className: inactiveLinkClasses }}
            >
              {linkContent}
            </Link>
          </li>
        )
      })}
    </ul>
  )
}

export function Sidebar() {
  const sidebarCollapsed = useUIStore((s) => s.sidebarCollapsed)
  const toggleSidebar = useUIStore((s) => s.toggleSidebar)

  return (
    <>
      {/* Mobile hamburger trigger */}
      <div className="md:hidden fixed top-4 left-4 z-50">
        <Sheet>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon-sm" aria-label="Open navigation">
              <Menu className="size-5" />
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-60 bg-sidebar p-0">
            <SheetTitle className="px-4 pt-4 text-sm font-semibold text-sidebar-foreground">
              llm-pipeline
            </SheetTitle>
            <Separator className="my-2" />
            <nav aria-label="Main navigation">
              <NavLinks collapsed={false} />
            </nav>
          </SheetContent>
        </Sheet>
      </div>

      {/* Desktop/tablet sidebar */}
      <aside
        className={cn(
          'bg-sidebar border-r border-sidebar-border shrink-0 flex-col transition-all duration-200 hidden md:flex',
          sidebarCollapsed ? 'w-16' : 'w-60',
          'max-lg:w-16',
        )}
      >
        {/* Header */}
        <div className="flex items-center gap-2 px-3 py-3">
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={toggleSidebar}
            aria-expanded={!sidebarCollapsed}
            aria-controls="sidebar-nav"
            aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {sidebarCollapsed ? (
              <PanelLeftOpen className="size-5" />
            ) : (
              <PanelLeftClose className="size-5" />
            )}
          </Button>
          <span
            className={cn(
              'text-sm font-semibold text-sidebar-foreground',
              sidebarCollapsed && 'sr-only',
              'max-lg:sr-only',
            )}
          >
            llm-pipeline
          </span>
        </div>

        <Separator />

        {/* Navigation */}
        <TooltipProvider delayDuration={0}>
          <nav aria-label="Main navigation" id="sidebar-nav" className="flex-1 py-2">
            <NavLinks collapsed={sidebarCollapsed} responsiveCollapse />
          </nav>
        </TooltipProvider>
      </aside>
    </>
  )
}
