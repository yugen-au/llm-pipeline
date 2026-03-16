# Research Summary

## Executive Summary

Validated research findings against actual codebase. The core issue is a **data mapping mismatch** across three tabs in StepDetailPanel, not missing functionality. The Instructions tab is bound to prompt template data (wrong); the Prompts tab is bound to runtime events (correct source, but shows rendered prompts instead of templates); the Response tab is correctly wired but backend always emits `raw_response=None`.

Three changes required:
1. **Instructions tab**: Rewire from `useStepInstructions` (prompt templates) to `usePipeline` (instructions_schema from introspection)
2. **Prompts tab**: Rewire from `llm_call_starting` events to `useStepInstructions` (prompt templates with `{variable}` placeholders)
3. **Response tab**: Backend fix -- extract raw LLM response text from `pydantic-ai run_result.all_messages()` and pass to `LLMCallCompleted.raw_response`

Research step-1 (backend) was **partially correct** -- identified raw_response gap accurately but missed the Instructions tab data mapping issue and overstated "no schema changes needed" (Instructions tab needs a different data source). Research step-2 (frontend) was **structurally correct** but missed the semantic mismatch: it described the Instructions tab as "Works" when it's showing the wrong data per CEO intent.

## Domain Findings

### Finding 1: Instructions Tab -- Wrong Data Source (RESEARCH GAP)
**Source:** step-2-frontend-step-ui-research.md (Table row "Instructions"), validated against StepDetailPanel.tsx L183-227, L492-497, pipelines.ts L62-72

The InstructionsTab component receives `StepPromptItem[]` from `useStepInstructions()` which calls `GET /api/pipelines/{name}/steps/{step_name}/prompts`. This endpoint (pipelines.py L136-185) returns **prompt templates** from the DB `prompts` table -- raw content with `{variable}` placeholders, prompt_type badges, prompt_key labels.

CEO wants: Pydantic output model JSON schema (`instructions_schema`).

This data **already exists** in the backend:
- `PipelineIntrospector.get_metadata()` (introspection.py L140-145) produces `instructions_class` and `instructions_schema` per step
- `GET /api/pipelines/{name}` (pipelines.py L117-133) returns `PipelineMetadata` with `strategies[].steps[].instructions_schema`
- Frontend `PipelineStepMetadata` type (types.ts L334-347) already has `instructions_class: string | null` and `instructions_schema: Record<string, unknown> | null`
- `usePipeline(name)` hook (pipelines.ts L42-49) already fetches this data

**Fix**: Replace `useStepInstructions` call in StepContent with `usePipeline` + step lookup. Rewrite `InstructionsTab` to render JSON schema instead of prompt items.

### Finding 2: Prompts Tab -- Correct Wiring for Wrong Content
**Source:** step-2-frontend-step-ui-research.md (Table row "Prompts"), validated against StepDetailPanel.tsx L107-141

PromptsTab filters events for `llm_call_starting` and renders `rendered_system_prompt` + `rendered_user_prompt`. These are **variable-injected rendered prompts** from runtime events.

CEO wants: Prompt templates with `{variable}` placeholders (the data currently in Instructions tab).

**Fix**: Replace PromptsTab's data source from events to `useStepInstructions` (the hook currently used by InstructionsTab). Essentially swap data sources between Instructions and Prompts tabs. The existing `StepPromptItem` rendering logic from InstructionsTab can be moved to PromptsTab.

### Finding 3: Response Tab -- raw_response=None Confirmed
**Source:** step-1-backend-pipeline-research.md (Section 8.1), validated against pipeline.py L857 and L1281

Both emission sites hardcode `raw_response=None`:
- Normal path: pipeline.py L852-869 (after `run_result = agent.run_sync()` at L830-835)
- Consensus path: pipeline.py L1276-1293 (after `run_result = agent.run_sync()` at L1257)

`run_result` is available in scope at both sites. `run_result.all_messages()` / `run_result.new_messages()` return `list[ModelMessage]`.

**Fix**: Extract raw response from the last `ModelResponse` in `run_result.new_messages()`. Must handle two cases per pydantic-ai v1.0.5 message structure:
- `TextPart`: `part.content` (plain text output)
- `ToolCallPart`: `part.args` (structured output via tool calling -- **this is the common case** for llm-pipeline since it uses Pydantic output types)

### Finding 4: pydantic-ai Message Structure Validated
**Source:** step-1-backend-pipeline-research.md (Section 3.4, 10.1), validated against pydantic-ai v1.0.5 docs via Context7

Confirmed via Context7 (pydantic-ai v1.0.5):
- `run_result.all_messages()` returns `[ModelRequest, ModelResponse, ...]`
- `ModelResponse.parts` contains `TextPart(content=str)` or `ToolCallPart(tool_name=str, args=dict)`
- For structured output agents (which llm-pipeline uses exclusively), the output is typically delivered via `ToolCallPart` where `args` contains the structured data as a dict
- `TextPart` appears when agents use `NativeOutput` mode or plain text output
- `new_messages()` returns messages from the current run only (preferred over `all_messages()` for extraction)

Research step-1's extraction pseudocode (Section 10.1) is directionally correct but needs adjustment: it should check `ToolCallPart` first (more common for structured output) and serialize `args` to JSON string for `raw_response`.

