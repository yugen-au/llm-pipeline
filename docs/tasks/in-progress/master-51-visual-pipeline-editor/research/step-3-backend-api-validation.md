# Step 3: Backend API & Validation Research

## Existing API Surface

All routes registered via `app.include_router()` in `llm_pipeline/ui/app.py` under `/api` prefix:

| Prefix | File | Purpose |
|--------|------|---------|
| `/api/runs` | `routes/runs.py` | Pipeline run CRUD + trigger |
| `/api/steps` | `routes/steps.py` | Step details within runs |
| `/api/events` | `routes/events.py` | Event stream for runs |
| `/api/prompts` | `routes/prompts.py` | Prompt CRUD |
| `/api/pipelines` | `routes/pipelines.py` | Pipeline introspection (list, detail, step prompts) |
| `/api/creator` | `routes/creator.py` | Step creator (generate, test, accept, drafts) |
| `/ws/runs` | `routes/websocket.py` | WebSocket (no /api prefix) |

### Pattern Observations

- All routes use plain Pydantic `BaseModel` for request/response (NOT SQLModel)
- `DBSession` dependency yields `ReadOnlySession` -- write operations use explicit `Session(engine)` blocks
- Background tasks via FastAPI `BackgroundTasks` for long-running operations (runs, creator)
- All route files define their own request/response models at module top

## Existing Pipeline Config Models

### PipelineConfig (pipeline.py)

Abstract base class. Key ClassVars:
- `REGISTRY: ClassVar[Type[PipelineDatabaseRegistry]]` -- DB models this pipeline manages
- `STRATEGIES: ClassVar[Type[PipelineStrategies]]` -- step arrangement
- `AGENT_REGISTRY: ClassVar[Optional[Type[AgentRegistry]]]` -- pydantic-ai agent config
- `INPUT_DATA: ClassVar[Optional[Type[PipelineInputData]]]` -- validated input schema

Pipeline structure is defined by **strategies** which each contain an ordered list of **step definitions**.

### StepDefinition (strategy.py)

Dataclass connecting step class to its configuration:
```python
@dataclass
class StepDefinition:
    step_class: Type           # LLMStep subclass
    system_instruction_key: str
    user_prompt_key: str
    instructions: Type         # Pydantic BaseModel for LLM output
    action_after: Optional[str] = None
    extractions: List[Type[PipelineExtraction]] = field(default_factory=list)
    transformation: Optional[Type[PipelineTransformation]] = None
    context: Optional[Type] = None
    agent_name: str | None = None
    not_found_indicators: list[str] | None = None
    consensus_strategy: ConsensusStrategy | None = None
```

### PipelineStrategy (strategy.py)

Abstract base with `can_handle(context)` and `get_steps() -> List[StepDefinition]`.

### PipelineStrategies (strategy.py)

Container class: `class MyStrategies(PipelineStrategies, strategies=[StratA, StratB])`.

### LLMStep (step.py)

Abstract base. Key attributes: `system_instruction_key`, `user_prompt_key`, `instructions`, `pipeline`.

### step_definition decorator (step.py)

Validates naming conventions at class-definition time:
- Step class must end with `Step`
- Instructions class must be `{StepPrefix}Instructions`
- Transformation class must be `{StepPrefix}Transformation`
- Context class must be `{StepPrefix}Context`

## Existing Validation Logic

### Class-level (import/definition time)

1. `PipelineConfig.__init_subclass__()` validates naming:
   - Class ends with `Pipeline`
   - Registry named `{Prefix}Registry`
   - Strategies named `{Prefix}Strategies`
   - AgentRegistry named `{Prefix}AgentRegistry`

2. `PipelineStrategy.__init_subclass__()` validates class ends with `Strategy`

3. `step_definition` decorator validates naming conventions for instructions, transformation, context classes

### Instance-level (PipelineConfig.__init__)

1. `_build_execution_order()` -- collects unique steps across all strategies, assigns positions
2. `_validate_foreign_key_dependencies()` -- checks registry model FK ordering
3. `_validate_registry_order()` -- checks extraction step order matches registry model order
4. REGISTRY and STRATEGIES must be non-None

### Runtime (during execute)

1. `_validate_step_access()` -- ensures steps only access data from previously executed steps
2. `_validate_and_merge_context()` -- validates context type from `process_instructions()`
3. Pydantic validation on LLM outputs via `instructions` type

