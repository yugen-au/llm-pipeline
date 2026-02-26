# Research: Tailwind CSS v4 Dark Mode Configuration

## Executive Summary

The codebase already has most dark mode infrastructure from task 29. Tailwind v4 uses CSS-first config (no tailwind.config.ts). Remaining work: add monospace font tokens, color-scheme meta, and status color tokens to `@theme inline` block in `src/index.css`.

---

## 1. Tailwind v4 vs v3: Key Differences

### No tailwind.config.ts
Tailwind v4 eliminates the JavaScript config file entirely. All configuration is done in CSS via directives:

| v3 Pattern | v4 Equivalent |
|---|---|
| `tailwind.config.ts` with `darkMode: 'class'` | `@custom-variant dark (&:where(.dark, .dark *))` in CSS |
| `theme.extend.colors` in JS | `@theme { --color-*: value; }` in CSS |
| `theme.extend.fontFamily` in JS | `@theme { --font-*: value; }` in CSS |
| `@tailwind base/components/utilities` | `@import "tailwindcss"` (single import) |
| `plugins: [require('@tailwindcss/typography')]` | `@plugin "@tailwindcss/typography"` in CSS |
| PostCSS config with tailwindcss plugin | `@tailwindcss/vite` Vite plugin (already configured) |

### @theme directive
Defines design tokens as CSS custom properties. Two variants:
- `@theme { }` - generates CSS custom properties AND utility classes
- `@theme inline { }` - generates utility classes only, does NOT emit CSS variables (used when variables are defined separately, e.g. by shadcn)

### @custom-variant
Replaces `darkMode: 'class'` config. The `:where()` wrapper ensures zero specificity:
```css
@custom-variant dark (&:where(.dark, .dark *));
```

### @layer
Same concept as v3 but with native CSS cascade layers:
- `@layer base` - reset/normalize styles, element defaults
- `@layer components` - reusable component classes
- `@layer utilities` - single-purpose utility overrides

---

## 2. Current Codebase State (from task 29)

### Already Configured

| Feature | Location | Status |
|---|---|---|
| `@import "tailwindcss"` | `src/index.css:1` | Done |
| `@import "tw-animate-css"` | `src/index.css:2` | Done |
| `@import "shadcn/tailwind.css"` | `src/index.css:3` | Done |
| `@custom-variant dark` | `src/index.css:5` | Done |
| `@theme inline` with shadcn tokens | `src/index.css:7-46` | Done |
| `:root` OKLCH light vars | `src/index.css:48-81` | Done |
| `.dark` OKLCH dark vars | `src/index.css:83-115` | Done |
| `@layer base` body styles | `src/index.css:117-121` | Done |
| `.dark` class on `documentElement` | `src/stores/ui.ts` | Done |
| Default theme `'dark'` | `src/stores/ui.ts:31` | Done |
| localStorage persistence | `src/stores/ui.ts:57-69` | Done |
| `@tailwindcss/vite` plugin | `vite.config.ts:5,11` | Done |

### Not Yet Configured

| Feature | Required By | Priority |
|---|---|---|
| Monospace font tokens (`--font-mono`) | Task 42 | High |
| `color-scheme: dark` on `:root` | Task 42 | Medium |
| Status color tokens | Task 42 (step 2 agent) | High |
| `@tailwindcss/typography` plugin | Task 42 spec | Low (optional) |
| JetBrains Mono font loading | Task 42 | High |

---

## 3. Dark Mode Class Application

### Current Implementation (ui.ts Zustand store)
The store applies/removes `.dark` on `document.documentElement` via:
1. `setTheme()` action - toggles class on demand
2. `onRehydrateStorage` callback - applies persisted theme on page load
3. Default value `'dark'` ensures dark mode on first visit

### index.html
Currently does NOT have `class="dark"` on `<html>`. This means there's a brief flash of light mode (FOUC) before Zustand hydrates from localStorage. The store import in `main.tsx` (`import '@/stores/ui'`) triggers hydration, which adds the class.

### Recommendation: Add FOUC prevention
Add inline script to `index.html` `<head>` that reads localStorage before React mounts:
```html
<script>
  try {
    var s = JSON.parse(localStorage.getItem('llm-pipeline-ui'));
    if (!s || !s.state || s.state.theme !== 'light')
      document.documentElement.classList.add('dark');
  } catch(e) { document.documentElement.classList.add('dark'); }
</script>
```
This eliminates the light-mode flash. Falls back to dark if localStorage is missing/corrupt.

---

## 4. Monospace Font Configuration

### Tailwind v4 Pattern
Add to `@theme inline` block in `src/index.css`:
```css
@theme inline {
  --font-mono: 'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  /* ...existing shadcn tokens... */
}
```
This overrides the default `font-mono` utility to prioritize JetBrains Mono with Fira Code fallback, then system monospace stack.

### Font Loading Options

