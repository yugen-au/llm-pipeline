import { useState } from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { Check, RotateCcw, Pencil, AlertTriangle, ChevronDown, ChevronRight } from 'lucide-react'
import { useReview, useSubmitReview } from '@/api/reviews'
import type { ReviewSubmitRequest } from '@/api/reviews'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { JsonViewer } from '@/components/JsonViewer'

export const Route = createFileRoute('/review/$token')({
  component: ReviewPage,
})

// ---------------------------------------------------------------------------
// Display field renderer
// ---------------------------------------------------------------------------

function DisplayFieldRenderer({ field }: { field: { label: string; value: unknown; type: string } }) {
  const { label, value, type } = field

  if (type === 'progress' && typeof value === 'number') {
    const pct = Math.round(value * 100)
    return (
      <div className="space-y-1">
        <span className="text-xs text-muted-foreground">{label}</span>
        <div className="flex items-center gap-2">
          <div className="h-2 flex-1 rounded-full bg-muted">
            <div
              className="h-2 rounded-full bg-primary transition-all"
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className="text-sm font-medium">{pct}%</span>
        </div>
      </div>
    )
  }

  if (type === 'badge') {
    return (
      <div className="space-y-1">
        <span className="text-xs text-muted-foreground">{label}</span>
        <div><Badge variant="secondary">{String(value)}</Badge></div>
      </div>
    )
  }

  if (type === 'table' && Array.isArray(value)) {
    const headers = value.length > 0 ? Object.keys(value[0] as Record<string, unknown>) : []
    return (
      <div className="space-y-1">
        <span className="text-xs text-muted-foreground">{label}</span>
        <div className="overflow-auto rounded border">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b bg-muted/50">
                {headers.map((h) => <th key={h} className="px-2 py-1 text-left font-medium">{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {value.map((row, i) => (
                <tr key={i} className="border-b last:border-0">
                  {headers.map((h) => <td key={h} className="px-2 py-1">{String((row as Record<string, unknown>)[h])}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    )
  }

  if (type === 'code') {
    return (
      <div className="space-y-1">
        <span className="text-xs text-muted-foreground">{label}</span>
        <pre className="rounded bg-muted p-2 text-xs font-mono overflow-auto">{String(value)}</pre>
      </div>
    )
  }

  if (type === 'number') {
    return (
      <div className="space-y-1">
        <span className="text-xs text-muted-foreground">{label}</span>
        <p className="text-sm font-mono">{String(value)}</p>
      </div>
    )
  }

  // Default: text
  return (
    <div className="space-y-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <p className="text-sm">{String(value)}</p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Review page
// ---------------------------------------------------------------------------

function ReviewPage() {
  const { token } = Route.useParams()
  const navigate = useNavigate()
  const { data: review, isLoading, error } = useReview(token)
  const submitMutation = useSubmitReview(review?.run_id ?? '')

  const [notes, setNotes] = useState('')
  const [resumeFrom, setResumeFrom] = useState('')
  const [rawExpanded, setRawExpanded] = useState(false)

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-muted-foreground">Loading review...</p>
      </div>
    )
  }

  if (error || !review) {
    const detail = (error as { detail?: string })?.detail
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-destructive">{detail ?? 'Review not found or already completed'}</p>
      </div>
    )
  }

  const displayData = review.review_data?.display_data ?? []
  const rawData = review.review_data?.raw_data ?? null
  const isCompleted = review.status === 'completed'

  function handleSubmit(decision: ReviewSubmitRequest['decision']) {
    submitMutation.mutate(
      {
        decision,
        notes: notes || null,
        resume_from: decision === 'major_revision' && resumeFrom ? resumeFrom : null,
      },
      {
        onSuccess: () => {
          navigate({ to: '/live' })
        },
      },
    )
  }

  return (
    <ScrollArea className="h-full">
      <div className="mx-auto max-w-2xl space-y-6 p-6">
        {/* Header */}
        <div className="space-y-2">
          <h1 className="text-2xl font-semibold">Pipeline Review</h1>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Badge variant="outline">{review.pipeline_name}</Badge>
            <span>Step: <strong>{review.step_name}</strong> (#{review.step_number})</span>
          </div>
          <p className="text-xs text-muted-foreground font-mono">
            Run: {review.run_id.slice(0, 8)} / Token: {token.slice(0, 8)}
          </p>
        </div>

        {/* Display fields */}
        {displayData.length > 0 && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Step Output</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {displayData.map((field, i) => (
                <DisplayFieldRenderer key={i} field={field} />
              ))}
            </CardContent>
          </Card>
        )}

        {/* Raw data (collapsible) */}
        {rawData && (
          <Card>
            <button
              type="button"
              className="flex w-full items-center gap-2 p-4 text-sm text-muted-foreground hover:text-foreground transition-colors"
              onClick={() => setRawExpanded((v) => !v)}
            >
              {rawExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              Raw Data
            </button>
            {rawExpanded && (
              <CardContent className="pt-0">
                <JsonViewer data={rawData} />
              </CardContent>
            )}
          </Card>
        )}

        {/* Review form */}
        {!isCompleted && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Your Decision</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="notes">Notes (optional)</Label>
                <Textarea
                  id="notes"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Feedback for the pipeline..."
                  rows={3}
                />
              </div>

              <div className="flex flex-wrap gap-2">
                <Button
                  onClick={() => handleSubmit('approved')}
                  disabled={submitMutation.isPending}
                  className="gap-1"
                >
                  <Check className="h-4 w-4" />
                  Approve
                </Button>

                <Button
                  variant="secondary"
                  onClick={() => handleSubmit('minor_revision')}
                  disabled={submitMutation.isPending}
                  className="gap-1"
                >
                  <Pencil className="h-4 w-4" />
                  Minor Revision
                </Button>

                <Button
                  variant="outline"
                  onClick={() => handleSubmit('major_revision')}
                  disabled={submitMutation.isPending || !resumeFrom}
                  className="gap-1"
                >
                  <AlertTriangle className="h-4 w-4" />
                  Major Revision
                </Button>

                <Button
                  variant="destructive"
                  onClick={() => handleSubmit('restart')}
                  disabled={submitMutation.isPending}
                  className="gap-1"
                >
                  <RotateCcw className="h-4 w-4" />
                  Restart
                </Button>
              </div>

              {/* Resume-from field for major revision */}
              <div className="space-y-2">
                <Label htmlFor="resume-from" className="text-xs text-muted-foreground">
                  Resume from step (for Major Revision)
                </Label>
                <Input
                  id="resume-from"
                  value={resumeFrom}
                  onChange={(e) => setResumeFrom(e.target.value)}
                  placeholder="step_name"
                  className="text-sm font-mono"
                />
              </div>
            </CardContent>
          </Card>
        )}

        {isCompleted && (
          <Card>
            <CardContent className="py-6 text-center text-muted-foreground">
              This review has already been completed.
            </CardContent>
          </Card>
        )}
      </div>
    </ScrollArea>
  )
}
