# Architecture Review

## Overall Assessment
**Status:** complete
Pure additive change. Two new SQLModel table definitions follow established codebase patterns precisely. Model structure, field types, index strategy, table registration, package exports, and test coverage are all correct and consistent.

## Project Guidelines Compliance
**CLAUDE.md:** `C:\Users\SamSG\Documents\claude_projects\llm-pipeline\CLAUDE.md`
| Guideline | Status | Notes |
| --- | --- | --- |
| Python 3.11+ | pass | Uses `Optional` from typing, no 3.10+ union syntax |
| Pydantic v2 / SQLModel | pass | SQLModel table=True with Field() and Column(JSON) |
| SQLAlchemy 2.0 | pass | sa_column=Column(JSON), Index, UniqueConstraint |
| Architecture: Pipeline+Strategy+Step | pass | Additive models only, no architectural change |
| PipelineStepState/PipelineRunInstance pattern | pass | Same id/timestamps/JSON/index patterns |
| init_pipeline_db() registration | pass | Tables added to existing create_all call |
| Tests: pytest | pass | 15 tests, class-per-concern, in-memory SQLite |

## Issues Found
### Critical
None

### High
None

### Medium

#### DraftStep has redundant name index alongside UniqueConstraint
**Step:** 1
**Details:** `DraftStep.__table_args__` contains both `UniqueConstraint("name", name="uq_draft_steps_name")` and `Index("ix_draft_steps_name", "name")`. A unique constraint implicitly creates a unique index on the column. The explicit `Index("ix_draft_steps_name", "name")` is redundant and adds unnecessary write overhead (two indexes maintained on the same column). DraftPipeline correctly omits the extra name index. Recommendation: remove `Index("ix_draft_steps_name", "name")` from DraftStep.__table_args__ and delete the corresponding test assertion.

### Low

#### updated_at not auto-updated on UPDATE
**Step:** 1
**Details:** Both models define `updated_at: datetime = Field(default_factory=utc_now)` which sets the value at INSERT time but does NOT auto-update on subsequent writes. Callers must explicitly set `updated_at = utc_now()` when modifying rows. This matches the existing Prompt model pattern and is documented in PLAN.md as a known risk, so it's consistent. Flagging for awareness only -- downstream tasks (51/52) must remember to set updated_at on every UPDATE.

#### Prompt uses inline lambda for timestamps, DraftStep/DraftPipeline use utc_now
**Step:** 1
**Details:** Prompt model uses `default_factory=lambda: datetime.now(timezone.utc)` while new models use `default_factory=utc_now`. Both produce identical results. The `utc_now` approach is cleaner and matches PipelineStepState/PipelineRunInstance/PipelineRun/PipelineEventRecord. Not a defect, but a minor codebase inconsistency inherited from Prompt (pre-existing). No action needed for this task.

## Review Checklist
[x] Architecture patterns followed - SQLModel table=True, Field(), Column(JSON), __table_args__ tuple, utc_now default_factory
[x] Code quality and maintainability - clean docstrings, field descriptions, proper class placement
[x] Error handling present - N/A for model definitions; tests use pytest.raises for IntegrityError
[x] No hardcoded values - status default "draft" is intentional domain default, not hardcoded config
[x] Project conventions followed - __tablename__, id pattern, Optional[int] PK, __all__ exports, test structure
[x] Security considerations - no user input handling, no SQL injection surface, JSON columns properly typed
[x] Properly scoped (DRY, YAGNI, no over-engineering) - minimal fields matching downstream task requirements, no premature abstractions

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| llm_pipeline/state.py | pass | DraftStep + DraftPipeline correctly placed after PipelineRun, before __all__. UniqueConstraint import added. Field patterns match existing models. One redundant index on DraftStep.name (MEDIUM). |
| llm_pipeline/db/__init__.py | pass | Import updated, tables list extended, docstring updated. Follows existing registration pattern exactly. |
| llm_pipeline/__init__.py | pass | Import line and __all__ updated. DraftStep/DraftPipeline placed in # State section. |
| tests/test_draft_tables.py | pass | 15 tests across 4 classes. Matches test_init_pipeline_db.py pattern (in-memory SQLite, engine.dispose() in finally). Covers table creation, indexes, unique constraints, CRUD, JSON round-trip, nullable fields, run_id optionality, status transitions. |

## New Issues Introduced
- Redundant index on DraftStep.name (MEDIUM -- see above)
- No other new issues detected

## Recommendation
**Decision:** CONDITIONAL
Remove the redundant `Index("ix_draft_steps_name", "name")` from DraftStep.__table_args__ in state.py and the corresponding `assert "ix_draft_steps_name" in index_names` from tests/test_draft_tables.py. The unique constraint already provides an index on name. After that fix, this is a clean APPROVE.

---

# Architecture Re-Review (Post-Fix)

## Overall Assessment
**Status:** complete
MEDIUM issue resolved. DraftStep.__table_args__ now contains only UniqueConstraint + status Index, matching DraftPipeline exactly. Test updated to assert absence of redundant index. 15/15 tests pass. No new issues.

## Verified Changes
| File | Change | Verified |
| --- | --- | --- |
| llm_pipeline/state.py | `Index("ix_draft_steps_name", "name")` removed from DraftStep.__table_args__ | pass -- __table_args__ now has exactly UniqueConstraint("name") + Index("ix_draft_steps_status", "status"), symmetric with DraftPipeline |
| tests/test_draft_tables.py | test_index_creation assertion changed to `assert "ix_draft_steps_name" not in index_names` | pass -- correctly verifies the index no longer exists; docstring updated to explain name uniqueness via constraint |

## Previous Issues Status
| Issue | Severity | Status |
| --- | --- | --- |
| Redundant name index on DraftStep | MEDIUM | RESOLVED -- index removed, test updated |
| updated_at not auto-updated on UPDATE | LOW | Acknowledged, consistent with codebase, deferred to tasks 51/52 |
| Prompt lambda vs utc_now inconsistency | LOW | Pre-existing, no action needed |

## New Issues Introduced
- None detected

## Recommendation
**Decision:** APPROVE
All issues from initial review resolved or acknowledged as pre-existing/deferred. Implementation is clean, consistent with codebase patterns, and fully tested.
