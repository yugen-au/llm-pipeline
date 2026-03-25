# Step 3: Database Integration Patterns for StepIntegrator

## 1. Database Layer Overview

### Engine & Session Bootstrap

**File**: `llm_pipeline/db/__init__.py`

- Module-level `_engine` singleton, initialized by `init_pipeline_db(engine=None)`
- If no engine provided, auto-creates SQLite at `.llm_pipeline/pipeline.db` (or `LLM_PIPELINE_DB` env var)
- `get_engine()` returns singleton, lazy-inits if needed
- `get_session()` returns `Session(get_engine())` -- a **writable** SQLModel Session
- WAL mode enabled for SQLite (concurrent read/write)
- `create_all` called with explicit table list (PipelineStepState, PipelineRunInstance, PipelineRun, Prompt, PipelineEventRecord, DraftStep, DraftPipeline)
- Post-creation migrations add columns to existing tables (`_migrate_add_columns`)
- Performance indexes added separately (`add_missing_indexes`)

### Tables Managed by Framework

| Table | Model | File |
|-------|-------|------|
| `prompts` | `Prompt` | `db/prompt.py` |
| `pipeline_step_states` | `PipelineStepState` | `state.py` |
| `pipeline_run_instances` | `PipelineRunInstance` | `state.py` |
| `pipeline_runs` | `PipelineRun` | `state.py` |
| `pipeline_events` | `PipelineEventRecord` | `events/models.py` |
| `draft_steps` | `DraftStep` | `state.py` |
| `draft_pipelines` | `DraftPipeline` | `state.py` |
| `creator_generation_records` | `GenerationRecord` | `creator/models.py` |

---

## 2. Prompt Model (db/prompt.py)

```python
class Prompt(SQLModel, table=True):
    __tablename__ = "prompts"

    id: Optional[int] = Field(default=None, primary_key=True)
    prompt_key: str          # max 100, indexed
    prompt_name: str         # max 200
    prompt_type: str         # max 50, values: "system", "user"
    category: Optional[str]  # max 50
    step_name: Optional[str] # max 50
    content: str
    required_variables: Optional[List[str]]  # JSON column
    description: Optional[str]
    version: str = "1.0"     # max 20
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]  # max 100

    # UniqueConstraint('prompt_key', 'prompt_type', name='uq_prompts_key_type')
    # Index("ix_prompts_category_step", "category", "step_name")
    # Index("ix_prompts_active", "is_active")
```

**Key constraint**: UniqueConstraint on `(prompt_key, prompt_type)` means each step gets at most one system prompt + one user prompt per prompt_key. Re-registration must use upsert-or-skip semantics.

---

## 3. Session Patterns in Codebase

### Pattern A: Dual-Session (PipelineConfig)

**File**: `pipeline.py` L267-279

```python
# Writable session for internal pipeline operations
self._real_session = Session(engine)
# Read-only wrapper exposed to steps
self.session = ReadOnlySession(self._real_session)
```

- Pipeline owns session lifecycle (`_owns_session` flag)
- `_real_session` used for: add/flush PipelineRun, add/flush PipelineStepState
- `self.session` (ReadOnlySession) used by steps for prompt lookups (strategy.py `create_step()`)
- Commit happens only in `save()` method -- single commit for all extractions
- `close()` called when pipeline is done

**Relevance to StepIntegrator**: The integrator will NOT run during pipeline execution. It runs from the accept endpoint (task 48) AFTER the creator pipeline completes. It needs its own writable Session.

### Pattern B: Session-per-Operation (Event Handlers)

**File**: `events/handlers.py`

```python
# SQLiteEventHandler: one session per emit
session = Session(self._engine)
try:
    session.add(record)
    session.commit()
finally:
    session.close()
```

**Relevance**: Too granular for StepIntegrator. We need batched writes.

### Pattern C: Context Manager with Single Commit (seed_prompts)

**File**: `creator/prompts.py` L256-267, `demo/prompts.py` L132-143

```python
with Session(engine) as session:
    for prompt_data in ALL_PROMPTS:
        existing = session.exec(
            select(Prompt).where(
                Prompt.prompt_key == prompt_data["prompt_key"],
                Prompt.prompt_type == prompt_data["prompt_type"],
            )
        ).first()
        if existing is None:
            session.add(Prompt(**prompt_data))
    session.commit()
```

