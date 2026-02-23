# Step 3: Introspection API Patterns Research

## 1. Industry Patterns for Pipeline/Workflow Metadata APIs

### Airflow REST API (v1)
- `GET /api/v1/dags` - list with offset/limit pagination, typed DAG summary (dag_id, description, is_paused, tags, schedule_interval)
- `GET /api/v1/dags/{dag_id}` - full detail with task count, owners, file locations, serialized parameters
- `GET /api/v1/dags/{dag_id}/tasks` - separate endpoint for task-level detail
- Key pattern: list returns lightweight summary, detail returns full metadata; 404 on missing dag_id

### Prefect REST API (v2)
- `POST /api/deployments/filter` - list with filter body (name, tags, flow_id), paginated
- `GET /api/deployments/{id}` - full deployment detail
- `GET /api/flows` - flow metadata list (name, created, tags)
- `GET /api/flows/{id}` - flow detail
- Key pattern: separates "flow definition" (metadata) from "deployment" (runnable instance) -- analogous to our introspection_registry vs pipeline_registry

### Dagster (GraphQL-based)
- `query { pipelinesOrError { ... on PipelineConnection { nodes { name, modes, solidSelection } } } }`
- Exposes pipeline metadata via GraphQL with rich nesting (solids, inputs, outputs, configs)
- Key pattern: deeply nested schema for introspection data, similar to our PipelineIntrospector output

### Common patterns across all three:
1. **List returns summary** (name, counts, status flags) -- NOT full metadata
2. **Detail returns rich nested data** (steps/tasks/solids with their configs)
3. **404 for not-found** on detail endpoints
4. **No DB required for metadata** -- pipeline structure is derived from code definitions, not runtime state
5. **Caching** -- pipeline metadata is immutable once defined; cache aggressively

## 2. Registry Pattern Analysis

### Current state in codebase
`create_app()` already accepts and stores two separate registries on `app.state`:
- `pipeline_registry: Dict[str, Callable]` -- factory callables for triggering runs (used by POST /api/runs)
- `introspection_registry: Dict[str, Type[PipelineConfig]]` -- class types for metadata extraction (used by task 24 endpoints)

This separation is correct: execution factories need runtime dependencies (engine, event_emitter) while introspection only needs the class type.

### Access pattern
Existing routes access state via `request.app.state`:
```python
# From runs.py trigger_run
registry: dict = getattr(request.app.state, "pipeline_registry", {})
```

Pipeline endpoints should follow the same pattern:
```python
registry: dict = getattr(request.app.state, "introspection_registry", {})
```

### Why NOT module-level global
- Testability: tests can create isolated apps with different registries (already proven in test_runs.py)
- Multiple instances: library consumers may create multiple FastAPI apps
- Consistent with existing codebase pattern

### Registration
Consumer registers pipelines at app creation:
```python
app = create_app(
    introspection_registry={
        "ShippingRatePipeline": ShippingRatePipeline,
        "InvoicePipeline": InvoicePipeline,
    }
)
```
No separate `register_pipeline()` function needed -- the dict is passed to create_app(). The task 24 spec suggests a `register_pipeline()` helper, but this is unnecessary given the existing create_app() parameter. If needed later, a convenience function can be added.

## 3. List Endpoint Design

### `GET /api/pipelines`

**No pagination needed.** Key reasoning:
- Pipeline count is bounded by registered PipelineConfig subclasses (typically 1-10, max ~50)
- Unlike runs/prompts which are DB-backed and can have thousands of rows
- All industry frameworks return full lists for pipeline/flow definitions
- Downstream consumer (task 40 frontend) renders all pipelines in a sidebar

**Summary metadata per item:**
Based on PipelineIntrospector.get_metadata() output and task 40 frontend needs:
- `name: str` -- pipeline_name from introspector
- `strategy_count: int` -- len(metadata["strategies"])
- `step_count: int` -- len(metadata["execution_order"]) (deduplicated unique steps)
- `registry_model_count: int` -- len(metadata["registry_models"])

**Sorting:** Alphabetical by name (deterministic, no sort params needed).

**Response shape:**
```python
class PipelineListItem(BaseModel):
    name: str
    strategy_count: int
    step_count: int
    registry_model_count: int

class PipelineListResponse(BaseModel):
    items: List[PipelineListItem]
    total: int
```

Note: `total` included for consistency with runs/prompts responses even though no pagination. Allows frontend to display count without computing len(items).

### Error handling
- Empty registry: return `{"items": [], "total": 0}` (not an error)
- Introspection failure during list: use try/except per pipeline, include error pipelines with count=0 or skip them (recommend: include with zero counts + an error flag)

## 4. Detail Endpoint Design

### `GET /api/pipelines/{pipeline_name}`

Returns full PipelineIntrospector.get_metadata() output.

**Response model approach -- two options:**

