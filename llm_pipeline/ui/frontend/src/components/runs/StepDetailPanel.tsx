import { useCallback, useEffect, useRef } from 'react'
import { useStep } from '@/api/steps'
import { formatDuration, formatAbsolute } from '@/lib/time'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { X } from 'lucide-react'

interface StepDetailPanelProps {
  runId: string
  stepNumber: number | null
  open: boolean
  onClose: () => void
  runStatus?: string
}

function StepContent({
  runId,
  stepNumber,
  runStatus,
}: {
  runId: string
  stepNumber: number
  runStatus?: string
}) {
  const { data: step, isLoading, isError } = useStep(runId, stepNumber, runStatus)

  if (isLoading) {
    return (
      <div className="space-y-3">
        <div className="h-5 w-40 animate-pulse rounded bg-muted" />
        <div className="h-4 w-24 animate-pulse rounded bg-muted" />
        <div className="h-4 w-32 animate-pulse rounded bg-muted" />
      </div>
    )
  }

  if (isError) {
    return <p className="text-sm text-destructive">Failed to load step</p>
  }

  if (!step) return null

  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-base font-semibold">{step.step_name}</h3>
        <p className="text-xs text-muted-foreground">Step {step.step_number}</p>
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-muted-foreground">Model</dt>
        <dd>{step.model ?? '\u2014'}</dd>
        <dt className="text-muted-foreground">Duration</dt>
        <dd>{formatDuration(step.execution_time_ms)}</dd>
        <dt className="text-muted-foreground">Created</dt>
        <dd>{formatAbsolute(step.created_at)}</dd>
      </dl>
      {/* Task 35: replace with tabbed implementation */}
    </div>
  )
}

const FOCUSABLE = 'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function StepDetailPanel({
  runId,
  stepNumber,
  open,
  onClose,
  runStatus,
}: StepDetailPanelProps) {
  const visible = open && stepNumber != null
  const panelRef = useRef<HTMLDivElement>(null)
  const closeBtnRef = useRef<HTMLButtonElement>(null)

  // Escape key handler
  useEffect(() => {
    if (!visible) return
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
      }
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [visible, onClose])

  // Focus close button on open
  useEffect(() => {
    if (visible) {
      closeBtnRef.current?.focus()
    }
  }, [visible])

  // Trap focus within panel
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key !== 'Tab' || !panelRef.current) return
      const focusable = panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE)
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    },
    [],
  )

  return (
    <>
      {/* Backdrop */}
      {visible && (
        <div
          className="fixed inset-0 z-40 bg-black/50"
          aria-hidden="true"
          onClick={onClose}
        />
      )}

      {/* Panel */}
      <div
        ref={panelRef}
        role="dialog"
        aria-modal={visible}
        aria-label="Step detail"
        onKeyDown={handleKeyDown}
        className={cn(
          'fixed inset-y-0 right-0 z-50 w-96 bg-background border-l border-border shadow-xl transition-transform duration-200',
          visible ? 'translate-x-0' : 'translate-x-full',
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b px-4 py-3">
          <h2 className="text-sm font-semibold">Step Detail</h2>
          <Button
            ref={closeBtnRef}
            variant="ghost"
            size="icon-xs"
            aria-label="Close step detail"
            onClick={onClose}
          >
            <X />
          </Button>
        </div>

        {/* Body */}
        <div className="p-4">
          {visible ? (
            <StepContent
              runId={runId}
              stepNumber={stepNumber}
              runStatus={runStatus}
            />
          ) : null}
        </div>
      </div>
    </>
  )
}