**Relevance**: **Best match** for StepIntegrator prompt registration. Idempotent check-then-insert, single commit. Used in both demo and creator pipelines.

### Pattern D: Try/Rollback/Finally (sync_prompts)

**File**: `prompts/loader.py` L84-158

```python
session = Session(bind=bind)
try:
    # ... iterate prompts, add/update ...
    session.commit()
except Exception as e:
    session.rollback()
    raise e
finally:
    session.close()
```

**Relevance**: **Exact transaction pattern** for StepIntegrator. Explicit rollback on failure, close in finally. Supports both insert and update (version-based upsert).

### Pattern E: Buffered Bulk Insert with Fallback

**File**: `events/handlers.py` L269-317 (BufferedEventHandler.flush)

```python
session = Session(self._engine)
try:
    session.add_all(records)
    session.commit()
    # success: clear buffer
except Exception:
    session.rollback()
    # fallback: per-record insert
finally:
    session.close()
```

**Relevance**: Shows bulk insert + rollback + per-record fallback pattern. StepIntegrator could use `add_all` for prompt batch insertion.

---

## 4. ReadOnlySession (session/readonly.py)

Wraps SQLModel Session. Blocks: `add`, `add_all`, `delete`, `flush`, `commit`, `merge`, `refresh`, `expire`, `expire_all`, `expunge`, `expunge_all`. Allows: `query`, `exec`, `get`, `execute`, `scalar`, `scalars`.

**Purpose**: Prevents accidental DB writes during step execution. Steps can only read prompts/state.

**UI DI**: `get_db()` in `ui/deps.py` yields `ReadOnlySession(session)` for route handlers. All GET endpoints use `DBSession` (ReadOnlySession). Write endpoints (like `trigger_run`) bypass this by creating `Session(engine)` directly.

**StepIntegrator implication**: The integrator MUST receive a writable `Session`, NOT `ReadOnlySession`. The accept endpoint (task 48) should create a writable Session and pass it to the integrator, following the `trigger_run` and `seed_prompts` patterns.

---

## 5. DraftStep Model (state.py)

```python
class DraftStep(SQLModel, table=True):
    __tablename__ = "draft_steps"
    id: Optional[int]
    name: str                    # unique constraint
    description: Optional[str]
    generated_code: dict         # JSON column - structured dict of generated artifacts
    test_results: Optional[dict] # JSON
    validation_errors: Optional[dict]  # JSON
    status: str                  # "draft", "tested", "accepted", "error"
    run_id: Optional[str]       # links to creator_generation_records.run_id
    created_at: datetime
    updated_at: datetime
```

**StepIntegrator flow**: Accept endpoint fetches DraftStep by ID, passes to `StepIntegrator.integrate()`. On success, DraftStep.status should be updated to "accepted". On failure, status stays unchanged (or set to "error").

---

## 6. Recommended Transaction Pattern for StepIntegrator

### Atomic Operation Sequence

The StepIntegrator must perform these steps atomically:

1. Write Python files (step, instructions, extraction) to `target_dir`
2. Write prompt YAML files
3. Register prompts in DB
4. AST-update strategy file (add step to `get_steps()`)
5. AST-update registry file (add model to `models=[]`)
6. Update DraftStep.status to "accepted"

### Recommended Implementation

