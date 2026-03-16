# PLANNING

## Summary

Fix data mapping across three tabs in StepDetailPanel. The Instructions tab currently shows prompt templates (wrong); it should show the Pydantic output model JSON schema from `/api/pipelines/{name}`. The Prompts tab currently shows rendered (variable-injected) prompts from events; it should show prompt templates with `{variable}` placeholders (swapping data sources with Instructions tab). The Response tab always shows nothing because backend hardcodes `raw_response=None`; backend must extract the raw LLM response from `run_result.new_messages()` at both emission sites in pipeline.py.

No new API endpoints, no DB schema changes, no new TypeScript types needed -- all infrastructure already exists.

## Plugin & Agents

**Plugin:** backend-development, frontend-mobile-development
**Subagents:** backend-architect, frontend-developer
**Skills:** none

## Phases

1. Backend fix: populate `raw_response` in `LLMCallCompleted` events from pydantic-ai run_result
2. Frontend rewire: swap data sources between Instructions and Prompts tabs; Instructions gets `instructions_schema` from `usePipeline`, Prompts gets prompt templates from `useStepInstructions`
3. Test updates: add `usePipeline` mock to StepDetailPanel.test.tsx; add backend unit test for raw_response extraction

## Architecture Decisions

### raw_response Extraction Strategy
**Choice:** Extract from last `ModelResponse` in `run_result.new_messages()`. For `ToolCallPart` (structured output -- the common case), serialize `part.args` to JSON string. For `TextPart` (plain text output), use `part.content` directly. Join multiple parts with newline if multiple exist.
**Rationale:** pydantic-ai v1.0.5 delivers structured output via `ToolCallPart.args` (confirmed via Context7 /pydantic/pydantic-ai). `new_messages()` returns only current-run messages, avoiding duplication. Both extraction sites (normal path L830-869, consensus path L1257-1293) have `run_result` in scope.
**Alternatives:** Use `run_result.data` (only gives the final parsed result, not the raw LLM text); use `all_messages()` (includes prior-run messages, risk of duplication).

### InstructionsTab Rendering Approach
**Choice:** Render `instructions_schema` as a formatted `<pre>` block with `JSON.stringify(schema, null, 2)`. Show `instructions_class` as a label above.
**Rationale:** Minimal implementation, consistent with JSON display patterns elsewhere in the codebase. No JSON tree viewer dependency needed for MVP.
**Alternatives:** Interactive JSON tree viewer (adds dependency, overkill for planning phase); raw text (no formatting).

### Frontend Swap Atomicity
**Choice:** Both tab rewires (Instructions and Prompts) are done in a single step by a single agent.
**Rationale:** The two changes are tightly coupled -- moving rendering logic from InstructionsTab to PromptsTab and replacing InstructionsTab content. Splitting risks broken intermediate state where both tabs show wrong data.
**Alternatives:** Separate steps for each tab (rejected due to coupling).

## Implementation Steps

### Step 1: Backend -- Populate raw_response from pydantic-ai run_result
**Agent:** backend-development:backend-architect
**Skills:** none
**Context7 Docs:** /pydantic/pydantic-ai
**Group:** A

1. In `llm_pipeline/pipeline.py`, create a helper function `_extract_raw_response(run_result) -> str | None` that:
   - Calls `run_result.new_messages()` to get current-run messages
   - Finds the last `ModelResponse` in the list
   - Iterates `ModelResponse.parts`; for each part: if `ToolCallPart`, serialize `part.args` to JSON string via `json.dumps`; if `TextPart`, use `part.content`
   - Joins all extracted strings with `\n` if multiple parts; returns `None` if no `ModelResponse` found
2. At normal execution path (approx. L852-869): replace `raw_response=None` with `raw_response=_extract_raw_response(run_result)` in the `LLMCallCompleted` emission
3. At consensus execution path (approx. L1276-1293): same replacement using the consensus `run_result`
4. Ensure `json` is imported (standard library, should already be present)

### Step 2: Frontend -- Swap data sources between Instructions and Prompts tabs; rewire both components
**Agent:** frontend-mobile-development:frontend-developer
**Skills:** none
**Context7 Docs:** /reactjs/react.dev
**Group:** A

