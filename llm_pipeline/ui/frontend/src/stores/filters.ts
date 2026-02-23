/**
 * Zustand store for run list filter state.
 *
 * Holds ephemeral filter values (pipeline name, date range).
 * Null means "omit from API query" -- toSearchParams skips null.
 * No persist middleware: filters reset on page reload.
 */

import { create } from 'zustand'
import { devtools } from 'zustand/middleware'

interface FiltersState {
  pipelineName: string | null
  startedAfter: string | null
  startedBefore: string | null
  setPipelineName: (name: string | null) => void
  setDateRange: (startedAfter: string | null, startedBefore: string | null) => void
  resetFilters: () => void
}

export const useFiltersStore = create<FiltersState>()(
  devtools(
    (set) => ({
      pipelineName: null,
      startedAfter: null,
      startedBefore: null,
      setPipelineName: (name) => set({ pipelineName: name }),
      setDateRange: (startedAfter, startedBefore) => set({ startedAfter, startedBefore }),
      resetFilters: () => set({ pipelineName: null, startedAfter: null, startedBefore: null }),
    }),
    { name: 'filters', enabled: import.meta.env.DEV },
  ),
)
