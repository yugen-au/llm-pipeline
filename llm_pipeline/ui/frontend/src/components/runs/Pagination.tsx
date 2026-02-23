import { Button } from '@/components/ui/button'
import { useNavigate } from '@tanstack/react-router'

interface PaginationProps {
  total: number
  page: number
  pageSize: number
}

export function Pagination({ total, page, pageSize }: PaginationProps) {
  const navigate = useNavigate()
  const totalPages = Math.ceil(total / pageSize)

  const rangeStart = total === 0 ? 0 : (page - 1) * pageSize + 1
  const rangeEnd = Math.min(page * pageSize, total)

  const handlePrev = () => {
    navigate({ to: '/', search: (prev) => ({ ...prev, page: page - 1 }) })
  }

  const handleNext = () => {
    navigate({ to: '/', search: (prev) => ({ ...prev, page: page + 1 }) })
  }

  return (
    <div className="flex items-center justify-between py-4">
      <span className="text-sm text-muted-foreground">
        Showing {rangeStart}-{rangeEnd} of {total}
      </span>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={handlePrev}
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
          onClick={handleNext}
          disabled={page >= totalPages || total === 0}
        >
          Next
        </Button>
      </div>
    </div>
  )
}
