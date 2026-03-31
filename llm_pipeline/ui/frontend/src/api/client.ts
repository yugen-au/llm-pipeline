import { toast } from 'sonner'
import { ApiError } from './types'

/**
 * Shared fetch wrapper for all REST API calls.
 *
 * Prepends `/api` to the given path so Vite's dev proxy (and
 * same-origin prod serving) resolves the backend automatically.
 * Throws a typed {@link ApiError} on non-OK responses.
 * Shows a toast notification on errors by default.
 */
export async function apiClient<T>(
  path: string,
  options?: RequestInit & { silent?: boolean },
): Promise<T> {
  const { silent, ...fetchOptions } = options ?? {}
  const response = await fetch(`/api${path}`, fetchOptions)

  if (!response.ok) {
    let detail: string = response.statusText
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (body.detail != null) {
        detail =
          typeof body.detail === 'string'
            ? body.detail
            : JSON.stringify(body.detail)
      }
    } catch {
      // body not parseable as JSON, keep statusText
    }
    const error = new ApiError(response.status, detail)
    if (!silent) {
      toast.error(`${response.status}: ${detail}`)
    }
    throw error
  }

  return response.json() as Promise<T>
}