#### Option A: Google Fonts CDN (recommended for simplicity)
Add to `index.html` `<head>`:
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
```
- Pros: zero build config, CDN caching, automatic subsetting
- Cons: external dependency, privacy (Google tracks requests)

#### Option B: Self-hosted via @font-face
Download woff2 files to `public/fonts/`, add to CSS:
```css
@font-face {
  font-family: 'JetBrains Mono';
  font-style: normal;
  font-weight: 400 700;
  font-display: swap;
  src: url('/fonts/JetBrainsMono-Variable.woff2') format('woff2');
}
```
- Pros: no external deps, full privacy, works offline
- Cons: larger initial bundle, manual updates

#### Option C: fontsource (npm package)
```bash
npm install @fontsource-variable/jetbrains-mono
```
Then in `main.tsx`:
```typescript
import '@fontsource-variable/jetbrains-mono';
```
- Pros: npm-managed versioning, automatic tree-shaking, Vite handles bundling
- Cons: adds to JS bundle, another dependency

### Recommendation
Option A (Google Fonts) for initial setup. Simplest, widely used, good performance with preconnect hints. Can migrate to Option B later if privacy is a concern.

---

## 5. color-scheme Property

Add to `:root` in `src/index.css`:
```css
:root {
  color-scheme: dark;
  /* ...existing vars... */
}
```
And conditionally in `.dark`:
```css
.dark {
  color-scheme: dark;
  /* ...existing vars... */
}
```

This tells the browser to render form controls, scrollbars, and other UA-styled elements in dark mode. Without it, native inputs/scrollbars appear in light mode even when the page is visually dark.

Note: Since dark is the default theme, setting `color-scheme: dark` on `:root` is correct. If light mode support is needed, `:root` should use `color-scheme: light dark` and `.dark` should use `color-scheme: dark`.

---

## 6. @tailwindcss/typography Plugin

Task spec mentions `require('@tailwindcss/typography')` (v3 syntax). In v4:
```css
@plugin "@tailwindcss/typography";
```

This provides `prose` classes for rich text/markdown rendering. Useful for displaying LLM output or pipeline step logs. However, it's not strictly required for dark mode/status colors. Recommend deferring unless explicitly needed for a downstream task.

**Installation:** `npm install @tailwindcss/typography`

---

## 7. Task Spec Discrepancies

| Task Spec Says | Actual Codebase | Resolution |
|---|---|---|
| "Update `tailwind.config.ts`" | No config file; v4 uses CSS-first | Use `@theme` in `src/index.css` |
| "Create `src/styles/globals.css`" | CSS lives at `src/index.css` (task 29) | Extend `src/index.css` |
| `@tailwind base/components/utilities` | `@import "tailwindcss"` (v4 single import) | Already correct |
| `darkMode: 'class'` | `@custom-variant dark (...)` | Already correct |
| `theme.extend.colors` JS object | `@theme { --color-*: value; }` CSS | Use @theme directive |
| `require('@tailwindcss/typography')` | `@plugin "@tailwindcss/typography"` | v4 CSS syntax |
| "Next.js pipeline monitoring dashboard" | Vite + React 19 + TanStack Router | Research covers actual stack |

---

## 8. Recommended Implementation Plan

### Changes to `src/index.css`

1. Add `--font-mono` to `@theme inline` block
2. Add `color-scheme: dark` to `:root` block
3. Add `color-scheme: dark` to `.dark` block
4. (Step 2 agent) Add `--color-status-*` tokens to `@theme inline` block

### Changes to `index.html`

1. Add FOUC-prevention inline script in `<head>`
2. Add Google Fonts preconnect + stylesheet link for JetBrains Mono

### No Changes Needed

- `vite.config.ts` - already correct
- `ui.ts` store - already handles dark class + persistence
- No `tailwind.config.ts` to create (v4 CSS-first)
- No PostCSS config needed (`@tailwindcss/vite` handles it)

---

## 9. CSS Architecture Reference

Final `src/index.css` structure after task 42:
```
@import "tailwindcss"              -- core framework
@import "tw-animate-css"           -- shadcn animations
@import "shadcn/tailwind.css"      -- shadcn base

@custom-variant dark (...)         -- class-based dark mode

@theme inline {                    -- design tokens (utilities only)
  --font-mono: ...                 -- [NEW] monospace font stack
  --color-status-*: ...            -- [NEW] step status colors (step 2)
  --radius-*: ...                  -- existing shadcn radius tokens
  --color-*: ...                   -- existing shadcn color mappings
}

:root {                            -- light mode CSS variables
  color-scheme: dark;              -- [NEW] browser chrome dark mode
  ...existing OKLCH vars...
}

.dark {                            -- dark mode CSS variables
  color-scheme: dark;              -- [NEW] browser chrome dark mode
  ...existing OKLCH vars...
}

@layer base {                      -- base element styles
  * { @apply border-border... }
  body { @apply bg-background... }
}
```

---

## Sources

- Tailwind CSS v4 docs (Context7: /websites/tailwindcss)
- Existing codebase: `llm_pipeline/ui/frontend/src/index.css`
- Task 29 implementation: `docs/tasks/completed/master-29-init-frontend-structure/`
- Graphiti memory: llm-pipeline group facts on Tailwind v4 config
