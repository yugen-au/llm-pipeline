# IMPLEMENTATION - STEP 7: COMPONENT TESTS
**Status:** completed

## Summary
Vitest component tests for StepTimeline, ContextEvolution, and StepDetailPanel. 25 new tests covering rendering, loading/error/empty states, user interaction, and deriveStepStatus unit logic.

## Files
**Created:** `llm_pipeline/ui/frontend/src/components/runs/StepTimeline.test.tsx`, `llm_pipeline/ui/frontend/src/components/runs/ContextEvolution.test.tsx`, `llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.test.tsx`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/runs/StepTimeline.test.tsx`
14 tests: renders step rows (name/number/status/duration/model), loading skeleton (16 animate-pulse), error state, empty state, selected step highlight (bg-muted/50), onSelectStep callback. 7 deriveStepStatus unit tests: completed from DB, empty inputs, running from unmatched step_started, completed negates running, skipped override, failed override, sort by step_number.

### File: `llm_pipeline/ui/frontend/src/components/runs/ContextEvolution.test.tsx`
5 tests: step name headers via heading role query, JSON snapshot rendering, loading skeleton (6 animate-pulse), error state, empty state.

### File: `llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.test.tsx`
6 tests: translate-x-full when closed, panel content when open+loaded, loading skeleton, error message, onClose callback, null stepNumber handling. Mocks useStep hook.

## Decisions
### Query strategy for ContextEvolution headers
**Choice:** Use `getAllByRole('heading', { level: 4 })` instead of `getByText(/extract/)`
**Rationale:** Step name appears in both h4 header and JSON pre block (e.g. "extracted" matches /extract/). Role query targets headers specifically.

### Mock pattern for useStep
**Choice:** `vi.mock('@/api/steps')` with `mockUseStep` fn returning `{ data, isLoading, isError }`
**Rationale:** Matches RunsTable pattern of mocking external dependencies. Avoids QueryClient provider setup complexity.

## Verification
[x] All 25 new tests pass
[x] Full suite 86/86 tests pass with no regressions
[x] TypeScript build passes with no errors
[x] No new warnings
[x] Follows RunsTable.test.tsx mock/setup patterns (vi.useFakeTimers, vi.mock router/time)

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] ContextEvolution.test.tsx mocks unused modules (@tanstack/react-router, @/lib/time) -- removed both mock blocks and unused timer setup
[x] StepTimeline.test.tsx mocks unused useNavigate from @tanstack/react-router -- removed router mock block
[x] StepDetailPanel.test.tsx missing Escape key close test -- added fireEvent.keyDown(document, {key:'Escape'}) test
[x] StepDetailPanel.test.tsx missing backdrop click close test -- added userEvent.click on aria-hidden overlay test

### Changes Made
#### File: `llm_pipeline/ui/frontend/src/components/runs/ContextEvolution.test.tsx`
Removed `vi.mock('@tanstack/react-router')` block, `vi.mock('@/lib/time')` block, `beforeEach`/`afterEach` timer setup, unused `NOW` constant, and unused `beforeEach`/`afterEach` imports.

#### File: `llm_pipeline/ui/frontend/src/components/runs/StepTimeline.test.tsx`
Removed `vi.mock('@tanstack/react-router')` block.

#### File: `llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.test.tsx`
Removed `vi.mock('@tanstack/react-router')` block. Added `fireEvent` import. Updated panel detection from `container.firstElementChild` to `screen.getByRole('dialog')` for fragment-based rendering. Added 2 new tests: Escape key closes panel, backdrop click closes panel.

### Verification
[x] All 27 tests pass (25 original + 2 new Escape/backdrop tests)
[x] Full suite 88/88 tests pass with no regressions
[x] TypeScript build passes with no errors
[x] No new warnings
