import { useState } from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useReviews } from '@/api/reviews'
import type { ReviewListItem } from '@/api/reviews'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'

export const Route = createFileRoute('/reviews')({
  component: ReviewsPage,
})

function formatRelative(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const secs = Math.floor(diff / 1000)
  if (secs < 60) return `${secs}s ago`
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function statusBadge(status: string) {
  if (status === 'pending') return <Badge variant="outline" className="border-amber-500 text-amber-500">pending</Badge>
  if (status === 'completed') return <Badge variant="outline" className="border-status-completed text-status-completed">completed</Badge>
  return <Badge variant="secondary">{status}</Badge>
}

function decisionBadge(decision: string | null) {
  if (!decision) return null
  const colors: Record<string, string> = {
    approved: 'border-green-500 text-green-500',
    minor_revision: 'border-blue-500 text-blue-500',
    major_revision: 'border-orange-500 text-orange-500',
    restart: 'border-red-500 text-red-500',
  }
  return (
    <Badge variant="outline" className={colors[decision] ?? ''}>
      {decision.replace('_', ' ')}
    </Badge>
  )
}

function ReviewsPage() {
  const navigate = useNavigate()
  const [statusFilter, setStatusFilter] = useState<string>('all')

  const filters = statusFilter === 'all' ? {} : { status: statusFilter }
  const { data, isLoading } = useReviews(filters)

  const reviews = data?.items ?? []

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-card-foreground">Reviews</h1>
          <p className="text-sm text-muted-foreground">Human-in-the-loop review queue</p>
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-36 h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="completed">Completed</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <Card className="min-h-0 flex-1 overflow-hidden">
        {isLoading ? (
          <CardContent className="flex h-full items-center justify-center">
            <p className="text-sm text-muted-foreground">Loading...</p>
          </CardContent>
        ) : reviews.length === 0 ? (
          <CardContent className="flex h-full items-center justify-center">
            <p className="text-sm text-muted-foreground">No reviews found</p>
          </CardContent>
        ) : (
          <ScrollArea className="h-full">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Pipeline</TableHead>
                  <TableHead className="text-xs">Step</TableHead>
                  <TableHead className="text-xs">Run</TableHead>
                  <TableHead className="text-xs">Status</TableHead>
                  <TableHead className="text-xs">Decision</TableHead>
                  <TableHead className="text-xs">Created</TableHead>
                  <TableHead className="text-xs w-20" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {reviews.map((r) => (
                  <ReviewRow key={r.token} review={r} onOpen={() => navigate({ to: `/review/${r.token}` })} />
                ))}
              </TableBody>
            </Table>
          </ScrollArea>
        )}
      </Card>
    </div>
  )
}

function ReviewRow({ review, onOpen }: { review: ReviewListItem; onOpen: () => void }) {
  return (
    <TableRow className="cursor-pointer hover:bg-muted/50" onClick={onOpen}>
      <TableCell className="text-sm font-medium">{review.pipeline_name}</TableCell>
      <TableCell className="text-sm">{review.step_name}</TableCell>
      <TableCell className="text-xs font-mono text-muted-foreground">{review.run_id.slice(0, 8)}</TableCell>
      <TableCell>{statusBadge(review.status)}</TableCell>
      <TableCell>{decisionBadge(review.decision)}</TableCell>
      <TableCell className="text-xs text-muted-foreground">{formatRelative(review.created_at)}</TableCell>
      <TableCell>
        {review.status === 'pending' && (
          <Button size="sm" variant="outline" className="h-7 text-xs">Review</Button>
        )}
      </TableCell>
    </TableRow>
  )
}
