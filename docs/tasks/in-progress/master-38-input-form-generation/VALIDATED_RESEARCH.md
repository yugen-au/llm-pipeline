# Research Summary

## Executive Summary

Cross-referenced both research files against actual codebase (14 source files inspected). 14 factual claims validated; 7 hidden assumptions identified, 3 of which are blocking. The central issue: Task 38's code snippet references `pipelineData?.input_schema` but this field exists nowhere -- not on PipelineMetadata (backend or TS), not in PipelineIntrospector output. Task 43 (PipelineInputData) creates the base class but does NOT add the introspection/API/TS plumbing to expose it. Additionally, the existing `has_input_schema` boolean is derived from step-level `instructions_schema` (LLM output schema), not pipeline input data -- a semantic mismatch that will confuse developers. The factory contract (pre-bound execute() with zero args) means user-provided input_data has no path to pipeline execution without backend changes. Six CEO questions raised before planning can proceed.

## Domain Findings

### Backend Schema State
**Source:** step-2-pydantic-schema-research.md, introspection.py, pipelines.py, runs.py

- PipelineInputData does NOT exist. Only PipelineContext in context.py -- CONFIRMED
- PipelineIntrospector.get_metadata() returns: pipeline_name, registry_models, strategies, execution_order -- NO input_schema field (introspection.py L255-259)
- PipelineMetadata backend model (pipelines.py L57-61) has no input_schema field
- PipelineMetadata TS interface (types.ts L352-357) has no input_schema field
- has_input_schema on PipelineListItem (pipelines.py L97-101) is computed from `any(step.instructions_schema is not None)` -- this checks LLM OUTPUT schemas, not pipeline input data
- TriggerRunRequest (runs.py L61-62): only `pipeline_name: str`
- trigger_run() (runs.py L222-224) calls `factory(run_id, engine, event_emitter)` then `pipeline.execute()` with ZERO args
- PipelineConfig.execute() signature (pipeline.py L424-430) accepts `data, initial_context, use_cache, consensus_polling` but HTTP layer doesn't forward them
- Task 37 VALIDATED_RESEARCH confirmed: factories PRE-BIND data/initial_context at construction. This is intentional design, not a gap

### Schema Utilities
**Source:** step-2-pydantic-schema-research.md, llm/schema.py

- flatten_schema() (schema.py L13-53) inlines all $ref/$defs and removes $defs section -- CONFIRMED, production-tested
- _get_schema() (introspection.py L82-95) calls model_json_schema() on BaseModel subclasses -- CONFIRMED
- Pydantic v2 JSON Schema output patterns (simple types, nested with $defs, Optional/anyOf, arrays) documented correctly in research

### Frontend State
**Source:** step-1-frontend-component-research.md, types.ts, live.tsx, pipelines.ts, package.json

- React 19.2, Zod 4.3.6 -- CONFIRMED (package.json)
- No form library (no RHF, no Formik) -- CONFIRMED
- Available shadcn: badge, button, card, scroll-area, select, separator, sheet, table, tabs, tooltip -- CONFIRMED
- Missing shadcn: input, label, checkbox, textarea -- CONFIRMED
- live.tsx L195-196: placeholder `<div data-testid="input-form-placeholder" />` ready for InputForm -- CONFIRMED
- handleRunPipeline() (live.tsx L108-127) calls `createRun.mutate({ pipeline_name: selectedPipeline })` with NO input_data -- CONFIRMED
- usePipeline(name) returns PipelineMetadata (pipelines.ts L42-48) -- CONFIRMED
- The ONLY `input_schema` in TS types is on TransformationMetadata (types.ts L309) -- this is transformation I/O, NOT pipeline input data

### Research Quality Assessment
**Source:** both research files

- JSON Schema type -> form field mapping table is accurate and comprehensive
- $ref/$defs resolution approach is correct (Pydantic v2 always uses $defs for nested models)
- LLMResultMixin inherited fields (confidence_score, notes) correctly identified as always having defaults
- Research correctly identified the 6-item gap chain (PipelineInputData -> ClassVar -> Introspector -> API -> TS type -> component)
- Research DID NOT address: form reset after submission, loading states during schema fetch, interaction with handleRunPipeline callback, or the semantic mismatch between has_input_schema and actual pipeline input

### Hidden Assumption: instructions_schema as Interim
**Source:** step-1-frontend-component-research.md Q1 option A, step-2-pydantic-schema-research.md Section 6

- Research suggests using first step's instructions_schema as interim. But instructions_schema is the LLM OUTPUT schema -- it describes what the LLM should return (e.g. widget_count, category, confidence_score, notes). Showing this as a user input form is semantically wrong and confusing
- LLMResultMixin always adds confidence_score (number, default 0.95) and notes (Optional[str]) to every instructions_schema. These are LLM response fields, not user input fields
- This assumption is INVALID as an interim approach

