# IMPLEMENTATION - STEP 6: FILTERBAR COMPONENT
**Status:** completed

## Summary
Created FilterBar component with shadcn Select, using props pattern (pure component, parent owns navigation). Added Radix UI polyfills to test setup for jsdom compatibility.

## Files
**Created:** `llm_pipeline/ui/frontend/src/components/runs/FilterBar.tsx`, `llm_pipeline/ui/frontend/src/components/runs/FilterBar.test.tsx`
**Modified:** `llm_pipeline/ui/frontend/src/test/setup.ts`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/runs/FilterBar.tsx`
New file. Pure component accepting `status: string` and `onStatusChange: (status: string) => void`. Uses `__all` sentinel value internally because Radix Select disallows empty string values. Translates `__all` <-> `''` at the boundary so parent sees empty string for "All".

### File: `llm_pipeline/ui/frontend/src/components/runs/FilterBar.test.tsx`
New file. 6 tests: renders label + trigger, shows "All" when status='', shows current status, renders all 4 options when opened, calls onStatusChange with status value, calls onStatusChange with '' when "All" selected.

### File: `llm_pipeline/ui/frontend/src/test/setup.ts`
Added polyfills for `hasPointerCapture`, `setPointerCapture`, `releasePointerCapture`, and `scrollIntoView` on Element.prototype. Required by Radix UI Select internals that use pointer capture APIs not available in jsdom.

```
# Before
import '@testing-library/jest-dom/vitest'

# After
import '@testing-library/jest-dom/vitest'

// Polyfill pointer capture APIs missing in jsdom (required by Radix UI)
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false
}
if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = () => {}
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = () => {}
}

// Polyfill scrollIntoView (used by Radix for select items)
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {}
}
```

## Decisions
### Radix Select empty value sentinel
**Choice:** Use `__all` sentinel internally, translate to/from `''` at component boundary
**Rationale:** Radix Select `SelectItem` requires non-empty string values. Using sentinel keeps parent API clean (empty string = all statuses) while satisfying Radix constraint.

### Polyfills in test setup
**Choice:** Add pointer capture + scrollIntoView polyfills to shared `setup.ts`
**Rationale:** jsdom lacks these DOM APIs that Radix UI relies on. Adding to shared setup benefits all future component tests using Radix primitives.

## Verification
[x] FilterBar renders all 4 options (All, Running, Completed, Failed)
[x] onStatusChange called with correct values on selection
[x] Shows "All" when status=''
[x] All 6 FilterBar tests pass
[x] Full test suite (39 tests) passes with no regressions
[x] TypeScript type check passes
