# IMPLEMENTATION - STEP 1: STATUS TOKENS AND COLOR-SCHEME
**Status:** completed

## Summary
Added color-scheme properties, 5 step status color tokens (OKLCH) for light/dark modes, @theme inline aliases, and --font-mono token to the existing Tailwind v4 CSS-first config.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/src/index.css
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/index.css`
Added color-scheme properties to :root and .dark blocks, 5 --status-* custom properties in both blocks with OKLCH values, 5 --color-status-* @theme inline aliases, and --font-mono token.

```
# Before (@theme inline block ended with)
  --color-sidebar-ring: var(--sidebar-ring)
}

# After (@theme inline block now ends with)
  --color-sidebar-ring: var(--sidebar-ring);
  --color-status-pending: var(--status-pending);
  --color-status-running: var(--status-running);
  --color-status-completed: var(--status-completed);
  --color-status-failed: var(--status-failed);
  --color-status-skipped: var(--status-skipped);
  --font-mono: 'JetBrains Mono Variable', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
}
```

```
# Before (:root block started with)
:root {
  --radius: 0.625rem;

# After (:root block starts with)
:root {
  color-scheme: light;
  --radius: 0.625rem;
```

```
# Before (:root block ended with)
  --sidebar-ring: oklch(0.708 0 0);
}

# After (:root block ends with)
  --sidebar-ring: oklch(0.708 0 0);
  --status-pending: oklch(0.551 0.018 256.802);
  --status-running: oklch(0.666 0.179 58.318);
  --status-completed: oklch(0.627 0.194 149.214);
  --status-failed: oklch(0.577 0.245 27.325);
  --status-skipped: oklch(0.681 0.162 75.834);
}
```

```
# Before (.dark block started with)
.dark {
  --background: oklch(0.145 0 0);

# After (.dark block starts with)
.dark {
  color-scheme: dark;
  --background: oklch(0.145 0 0);
```

```
# Before (.dark block ended with)
  --sidebar-ring: oklch(0.556 0 0);
}

# After (.dark block ends with)
  --sidebar-ring: oklch(0.556 0 0);
  --status-pending: oklch(0.716 0.013 256.788);
  --status-running: oklch(0.828 0.189 84.429);
  --status-completed: oklch(0.765 0.177 163.223);
  --status-failed: oklch(0.704 0.191 22.216);
  --status-skipped: oklch(0.795 0.184 86.047);
}
```

## Decisions
None - all values and patterns were pre-defined in PLAN.md.

## Verification
[x] color-scheme: light present in :root block
[x] color-scheme: dark present in .dark block
[x] 5 --status-* custom properties in :root with correct light OKLCH values
[x] 5 --status-* custom properties in .dark with correct dark OKLCH values
[x] 5 --color-status-* aliases in @theme inline block
[x] --font-mono token in @theme inline block
[x] Follows existing shadcn two-layer pattern (CSS vars + @theme inline aliases)
[x] All OKLCH values match PLAN.md Step 1 specification
