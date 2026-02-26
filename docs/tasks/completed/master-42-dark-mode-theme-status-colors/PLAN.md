# PLANNING

## Summary

Extend the existing Tailwind v4 CSS-first setup in `src/index.css` with: correct `color-scheme` properties for light/dark toggle, 5 step status color tokens (pending/running/completed/failed/skipped) in OKLCH following the existing shadcn two-layer pattern, JetBrains Mono font token via fontsource, and a FOUC-prevention script in `index.html`. Migrate `StatusBadge.tsx` and the step lifecycle events in `EventStream.tsx` to use the new semantic status tokens. Non-status event types in `EventStream.tsx` (llm_call, extraction, transformation, context, pipeline_started/completed) retain existing hardcoded Tailwind classes as they do not map to step status states.

## Plugin & Agents

**Plugin:** frontend-mobile-development
**Subagents:** [available agents]
**Skills:** [available skills]

## Phases

1. **Token Infrastructure**: Add color-scheme properties, 5 status color tokens, and font token to `src/index.css`; add FOUC script and fontsource to `index.html` + `main.tsx`
2. **Component Migration**: Migrate `StatusBadge.tsx` and `EventStream.tsx` step lifecycle events to semantic status token classes

## Architecture Decisions

### Non-Status Event Types in EventStream

**Choice:** Keep existing hardcoded Tailwind classes for non-status events (llm_call, extraction, transformation, context, pipeline_started, pipeline_completed)
**Rationale:** Task 42 scope is step status color tokens. These event types represent pipeline operational events, not step states. Creating separate event-type tokens would exceed task scope. VALIDATED_RESEARCH confirms only step lifecycle events map to status tokens.
**Alternatives:** Define separate `--event-type-*` tokens for all event types (deferred to a future task if needed)

### OKLCH Values for Running (Amber) Token

