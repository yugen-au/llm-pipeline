import { useEffect, useRef, useState } from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { AlertCircle } from 'lucide-react'
import { useCreateVariant } from '@/api/evals'
import { ApiError } from '@/api/types'
import { Button } from '@/components/ui/button'

export const Route = createFileRoute('/evals/$datasetId/variants/new')({
  component: NewVariantPage,
})

/**
 * Creates a blank variant via useCreateVariant then redirects to the editor.
 *
 * Uses a ref-guarded effect so StrictMode's double-mount doesn't fire two
 * POST requests. On 422 (backend rejected dry-run), surfaces the error
 * inline with retry; otherwise apiClient's toast handles generic errors.
 */
function NewVariantPage() {
  const { datasetId: rawDatasetId } = Route.useParams()
  const datasetId = Number(rawDatasetId)
  const navigate = useNavigate()
  const createVariantMut = useCreateVariant(datasetId)

  const attemptedRef = useRef(false)
  const [error, setError] = useState<string | null>(null)
  // Retry counter — bumping this re-runs the effect without a URL round-trip.
  const [retryKey, setRetryKey] = useState(0)

  useEffect(() => {
    if (attemptedRef.current) return
    attemptedRef.current = true

    const defaultName = `Variant ${new Date()
      .toISOString()
      .replace('T', ' ')
      .slice(0, 16)}`

    createVariantMut.mutate(
      {
        name: defaultName,
        description: null,
        delta: {
          model: null,
          system_prompt: null,
          user_prompt: null,
          instructions_delta: null,
        },
      },
      {
        onSuccess: (v) => {
          navigate({
            to: `/evals/${datasetId}/variants/${v.id}` as string,
            replace: true,
          })
        },
        onError: (err) => {
          if (err instanceof ApiError) {
            setError(err.detail || `${err.status}: failed to create variant`)
          } else if (err instanceof Error) {
            setError(err.message)
          } else {
            setError('Failed to create variant')
          }
        },
      },
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId, retryKey])

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <div className="max-w-md space-y-3">
          <div className="rounded border border-destructive/50 bg-destructive/5 p-3 flex items-start gap-2 text-xs text-destructive">
            <AlertCircle className="size-4 shrink-0 mt-0.5" />
            <div>
              <p className="font-medium">Failed to create variant</p>
              <p className="font-mono mt-1 whitespace-pre-wrap">{error}</p>
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <Button
              size="sm"
              variant="outline"
              className="h-8 text-xs"
              onClick={() =>
                navigate({ to: `/evals/${datasetId}` as string })
              }
            >
              Back to dataset
            </Button>
            <Button
              size="sm"
              className="h-8 text-xs"
              onClick={() => {
                setError(null)
                attemptedRef.current = false
                // Re-run the effect locally — no navigation, no remount.
                setRetryKey((k) => k + 1)
              }}
            >
              Retry
            </Button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full items-center justify-center">
      <p className="text-muted-foreground text-sm">Creating variant...</p>
    </div>
  )
}