### Key constraint: All validation requires live Python classes

Current validation operates on `Type` references (class objects). Draft pipelines in the visual editor are JSON structures -- **no Python classes exist yet**. The compile endpoint must implement a parallel validation path that works with JSON metadata rather than class references.

## Draft Models (Task 50 -- completed)

### DraftStep (state.py)

```python
class DraftStep(SQLModel, table=True):
    id: Optional[int]
    name: str              # unique
    description: Optional[str]
    generated_code: dict   # JSON: generated step code
    test_results: Optional[dict]
    validation_errors: Optional[dict]
    status: str            # draft, tested, accepted, error
    run_id: Optional[str]
    created_at: datetime
    updated_at: datetime
```

### DraftPipeline (state.py)

```python
class DraftPipeline(SQLModel, table=True):
    id: Optional[int]
    name: str                       # unique
    structure: dict                  # JSON: step order, strategy config
    compilation_errors: Optional[dict]  # JSON: validation errors
    status: str                     # draft, tested, accepted, error
    created_at: datetime
    updated_at: datetime
```

**Critical**: `DraftPipeline.structure` schema is not yet defined. The compile endpoint defines this shape.

**Critical**: `DraftPipeline.compilation_errors` already exists for storing per-step validation results.

## Existing Draft/Partial Validation

No existing endpoint supports draft/partial pipeline validation. The creator endpoints validate individual steps (sandbox import check), not pipeline composition.

## Proposed Compile Endpoint

### Route Organization

New route file: `llm_pipeline/ui/routes/editor.py` with prefix `/editor`.

Rationale: Creator handles step CREATION. Editor handles pipeline COMPOSITION. Different concerns warrant separate route files, consistent with existing separation (runs vs steps vs events vs pipelines vs creator).

Registration in `app.py`:
```python
from llm_pipeline.ui.routes.editor import router as editor_router
app.include_router(editor_router, prefix="/api")
```

### Input Schema

```python
class CompileStepRef(BaseModel):
    """Reference to a step in the visual arrangement."""
    step_ref: str                          # DraftStep.name or registered step_name
    source: Literal["draft", "registered"] # provenance
    position: int                          # 0-indexed within strategy

class CompileStrategyDef(BaseModel):
    """Strategy definition in the visual arrangement."""
    strategy_name: str
    steps: list[CompileStepRef]

class CompileRequest(BaseModel):
    """Visual pipeline arrangement to validate."""
    pipeline_name: str
    strategies: list[CompileStrategyDef]
    save_draft: bool = False  # persist to DraftPipeline table
    draft_pipeline_id: int | None = None  # update existing draft (if save_draft=True)
```

### Output Schema

```python
class StepError(BaseModel):
    """Single validation error/warning tied to a step or pipeline-level."""
    step_ref: str | None = None       # None for pipeline-level errors
    strategy_name: str | None = None
    field: str | None = None          # specific field (e.g. "system_instruction_key")
    message: str
    severity: Literal["error", "warning"]

class CompileResponse(BaseModel):
    """Compile-to-validate result."""
    valid: bool
    errors: list[StepError]
    warnings: list[StepError]
    draft_pipeline_id: int | None = None  # set if save_draft=True
```

### Endpoint Signature

```python
@router.post("/compile", response_model=CompileResponse)
def compile_pipeline(
    body: CompileRequest,
    request: Request,
    db: DBSession,  # read-only for lookups
) -> CompileResponse:
```

Not a background task -- validation is synchronous and fast (no LLM calls).

### Validation Rules (Structural)

| # | Rule | Severity | Scope |
|---|------|----------|-------|
| 1 | `pipeline_name` non-empty and valid identifier | error | pipeline |
| 2 | At least one strategy | error | pipeline |
| 3 | Each strategy has at least one step | error | strategy |
| 4 | No duplicate step_ref within a strategy | error | strategy |
| 5 | Draft step references resolve (DraftStep.name exists in DB) | error | step |
| 6 | Registered step references resolve (step_name in introspection_registry) | error | step |
| 7 | Draft steps have non-empty generated_code | warning | step |
| 8 | Draft steps in "error" status | warning | step |
| 9 | `pipeline_name` doesn't conflict with existing registered pipeline | warning | pipeline |
| 10 | Positions are sequential (0, 1, 2...) within strategy | error | strategy |