**Choice:** amber-400 for dark mode (`oklch(0.828 0.189 84.429)`), amber-600 for light mode (`oklch(0.666 0.179 58.318)`)
**Rationale:** CEO confirmed amber (not blue as originally spec'd). Matches existing StatusBadge usage. -400 variant accepted for WCAG AA compliance.
**Alternatives:** amber-500 (fails WCAG AA for normal text on dark card background)

### Status Token Architecture (Two-Layer Pattern)

**Choice:** CSS custom properties in `:root`/`.dark` blocks + `@theme inline` aliases
**Rationale:** Identical to existing shadcn token pattern in the codebase. OKLCH color space matches all existing tokens. `@theme inline` avoids duplicate CSS variable emission (shadcn owns the `:root`/`.dark` vars).
**Alternatives:** Static `@theme` (non-inline) - rejected because static values cannot switch between light/dark themes

### Font Loading Strategy

**Choice:** `@fontsource-variable/jetbrains-mono` npm package imported in `main.tsx`
**Rationale:** CEO confirmed fontsource as equivalent to next/font for Vite+React project. npm-managed, Vite auto-bundles, no CDN dependency, no privacy concerns.
**Alternatives:** Google Fonts CDN (privacy concerns, external dependency); self-hosted @font-face (manual maintenance)

### color-scheme Property

**Choice:** `color-scheme: light` on `:root`, `color-scheme: dark` on `.dark`
**Rationale:** CEO confirmed correction. Ensures scrollbars and native form controls render correctly in both light and dark modes. Research originally recommended dark on both which was incorrect.
**Alternatives:** `color-scheme: dark` on both (incorrect - breaks light-mode native controls)

## Implementation Steps

### Step 1: Add Status Tokens and color-scheme to index.css

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /websites/tailwindcss
**Group:** A

1. Add `color-scheme: light` as first property inside the `:root` block in `llm_pipeline/ui/frontend/src/index.css`
2. Add `color-scheme: dark` as first property inside the `.dark` block in `llm_pipeline/ui/frontend/src/index.css`
3. Add 5 status CSS custom properties to the `:root` block (light mode values):
   - `--status-pending: oklch(0.551 0.018 256.802)` (gray-500)
   - `--status-running: oklch(0.666 0.179 58.318)` (amber-600)
   - `--status-completed: oklch(0.627 0.194 149.214)` (green-600)
   - `--status-failed: oklch(0.577 0.245 27.325)` (red-600)
   - `--status-skipped: oklch(0.681 0.162 75.834)` (yellow-600)
4. Add 5 status CSS custom properties to the `.dark` block (dark mode values):
   - `--status-pending: oklch(0.716 0.013 256.788)` (gray-400)
   - `--status-running: oklch(0.828 0.189 84.429)` (amber-400)
   - `--status-completed: oklch(0.765 0.177 163.223)` (green-500)
   - `--status-failed: oklch(0.704 0.191 22.216)` (red-400)
   - `--status-skipped: oklch(0.795 0.184 86.047)` (yellow-500)
5. Add 5 `@theme inline` aliases inside the existing `@theme inline` block:
   - `--color-status-pending: var(--status-pending)`
   - `--color-status-running: var(--status-running)`
   - `--color-status-completed: var(--status-completed)`
   - `--color-status-failed: var(--status-failed)`
   - `--color-status-skipped: var(--status-skipped)`
6. Add `--font-mono: 'JetBrains Mono Variable', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace` to the `@theme inline` block

### Step 2: Add FOUC Script and Font Loading to index.html

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Add inline FOUC-prevention script in `<head>` of `llm_pipeline/ui/frontend/index.html` before any other scripts:
   ```html
   <script>
     try {
       var s = JSON.parse(localStorage.getItem('llm-pipeline-ui'))
       if (!s || !s.state || s.state.theme !== 'light')
         document.documentElement.classList.add('dark')
     } catch(e) { document.documentElement.classList.add('dark') }
   </script>
   ```
   Script logic: reads localStorage key `llm-pipeline-ui` (Zustand store key confirmed in ui.ts), defaults to dark if absent or corrupt, only stays light if state.theme === 'light'

### Step 3: Install Fontsource and Import in main.tsx

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /websites/fontsource
**Group:** A

1. Run `npm install @fontsource-variable/jetbrains-mono` in `llm_pipeline/ui/frontend/`
2. Add import `import '@fontsource-variable/jetbrains-mono'` at the top of `llm_pipeline/ui/frontend/src/main.tsx` (before other imports)

### Step 4: Migrate StatusBadge.tsx to Status Tokens

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. In `llm_pipeline/ui/frontend/src/components/runs/StatusBadge.tsx`, replace `statusConfig` entries with semantic token classes:
   - `running`: replace `'border-amber-500 text-amber-600 dark:text-amber-400'` with `'border-status-running text-status-running'`, keep `variant: 'outline'`
   - `completed`: replace `'border-green-500 text-green-600 dark:text-green-400'` with `'border-status-completed text-status-completed'`, keep `variant: 'outline'`
   - `failed`: keep `variant: 'destructive'`, className remains `''` (destructive variant already uses `--destructive` token which maps to red; alternatively use `variant: 'outline'` with `'border-status-failed text-status-failed'` for consistency - use outline approach for semantic clarity)
   - `skipped`: replace `'text-muted-foreground'` with `'border-status-skipped text-status-skipped'`, change `variant` from `'secondary'` to `'outline'`
   - `pending`: replace `'text-muted-foreground'` with `'border-status-pending text-status-pending'`, change `variant` from `'secondary'` to `'outline'`
2. Remove `BadgeConfig` variant values `'secondary'` and `'destructive'` from statusConfig if no longer used; keep `'outline'` as uniform variant

### Step 5: Migrate EventStream.tsx Step Lifecycle Events to Status Tokens

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. In `llm_pipeline/ui/frontend/src/components/live/EventStream.tsx`, update `getEventBadgeConfig` for step lifecycle events only:
   - `step_started`: replace `'border-blue-500 text-blue-600 dark:text-blue-400'` with `'border-status-running text-status-running'` (amber, running state)
   - `step_completed`: replace `'border-green-500 text-green-600 dark:text-green-400'` with `'border-status-completed text-status-completed'`
   - `step_failed` / `pipeline_failed`: replace `variant: 'destructive', className: ''` with `variant: 'outline', className: 'border-status-failed text-status-failed'`
   - `step_skipped`: replace `variant: 'secondary', className: 'text-muted-foreground'` with `variant: 'outline', className: 'border-status-skipped text-status-skipped'`
2. Leave unchanged (non-status operational events):
   - `llm_call`: keep `'border-purple-500 text-purple-600 dark:text-purple-400'`
   - `extraction` / `transformation`: keep `'border-amber-500 text-amber-600 dark:text-amber-400'`
   - `context`: keep `'border-teal-500 text-teal-600 dark:text-teal-400'`
   - `pipeline_started` / `pipeline_completed`: keep `variant: 'default'`

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| OKLCH values for amber-400/600 differ from Tailwind's canonical values | Medium | Values sourced from research doc cross-checked against codebase (chart-4 uses same amber hue). Verify visually after implementation. |
| FOUC script localStorage key changes (Zustand store rename) | Low | Key is `llm-pipeline-ui` confirmed in ui.ts. Document assumption in code comment. |
| fontsource package name mismatch (`@fontsource-variable/jetbrains-mono` vs `@fontsource/jetbrains-mono`) | Low | Use variable package for full weight range. Verify package exists on npm before install. |
| StatusBadge `failed` state: switching from `destructive` variant to `outline` changes badge background | Medium | `destructive` variant has a colored background; `outline` with `border-status-failed text-status-failed` is border+text only. Decide during implementation whether visual change is acceptable or if `failed` should retain `destructive` variant. |
| Non-status EventStream events retain hardcoded `dark:` prefix classes which become redundant with tokens | Low | Acceptable technical debt; those events are not in scope. Future task can define event-type tokens. |
| Skipped status: yellow-500 and amber-400 (running) are visually similar in dark mode | Low | Hue difference (84 vs 86) and lightness difference (0.828 vs 0.795) provide sufficient distinction. Monitor during visual review. |

## Success Criteria

- [ ] `src/index.css` `:root` block has `color-scheme: light`
- [ ] `src/index.css` `.dark` block has `color-scheme: dark`
- [ ] `src/index.css` `@theme inline` block has 5 `--color-status-*` aliases and `--font-mono`
- [ ] `src/index.css` `:root` and `.dark` blocks each have 5 `--status-*` custom properties
- [ ] `index.html` has inline FOUC script in `<head>` that reads `llm-pipeline-ui` from localStorage
- [ ] `@fontsource-variable/jetbrains-mono` installed in package.json
- [ ] Font import present in `main.tsx`
- [ ] `StatusBadge.tsx` uses `text-status-*` and `border-status-*` classes, no raw color classes
- [ ] `EventStream.tsx` step lifecycle events use `text-status-*` and `border-status-*` classes
- [ ] `EventStream.tsx` non-status events (llm_call, extraction, etc.) unchanged
- [ ] No TypeScript errors introduced
- [ ] Dark/light theme toggle shows correct colors for all 5 statuses in both modes
- [ ] Page load in dark mode shows no flash of light mode (FOUC eliminated)

## Phase Recommendation

**Risk Level:** low
**Reasoning:** All changes are additive (new CSS vars, new tokens) or mechanical substitutions (token class names). No API changes, no state management changes, no routing changes. Downstream task 44 is build config only and not affected. FOUC fix is a pure HTML change. Font loading is additive. StatusBadge and EventStream migrations are straightforward find-replace of class strings.
**Suggested Exclusions:** testing, review