```python
class StepIntegrator:
    def __init__(self, target_dir: Path, session: Session):
        self.target_dir = target_dir
        self.session = session  # writable Session

    def integrate(self, generated, target_pipeline=None, target_strategy=None):
        written_files: list[Path] = []
        original_file_contents: dict[Path, str | None] = {}  # for AST rollback

        try:
            # Phase 1: Write new files (track for rollback)
            for filename, content in generated.artifacts.items():
                path = self.target_dir / filename
                written_files.append(path)
                path.write_text(content)

            # Phase 2: AST modifications (backup originals first)
            if target_strategy:
                strategy_path = ...
                original_file_contents[strategy_path] = strategy_path.read_text()
                self._update_strategy(strategy_path, generated)

            if target_pipeline:
                registry_path = ...
                original_file_contents[registry_path] = registry_path.read_text()
                self._update_registry(registry_path, generated)

            # Phase 3: DB writes (single transaction)
            self._register_prompts(generated)

            # Phase 4: Commit
            self.session.commit()

            return IntegrationResult(files_written=[str(f) for f in written_files])

        except Exception:
            # Rollback DB
            self.session.rollback()

            # Rollback AST-modified files
            for path, original in original_file_contents.items():
                if original is not None:
                    path.write_text(original)
                else:
                    path.unlink(missing_ok=True)

            # Delete newly written files
            for path in written_files:
                path.unlink(missing_ok=True)

            raise

    def _register_prompts(self, generated):
        """Register prompts following seed_prompts idempotency pattern."""
        for prompt_data in generated.prompts:
            existing = self.session.exec(
                select(Prompt).where(
                    Prompt.prompt_key == prompt_data["prompt_key"],
                    Prompt.prompt_type == prompt_data["prompt_type"],
                )
            ).first()
            if existing is None:
                self.session.add(Prompt(**prompt_data))
            else:
                # Update existing (version bump)
                for key, value in prompt_data.items():
                    if key != "id":
                        setattr(existing, key, value)
```

### Why This Order

1. **Files first, DB last**: If file writes fail, no DB cleanup needed (just delete written files). Session hasn't been touched yet.
2. **AST modifications backed up**: Original file contents saved before modification. On failure, restore originals.
3. **Single session.commit()**: All DB writes (prompt inserts + DraftStep status update) committed atomically. Rollback reverts all DB changes.
4. **Written file tracking**: All created files tracked in list for cleanup on failure.

---

## 7. Session Lifecycle for Accept Endpoint (Task 48)

The accept endpoint should follow the `trigger_run` pattern -- create a writable Session scoped to the request:

```python
@router.post('/api/creator/accept/{draft_id}')
def accept_step(draft_id: int, request: Request):
    engine = request.app.state.engine
    with Session(engine) as session:
        draft = session.get(DraftStep, draft_id)
        if not draft:
            raise HTTPException(404)

        integrator = StepIntegrator(target_dir, session)
        result = integrator.integrate(draft, target_pipeline=...)

        draft.status = "accepted"
        session.commit()  # or let integrator commit both

    return result
```

**Note**: Either the endpoint or the integrator should own the commit -- not both. Recommended: integrator owns the commit (including DraftStep update), since it needs rollback control.

---

## 8. Existing Patterns Summary Table

| Pattern | Where Used | Session Source | Commit Strategy | Rollback |
|---------|-----------|---------------|-----------------|----------|
| Dual-session | pipeline.py | Session(engine) | save() commits | No explicit rollback (flush only) |
| Session-per-op | SQLiteEventHandler | Session(engine) | Per-emit commit | No (try/finally close) |
| Context manager | seed_prompts | with Session(engine) | Single commit | Auto-rollback on exception |
| Try/rollback/finally | sync_prompts | Session(bind=bind) | Single commit | Explicit rollback + close |
| Buffered bulk | BufferedEventHandler | Session(engine) | Bulk commit | Rollback + per-record fallback |

**StepIntegrator should use**: Try/rollback/finally (Pattern D) enhanced with file rollback tracking.

---

## 9. Key Constraints & Gotchas

1. **UniqueConstraint on prompts**: `(prompt_key, prompt_type)` -- must check existence before insert
2. **DraftStep unique name**: `uq_draft_steps_name` -- only one draft per step name
3. **SQLite WAL mode**: Concurrent reads OK during write, but only one writer at a time
4. **ReadOnlySession has no close()**: The underlying `_session` must be closed directly (see deps.py L24)
5. **Pipeline flush vs commit**: Pipeline uses `flush()` during execution (within open transaction), `commit()` only in `save()`. StepIntegrator should commit once at end.
6. **No FK between DraftStep and GenerationRecord**: `run_id` field on DraftStep is a soft reference (description says "no FK")
7. **Session(engine) vs Session(bind=)**: Both work. `Session(engine)` is used in newer code (handlers, seed_prompts); `Session(bind=bind)` in older sync_prompts. Prefer `Session(engine)` for consistency.
