# Research Summary

## Executive Summary

Validated both research outputs against actual codebase state. Research correctly identifies Tailwind v4 CSS-first config, existing dark mode infrastructure from task 29, and WCAG contrast failures for 3 of 6 proposed status colors. Found 6 hidden assumptions/gaps requiring CEO input before planning: (1) 'cached' is not an actual backend step status, (2) contrast was calculated against wrong background, (3) running status color mismatch between current code and spec, (4) EventStream scope unclear, (5) font loading strategy for internal tool, (6) color-scheme bug when light mode toggle exists.

## Domain Findings

### Tailwind v4 Dark Mode Infrastructure
**Source:** step-1-tailwind-dark-mode-research.md, index.css, ui.ts

Verified against codebase. All claims accurate:
- `@import "tailwindcss"` at line 1, `@custom-variant dark` at line 5, `@theme inline` block at lines 7-46
- `:root` OKLCH light vars (48-81), `.dark` OKLCH dark vars (83-115), `@layer base` at 117-121
- Zustand store applies .dark class, defaults to 'dark', persists via localStorage key 'llm-pipeline-ui'
- No FOUC prevention script in index.html currently -- research recommendation is sound
- No `tailwind.config.ts` exists (v4 CSS-first) -- task 42 spec references v3 patterns, research correctly flags this

### WCAG Contrast Analysis -- Background Mismatch
**Source:** step-2-status-color-tokens-research.md, index.css

Research uses gray-900 (#111827) as contrast reference. Actual backgrounds:
- Page: `--background: oklch(0.145 0 0)` (approx #242424, darker than gray-900)
- Card: `--card: oklch(0.205 0 0)` (approx #333333, lighter than gray-900)

Status badges appear on BOTH surfaces. Card background is lighter, meaning contrast ratios are LOWER than reported on cards. The -400 variant recommendation likely still passes (margins are 0.19:1 to 1.53:1 above AA), but should be verified against actual card surface.

### Status Token Architecture
**Source:** step-2-status-color-tokens-research.md, StatusBadge.tsx, StepTimeline.tsx, api/types.ts, events/types.py

Proposed two-layer pattern (CSS vars in :root/.dark + @theme inline aliases) correctly follows existing shadcn pattern. OKLCH color space matches existing tokens.

**Critical gap found:** 'cached' is NOT a backend step status. Backend StepStatus values: completed, running, failed, skipped, pending. When a step hits cache, it still completes as 'completed' -- CacheHit is a separate event with cached_at field. The frontend StepTimeline derives status from events but has no 'cached' derivation logic. Proposing --status-cached token without corresponding backend/frontend status is premature.

### Running Status Color Mismatch
**Source:** step-2-status-color-tokens-research.md, StatusBadge.tsx

Current StatusBadge uses AMBER for 'running' (border-amber-500 text-amber-600 dark:text-amber-400). Task 42 spec and research propose BLUE for 'running' (blue-400/blue-600). This is a visible color change that research does not call out. Needs explicit decision.

### EventStream Hardcoded Colors
**Source:** EventStream.tsx

EventStream uses event_type-based colors (step_started=blue, step_completed=green, llm_call=purple, extraction=amber, context=teal). These are event-type colors, not status colors. Research only discusses StatusBadge refactoring. Scope of EventStream migration is unclear.

### color-scheme Property Bug
**Source:** step-1-tailwind-dark-mode-research.md, ui.ts

Research recommends `color-scheme: dark` on both `:root` and `.dark`. Since the store supports theme toggling (light/dark exist), `:root` should be `color-scheme: light` and `.dark` should override to `color-scheme: dark`. Otherwise light-mode users see dark scrollbars/form controls.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| (pending -- see Questions below) | | |

## Assumptions Validated
- [x] Tailwind v4 uses CSS-first config, no tailwind.config.ts -- confirmed in codebase
- [x] @custom-variant dark already configured at index.css:5
- [x] @theme inline block exists with shadcn token aliases
- [x] Zustand store handles .dark class + localStorage persistence
- [x] Default theme is 'dark' in store (ui.ts:31)
- [x] No FOUC prevention exists in index.html
- [x] index.html has no class="dark" on html element
- [x] green-500 and yellow-500 pass WCAG AA on dark backgrounds
- [x] @tailwindcss/typography not needed for task 44 (downstream is build config only)
- [x] StepStatus type is 'completed' | 'running' | 'failed' | 'skipped' | 'pending' (no 'cached')
- [x] StatusBadge currently uses raw Tailwind classes, not semantic tokens

## Open Items
- Contrast ratios should be recalculated against actual card surface oklch(0.205 0 0) not just gray-900
- EventStream.tsx also has event-type colors (teal for context events, etc.) that may need tokens later
- @tailwindcss/typography deferred -- may be needed by future tasks with markdown/LLM output rendering

## Recommendations for Planning
1. Fix color-scheme: use `color-scheme: light` on `:root` and `color-scheme: dark` on `.dark`
2. Use -400 variants for running/failed/cached (if cached is kept) per research recommendation -- simpler and accessible
3. Add FOUC prevention inline script to index.html as described in research
4. Keep font loading decision separate from color token work -- can be decided independently
5. If 'cached' token is approved, add StepStatus type update + derivation logic in StepTimeline as part of this task to avoid orphan token
6. Clearly scope EventStream migration as in/out -- recommend out-of-scope for task 42, create follow-up task
