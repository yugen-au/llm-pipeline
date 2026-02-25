# Task 38 Research Step 1: Frontend Component Research

## Summary

Research into building an InputForm component that generates dynamic form fields from JSON Schema (derived from Pydantic models) for the llm-pipeline UI.

## Existing Codebase State

### Backend Schema Exposure

The `PipelineIntrospector._get_schema()` calls `model_json_schema()` on Pydantic BaseModel subclasses and returns standard JSON Schema (Draft 2020-12). This schema appears at two levels in the introspection output:

- **Per-step `instructions_schema`**: `PipelineMetadata.strategies[].steps[].instructions_schema` -- JSON Schema for the step's LLMResultMixin subclass (e.g. `{ type: "object", properties: { widget_count: { type: "integer" }, category: { type: "string" } }, required: [...] }`)
- **Per-step `context_schema`**: Same structure for PipelineContext subclass
- **Transformation schemas**: `transformation.input_schema` and `transformation.output_schema`

There is **no pipeline-level `input_schema` field**. The `PipelineListItem.has_input_schema` boolean is computed from `any(step.instructions_schema is not None)` across all strategies/steps.

### Frontend Hooks and Types

- `usePipeline(name)` returns `PipelineMetadata` with full strategy/step/schema data
- `usePipelines()` returns list with `has_input_schema` boolean per pipeline
- TypeScript types already defined: `PipelineMetadata`, `PipelineStepMetadata` (with `instructions_schema: Record<string, unknown> | null`), `PipelineStrategyMetadata`

### Backend Data Flow Gap

- `TriggerRunRequest` currently only accepts `{ pipeline_name: string }`
- `trigger_run()` endpoint calls `factory(run_id, engine, event_emitter)` then `pipeline.execute()` with **no user-supplied input data**
- `PipelineConfig.execute()` signature: `execute(data, initial_context, use_cache, consensus_polling)` -- does accept `data` and `initial_context` but the HTTP layer doesn't pass them through

### Integration Point

- `live.tsx` line 196: `<div data-testid="input-form-placeholder" />` ready for InputForm
- `handleRunPipeline()` currently calls `createRun.mutate({ pipeline_name: selectedPipeline })`
- Would need `input_data` added to both `TriggerRunRequest` and the mutation call

### Available UI Primitives

**Existing shadcn components**: badge, button, card, scroll-area, select, separator, sheet, table, tabs, tooltip

**Missing shadcn components needed**: input, label, checkbox, textarea (can add via `npx shadcn add input label checkbox textarea`)

### Dependencies

- React 19.2, TanStack Query 5, TanStack Router 1, Zod 4, Zustand 5, Radix UI, Tailwind 4
- **No form library** (no React Hook Form, no Formik)
- Target: ES2020 (tsconfig), strict TS

## JSON Schema Mapping Plan

| JSON Schema Type | Form Element | shadcn Component |
|---|---|---|
| `string` | Text input | `<Input type="text" />` |
| `string` + `enum` | Select dropdown | `<Select>` (existing) |
| `integer` / `number` | Number input | `<Input type="number" />` |
| `boolean` | Checkbox | `<Checkbox />` |
| `object` | Nested fieldset | Recursive `<fieldset>` with `<FormField>` children |
| `array` | Repeatable group | Add/remove buttons wrapping child fields |
| `string` + `format: "date"` | Date input | `<Input type="date" />` |
| No schema | JSON textarea | `<textarea>` with JSON.parse validation |

## Form Library Recommendation

**Recommended: React 19 native form handling + Zod 4 validation** (no new runtime dependency)

Rationale:
- Project already uses Zod 4 (in deps)
- React 19 has improved form handling with Actions
- JSON Schema -> form field mapping is custom regardless of form library
- Keeps bundle small, no new dep learning curve
- RHF could be added later if form complexity grows

## JSON Editor Fallback Recommendation

**Recommended: Simple textarea with JSON.parse validation** for v1

Rationale:
- Monaco Editor is ~2MB (overkill for occasional JSON input)
- Textarea is zero-dep, adequate for free-form JSON input
- Can upgrade to CodeMirror/Monaco in a future task if needed

## Blocking Questions

### Q1: Which schema should InputForm render?

The backend has per-step `instructions_schema` but no pipeline-level `input_schema`. Options:

- **A**: First strategy's first step's `instructions_schema` (simplest, covers most use cases)
- **B**: Let user select which step to provide input for (flexible, but complex UX)
- **C**: Create a new pipeline-level `input_schema` concept (requires backend changes)

### Q2: Should this task wire input_data to the backend?

`TriggerRunRequest` doesn't accept `input_data`. Options:

- **A**: Add `input_data: dict | null` to `TriggerRunRequest`, pass through factory to `pipeline.execute(data=input_data, initial_context={})` (backend + frontend change)
- **B**: Build frontend form UI only, send collected data in existing mutation body (backend wiring deferred)
- **C**: Create separate backend task for wiring

### Q3: Form library choice?

- **A**: Add React Hook Form as dependency (mature ecosystem, schema resolvers)
- **B**: React 19 native + Zod 4 (no new deps, project convention)

## Non-Blocking Decisions (Defaulted)

| Decision | Default | Rationale |
|---|---|---|
| JSON editor | textarea + JSON.parse | Zero deps, adequate for v1 |
| Shadcn primitives | Add input, label, checkbox, textarea via CLI | Standard shadcn workflow |
| Array fields | Basic add/remove buttons | Sufficient for v1 |
| Nested objects | Recursive fieldset rendering | Matches JSON Schema structure |
| `$defs` / `$ref` handling | Dereference inline before rendering | Pydantic v2 uses `$defs` for nested models |