1. In `StepContent` component (`StepDetailPanel.tsx` approx. L401-516):
   - Add `usePipeline(step.pipeline_name)` hook call (hook already exists in `pipelines.ts`)
   - Derive the matching step metadata: find entry in `pipeline.strategies[].steps[]` where `step_name === step.step_name`
   - Pass `stepMeta.instructions_schema` and `stepMeta.instructions_class` as props to `InstructionsTab`
   - Change the `useStepInstructions` data (currently passed to InstructionsTab) to instead be passed to `PromptsTab`
2. Rewrite `InstructionsTab` component (approx. L183-227):
   - Replace `StepPromptItem[]` prop with `instructionsSchema: Record<string, unknown> | null` and `instructionsClass: string | null`
   - Render `instructionsClass` as a label/badge above the schema block
   - Render `instructionsSchema` as `<pre>{JSON.stringify(instructionsSchema, null, 2)}</pre>` inside a scrollable container; show a "No schema available" empty state when `null`
3. Rewrite `PromptsTab` component (approx. L107-141):
   - Change prop from events array to `StepPromptItem[]` (the type currently consumed by InstructionsTab)
   - Move the existing InstructionsTab rendering logic (prompt item list with badges, prompt_type, prompt_key, content display) into PromptsTab
   - Remove the `llm_call_starting` event filtering logic from PromptsTab (rendered prompts are no longer shown in any tab)

### Step 3: Test updates -- StepDetailPanel and backend raw_response
**Agent:** backend-development:tdd-orchestrator
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. In `StepDetailPanel.test.tsx`:
   - Add mock for `usePipeline` hook returning pipeline metadata with `strategies[0].steps[0].instructions_schema` set to a sample JSON object and `instructions_class` set to a sample class name
   - Update InstructionsTab assertions: verify JSON schema content is rendered (not prompt template content)
   - Update PromptsTab assertions: verify prompt template items (with `{variable}` placeholders) are rendered (not rendered event prompts)
   - Ensure all 8 existing tests still pass after changes
2. Add a unit test for `_extract_raw_response` in the backend test suite (file: `tests/test_pipeline.py` or a new `tests/test_raw_response.py`):
   - Test `ToolCallPart` case: mock a `ModelResponse` with a single `ToolCallPart`; assert result is a JSON string of the args dict
   - Test `TextPart` case: mock a `ModelResponse` with a single `TextPart`; assert result equals `part.content`
   - Test no `ModelResponse` case: assert result is `None`
   - Test multiple parts case: assert result joins parts with `\n`

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| pydantic-ai `new_messages()` returns empty list when no LLM call occurred (e.g., cached result) | Low | `_extract_raw_response` returns `None` gracefully; `LLMCallCompleted.raw_response` is already nullable |
| `ToolCallPart.args` is not JSON-serializable (e.g., contains non-serializable types) | Medium | Wrap `json.dumps` in try/except; fall back to `str(part.args)` |
| `usePipeline` returns `undefined` or loading state during StepDetailPanel render | Low | Guard with `?? null` before passing to InstructionsTab; InstructionsTab already handles `null` with empty state |
| Multiple strategies in a pipeline -- step name lookup finds wrong step | Low | Step names are unique within a pipeline (enforced by PipelineConfig); use `next()` with `step_name` match across all strategies |
| Removing rendered prompts from Prompts tab loses runtime prompt visibility | Low | This is intentional per CEO decision; rendered prompts remain in event payload for future use |

## Success Criteria

- [ ] Instructions tab shows `instructions_schema` JSON (e.g., Pydantic model field definitions) for a step with a defined output type, not prompt template content
- [ ] Instructions tab shows `instructions_class` label above the schema
- [ ] Instructions tab shows "No schema available" empty state for steps without an instructions schema
- [ ] Prompts tab shows prompt templates with `{variable}` placeholders, not rendered/injected prompts
- [ ] Response tab shows non-null `raw_response` content after a real pipeline run
- [ ] For structured output steps (tool-call based), `raw_response` is a JSON string of the args dict
- [ ] For text output steps, `raw_response` is the raw text string
- [ ] All existing StepDetailPanel tests pass
- [ ] New backend unit tests for `_extract_raw_response` pass
- [ ] No regressions in other tabs (Input, Context Diff, Extractions, Meta)

## Phase Recommendation

**Risk Level:** low
**Reasoning:** All data sources already exist and are served; changes are isolated to two files per layer (pipeline.py backend, StepDetailPanel.tsx frontend). No API surface changes, no DB changes, no new dependencies. Frontend hook swap is well-understood with validated type compatibility. Main risk is the json serialization edge case in backend, mitigated by a try/except fallback.
**Suggested Exclusions:** testing, review
