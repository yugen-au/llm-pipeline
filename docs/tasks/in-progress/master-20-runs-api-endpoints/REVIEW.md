# Architecture Review

## Overall Assessment
**Status:** complete
Solid implementation across all 5 steps. Architecture decisions are sound and well-documented. All 31 new tests pass, full suite 558 passed with 0 regressions. Code follows existing codebase patterns (lazy imports, SQLModel conventions, sync endpoints). No critical or high issues found.

## Project Guidelines Compliance
**CLAUDE.md:** C:\Users\SamSG\Documents\claude_projects\llm-pipeline\CLAUDE.md

| Guideline | Status | Notes |
| --- | --- | --- |
| Python 3.11+ | pass | No 3.12+ features used; `str \| None` syntax is 3.10+ compatible |
| Pydantic v2 | pass | Response models use `BaseModel` from pydantic, not SQLModel |
| SQLModel / SQLAlchemy 2.0 | pass | PipelineRun uses SQLModel table=True, WAL uses SQLAlchemy event API |
| Hatchling build | pass | pyproject.toml unchanged except dev dep addition |
| pytest testing | pass | 31 tests in pytest, all passing |
| No hardcoded values | pass | Pagination limits use Query() defaults with validation |
| Error handling present | pass | 404 for missing runs, 404 for unregistered pipelines, None-guard in except |
| Atomic commits per piece | pass | 5 implementation steps each independently verified |

## Issues Found
### Critical
None

### High
None

### Medium
#### WAL event listener registered multiple times on repeated init_pipeline_db() calls
**Step:** 1
**Details:** Each call to `init_pipeline_db()` with the same engine registers a new `set_sqlite_wal` listener (each call creates a new function object, so SQLAlchemy cannot deduplicate). If `init_pipeline_db()` is called N times with the same engine, every new connection will execute `PRAGMA journal_mode=WAL` N times. Functionally harmless (idempotent PRAGMA) but wasteful. Plan acknowledged this risk and accepted it. Fix: guard with `if not event.contains(engine, "connect", ...)` or use a module-level set to track already-registered engines.

#### PipelineRun not exported from top-level __init__.py
**Step:** 1
**Details:** `PipelineStepState` and `PipelineRunInstance` are exported from `llm_pipeline/__init__.py` and listed in `__all__`. `PipelineRun` is only exported from `llm_pipeline.state`. For API consistency, it should be added to `__init__.py` imports and `__all__`. Consumers will need `from llm_pipeline.state import PipelineRun` instead of `from llm_pipeline import PipelineRun`.

#### POST /runs background task has no error handling
**Step:** 3
**Details:** The `run_pipeline()` closure in `trigger_run()` calls `pipeline.execute()` and `pipeline.save()` with no try/except. If the factory raises, or execute/save raises an unhandled exception, FastAPI's BackgroundTasks will silently swallow it (logged at ERROR level by Starlette but no structured error tracking). The PipelineRun row will remain stuck at status="running" forever if the exception happens before `pipeline.execute()` creates the PipelineRun record, or if the factory itself raises. Consider wrapping in try/except with logging or a status update mechanism.

### Low
#### POST /runs factory contract loosely typed
**Step:** 3
**Details:** `pipeline_registry: Optional[dict]` uses untyped `dict`. A `Dict[str, Callable[[str, Engine], Any]]` type hint would make the factory contract explicit. The docstring documents the signature but the type system cannot enforce it. Acceptable for a framework-level API but could use a Protocol or TypeAlias.

#### No validation on run_id path parameter format
**Step:** 3
**Details:** `GET /runs/{run_id}` accepts any string. While there is no security risk (parameterized query prevents injection), accepting non-UUID strings means meaningless requests are processed before returning 404. A UUID path constraint (e.g., `Path(pattern=...)`) would fail-fast with 422.

#### test_pipeline_run_tracking.py uses SQLModel.metadata.create_all(engine) globally
**Step:** 5
**Details:** The `tracking_engine` fixture calls `SQLModel.metadata.create_all(engine)` after `init_pipeline_db(engine)`. This creates ALL SQLModel tables ever imported (not just framework tables), which could create `gadgets_tracking` in production engines if this pattern is copied. The `init_pipeline_db()` call with explicit `tables=[...]` is the correct pattern; the global `create_all` is needed here only because `Gadget` is a test-only model. Acceptable in test code but worth a comment.

## Review Checklist
[x] Architecture patterns followed - Pipeline+Strategy+Step pattern maintained, dedicated table for perf, sync endpoints for SQLite
[x] Code quality and maintainability - DRY filter helper, clean Pydantic models, consistent naming
[x] Error handling present - 404s, None-guard on pipeline_run in except, validation on offset/limit
[x] No hardcoded values - defaults via Query(), status strings match documented set
[x] Project conventions followed - snake_case, lazy imports, SQLModel patterns, ReadOnlySession for GET
[x] Security considerations - parameterized queries (no SQL injection), ReadOnlySession prevents writes via API, CORS configured
[x] Properly scoped (DRY, YAGNI, no over-engineering) - minimal response models, no premature abstractions

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| llm_pipeline/state.py | pass | PipelineRun model correct, redundant index removal justified, added to __all__ |
| llm_pipeline/db/__init__.py | pass | WAL listener works, PipelineRun table registered, idempotent PRAGMA acceptable |
| llm_pipeline/pipeline.py | pass | run_id injection backward compatible, PipelineRun lifecycle correct, None-guard in except |
| llm_pipeline/ui/app.py | pass | pipeline_registry param clean, docstring documents factory contract |
| llm_pipeline/ui/routes/runs.py | pass | All 3 endpoints correct, Pydantic models clean, filter helper DRY |
| pyproject.toml | pass | httpx dev dep added correctly |
| tests/ui/conftest.py | pass | StaticPool pattern correct for in-memory SQLite with threadpool |
| tests/ui/test_runs.py | pass | 23 tests covering happy path, edge cases, validation, pagination |
| tests/ui/test_wal.py | pass | 4 tests verify WAL mode and engine return |
| tests/test_pipeline_run_tracking.py | pass | 4 integration tests cover success/failure/run_id preservation/pipeline_name |

## New Issues Introduced
- WAL listener accumulates on repeated init_pipeline_db() calls (medium, functionally harmless)
- PipelineRun not in top-level __init__.py exports (medium, API consistency)
- Background task in POST /runs has no error handling wrapper (medium, silent failures possible)
- Factory contract loosely typed (low)
- No UUID validation on run_id path param (low)

## Recommendation
**Decision:** APPROVE
Implementation is architecturally sound, well-tested, and follows codebase conventions. The 3 medium issues are non-blocking: WAL duplication is harmless, missing __init__.py export is a follow-up, and background task error handling is an enhancement. No data loss, security, or correctness risks identified.
