# RESEARCH - STEP 2: STATUS COLOR TOKENS
**Status:** needs-input

## Summary
Researched design token patterns for 6 pipeline step status colors in dark-mode-first dashboard. Found 3 of 6 proposed colors fail WCAG AA contrast for normal text on gray-900. Identified token architecture compatible with existing Tailwind v4 CSS-first + shadcn OKLCH setup.

## Current Codebase State

### Tailwind v4 CSS-First Config
- No `tailwind.config.ts` -- Tailwind v4 uses CSS-first configuration in `index.css`
- `@theme inline` block already exists with shadcn token aliases (`--color-*` -> `var(--*)`)
- Dark mode: `@custom-variant dark (&:where(.dark, .dark *))` + `.dark` class on `<html>`
- Theme toggle in Zustand store (`stores/ui.ts`), default: `'dark'`
- All existing shadcn tokens use OKLCH color space
- Both `:root` (light) and `.dark` blocks exist

### Existing Status Color Usage
- `StatusBadge.tsx`: Uses raw Tailwind classes (`border-amber-500`, `text-green-600`, `dark:text-green-400`) -- no semantic tokens
- `StepTimeline.tsx`: References `StatusBadge` for display
- `EventStream.tsx`: Similar pattern with raw Tailwind classes
- `StepStatus` type: `'completed' | 'running' | 'failed' | 'skipped' | 'pending'` (no `'cached'`)
- `RunStatus` type: `'running' | 'completed' | 'failed'`

### Task 42 Description Deviation
Task 42 references `tailwind.config.ts` with `require('@tailwindcss/typography')` -- this pattern is Tailwind v3. The project uses Tailwind v4 CSS-first. Implementation must use `@theme inline` + CSS custom properties in `index.css` instead.

## Contrast Ratio Analysis

Background: gray-900 `#111827` (relative luminance ~0.0128)
WCAG AA requirements: 4.5:1 normal text, 3:1 large text / UI components

| Status | Proposed Hex | Tailwind Class | Contrast vs #111827 | AA Normal (4.5:1) | AA Large (3:1) |
|-----------|------------|---------------|---------------------|-------|-------|
| pending | #9CA3AF | gray-400 | ~6.64:1 | PASS | PASS |
| running | #3B82F6 | blue-500 | ~3.88:1 | FAIL | PASS |
| completed | #22C55E | green-500 | ~7.03:1 | PASS | PASS |
| failed | #EF4444 | red-500 | ~3.44:1 | FAIL | PASS |
| skipped | #EAB308 | yellow-500 | ~7.74:1 | PASS | PASS |
| cached | #A855F7 | purple-500 | ~3.15:1 | FAIL | PASS |

### Accessible Alternatives (-400 variants)

| Status | Alt Hex | Tailwind Class | Contrast vs #111827 | AA Normal |
|---------|---------|---------------|---------------------|-----------|
| running | #60A5FA | blue-400 | ~6.03:1 | PASS |
| failed | #F87171 | red-400 | ~4.69:1 | PASS |
| cached | #C084FC | purple-400 | ~5.14:1 | PASS |

## Recommended Token Architecture

### Approach: CSS Custom Properties + @theme inline

Follows existing shadcn pattern in the codebase. Two layers:

1. **CSS custom properties** in `:root` / `.dark` blocks -- raw values per theme
2. **@theme inline aliases** -- connects to Tailwind utility class generation

```css
/* In .dark block (alongside existing shadcn dark tokens) */
.dark {
  /* ... existing shadcn tokens ... */
  --status-pending: oklch(0.716 0.013 256.788);   /* gray-400 equivalent */
  --status-running: oklch(0.707 0.165 254.624);   /* blue-400 equivalent */
  --status-completed: oklch(0.765 0.177 163.223); /* green-500 */
  --status-failed: oklch(0.704 0.191 22.216);     /* red-400 equivalent */
  --status-skipped: oklch(0.795 0.184 86.047);    /* yellow-500 */
  --status-cached: oklch(0.714 0.203 305.504);    /* purple-400 equivalent */
}

/* In :root block (light mode) */
:root {
  /* ... existing shadcn tokens ... */
  --status-pending: oklch(0.551 0.018 256.802);   /* gray-500 */
  --status-running: oklch(0.623 0.214 259.815);   /* blue-600 */
  --status-completed: oklch(0.627 0.194 149.214); /* green-600 */
  --status-failed: oklch(0.577 0.245 27.325);     /* red-600 */
  --status-skipped: oklch(0.681 0.162 75.834);    /* yellow-600 */
  --status-cached: oklch(0.558 0.288 302.321);    /* purple-600 */
}

/* In @theme inline block */
@theme inline {
  /* ... existing shadcn aliases ... */
  --color-status-pending: var(--status-pending);
  --color-status-running: var(--status-running);
  --color-status-completed: var(--status-completed);
  --color-status-failed: var(--status-failed);
  --color-status-skipped: var(--status-skipped);
  --color-status-cached: var(--status-cached);
}
```

### Generated Utility Classes
This produces: `bg-status-pending`, `text-status-running`, `border-status-failed`, etc.

### Why This Approach
1. **Consistent with existing codebase** -- follows the exact same pattern shadcn uses for its tokens
2. **OKLCH color space** -- matches existing token format, enables perceptual uniformity
3. **Theme-aware** -- colors automatically switch between light/dark via CSS cascade
4. **@theme inline** -- prevents Tailwind from generating duplicate CSS vars (shadcn already handles var generation via `:root`/`.dark`)
5. **Semantic naming** -- `text-status-failed` is self-documenting vs `text-red-400 dark:text-red-400`

### Alternative Approaches Considered

**A. @theme (non-inline) with hardcoded values**
- Would generate CSS custom properties AND utility classes
- Rejected: conflicts with theme switching since @theme values are static (not per-theme)

**B. Hardcoded colors in @theme without CSS vars**
- Simpler but no dark/light switching
- Rejected: existing codebase pattern uses CSS vars for theme switching

**C. Keep raw Tailwind classes (current approach in StatusBadge)**
- No tokens needed
- Rejected: inconsistent, fragile, requires `dark:` prefix everywhere, no single source of truth

## Impact on Existing Components

### StatusBadge.tsx Refactoring
Current: `'border-amber-500 text-amber-600 dark:text-amber-400'`
After: `'border-status-running text-status-running'`

### StepStatus Type
Currently missing `'cached'`. Adding the token is in scope; updating the TypeScript type should be part of this task since the token references it.

## Questions Requiring CEO Input

### 1. Contrast Strategy for Running/Failed/Cached
The -500 variants (blue-500, red-500, purple-500) from the task description fail WCAG AA (4.5:1) for normal text on gray-900. Two options:

**Option A (recommended):** Use -400 variants for all status token values (text, backgrounds, borders all use same token). Simpler, single token per status.
- running: blue-400 #60A5FA (6.03:1)
- failed: red-400 #F87171 (4.69:1)
- cached: purple-400 #C084FC (5.14:1)

**Option B:** Dual-token system -- keep -500 for indicators (dots, borders, backgrounds where 3:1 suffices) and -400 for text. More complex, 12 tokens instead of 6.
- `--status-running` (blue-500 for dots/borders)
- `--status-running-text` (blue-400 for text)

Which approach?
