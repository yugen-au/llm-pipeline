# Research Summary

## Executive Summary

Research steps 1 and 2 provide thorough analysis of existing codebase patterns and a well-reasoned schema design. JSON column patterns, status-as-string, timestamp conventions, and index strategy are all correctly aligned with the codebase. Validation surfaced 5 hidden assumptions -- all 5 now resolved via CEO decisions. Key outcomes: UNIQUE constraints on both name fields, models live in state.py (core), tables created via init_pipeline_db(), DraftStep links to GenerationRecord via nullable run_id, and "accepted" is terminal.

## Domain Findings

### Existing Patterns (Validated)
**Source:** research/step-1-existing-state-models.md

- Two-tier table creation pattern correctly identified: framework tables in `init_pipeline_db()`, module tables on-demand (e.g., `seed_prompts()` creates `GenerationRecord.__table__`)
- All 6 existing SQLModel tables accurately catalogued with field conventions (`id: Optional[int]`, `sa_column=Column(JSON)`, `utc_now()`, `__tablename__`, `__table_args__`)
- Creator module structure and optional dependency guard (`jinja2`) correctly documented
- Downstream tasks 51/52 accurately analyzed -- task 52 imports DraftPipeline directly in `ui` routes

### Schema Design (Validated, Gaps Resolved)
**Source:** research/step-2-schema-design-patterns.md

- JSON column pattern: correctly matches codebase (`sa_column=Column(JSON)` for required, `Optional[dict]` with `default=None` for nullable). No issues.
- Status as plain string: correct -- no Enum usage anywhere in codebase. Valid transitions documented.
- No FK between DraftPipeline/DraftStep: correct -- matches loose coupling. DraftPipeline.structure references steps by name (string), not by FK.
- Timestamps: `utc_now` from state.py (Pattern A) preferred over inline lambda (Pattern B). Application-managed `updated_at` matches Prompt precedent.
- Indexes: minimal strategy appropriate for low-volume tables. Status + name indexes on DraftStep, status-only on DraftPipeline.

### Cross-Cutting Import Concern (Resolved)
**Source:** research/step-2-schema-design-patterns.md, validated against actual code

Research recommended `creator/models.py` for file placement. Verified that `creator/models.py` currently has NO jinja2 dependency, so importing from ui works today but is fragile. **Decision: models go in state.py** -- eliminates this concern entirely. Both creator and ui can safely import from `llm_pipeline.state` with zero optional-dep risk.

### Name Uniqueness (Resolved)
**Source:** Not addressed in either research step; surfaced during validation

Neither research step addressed UNIQUE constraints on `DraftStep.name` or `DraftPipeline.name`. **Decision: UNIQUE constraint on both.** Re-generation UPDATEs the existing row rather than INSERTing a new one. This resolves DraftPipeline.structure name-reference ambiguity and matches the domain (a draft IS a mutable work-in-progress, not version history).

### DraftStep-GenerationRecord Link (Resolved)
**Source:** Not addressed in either research step; surfaced during validation

GenerationRecord tracks `run_id`, `step_name_generated`, `is_valid`, `files_generated`. DraftStep overlaps conceptually. **Decision: add optional `run_id` field to DraftStep as nullable FK to GenerationRecord.** Provides traceability back to the generation run without requiring it. Note: this is the FIRST FK in the codebase -- all other inter-table references use plain string keys. CEO explicitly chose FK here for stronger referential integrity on this specific link.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Should DraftStep.name and DraftPipeline.name be UNIQUE? | Yes, UNIQUE constraint on both. Re-generation UPDATEs existing row. | Add UniqueConstraint to `__table_args__`. Query patterns simplified (no latest-by-created_at needed). |
| File placement: state.py or creator/models.py? | state.py (core module). | Eliminates fragile cross-optional-dep import. Both creator and ui import safely. No architectural risk. |
| Table creation: init_pipeline_db() or separate init? | init_pipeline_db(). Models in state.py makes this clean. | Follow task 50 description. No separate init function needed. Same pattern as PipelineRun/PipelineEvent. |
| Should DraftStep link to GenerationRecord? | Yes, optional run_id as nullable FK. | First FK in codebase. Provides traceability without requiring generation context (editor-created drafts have null run_id). |
| Is "accepted" terminal? | Yes. Draft lifecycle ends at accepted. | No need for "integrated"/"deployed" states. Accepted steps become real pipeline steps in different models. Status enum is final: draft, tested, accepted, error. |

## Assumptions Validated
- [x] JSON columns use `sa_column=Column(JSON)` pattern -- confirmed across 5 existing usages
- [x] Status fields use plain `str` with `max_length` -- confirmed, no Enum usage in codebase
- [x] No FK/Relationship() usage in codebase currently -- confirmed; DraftStep.run_id will be FIRST FK (CEO decision)
- [x] `utc_now()` exported via `__all__` in state.py -- confirmed, available for import
- [x] `creator` and `ui` are separate optional deps -- confirmed in pyproject.toml
- [x] Task 50 description says "Update init_pipeline_db()" -- confirmed, now aligned with CEO decision
- [x] `ui/app.py` calls `init_pipeline_db()` at startup -- confirmed, draft tables auto-created for editor
- [x] DraftStep.name UNIQUE -- CEO confirmed, resolves DraftPipeline.structure reference ambiguity
- [x] DraftPipeline.name UNIQUE -- CEO confirmed, one draft pipeline per name
- [x] "accepted" is terminal -- CEO confirmed, no post-acceptance states needed

## Open Items
- None. All 5 questions resolved.

## Recommendations for Planning
1. **File**: Add DraftStep and DraftPipeline classes to `llm_pipeline/state.py` alongside PipelineStepState, PipelineRunInstance, PipelineRun
2. **Table creation**: Import new models in `llm_pipeline/db/__init__.py` and add to `init_pipeline_db()` metadata create_all
3. **DraftStep schema**: `name` (unique, max_length=100), `description` (optional str), `generated_code` (JSON, required), `test_results` (JSON, nullable), `validation_errors` (JSON, nullable), `status` (str, default='draft'), `run_id` (nullable FK to generation_records), `created_at`, `updated_at`
4. **DraftPipeline schema**: `name` (unique, max_length=100), `structure` (JSON, required), `compilation_errors` (JSON, nullable), `status` (str, default='draft'), `created_at`, `updated_at`
5. **Unique constraints**: `UniqueConstraint('name', name='uq_draft_steps_name')` and `UniqueConstraint('name', name='uq_draft_pipelines_name')` in respective `__table_args__`
6. **FK pattern**: `run_id: Optional[str] = Field(default=None, max_length=36, foreign_key="generation_records.run_id")` -- first FK in codebase, keep it simple (no Relationship/back_populates)
7. **Exports**: Add DraftStep, DraftPipeline to `llm_pipeline/__init__.py` `__all__`
8. **Status values**: draft, tested, accepted, error (both tables)
