import type { EventItem } from '@/api/types'
import type { WsConnectionStatus } from '@/stores/websocket'
import type { TestResponse, AcceptResponse } from '@/api/creator'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { EmptyState, SkeletonBlock, LabeledPre } from '@/components/shared'
import { EventStream } from '@/components/live/EventStream'
import { TestResultsCard } from './TestResultsCard'
import { AcceptResultsCard } from './AcceptResultsCard'

// ---------------------------------------------------------------------------
// WorkflowState type (matches route-level state machine)
// ---------------------------------------------------------------------------

export type WorkflowState =
  | 'idle'
  | 'generating'
  | 'draft'
  | 'testing'
  | 'tested'
  | 'accepting'
  | 'accepted'
  | 'error'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface CreatorResultsPanelProps {
  workflowState: WorkflowState
  activeRunId: string | null
  testResults: TestResponse | null
  acceptResults: AcceptResponse | null
  wsStatus: WsConnectionStatus
  events: EventItem[]
  errorMessage?: string | null
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CreatorResultsPanel({
  workflowState,
  activeRunId,
  testResults,
  acceptResults,
  wsStatus,
  events,
  errorMessage,
}: CreatorResultsPanelProps) {
  return (
    <Card className="flex h-full flex-col overflow-hidden">
      <CardHeader>
        <CardTitle className="text-sm">Results</CardTitle>
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col">
        <ResultsContent
          workflowState={workflowState}
          activeRunId={activeRunId}
          testResults={testResults}
          acceptResults={acceptResults}
          wsStatus={wsStatus}
          events={events}
          errorMessage={errorMessage}
        />
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Internal: state-driven content switcher
// ---------------------------------------------------------------------------

function ResultsContent({
  workflowState,
  activeRunId,
  testResults,
  acceptResults,
  wsStatus,
  events,
  errorMessage,
}: CreatorResultsPanelProps) {
  switch (workflowState) {
    case 'idle':
      return <EmptyState message="Generate a step to see results" />

    case 'generating':
      return (
        <div className="flex min-h-0 flex-1 flex-col">
          <EventStream events={events} wsStatus={wsStatus} runId={activeRunId} />
        </div>
      )

    case 'draft':
      return (
        <div className="space-y-2">
          <Badge variant="outline">Ready to test</Badge>
          <p className="text-xs text-muted-foreground">
            Generation complete. Review the code and run tests.
          </p>
        </div>
      )

    case 'testing':
      return (
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">Running sandbox tests...</p>
          <SkeletonBlock />
          <SkeletonBlock className="h-12" />
        </div>
      )

    case 'tested':
      if (!testResults) return <EmptyState message="No test results available" />
      return <TestResultsCard results={testResults} />

    case 'accepting':
      return (
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">Accepting step...</p>
          <SkeletonBlock />
          <SkeletonBlock className="h-12" />
        </div>
      )

    case 'accepted':
      if (!acceptResults) return <EmptyState message="No accept results available" />
      return <AcceptResultsCard results={acceptResults} />

    case 'error':
      return (
        <div className="space-y-2">
          <Badge variant="destructive">Error</Badge>
          {errorMessage ? (
            <LabeledPre label="Details" content={errorMessage} />
          ) : (
            <p className="text-xs text-muted-foreground">
              An error occurred. Check logs or retry.
            </p>
          )}
        </div>
      )

    default: {
      const _exhaustive: never = workflowState
      return <EmptyState message={`Unknown state: ${_exhaustive}`} />
    }
  }
}