#### Option A: Strictly typed nested Pydantic models
```python
class ExtractionInfo(BaseModel):
    class_name: str
    model_class: Optional[str]
    methods: List[str]

class TransformationInfo(BaseModel):
    class_name: str
    input_type: Optional[str]
    input_schema: Optional[Dict[str, Any]]
    output_type: Optional[str]
    output_schema: Optional[Dict[str, Any]]

class StepInfo(BaseModel):
    step_name: str
    class_name: str
    system_key: str
    user_key: str
    instructions_class: Optional[str]
    instructions_schema: Optional[Dict[str, Any]]
    context_class: Optional[str]
    context_schema: Optional[Dict[str, Any]]
    extractions: List[ExtractionInfo]
    transformation: Optional[TransformationInfo]
    action_after: Optional[str]

class StrategyInfo(BaseModel):
    name: str
    display_name: str
    class_name: str
    steps: List[StepInfo]
    error: Optional[str] = None

class PipelineDetailResponse(BaseModel):
    pipeline_name: str
    registry_models: List[str]
    strategies: List[StrategyInfo]
    execution_order: List[str]
```

Pros: OpenAPI docs show full schema, frontend can generate types, validation catches introspector regressions.
Cons: 6+ model definitions, maintenance burden, must stay in sync with introspector output.

#### Option B: Thin wrapper with Dict body
```python
class PipelineDetailResponse(BaseModel):
    pipeline_name: str
    metadata: Dict[str, Any]
```

Pros: Zero maintenance, always matches introspector output.
Cons: No OpenAPI detail, no frontend type generation, no validation.

**Recommendation:** Option A (strict typing). Reasons:
1. Codebase convention: all other endpoints use strict Pydantic models
2. The introspector output shape is stable (tested in test_introspection.py)
3. Frontend (task 40) accesses individual fields -- type safety helps
4. OpenAPI docs become useful for frontend developers

### Error handling
- **404**: pipeline_name not in introspection_registry
  ```python
  if pipeline_name not in registry:
      raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_name}' not found")
  ```
- **500 (introspection failure)**: Wrap get_metadata() in try/except for unexpected errors
  ```python
  try:
      metadata = PipelineIntrospector(pipeline_cls).get_metadata()
  except Exception as exc:
      raise HTTPException(status_code=500, detail=f"Introspection failed: {exc}")
  ```
  Note: PipelineIntrospector already handles broken strategies defensively (returns error key in strategy dict, no exception). The 500 catch is a safety net for truly unexpected failures.

## 5. Implementation Patterns (Codebase Alignment)

### Sync def (not async)
All existing route endpoints use `def` not `async def`:
```python
# runs.py, prompts.py, events.py, steps.py -- all sync
@router.get("", response_model=RunListResponse)
def list_runs(...):
```
Pipeline endpoints have no async operations (no DB, no I/O). Sync def is correct.

### No DBSession dependency
Unlike runs/prompts/events/steps which inject `db: DBSession`, pipeline endpoints access `request.app.state.introspection_registry` directly via `request: Request`. No database involved.

### Response models: plain Pydantic BaseModel
All existing response models inherit from `pydantic.BaseModel`, NOT SQLModel. Pipeline response models follow the same pattern.

### Router structure
```python
router = APIRouter(prefix="/pipelines", tags=["pipelines"])
```
Already exists in pipelines.py. Mounted at `/api` prefix in create_app().

### Full endpoint URLs
- `GET /api/pipelines` -- list
- `GET /api/pipelines/{pipeline_name}` -- detail

## 6. Test Conftest Consideration

The existing `tests/ui/conftest.py` `_make_app()` does NOT set `introspection_registry` on `app.state`. Tests for pipeline endpoints will need either:
1. A new fixture that creates an app with introspection_registry populated with test PipelineConfig subclasses
2. Reuse the test pipeline classes from test_introspection.py (WidgetPipeline, ScanPipeline, etc.)

Approach 2 is preferred -- those classes are already well-tested and cover edge cases (broken strategies, transformations, etc.).

## 7. Summary of Recommendations

| Aspect | Recommendation | Rationale |
|--------|---------------|-----------|
| Registry | app.state.introspection_registry (already configured) | Testable, consistent, no changes needed |
| List pagination | None | Bounded dataset (<50 items), not DB-backed |
| List response | PipelineListItem with counts + PipelineListResponse | Matches frontend needs (task 40) |
| Detail response | Strictly typed nested Pydantic models | Codebase convention, OpenAPI docs, type safety |
| Error: not-found | HTTPException(404) | Standard REST, matches existing pattern |
| Error: introspection | try/except -> HTTPException(500) safety net | Introspector is already defensive |
| Endpoint style | sync def, no DBSession, Request param | No DB/async needed, consistent with codebase |
| Empty registry | Return empty list (not error) | Valid state, UI handles gracefully |
