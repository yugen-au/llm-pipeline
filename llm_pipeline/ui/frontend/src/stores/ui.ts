/**
 * Zustand store for UI-only state.
 *
 * Holds sidebar, theme, and step-detail panel state.
 * Persists sidebar + theme to localStorage so preferences
 * survive reloads. Ephemeral state (selectedStepId, stepDetailOpen)
 * is excluded from persistence.
 */

import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'

export type Theme = 'dark' | 'light'

interface UIState {
  sidebarCollapsed: boolean
  theme: Theme
  selectedStepId: number | null
  stepDetailOpen: boolean
  toggleSidebar: () => void
  setTheme: (theme: Theme) => void
  selectStep: (stepId: number | null) => void
  closeStepDetail: () => void
}

export const useUIStore = create<UIState>()(
  devtools(
    persist(
      (set) => ({
        sidebarCollapsed: false,
        theme: 'dark',
        selectedStepId: null,
        stepDetailOpen: false,

        toggleSidebar: () =>
          set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),

        setTheme: (theme) => {
          if (theme === 'dark') {
            document.documentElement.classList.add('dark')
          } else {
            document.documentElement.classList.remove('dark')
          }
          set({ theme })
        },

        selectStep: (stepId) =>
          set({
            selectedStepId: stepId,
            stepDetailOpen: stepId !== null,
          }),

        closeStepDetail: () =>
          set({ stepDetailOpen: false, selectedStepId: null }),
      }),
      {
        name: 'llm-pipeline-ui',
        partialize: (state) => ({
          sidebarCollapsed: state.sidebarCollapsed,
          theme: state.theme,
        }),
        onRehydrateStorage: () => (state) => {
          const theme = state?.theme ?? 'dark'
          if (theme === 'dark') {
            document.documentElement.classList.add('dark')
          } else {
            document.documentElement.classList.remove('dark')
          }
        },
      },
    ),
    { name: 'ui', enabled: import.meta.env.DEV },
  ),
)
