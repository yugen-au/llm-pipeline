# Research Summary

## Executive Summary

Cross-referenced both research files against actual codebase (14 source files inspected). 14 factual claims validated; 7 hidden assumptions identified, all now resolved via CEO Q&A. Task 38 is END-TO-END: InputForm component (pure, generic `schema: JsonSchema | null` prop) + TriggerRunRequest.input_data field + backend threading input_data as initial_context to execute(). No Task 43 dependency -- component mock-tested with synthetic schemas. Backend flattens $ref/$defs via existing flatten_schema(). Hybrid validation: frontend required-field checks + backend Pydantic 422 with per-field errors. No new deps (no RHF, no ajv). has_input_schema rename deferred to Task 43.

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
| Q1: Scope -- is Task 38 frontend-only component or end-to-end with backend wiring? | END-TO-END. No downstream task covers TriggerRunRequest. Task 38 includes InputForm component + TriggerRunRequest input_data field + minimal backend wiring to pass input_data through. | Full scope confirmed: frontend InputForm + backend TriggerRunRequest.input_data + threading input_data as initial_context to execute(). Eliminates "UI-only" option. |
| Q2: What schema should InputForm render given PipelineInputData doesn't exist? Build against generic JSON Schema prop (mock-tested) or use step-level schema as interim? | GENERIC PROP. Build against `schema: JsonSchema \| null` prop, mock-tested with synthetic schemas. No Task 43 dependency. Do NOT use step-level instructions_schema. | Confirms research recommendation. InputForm is a pure component decoupled from schema source. No interim hack with instructions_schema. |
| Q3: How does user input_data reach execute() given factories pre-bind args? Change factory contract, add new param, or defer? | Add input_data to TriggerRunRequest, pass as initial_context to pipeline.execute(). Minimal factory changes -- don't restructure factory contract, just thread input_data through existing context mechanism. | Key decision: input_data merges into initial_context dict, NOT a new execute() param. Factory receives input_data and merges into the context it already pre-binds. Minimal disruption. |
| Q4: Should we rename has_input_schema (currently means "has step instructions_schema") to avoid confusion with pipeline input data? | DEFER. Keep existing field. Add separate pipeline_input_schema field when Task 43 lands. | No rename needed now. Future task adds distinct field. |
| Q5: Should $ref/$defs flattening happen backend-side (via existing flatten_schema()) or frontend-side? | BACKEND. Use existing flatten_schema() in llm/schema.py. Frontend receives pre-flattened schemas. | Frontend InputForm can assume flat schemas with no $ref/$defs. Simplifies component. Backend uses existing utility. |
| Q6: Form validation approach -- manual JSON Schema checks, Zod runtime conversion, RHF, or backend-only validation? | HYBRID. Manual required-field checks on frontend + backend Pydantic validation on submit. No new deps. Frontend shows required indicators from schema.required, type-appropriate inputs. Backend returns structured 422 errors mapped to inline per-field messages. | No new dependencies (no RHF, no ajv, no json-schema-to-zod). Frontend does lightweight required/type checks. Backend Pydantic does authoritative validation. 422 response must include field-level error mapping for inline display. |

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
- [x] Task 38 scope is end-to-end: InputForm + TriggerRunRequest.input_data + backend threading (CEO confirmed)
- [x] InputForm accepts generic schema prop, no Task 43 dependency (CEO confirmed)
- [x] input_data flows as initial_context, no factory contract restructure (CEO confirmed)
- [x] has_input_schema rename deferred to Task 43 (CEO confirmed)
- [x] Backend flattens $ref/$defs via existing flatten_schema() (CEO confirmed)
- [x] Hybrid validation: frontend required checks + backend Pydantic 422 per-field errors, no new deps (CEO confirmed)

## Open Items
- RESOLVED: Factory contract -- input_data threads through as initial_context, no restructure needed
- RESOLVED: has_input_schema -- defer rename, add separate pipeline_input_schema field in Task 43
- DEFERRED TO TASK 43: introspector + backend model + API endpoint + TS type plumbing for real PipelineInputData schema exposure (4 items)
- Form reset behavior after successful pipeline run submission -- define during planning
- Loading state UX while usePipeline() fetches schema -- define during planning
- When pipeline has NO schema (null prop): InputForm should render nothing or just the Run button -- define during planning
- TransformationMetadata.input_schema naming collision risk with future pipeline-level input_schema -- low risk, different TS interfaces
- Backend 422 error response shape: must define structured field-level error format (e.g. `{ detail: [{ field: "name", message: "required" }] }`) during planning

## Recommendations for Planning
1. **InputForm component**: pure component accepting `schema: JsonSchema | null` prop + `onSubmit: (data: Record<string, unknown>) => void` callback. Decoupled from schema source, mock-tested with synthetic schemas
2. **Backend flattening**: use existing flatten_schema() in llm/schema.py. Frontend assumes flat schemas (no $ref/$defs). Apply in introspection layer when serving schema to API
3. **Do NOT use instructions_schema** as interim -- it's LLM output schema, semantically wrong for user input (CEO confirmed)
4. **End-to-end scope** (CEO confirmed): (a) InputForm component + FormField components, (b) TriggerRunRequest gains optional `input_data: dict | None`, (c) trigger_run() merges input_data into initial_context before calling factory/execute, (d) wire into live.tsx replacing placeholder
5. **Install missing shadcn**: input, label, checkbox, textarea as first implementation step
6. **Hybrid validation**: frontend shows required indicators from schema.required + type-appropriate inputs. Backend Pydantic validates on submit, returns structured 422 with per-field error mapping. No new deps
7. **422 error contract**: backend returns `{ detail: [{ loc: ["field_name"], msg: "error message", type: "error_type" }] }` (Pydantic v2 native ValidationError format). Frontend maps loc to inline field errors
8. **Factory threading**: input_data from TriggerRunRequest merges into initial_context dict that factory already pre-binds. Factory contract unchanged -- just receives richer initial_context
9. **Null schema handling**: when schema is null, InputForm renders nothing (just the Run button, no form fields). JSON editor fallback is out of scope for Task 38
