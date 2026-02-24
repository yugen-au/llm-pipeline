# IMPLEMENTATION - STEP 8: REWRITE TESTS
**Status:** completed

## Summary
Rewrote StepDetailPanel.test.tsx for the new Sheet+Tabs implementation. All 8 original test scenarios updated for Radix portal DOM structure plus 2 new tests (7-tab verification, tab switching). All 10 tests pass against the Step 7 implementation.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.test.tsx
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.test.tsx`
Full rewrite. Key changes from old to new:

```
# Before (old div-based assertions)
- CSS class assertions: translate-x-full / translate-x-0
- container.querySelectorAll('.animate-pulse')
- screen.getByRole('button', { name: 'Close step detail' })
- fireEvent.keyDown(document, { key: 'Escape' })
- document.querySelector('[aria-hidden="true"]') for backdrop
- Only mocked useStep

# After (Radix Sheet+Tabs assertions)
- data-state="open"/"closed" via getSheetContent() helper
- document.querySelectorAll('.animate-pulse') (full document for portal)
- screen.getByRole('button', { name: /close/i }) (Sheet sr-only "Close")
- userEvent.keyboard('{Escape}') (Radix onOpenChange handles natively)
- document.querySelector('[data-slot="sheet-overlay"]') for overlay
- Mocks: useStep, useStepEvents, useStepInstructions, useRunContext
- New: 7-tab trigger count test
- New: tab switching (data-state=active) test
```

## Decisions
### Radix Sheet closed state assertion
**Choice:** Assert `getSheetContent()` returns null when `open=false`
**Rationale:** Radix Dialog unmounts portal content when `open=false` by default (no `forceMount`). Checking for null is more reliable than checking `data-state="closed"` since the element won't exist.

### Close button query strategy
**Choice:** `screen.getByRole('button', { name: /close/i })` instead of exact aria-label match
**Rationale:** Sheet's built-in close button uses `<span className="sr-only">Close</span>`. The old component used `aria-label="Close step detail"`. Using regex `/close/i` matches either pattern, making the test robust to minor label changes in the Sheet component.

### Mock hook defaults in beforeEach
**Choice:** Set default mock returns for useStepEvents (empty response) and useStepInstructions (undefined) in beforeEach
**Rationale:** Most tests don't care about events/instructions data. Setting defaults avoids repeating mock setup in every test while allowing individual tests to override.

### stepNumber=null with open=true
**Choice:** Assert no tablist and no step content, without asserting Sheet portal absence
**Rationale:** Per PLAN spec, `Sheet open={open}` is controlled directly by the `open` prop. `StepContent` (containing tabs) only mounts when `open && stepNumber != null`. So the Sheet may still render an open portal with no meaningful content. The test verifies the important behavior: no step data or tabs are shown.

## Verification
[x] All 10 tests compile and execute without syntax errors
[x] Tests target Radix portal DOM structure (data-slot, data-state attributes)
[x] Mocks cover all 4 hooks: useStep, useStepEvents, useStepInstructions, useRunContext
[x] Original 8 test scenarios preserved (closed, open+loaded, loading, error, close button, null stepNumber, Escape, overlay click)
[x] 2 new tests added (7-tab verification, tab switching)
[x] No CSS translate class assertions remain
[x] screen.getByRole used for portal-safe queries
