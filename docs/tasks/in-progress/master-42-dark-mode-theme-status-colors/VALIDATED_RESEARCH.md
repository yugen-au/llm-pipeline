# Research Summary

## Executive Summary

Validated both research outputs against codebase. All 6 ambiguities resolved via CEO input. Final scope: 5 status tokens (pending/running/completed/failed/skipped -- no cached), running=amber (not blue), -400 variants accepted for contrast, EventStream in scope (partial -- step lifecycle events only), fontsource for fonts (next/font unavailable in Vite), color-scheme corrected for light/dark toggle support.

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

**Gap found and resolved:** 'cached' is NOT a backend step status. Backend StepStatus values: completed, running, failed, skipped, pending. CEO decision: SKIP cached token. Define 5 tokens only (pending, running, completed, failed, skipped).

### Running Status Color -- Resolved
**Source:** step-2-status-color-tokens-research.md, StatusBadge.tsx

Current StatusBadge uses AMBER for 'running'. Task 42 spec proposed BLUE. CEO decision: keep AMBER. Token values for running: amber-400 (dark), amber-600 (light). Research OKLCH values for running must be updated from blue to amber equivalents.

### EventStream Migration -- In Scope (Partial)
**Source:** EventStream.tsx

CEO decision: EventStream IN SCOPE for task 42. However, only step lifecycle events map cleanly to status tokens:
- `step_started` -> --status-running (amber)
- `step_completed` -> --status-completed (green)
- `step_failed` / `pipeline_failed` -> --status-failed (red)
- `step_skipped` -> --status-skipped (yellow)

Non-status event types (`llm_call`=purple, `extraction`/`transformation`=amber, `context`=teal, `pipeline_started`/`pipeline_completed`=default) do NOT map to step status tokens. These need either (a) separate event-type tokens or (b) remain as hardcoded Tailwind classes. Planning must address this split.

### color-scheme Property -- Corrected
**Source:** step-1-tailwind-dark-mode-research.md, ui.ts

Research recommended `color-scheme: dark` on both `:root` and `.dark`. CEO confirmed correction: `:root` gets `color-scheme: light`, `.dark` gets `color-scheme: dark`. This ensures light-mode users see correct scrollbars/form controls.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Define --status-cached token? Backend has no 'cached' step status. | SKIP. 5 tokens only (pending/running/completed/failed/skipped). | Removes 1 token + avoids orphan token with no backend state |
| Running color: blue (task spec) or amber (current code)? | AMBER. Keep current. | Research OKLCH values for running must use amber-400/amber-600, not blue |
| Contrast: recalculate against actual card surface? | Accept -400 variants as sufficient margin. | No recalculation needed, proceed with -400 for failed/running adjustments |
| EventStream hardcoded colors in scope? | YES, include. Migrate to status tokens. | Expands scope; only step lifecycle events map to status tokens, non-status events need separate handling |
| Font loading: CDN vs fontsource vs next/font? | CEO said next/font but project is Vite+React (no Next.js). Equivalent: fontsource npm package (self-hosted, no CDN). | Use @fontsource packages, auto-bundled by Vite |
| color-scheme: dark on :root correct when light toggle exists? | NO. :root=light, .dark=dark. Confirmed correction. | Fixes research recommendation bug |

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
- EventStream non-status event types (llm_call, extraction, transformation, context, pipeline_started/completed) need either separate event-type tokens or remain hardcoded -- planning must decide
- @tailwindcss/typography deferred -- may be needed by future tasks with markdown/LLM output rendering
- fontsource package selection: Inter is common for dashboards, but specific font choice not yet decided

## Recommendations for Planning
1. Define 5 status tokens: --status-pending (gray-400/gray-500), --status-running (amber-400/amber-600), --status-completed (green-500/green-600), --status-failed (red-400/red-600), --status-skipped (yellow-500/yellow-600)
2. Use CSS custom properties in :root/.dark + @theme inline aliases (existing shadcn pattern)
3. Add `color-scheme: light` on `:root`, `color-scheme: dark` on `.dark`
4. Add FOUC prevention inline script to index.html (read localStorage, apply .dark before paint)
5. Use @fontsource npm packages for font loading (Vite self-hosts, no CDN dependency)
6. Migrate StatusBadge.tsx to semantic tokens (`text-status-failed` instead of `text-red-400 dark:text-red-400`)
7. Migrate EventStream.tsx step lifecycle events to status tokens; decide on non-status events during planning (keep hardcoded or add event-type tokens)
8. All OKLCH values for running status must use amber equivalents, not blue as in original research
