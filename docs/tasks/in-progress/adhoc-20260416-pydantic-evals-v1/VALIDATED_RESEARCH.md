# Research Summary

## Executive Summary

pydantic-evals integration into llm-pipeline is well-scoped. The library's `Dataset[InputsT, OutputT, MetadataT]` maps cleanly onto llm-pipeline's step/pipeline model. All 5 blocking assumptions resolved by CEO. Key architectural decisions: cases use pipeline input_data (full step wiring via prepare_calls), DB is source of truth for YAML sync (no version tracking), pipeline-level evals included in v1, case editor uses typed form fields via introspection endpoint, and pydantic-evals is a core dependency (always installed).

## Domain Findings

### pydantic-evals API Surface
**Source:** step-1-pydantic-evals-api-research.md

- `Case[I, O, M]` is a dataclass (not BaseModel) with inputs, expected_output, metadata, evaluators
- `Dataset[I, O, M]` is a BaseModel with cases + evaluators + report_evaluators
- Task function signature: `(InputsT) -> OutputT` (sync or async)
- Evaluators return `bool | int | float | str | EvaluationReason | dict`; `{}` = skip
- `EqualsExpected` does full equality only -- partial field match requires custom evaluator
- `FieldMatch` custom evaluator pattern: return `{}` for None expected fields (self-skipping)
- Native YAML/JSON serialization with auto JSON Schema sidecar
- `EvaluationReport` supports `print(baseline=)` for diff comparison, `averages()` for aggregation
- No dependency on pydantic-ai; agent integration via wrapper function

### Backend Architecture
**Source:** step-2-backend-architecture-research.md

- YAML sync parallels existing prompts system: `llm-pipeline-evals/` dir, startup sync to DB, UI-save writeback
- 4 new DB tables: `EvaluationDataset`, `EvaluationCase`, `EvaluationRun`, `EvaluationCaseResult`
- DB models follow existing SQLModel patterns (Optional[int] PK, JSON columns, indexes)
- Routes under `/api/evals/` -- dataset CRUD, case CRUD, run trigger/list/detail
- Step eval task_fn reuses `build_step_agent()` + `PromptService` + `StepDeps`
- Pipeline eval task_fn instantiates full pipeline with `pipeline.execute(input_data=inputs)`
- Auto-generated `FieldMatch` evaluators from `instructions_cls.model_fields` when no explicit evaluators
- New module: `llm_pipeline/evals/` with yaml_sync.py, models.py, runner.py, evaluators.py

### Frontend Patterns
**Source:** step-3-frontend-patterns-research.md

- TanStack Router file-based routing; add `/evals`, `/evals/$datasetId`, `/evals/$datasetId/runs/$runId`
- API layer: TanStack Query hooks following reviews.ts pattern (useDatasets, useEvalRuns, etc.)
- Dataset list page: table with name, target, case count, last run score, status
- Dataset detail page: tabbed (Cases + Run History)
- Case editor: schema-driven form fields derived from step/pipeline input schema via introspection
- Run detail: per-case results grid with evaluator columns, expandable rows
- shadcn/ui components throughout; reuse Table, Badge, Card, Tabs, ScrollArea, JsonViewer

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| What do case `inputs` represent -- prompt template variables or full pipeline input_data? | Pipeline input_data (NOT prompt template vars). Cases run through prepare_calls(), testing full step wiring. | task_fn must call prepare_calls() with input_data, not just render prompts. Cases represent real pipeline inputs, giving higher-fidelity evals but requiring knowledge of pipeline input schema. Needs introspection API for input schema. |
| How does YAML sync work -- version tracking like prompts, or simpler? | DB is source of truth. No version tracking. YAML seeds DB on first load, DB overwrites YAML on save. | Dramatically simplifies sync logic. No version comparison, no conflict resolution. First load = insert if not exists. UI save = overwrite YAML. Startup sync = insert-if-missing only (DB wins on conflict). |
| Are pipeline-level evals included in v1 or deferred? | INCLUDED in v1. Full pipeline-level support with nested expected_output by step name, multi-step execution, different evaluator aggregation. | Adds complexity: pipeline task_fn must execute all steps, expected_output is `dict[step_name, output]`, evaluators run per-step within pipeline context. Need aggregation strategy (per-step scores rolled up). Dataset target_type="pipeline" needs distinct UI treatment. |
| How should the case editor render inputs -- raw JSON textarea or typed form fields? | Typed form fields. UI resolves step/pipeline input schema via introspection API, renders per-field labeled inputs. | Requires new backend introspection endpoint returning input JSON schema for a given step/pipeline. Frontend CaseEditor maps JSON Schema types to form components (string->Input, number->Input[number], boolean->Checkbox, enum->Select, object/array->JSON textarea). Better UX but more implementation work. |
| Is pydantic-evals a core or optional dependency? | Core dependency. Always installed, no conditional imports needed. | Simplifies all import paths. No try/except guards, no feature flags. Add `pydantic-evals` to pyproject.toml core dependencies. Already in uv.lock. |

