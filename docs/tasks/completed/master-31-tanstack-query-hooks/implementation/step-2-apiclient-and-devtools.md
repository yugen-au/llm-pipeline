# IMPLEMENTATION - STEP 2: APICLIENT AND DEVTOOLS
**Status:** completed

## Summary
Created shared `apiClient<T>` fetch wrapper in `src/api/client.ts` and mounted ReactQuery DevTools in `main.tsx` with lazy dynamic import for zero production bundle impact.

## Files
**Created:** `llm_pipeline/ui/frontend/src/api/client.ts`
**Modified:** `llm_pipeline/ui/frontend/src/main.tsx`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/api/client.ts`
New file. Exports `apiClient<T>(path, options?)` that prepends `/api`, calls native `fetch`, throws `ApiError` (from `./types`) on non-OK responses after attempting to parse `detail` from JSON body, returns `response.json() as Promise<T>` on success.

```ts
# Key implementation
export async function apiClient<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, options)
  if (!response.ok) {
    // parse body.detail if available, fallback to statusText
    throw new ApiError(response.status, detail)
  }
  return response.json() as Promise<T>
}
```

### File: `llm_pipeline/ui/frontend/src/main.tsx`
Added lazy DevTools import and conditional rendering.

```tsx
# Before
import { StrictMode } from 'react'
// ... no devtools

# After
import { lazy, StrictMode, Suspense } from 'react'

const ReactQueryDevtools = import.meta.env.DEV
  ? lazy(() =>
      import('@tanstack/react-query-devtools').then((m) => ({
        default: m.ReactQueryDevtools,
      })),
    )
  : () => null

// Inside QueryClientProvider:
{import.meta.env.DEV && (
  <Suspense fallback={null}>
    <ReactQueryDevtools initialIsOpen={false} />
  </Suspense>
)}
```

## Decisions
### DevTools lazy import pattern
**Choice:** `React.lazy` with module-level conditional assignment (DEV -> lazy component, prod -> null component), wrapped in `Suspense` inside JSX.
**Rationale:** Vite statically analyzes `import.meta.env.DEV` at build time, completely dead-code-eliminating both the lazy wrapper and the dynamic import in production. The `Suspense` fallback of `null` avoids any layout shift while the devtools chunk loads. This is cleaner than an effect-based approach and follows TanStack Query's own recommended pattern.

### ApiError body parsing with try/catch
**Choice:** Wrap `response.json()` in try/catch when parsing error bodies, falling back to `response.statusText`.
**Rationale:** Some error responses may not have JSON bodies (e.g. 502 from proxy, HTML error pages). Graceful fallback prevents double-throw scenarios where both the original error and the JSON parse error would surface.

## Verification
[x] TypeScript compilation passes (`npx tsc -b --noEmit` - clean)
[x] `apiClient` imports `ApiError` from `./types` (class exists from Step 1)
[x] No semicolons, single quotes throughout
[x] `import.meta.env.DEV` guard ensures zero prod bundle impact for devtools
[x] DevTools rendered inside `QueryClientProvider` (has access to query client)
[x] `verbatimModuleSyntax` compatible - no type-only imports needed (ApiError is a runtime class)
