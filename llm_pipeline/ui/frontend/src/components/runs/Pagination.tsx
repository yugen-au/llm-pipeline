import { Button } from '@/components/ui/button'

interface PaginationProps {
  total: number
  page: number
  pageSize: number
  onPageChange: (page: number) => void
}

export function Pagination({ total, page, pageSize, onPageChange }: PaginationProps) {
  const totalPages = Math.ceil(total / pageSize)

  const rangeStart = total === 0 ? 0 : (page - 1) * pageSize + 1
  const rangeEnd = Math.min(page * pageSize, total)

  return (
    <div className="flex items-center justify-between py-4">
      <span className="text-sm text-muted-foreground">
        Showing {rangeStart}-{rangeEnd} of {total}
      </span>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
        >
          Previous
        </Button>
        <span className="text-sm">
          Page {page} of {totalPages || 1}
        </span>
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages || total === 0}
        >
          Next
        </Button>
      </div>
    </div>
  )
}