### Validation Rules (Deep -- future phase)

These require resolving step metadata and are recommended for a follow-up:
- Prompt key existence in DB
- Extraction FK ordering across steps
- Schema compatibility between step outputs and next step inputs
- Instructions class field validation

### DraftPipeline.structure Schema

Proposed shape (stored as JSON in the `structure` column):

```json
{
  "strategies": [
    {
      "strategy_name": "default",
      "steps": [
        {
          "step_ref": "data_validation",
          "source": "registered",
          "position": 0
        },
        {
          "step_ref": "my_custom_step",
          "source": "draft",
          "position": 1
        }
      ]
    }
  ]
}
```

This matches the `CompileRequest.strategies` shape exactly, enabling round-tripping between frontend state and DB persistence.

### Additional CRUD Endpoints (editor.py)

The compile endpoint alone is insufficient for a full visual editor. Recommended endpoints for the editor route file:

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/editor/compile` | Validate step arrangement |
| `GET` | `/editor/available-steps` | List all steps available for editor (both draft + registered) |
| `POST` | `/editor/drafts` | Create new DraftPipeline |
| `GET` | `/editor/drafts` | List DraftPipelines |
| `GET` | `/editor/drafts/{id}` | Get DraftPipeline detail |
| `PATCH` | `/editor/drafts/{id}` | Update DraftPipeline structure/name |
| `DELETE` | `/editor/drafts/{id}` | Delete DraftPipeline |

The `available-steps` endpoint merges:
1. All DraftStep rows (filtered by status != "error")
2. All registered steps from introspection_registry (deduplicated across strategies)

Each returns enough metadata for the frontend step picker (name, description, source, prompt keys, has_extraction, has_transformation).

### Frontend Integration

New query key namespace in `query-keys.ts`:
```typescript
editor: {
    all: ['editor'] as const,
    compile: () => ['editor', 'compile'] as const,
    availableSteps: () => ['editor', 'available-steps'] as const,
    drafts: () => ['editor', 'drafts'] as const,
    draft: (id: number) => ['editor', 'drafts', id] as const,
}
```

New hook: `useCompilePipeline()` as a mutation (POST, not cached).

TypeScript types mirror backend Pydantic models:
```typescript
interface CompileStepRef {
    step_ref: string
    source: 'draft' | 'registered'
    position: number
}

interface CompileStrategyDef {
    strategy_name: string
    steps: CompileStepRef[]
}

interface CompileRequest {
    pipeline_name: string
    strategies: CompileStrategyDef[]
    save_draft: boolean
    draft_pipeline_id: number | null
}

interface StepError {
    step_ref: string | null
    strategy_name: string | null
    field: string | null
    message: string
    severity: 'error' | 'warning'
}

interface CompileResponse {
    valid: boolean
    errors: StepError[]
    warnings: StepError[]
    draft_pipeline_id: number | null
}
```

## Dependencies and Constraints

1. **DBSession (ReadOnlySession)** for step/pipeline lookups -- write operations (save_draft) need explicit `Session(engine)` like creator.py does
2. **introspection_registry** on `request.app.state` for registered step resolution
3. **DraftStep table** must exist (task 50 done)
4. **DraftPipeline table** must exist (task 50 done)
5. `updated_at` must be explicitly set on UPDATE (no DB trigger, per task 50 summary recommendation)

## Risk: Registered Step Resolution

Registered steps are discovered via `introspection_registry` which maps pipeline names to `PipelineConfig` subclasses. To resolve a step by name, the compile endpoint must:

1. Iterate all pipelines in introspection_registry
2. Introspect each to get step metadata
3. Build a lookup map: `step_name -> StepMetadata`

This is safe (PipelineIntrospector caches per class) but could be slow on first call with many pipelines. Should be cached at app startup or lazily cached.

## Summary

- New route file `routes/editor.py` with `/api/editor` prefix
- POST `/api/editor/compile` validates visual step arrangement against structural rules
- Input: pipeline name + strategies with ordered step references
- Output: valid flag + per-step errors/warnings
- DraftPipeline.structure stores the same shape as CompileRequest.strategies
- DraftPipeline.compilation_errors stores CompileResponse errors
- Structural validation first; deep validation (prompts, schemas, FK ordering) in follow-up
- Additional CRUD endpoints for DraftPipeline management
- Available-steps endpoint merges draft + registered steps for the step picker