### Finding 5: No New Backend Endpoints Needed
**Source:** validated against pipelines.py, types.ts, pipelines.ts

All data sources already exist:
- Instructions schema: `GET /api/pipelines/{name}` -> `strategies[].steps[].instructions_schema` (already served, already typed in TS)
- Prompt templates: `GET /api/pipelines/{name}/steps/{step_name}/prompts` (already served via `useStepInstructions`)
- Raw response: `LLMCallCompleted.raw_response` field exists, just needs population

No new API endpoints, no DB schema changes, no new TypeScript types needed.

### Finding 6: Frontend Hook Swap is Low-Risk
**Source:** validated against StepDetailPanel.tsx L401-516

`StepContent` already fetches:
- `useStep()` -> `step.pipeline_name`, `step.step_name` (available for both hooks)
- `useStepEvents()` -> events (for Prompts tab currently, will remain for Response tab)
- `useStepInstructions()` -> prompt templates (currently feeds Instructions tab, will feed Prompts tab)
- `useRunContext()` -> context snapshots (unchanged)

Adding `usePipeline(step.pipeline_name)` is needed for the new Instructions tab. This hook already exists with `staleTime: Infinity` caching.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Prompts tab: should it show (a) templates with placeholders, (b) rendered prompts from events, or (c) both? | (a) Templates with `{variable}` placeholders -- move from Instructions tab | Clarifies the fix is a data source swap between Instructions and Prompts tabs, NOT event-based rendering |
| Instructions tab: confirm it should show Pydantic output model JSON schema from introspection? | Yes, from `/api/pipelines/{name}` | Confirms new data source needed: `usePipeline` hook instead of `useStepInstructions` |

## Assumptions Validated
- [x] `raw_response=None` is hardcoded at both emission sites (pipeline.py L857, L1281) -- confirmed by reading source
- [x] `run_result` (AgentRunResult) is in scope at both emission sites and `.new_messages()` is available -- confirmed
- [x] pydantic-ai v1.0.5 `ModelResponse.parts` contains `TextPart` or `ToolCallPart` -- confirmed via Context7 docs
- [x] `instructions_schema` already exists in `PipelineMetadata` response from `/api/pipelines/{name}` -- confirmed (pipelines.py L41, introspection.py L145)
- [x] Frontend `PipelineStepMetadata` type already has `instructions_schema` field -- confirmed (types.ts L340)
- [x] `usePipeline` hook exists and is functional -- confirmed (pipelines.ts L42-49)
- [x] `useStepInstructions` currently feeds InstructionsTab -- confirmed (StepDetailPanel.tsx L417-421, L492-497)
- [x] PromptsTab currently reads `llm_call_starting` events -- confirmed (StepDetailPanel.tsx L107-108)
- [x] No new backend endpoints needed -- confirmed; all data sources already served
- [x] No DB schema changes needed -- confirmed; PipelineEventRecord stores full event payload as JSON
- [x] For structured output agents, pydantic-ai delivers output via `ToolCallPart.args` (not `TextPart.content`) -- confirmed via Context7

## Open Items
- Structured output raw_response format: For tool-call-based output (the common case), `raw_response` will be JSON-serialized `ToolCallPart.args`. This is the same data as `parsed_result` but pre-validation. For text-based output, it will be the raw text string. Implementation should document this distinction.
- InstructionsTab component rewrite scope: Current component renders a list of `StepPromptItem` with badges. New version needs to render a JSON schema object. Decide whether to use a JSON tree viewer or simple `<pre>` block.
- PromptsTab rendered prompts: The current PromptsTab shows rendered (variable-injected) prompts from events. After the swap, this runtime data will no longer be displayed in any tab. Consider whether rendered prompts should appear elsewhere (e.g., as a sub-section in Response tab, or a toggle in Prompts tab) in a future iteration.
- Test updates: `StepDetailPanel.test.tsx` has 8 tests mocking all 4 hooks. Adding `usePipeline` mock and updating InstructionsTab/PromptsTab assertions needed.

## Recommendations for Planning
1. **Backend task (1 change, 2 sites)**: Extract raw response from `run_result.new_messages()` in pipeline.py at L830-869 (normal path) and L1257-1293 (consensus path). Handle both `TextPart.content` and `ToolCallPart.args` serialization. Pass result as `raw_response` in `LLMCallCompleted` emission.
2. **Frontend task -- Instructions tab rewire**: Add `usePipeline(step.pipeline_name)` to StepContent. Find matching step metadata via `step.step_name`. Pass `instructions_schema` + `instructions_class` to a rewritten InstructionsTab that renders JSON schema.
3. **Frontend task -- Prompts tab rewire**: Move the current InstructionsTab rendering logic (StepPromptItem list with badges) into PromptsTab. Wire it to `useStepInstructions` data that was previously consumed by InstructionsTab.
4. **Sequence**: Backend fix (raw_response) is independent and can be done in parallel with frontend rewiring. Frontend changes are interdependent (swapping data sources between two tabs) and should be done atomically.
5. **Testing**: Update `StepDetailPanel.test.tsx` to mock `usePipeline` and verify both tabs render correct data types. Add a backend unit test for raw_response extraction from pydantic-ai messages.
