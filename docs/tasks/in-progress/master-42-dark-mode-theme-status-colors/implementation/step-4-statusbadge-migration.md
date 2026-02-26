# IMPLEMENTATION - STEP 4: STATUSBADGE MIGRATION
**Status:** completed

## Summary
Migrated StatusBadge.tsx from hardcoded Tailwind color classes to semantic status token classes. All five statuses now use uniform `variant: 'outline'` with `border-status-*` and `text-status-*` classes that resolve via CSS custom properties, eliminating `dark:` prefixes.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/src/components/runs/StatusBadge.tsx
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/runs/StatusBadge.tsx`
Replaced all hardcoded color classes with semantic status tokens. Unified all variants to `'outline'`. Narrowed `BadgeConfig.variant` type from `'outline' | 'destructive' | 'secondary'` to `'outline'`.

```
# Before
running:   variant 'outline',   className 'border-amber-500 text-amber-600 dark:text-amber-400'
completed: variant 'outline',   className 'border-green-500 text-green-600 dark:text-green-400'
failed:    variant 'destructive', className ''
skipped:   variant 'secondary',  className 'text-muted-foreground'
pending:   variant 'secondary',  className 'text-muted-foreground'

# After
running:   variant 'outline', className 'border-status-running text-status-running'
completed: variant 'outline', className 'border-status-completed text-status-completed'
failed:    variant 'outline', className 'border-status-failed text-status-failed'
skipped:   variant 'outline', className 'border-status-skipped text-status-skipped'
pending:   variant 'outline', className 'border-status-pending text-status-pending'
```

## Decisions
### Uniform outline variant for failed status
**Choice:** Changed `failed` from `destructive` variant to `outline` with `border-status-failed text-status-failed`
**Rationale:** Plan explicitly states "use outline approach for semantic clarity". Uniform `outline` variant across all statuses ensures consistent visual language (border+text only). The `--status-failed` token already provides the correct red color in both modes.

### Narrowed BadgeConfig type
**Choice:** Changed `BadgeConfig.variant` from `'outline' | 'destructive' | 'secondary'` to `'outline'`
**Rationale:** All statuses now use `'outline'` exclusively. Narrowing the type prevents accidental reintroduction of other variants.

## Verification
[x] All 5 statuses use `border-status-*` and `text-status-*` classes
[x] No raw color classes remain in statusConfig
[x] No `dark:` prefixes in statusConfig
[x] All variants are `'outline'`
[x] TypeScript compiles with no errors (`npx tsc --noEmit` clean)
[x] Fallback badge for unknown statuses unchanged (still `variant="secondary"`)
