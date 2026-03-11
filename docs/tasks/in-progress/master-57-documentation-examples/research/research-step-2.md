# Step 2: Existing Docs Audit

## Scope Covered

- `README.md` (root)
- `docs/index.md`
- `docs/api/*.md` (all 10 files)
- `docs/guides/*.md` (all 4 files)
- `docs/architecture/overview.md`
- `pyproject.toml` (package metadata and optional deps)
- Inline docstrings for: `llm_pipeline/events/types.py`, `emitter.py`, `handlers.py`, `models.py`, `__init__.py`, `llm/result.py`, `llm/provider.py`, `ui/cli.py`, `ui/app.py`, `ui/bridge.py`
- No CHANGELOG file found (none exists in repo root or docs/)

---

## What Is Already Documented

### README.md

File: `README.md` (root)

Content: exactly 3 lines.

```
# llm-pipeline

Declarative LLM pipeline orchestration framework.
```

No installation instructions, no usage examples, no feature descriptions. Functionally empty.

### docs/index.md

Full navigation index. Covers all existing docs. Does NOT list an events API module in the module index table. The table has 9 rows (Pipeline, Step, Strategy, Extraction, Transformation, LLM Provider, Prompts, State, Registry) — events is absent. Cross-reference section "LLM Provider" points to `api/llm.md` but no entry for events or event system.

### docs/api/llm.md

Documents `LLMProvider`, `GeminiProvider`, `execute_llm_step()`, `RateLimiter`, validation layers, schema utilities.

**Outdated:** `call_structured()` is documented as returning `Optional[Dict[str, Any]]`. Actual current return type is `LLMCallResult`. The documented parameter list also omits the four event-integration params added alongside the event system: `event_emitter`, `step_name`, `run_id`, `pipeline_name`.

`LLMCallResult` class is not mentioned anywhere in this file.

### docs/guides/getting-started.md

Step-by-step first-pipeline guide. Mentions `pip install llm-pipeline[ui]` only as an install option (one bullet in the installation section, no further explanation of what UI is or how to use it). No event system coverage. No `LLMCallResult` mention.

### docs/architecture/overview.md

Full architecture deep-dive (1200+ lines). Monitoring/Observability section says:

> "Framework uses standard logging. `logging.basicConfig(level=logging.INFO)`"

No event system coverage. Optional Dependencies section lists only `google-generativeai` and `pytest` — `fastapi`, `uvicorn`, `python-multipart` ([ui] extra) are absent.

### docs/api/ (all other files)

`pipeline.md`, `step.md`, `strategy.md`, `extraction.md`, `transformation.md`, `prompts.md`, `state.md`, `registry.md` — none reference events, `LLMCallResult`, or the UI.

### pyproject.toml

Has both extras correctly defined:

```toml
[project.optional-dependencies]
gemini = ["google-generativeai>=0.3.0"]
ui = ["fastapi>=0.115.0", "uvicorn[standard]>=0.32.0", "python-multipart>=0.0.9"]
```

Entry point is defined:

```toml
[project.scripts]
llm-pipeline = "llm_pipeline.ui.cli:main"
```

This is not documented anywhere in existing docs.

---

## What Is Missing (Gaps)

### Gap 1: No events API docs file — CRITICAL

`docs/api/events.md` does not exist. The event system is fully implemented with:
- 28+ concrete event types across 9 categories
- `PipelineEventEmitter` Protocol (runtime-checkable)
- `CompositeEmitter` with per-handler error isolation
- `LoggingEventHandler` with `DEFAULT_LEVEL_MAP`
- `InMemoryEventHandler` (thread-safe, for testing/UI)
- `SQLiteEventHandler` (persists to `pipeline_events` table)
- `PipelineEventRecord` SQLModel DB table
- `resolve_event()` convenience function for deserialization
- Full re-export via `llm_pipeline.events.__init__` and `llm_pipeline.__init__`

None of this is documented anywhere.

### Gap 2: LLMCallResult not documented — CRITICAL

`LLMCallResult` is exported from both `llm_pipeline.llm` and `llm_pipeline` (top-level) but has zero documentation coverage. The class provides:
- Frozen dataclass with `slots=True`
- Fields: `parsed`, `raw_response`, `model_name`, `attempt_count`, `validation_errors`
- Properties: `is_success`, `is_failure`
- Factory classmethods: `LLMCallResult.success()`, `LLMCallResult.failure()`
- Serialization: `to_dict()`, `to_json()`

### Gap 3: docs/api/llm.md shows wrong return type — CRITICAL (outdated)

`LLMProvider.call_structured()` is documented as returning `Optional[Dict[str, Any]]`. Actual return type is `LLMCallResult`. This is a breaking misrepresentation.