## Assumptions Validated

- [x] pydantic-evals `Case.inputs` maps to llm-pipeline `input_data` (full pipeline input, not prompt vars)
- [x] YAML sync uses insert-if-missing on startup, DB overwrites YAML on save (no versioning)
- [x] Pipeline-level evals are v1 scope -- nested expected_output keyed by step name
- [x] Case editor uses typed form fields from introspection endpoint (not raw JSON)
- [x] pydantic-evals is a core dependency -- unconditional imports throughout
- [x] Custom `FieldMatch` evaluator needed for partial field matching (not built-in)
- [x] `{}` return from evaluator = skip (confirmed in pydantic-evals API)
- [x] DB tables follow existing SQLModel patterns (JSON columns, Optional PK, indexes)
- [x] Routes follow existing reviews.py pattern (APIRouter, Pydantic response models, BackgroundTasks)
- [x] Frontend follows TanStack Router + TanStack Query + shadcn/ui patterns already established

## Open Items

- Introspection endpoint design: need to determine how to extract input schema for both steps (from prepare_calls signature / input_data typing) and pipelines (from pipeline config). May need new registry or reflection over step definitions.
- Pipeline-level evaluator aggregation strategy: how to roll up per-step scores into pipeline-level pass/fail. Options: all-must-pass, weighted average, per-step thresholds. CEO said "different evaluator aggregation" but specifics TBD during planning.
- Pipeline expected_output format: `dict[step_name, dict[field, value]]` -- need to define exact nesting structure and how partial step expectations work (e.g., only check 2 of 5 steps).
- LLMJudge evaluator requires model config (defaults to openai:gpt-5.2). Need to decide if eval runs use the same model as pipeline or allow override.
- `EvaluationReport` serialization to JSON for DB storage: need to verify `report_data` column can faithfully round-trip all report types (ConfusionMatrix, SpanTree, etc.) or if we store a subset.
- YAML writeback atomicity: if UI save fails mid-write, YAML file could be corrupted. Consider write-to-temp + rename pattern.

## Recommendations for Planning

1. **Start with step-level evals, then layer pipeline-level on top.** Step evals are simpler (single task_fn, flat expected_output) and validate the full vertical slice before adding pipeline complexity.
2. **Build introspection endpoint early.** Both case editor (frontend) and input validation (backend) depend on knowing the input schema. This is a prerequisite for the case editor UI.
3. **Implement YAML sync as thin layer.** CEO's "simplest approach" (no versioning) means sync logic is ~50 lines. Do it early to unblock dataset creation workflow.
4. **Use auto-generated FieldMatch as default evaluator.** When no evaluators specified on step, auto-generate from `instructions_cls.model_fields`. This gives useful evals out of the box with zero config.
5. **Design DB tables to store denormalized report data.** Keep `EvaluationRun.report_data` as full JSON blob for flexibility, plus denormalized counts (pass/fail/error) for fast list queries.
6. **Plan frontend in 3 phases:** dataset list + CRUD, case editor with introspection, run results viewer. Case editor is the most complex piece due to dynamic schema rendering.
7. **Add pydantic-evals to pyproject.toml core deps immediately.** Already in uv.lock; just needs the declaration. Unblocks all backend work.
8. **Pipeline-level eval runner should reuse existing pipeline.execute() path.** Avoid reimplementing pipeline orchestration; wrap the existing execute method as task_fn, collect per-step outputs into dict.
