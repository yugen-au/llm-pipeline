# IMPLEMENTATION - STEP 5: CONFIGURE TAILWINDCSS V4
**Status:** completed

## Summary
Replaced Vite scaffold's default `index.css` with Tailwind v4 CSS-first configuration. Added `@import "tailwindcss"`, class-based dark mode via `@custom-variant dark`, and empty `@theme inline` block for shadcn to extend in Step 6. No JS config file created (v4 pattern). No `tw-animate-css` import added (shadcn init adds it in Step 6).

## Files
**Created:** none
**Modified:** `llm_pipeline/ui/frontend/src/index.css`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/index.css`
Replaced entire Vite scaffold default CSS with Tailwind v4 CSS-first config.

```css
# Before
:root {
  font-family: system-ui, Avenir, Helvetica, Arial, sans-serif;
  line-height: 1.5;
  /* ... 68 lines of scaffold CSS ... */
}

# After
@import "tailwindcss";

@custom-variant dark (&:where(.dark, .dark *));

@theme inline {
  /* shadcn/ui will extend this block with OKLCH color tokens in Step 6 */
}
```

## Decisions
### Use `@theme inline` instead of `@theme`
**Choice:** `@theme inline` block (empty)
**Rationale:** `@theme inline` prevents Tailwind from generating CSS custom properties for theme values defined within the block. Since shadcn init (Step 6) will add its own OKLCH CSS variables in `:root`/`.dark` selectors, using `inline` avoids duplicate variable declarations. The block is empty now as a placeholder for shadcn to extend.

### Class-based dark mode selector
**Choice:** `@custom-variant dark (&:where(.dark, .dark *))`
**Rationale:** Matches Tailwind v4 docs and shadcn/ui expectations. Uses `:where()` for zero specificity. The `.dark` class will be applied to `<html>` element in `main.tsx` (Step 8) for default dark mode.

## Verification
[x] `index.css` contains `@import "tailwindcss"` as first directive
[x] `index.css` contains `@custom-variant dark (&:where(.dark, .dark *))` for class-based dark mode
[x] `index.css` contains `@theme inline` block (empty, ready for shadcn)
[x] No `tailwind.config.ts` file exists in frontend directory
[x] No `@import "tw-animate-css"` present (reserved for Step 6 shadcn init)
[x] All Vite scaffold default styles removed
