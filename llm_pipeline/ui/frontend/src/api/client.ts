import { ApiError } from './types'

/**
 * Shared fetch wrapper for all REST API calls.
 *
 * Prepends `/api` to the given path so Vite's dev proxy (and
 * same-origin prod serving) resolves the backend automatically.
 * Throws a typed {@link ApiError} on non-OK responses.
 */
export async function apiClient<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, options)

  if (!response.ok) {
    let detail: string = response.statusText
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) {
        detail = body.detail
      }
    } catch {
      // body not parseable as JSON, keep statusText
    }
    throw new ApiError(response.status, detail)
  }

  return response.json() as Promise<T>
}
