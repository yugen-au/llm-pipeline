# Research Summary

## Executive Summary

Research steps 1 and 2 provide thorough analysis of existing codebase patterns and a well-reasoned schema design. JSON column patterns, status-as-string, no-FK relationship, timestamp conventions, and index strategy are all correctly aligned with the codebase. However, validation surfaced 5 hidden assumptions requiring CEO clarification before planning can proceed: name uniqueness semantics, file placement given cross-module imports, table creation strategy, DraftStep-GenerationRecord relationship, and post-acceptance lifecycle.

## Domain Findings

### Existing Patterns (Validated)
**Source:** research/step-1-existing-state-models.md

- Two-tier table creation pattern correctly identified: framework tables in `init_pipeline_db()`, module tables on-demand (e.g., `seed_prompts()` creates `GenerationRecord.__table__`)
- All 6 existing SQLModel tables accurately catalogued with field conventions (`id: Optional[int]`, `sa_column=Column(JSON)`, `utc_now()`, `__tablename__`, `__table_args__`)
- Creator module structure and optional dependency guard (`jinja2`) correctly documented
- Downstream tasks 51/52 accurately analyzed -- task 52 imports DraftPipeline directly in `ui` routes

### Schema Design (Validated with Gaps)
**Source:** research/step-2-schema-design-patterns.md

- JSON column pattern: correctly matches codebase (`sa_column=Column(JSON)` for required, `Optional[dict]` with `default=None` for nullable). No issues.
- Status as plain string: correct -- no Enum usage anywhere in codebase. Valid transitions documented.
- No FK between DraftPipeline/DraftStep: correct -- matches loose coupling, no Relationship() usage in codebase. Future link table path documented.
- Timestamps: `utc_now` from state.py (Pattern A) preferred over inline lambda (Pattern B). Application-managed `updated_at` matches Prompt precedent.
- Indexes: minimal strategy appropriate for low-volume tables. Status + name indexes on DraftStep, status-only on DraftPipeline.

### Cross-Cutting Import Concern (Gap Found)
**Source:** research/step-2-schema-design-patterns.md, validated against actual code

Research recommends `creator/models.py` for file placement. Verified that `creator/models.py` currently has NO jinja2 dependency (only imports `pydantic.BaseModel`, `sqlmodel`, `datetime`), so `from llm_pipeline.creator.models import DraftPipeline` in `ui/routes/editor.py` works without triggering the `creator/__init__.py` jinja2 guard (Python resolves `creator.models` directly). However, this is fragile -- any future addition of jinja2-dependent code to `creator/models.py` would break the editor. This risk is undocumented in the research.

### Name Uniqueness (Gap Found)
**Source:** Not addressed in either research step

Neither research step addresses whether `DraftStep.name` or `DraftPipeline.name` should carry a UNIQUE constraint. This is critical because `DraftPipeline.structure` references steps by name. If multiple DraftStep rows can share the same name (e.g., re-generation creates a new row), name-based lookups become ambiguous. The schema proposes an index on `name` but not a uniqueness constraint.

### DraftStep-GenerationRecord Overlap (Gap Found)
**Source:** Not addressed in either research step

`GenerationRecord` already tracks `step_name_generated`, `is_valid`, `files_generated`, `run_id`. DraftStep will track `name`, `status`, `generated_code`, `test_results`. These overlap conceptually. Research does not address: (a) whether DraftStep should link to GenerationRecord via `run_id`, (b) who creates DraftStep rows (StepCreator pipeline? editor UI? both?), (c) whether DraftStep replaces or complements GenerationRecord for the draft lifecycle.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Pending: see Questions below | - | - |

## Assumptions Validated
- [x] JSON columns use `sa_column=Column(JSON)` pattern -- confirmed across 5 existing usages in state.py, events/models.py, db/prompt.py, creator/models.py
- [x] Status fields use plain `str` with `max_length` -- confirmed in PipelineRun.status, no Enum imports anywhere
- [x] No FK/Relationship() usage in codebase -- confirmed, all inter-table references are via string keys (run_id, step_name)
- [x] `utc_now()` is exported via `__all__` in state.py -- confirmed, available for import
- [x] `creator` and `ui` are separate optional deps -- confirmed in pyproject.toml (creator=jinja2, ui=fastapi)
- [x] `creator/models.py` has no jinja2 dependency -- confirmed, safe to import from ui TODAY (fragile)
- [x] Task 50 description says "Update init_pipeline_db()" -- confirmed, contradicts research step-2 recommendation
- [x] `ui/app.py` calls `init_pipeline_db()` at startup -- confirmed, tables added there would be auto-created for editor

## Open Items
- Name uniqueness: must resolve before implementation (affects schema, queries, and DraftPipeline.structure reference resolution)
- File placement: must decide between creator/models.py (fragile) vs neutral location (safe)
- Table creation: must reconcile task description (init_pipeline_db) vs research recommendation (separate init)
- DraftStep-GenerationRecord relationship: must clarify overlap and creation responsibility
- Post-acceptance lifecycle: "accepted" as terminal state vs future "integrated"/"deployed" states

## Recommendations for Planning
1. **File placement**: Put DraftStep/DraftPipeline in `llm_pipeline/state.py` alongside PipelineRun/PipelineStepState. These are cross-cutting models used by both `creator` and `ui` optional modules. state.py has no optional deps. This eliminates the fragile import path through creator/models.py.
2. **Table creation**: Add to `init_pipeline_db()` per the task 50 description. Since models would live in state.py (core, no optional deps), this is clean -- same pattern as PipelineRun which was added to init_pipeline_db() in task 17.
3. **Name uniqueness**: Add UNIQUE constraint on `DraftStep.name` (one active draft per step name). For re-generation, UPDATE the existing row rather than INSERT. This matches the domain: a draft step IS a step-in-progress, not a version history. If version history is needed later, GenerationRecord already serves that role.
4. **DraftPipeline.name**: Also UNIQUE -- one draft pipeline per name. Same reasoning.
5. **DraftStep-GenerationRecord link**: Add optional `run_id` field to DraftStep for traceability back to the generation run. Not a FK, just a string field matching the pattern used everywhere else (PipelineStepState.run_id, PipelineRunInstance.run_id, etc).
6. **Status lifecycle**: Keep "accepted" as defined. Post-acceptance behavior (file writing, integration) is task 51/52 scope, not schema scope. The string-based status field is extensible without migration.