### Hidden Assumption: Task 43 Unblocks Task 38
**Source:** step-2-pydantic-schema-research.md Section 7

- Task 43 description only covers: (a) create PipelineInputData base class, (b) add INPUT_DATA ClassVar to PipelineConfig
- Task 43 does NOT cover: (c) update PipelineIntrospector to extract INPUT_DATA schema, (d) add input_schema to PipelineMetadata backend model, (e) add input_schema to TS PipelineMetadata, (f) update usePipeline hook consumers
- Even after Task 43 completes, there's a 4-item plumbing gap before InputForm has a real schema source

### Hidden Assumption: Factory Contract Compatible with User Input
**Source:** runs.py L219-224, Task 37 VALIDATED_RESEARCH Q1

- Factories pre-bind data/initial_context. trigger_run() calls execute() with zero args
- Adding input_data to TriggerRunRequest is insufficient -- the factory contract must change to accept and forward user input
- This is a backend architectural change not scoped in either Task 38 or Task 43

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Q1: Scope -- is Task 38 frontend-only component or end-to-end with backend wiring? | PENDING | Determines ~50% of work. Frontend-only means just the component; end-to-end means TriggerRunRequest + factory contract changes |
| Q2: What schema should InputForm render given PipelineInputData doesn't exist? Build against generic JSON Schema prop (mock-tested) or use step-level schema as interim? | PENDING | Defines interim contract and testability approach |
| Q3: How does user input_data reach execute() given factories pre-bind args? Change factory contract, add new param, or defer? | PENDING | Determines whether form data actually does anything or is UI-only |
| Q4: Should we rename has_input_schema (currently means "has step instructions_schema") to avoid confusion with pipeline input data? | PENDING | Naming clarity, prevents future bugs |
| Q5: Should $ref/$defs flattening happen backend-side (via existing flatten_schema()) or frontend-side? | PENDING | Affects component complexity and API contract |
| Q6: Form validation approach -- manual JSON Schema checks, Zod runtime conversion, RHF, or backend-only validation? | PENDING | Affects dependencies and implementation complexity |

## Assumptions Validated
- [x] PipelineInputData does not exist in codebase (context.py only has PipelineContext)
- [x] PipelineMetadata (backend + TS) has no input_schema field
- [x] PipelineIntrospector returns no input_schema in metadata dict
- [x] TriggerRunRequest only accepts pipeline_name
- [x] trigger_run() calls factory then execute() with zero args (factories pre-bind)
- [x] flatten_schema() exists in llm/schema.py, inlines $ref/$defs
- [x] live.tsx has placeholder div for InputForm at line 196
- [x] handleRunPipeline() passes no input_data to createRun.mutate()
- [x] React 19.2, Zod 4.3 present; no form library installed
- [x] Missing shadcn components: input, label, checkbox, textarea
- [x] Pydantic v2 JSON Schema patterns (simple, nested/$defs, Optional/anyOf, arrays) documented accurately
- [x] LLMResultMixin adds confidence_score + notes to all instructions_schema (always with defaults)
- [x] has_input_schema is derived from step-level instructions_schema, not pipeline input data

## Open Items
- Task 43 dependency gap: even after Task 43, 4 plumbing changes needed (introspector, backend model, API endpoint, TS type) before real schema flows to InputForm
- Factory contract change: no mechanism exists to pass user input_data from HTTP request to pipeline.execute()
- has_input_schema semantic mismatch: name suggests pipeline input, computed from LLM output schema
- Form reset behavior after successful pipeline run submission not addressed in research
- Loading state UX while usePipeline() fetches schema not addressed
- When pipeline has NO schema at all (no PipelineInputData defined): should UI show JSON editor, empty state, or just the Run button?
- TransformationMetadata.input_schema naming collision risk with future pipeline-level input_schema

## Recommendations for Planning
1. Build InputForm as a pure component accepting `schema: JsonSchema | null` prop -- fully decoupled from schema source, testable with synthetic schemas, no Task 43 dependency
2. Backend flattening preferred: use existing flatten_schema() in introspection layer rather than duplicating $ref resolution in frontend
3. Do NOT use instructions_schema as interim -- it's LLM output schema, semantically wrong for user input
4. Consider splitting: (a) InputForm component + FormField components + JSON editor fallback (frontend-only, this task), (b) backend plumbing (introspector + API + TriggerRunRequest + factory contract, separate task or Task 43 extension)
5. Install missing shadcn components (input, label, checkbox, textarea) as first implementation step
6. Form validation: manual JSON Schema required-field checks + type coercion sufficient for v1; avoid adding json-schema-to-zod dependency
7. Wire InputForm into live.tsx by replacing placeholder div, passing collected data via onSubmit callback to handleRunPipeline -- the callback can include input_data even before backend accepts it (no-op field, forward-compatible)