Additionally, four params added when the event system was integrated are missing from the documented signature:
- `event_emitter: Optional[PipelineEventEmitter]`
- `step_name: Optional[str]`
- `run_id: Optional[str]`
- `pipeline_name: Optional[str]`

### Gap 4: No UI documentation — IMPORTANT

The UI subsystem has zero guide coverage:
- `llm-pipeline ui` CLI command and its flags (`--dev`, `--port`, `--db`) are undocumented
- `create_app()` factory parameters (`pipeline_registry`, `introspection_registry`) are undocumented
- `UIBridge` (sync event→WebSocket adapter) is undocumented
- WebSocket event stream contract is undocumented
- No guide for launching the UI in dev mode vs production mode
- No guide explaining the `[ui]` optional extra beyond "pip install llm-pipeline[ui]"

### Gap 5: docs/index.md module table missing events row — IMPORTANT

The module index table lacks an events row. `docs/index.md` also has no cross-reference entries for events or `LLMCallResult`. The "LLM Integration" section in the cross-reference map should link to events docs.

### Gap 6: README.md has no content — IMPORTANT

README is 3 lines. Task 57 scope explicitly requires adding usage examples for event system, UI, and `LLMCallResult` changes. Any user landing on the repo sees nothing useful.

### Gap 7: docs/architecture/overview.md observability section outdated — MINOR

The observability section directs users to `logging.basicConfig()`. With the event system, the correct approach is to attach handlers to a `CompositeEmitter` passed to the pipeline. The logging handler is now one of three handler options.

### Gap 8: docs/architecture/overview.md optional deps missing [ui] — MINOR

Technology stack section's "Optional Dependencies" only lists `google-generativeai` and `pytest`. `fastapi`, `uvicorn`, `python-multipart` ([ui] extra) are absent.

---

## What Is Already Well Documented (Do Not Duplicate)

- Pipeline + Strategy + Step pattern (architecture overview + all guides)
- Getting started / installation (with `[gemini]` and `[dev]` extras)
- `PipelineConfig`, `LLMStep`, `step_definition`, extraction, transformation, registry
- State tracking (`PipelineStepState`, `PipelineRunInstance`)
- Caching strategy and cache key construction
- Two-phase write pattern
- ReadOnly session pattern
- Consensus polling
- Prompt management (YAML, versioning, sync)
- Validation layers (schema, array, Pydantic)
- Design patterns and known limitations

---

## Inline Docstring Quality Assessment

| File | Docstring Quality | Notes |
|---|---|---|
| `events/types.py` | Good | Base class, all concretes have one-liner docstrings. `StepSelecting` has edge-case note. |
| `events/emitter.py` | Good | Protocol and CompositeEmitter both have examples in docstrings. |
| `events/handlers.py` | Good | `InMemoryEventHandler` has usage example. `SQLiteEventHandler` explains session-per-emit pattern. |
| `events/models.py` | Good | Explains index duplication rationale. |
| `events/__init__.py` | Good | Usage block at top showing import patterns. Has minor error: imports `LLMCallStarted` (wrong name — actual event is `LLMCallStarting`). |
| `llm/result.py` | Good | All fields, properties, and factory methods have docstrings. |
| `llm/provider.py` | Good | New params (event_emitter, step_name, etc.) are documented in docstring but not in docs/api/llm.md. |
| `ui/cli.py` | Minimal | `main()` has one line. `_run_ui()` has one line. Private helpers undocumented. |
| `ui/app.py` | Good | `create_app()` has full Args/Returns docstring. |
| `ui/bridge.py` | Excellent | Module-level docstring explains threading model and spec deviation. Class and all methods documented. |

Minor issue in `events/__init__.py` line 16: the usage block imports `LLMCallStarted` but the correct event class name is `LLMCallStarting`. This is a documentation error in the module docstring.

---

## Summary Table: What Needs Writing for Task 57

| Item | Location | Action |
|---|---|---|
| Event system usage examples | `README.md` | Add |
| UI launch examples | `README.md` | Add |
| `LLMCallResult` usage examples | `README.md` | Add |
| `docs/api/events.md` | `docs/api/` | Create new file |
| `LLMCallResult` class docs | `docs/api/llm.md` | Add section |
| `call_structured()` return type fix | `docs/api/llm.md` | Update (Optional[Dict] → LLMCallResult) |
| `call_structured()` missing params | `docs/api/llm.md` | Update (add event_emitter, step_name, run_id, pipeline_name) |
| events module row | `docs/index.md` | Add to module table |
| UI guide | `docs/guides/` | Create new file (optional, may be out of scope for task 57) |
| Observability section | `docs/architecture/overview.md` | Update to cover event handlers |
| Optional deps | `docs/architecture/overview.md` | Add [ui] extra |
| Typo fix | `events/__init__.py` line 16 | Fix `LLMCallStarted` → `LLMCallStarting` |
