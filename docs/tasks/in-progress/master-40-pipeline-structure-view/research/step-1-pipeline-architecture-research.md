# Pipeline Architecture Research - Task 40

## Executive Summary

All backend introspection APIs and frontend hooks are fully implemented (tasks 24, 31 done). The frontend route `pipelines.tsx` exists as an empty placeholder. Task 40 needs to build the React component that consumes existing hooks/APIs to display pipeline structure. The TS types marked `@provisional` need updating to match backend response shapes.

---

## 1. Backend Introspection Layer

### 1.1 PipelineIntrospector (`llm_pipeline/introspection.py`)

Pure class-level introspection. No DB, LLM, or FastAPI dependencies. Results cached by pipeline class identity (`id(cls)`).

**`get_metadata()` return shape:**

```python
{
    "pipeline_name": str,           # snake_case from class name
    "registry_models": List[str],   # model class names from REGISTRY.MODELS
    "strategies": [
        {
            "name": str,            # snake_case from class name
            "display_name": str,    # title case from class name
            "class_name": str,      # raw class name
            "steps": [
                {
                    "step_name": str,
                    "class_name": str,
                    "system_key": Optional[str],
                    "user_key": Optional[str],
                    "instructions_class": Optional[str],
                    "instructions_schema": Optional[dict],  # JSON Schema from model_json_schema()
                    "context_class": Optional[str],
                    "context_schema": Optional[dict],       # JSON Schema or {"type": name}
                    "extractions": [
                        {
                            "class_name": str,
                            "model_class": Optional[str],
                            "methods": List[str],  # custom methods via dir() comparison
                        }
                    ],
                    "transformation": Optional[{
                        "class_name": str,
                        "input_type": Optional[str],
                        "input_schema": Optional[dict],
                        "output_type": Optional[str],
                        "output_schema": Optional[dict],
                    }],
                    "action_after": Optional[str],
                }
            ],
            "error": Optional[str],  # present only if strategy init/get_steps failed
        }
    ],
    "execution_order": List[str],       # deduplicated step names, first occurrence wins
    "pipeline_input_schema": Optional[dict],  # JSON Schema from INPUT_DATA ClassVar
}
```

### 1.2 REST Endpoints (`llm_pipeline/ui/routes/pipelines.py`)

| Endpoint | Method | Response Model | Notes |
|----------|--------|---------------|-------|
| `/api/pipelines` | GET | `PipelineListResponse` | Lists all from `app.state.introspection_registry`, sorted alphabetically. Per-pipeline error isolation. |
| `/api/pipelines/{name}` | GET | `PipelineMetadata` | Full `PipelineIntrospector.get_metadata()`. 404 if not registered, 500 if introspection raises. |
| `/api/pipelines/{name}/steps/{step_name}/prompts` | GET | `StepPromptsResponse` | Returns prompt content. Scoped to declared keys to prevent cross-pipeline leakage. Requires DB session. |

**Pydantic response models in pipelines.py:**

```python
class PipelineListItem(BaseModel):
    name: str
    strategy_count: Optional[int] = None
    step_count: Optional[int] = None
    has_input_schema: bool = False
    registry_model_count: Optional[int] = None
    error: Optional[str] = None

class PipelineListResponse(BaseModel):
    pipelines: List[PipelineListItem]

class StepMetadata(BaseModel):
    step_name: str
    class_name: str
    system_key: Optional[str] = None
    user_key: Optional[str] = None
    instructions_class: Optional[str] = None
    instructions_schema: Optional[Any] = None
    context_class: Optional[str] = None
    context_schema: Optional[Any] = None
    extractions: List[Any] = []
    transformation: Optional[Any] = None
    action_after: Optional[str] = None

class StrategyMetadata(BaseModel):
    name: str
    display_name: str
    class_name: str
    steps: List[StepMetadata] = []
    error: Optional[str] = None

class PipelineMetadata(BaseModel):
    pipeline_name: str
    registry_models: List[str] = []
    strategies: List[StrategyMetadata] = []
    execution_order: List[str] = []
    pipeline_input_schema: Optional[Any] = None

class StepPromptItem(BaseModel):
    prompt_key: str
    prompt_type: str
    content: str
    required_variables: Optional[List[str]] = None
    version: str

class StepPromptsResponse(BaseModel):
    pipeline_name: str
    step_name: str
    prompts: List[StepPromptItem]
```

### 1.3 App Wiring (`llm_pipeline/ui/app.py`)

- `create_app(introspection_registry=...)` accepts `Dict[str, Type[PipelineConfig]]`
- Stored on `app.state.introspection_registry`
- Separate from `pipeline_registry` (factory callables for POST /api/runs)
- Pipelines router mounted at `/api/pipelines`

---

## 2. Frontend API Layer

### 2.1 TanStack Query Hooks (`src/api/pipelines.ts`)

| Hook | Query Key | Endpoint | Enabled Guard |
|------|-----------|----------|---------------|
| `usePipelines()` | `['pipelines']` | `GET /api/pipelines` | always |
| `usePipeline(name)` | `['pipelines', name]` | `GET /api/pipelines/{name}` | `Boolean(name)` |
| `useStepInstructions(pipelineName, stepName)` | `['pipelines', name, 'steps', stepName, 'prompts']` | `GET /api/pipelines/{name}/steps/{step_name}/prompts` | `Boolean(pipelineName && stepName)`, `staleTime: Infinity` |

### 2.2 Query Key Factory (`src/api/query-keys.ts`)

```typescript
pipelines: {
    all: ['pipelines'] as const,
    detail: (name: string) => ['pipelines', name] as const,
    stepPrompts: (name: string, stepName: string) =>
      ['pipelines', name, 'steps', stepName, 'prompts'] as const,
}
```

### 2.3 TypeScript Types (`src/api/types.ts`)

**Current types (marked @provisional):**

| TS Interface | Backend Model | Mismatches |
|-------------|---------------|------------|
| `PipelineListItem` | `PipelineListItem` | **Missing**: `registry_model_count`, `error`; `strategy_count`/`step_count` typed as `number` but backend returns `Optional[int]` |
| `PipelineMetadata` | `PipelineMetadata` | Matches |
| `PipelineStrategyMetadata` | `StrategyMetadata` | **Missing**: `error` field |
| `PipelineStepMetadata` | `StepMetadata` | `system_key`/`user_key` typed as `string` but backend returns `Optional[str]` |
| `ExtractionMetadata` | (inline dict) | Matches |
| `TransformationMetadata` | (inline dict) | Matches |
| `StepPromptItem` | `StepPromptItem` | Matches |
| `StepPromptsResponse` | `StepPromptsResponse` | Matches |

**Required TS type fixes for task 40:**

```typescript
// PipelineListItem - add missing fields, fix nullability
export interface PipelineListItem {
  name: string
  strategy_count: number | null      // was: number
  step_count: number | null           // was: number
  has_input_schema: boolean
  registry_model_count: number | null // NEW
  error: string | null                // NEW
}

// PipelineStrategyMetadata - add error field
export interface PipelineStrategyMetadata {
  name: string
  display_name: string
  class_name: string
  steps: PipelineStepMetadata[]
  error: string | null                // NEW
}

// PipelineStepMetadata - fix nullability
export interface PipelineStepMetadata {
  step_name: string
  class_name: string
  system_key: string | null           // was: string
  user_key: string | null             // was: string
  instructions_class: string | null
  instructions_schema: Record<string, unknown> | null
  context_class: string | null
  context_schema: Record<string, unknown> | null
  extractions: ExtractionMetadata[]
  transformation: TransformationMetadata | null
  action_after: string | null
}
```

---

## 3. Core Pipeline Classes (Data Model Reference)

### 3.1 PipelineConfig (`llm_pipeline/pipeline.py`)

- Abstract base class for pipeline orchestration
- `REGISTRY: ClassVar[Type[PipelineDatabaseRegistry]]` - DB models
- `STRATEGIES: ClassVar[Type[PipelineStrategies]]` - strategy container
- `INPUT_DATA: ClassVar[Optional[Type[PipelineInputData]]]` - input schema
- Naming: class must end with `Pipeline`, auto-derives `pipeline_name` via snake_case
- Naming enforcement: registry must be `{Prefix}Registry`, strategies must be `{Prefix}Strategies`

### 3.2 LLMStep (`llm_pipeline/step.py`)

- Abstract base class for pipeline steps
- Properties: `system_instruction_key`, `user_prompt_key`, `instructions` (Pydantic class), `pipeline` ref
- `step_name`: auto-derived snake_case from class name minus `Step` suffix
- Methods: `prepare_calls()`, `process_instructions()`, `should_skip()`, `log_instructions()`, `extract_data()`
- Class-level attrs set by `@step_definition`: `INSTRUCTIONS`, `DEFAULT_SYSTEM_KEY`, `DEFAULT_USER_KEY`, `DEFAULT_EXTRACTIONS`, `DEFAULT_TRANSFORMATION`, `CONTEXT`

### 3.3 step_definition Decorator (`llm_pipeline/step.py`)

- Stores config on step class and provides `create_definition()` classmethod
- Args: `instructions`, `default_system_key`, `default_user_key`, `default_extractions`, `default_transformation`, `context`
- Naming enforcement: instructions must be `{StepPrefix}Instructions`, transformation must be `{StepPrefix}Transformation`, context must be `{StepPrefix}Context`
- `create_definition()` returns a `StepDefinition` dataclass

### 3.4 StepDefinition (`llm_pipeline/strategy.py`)

Dataclass connecting step class with its configuration:
- `step_class`, `system_instruction_key`, `user_prompt_key`, `instructions`
- `extractions: List[Type[PipelineExtraction]]`
- `transformation: Optional[Type[PipelineTransformation]]`
- `context: Optional[Type]`
- `action_after: Optional[str]`
- `create_step(pipeline)` - instantiates step with auto-discovered prompt keys

### 3.5 PipelineStrategy / PipelineStrategies (`llm_pipeline/strategy.py`)

- `PipelineStrategy`: ABC with `can_handle(context) -> bool` and `get_steps() -> List[StepDefinition]`
- Auto-generates `NAME` (snake_case) and `DISPLAY_NAME` (title case) from class name
- `PipelineStrategies`: container class, `STRATEGIES: ClassVar[List[Type[PipelineStrategy]]]`
- `create_instances()` and `get_strategy_names()` classmethods

### 3.6 PipelineContext / PipelineInputData (`llm_pipeline/context.py`)

- Both are Pydantic `BaseModel` subclasses
- `PipelineContext`: base for step context contributions (merged into `pipeline._context`)
- `PipelineInputData`: base for structured pipeline input (validated via `INPUT_DATA`)

### 3.7 PipelineExtraction (`llm_pipeline/extraction.py`)

- ABC with `MODEL: ClassVar[Type[SQLModel]]`
- Smart method dispatch: `default` > strategy-specific > single custom > error
- Naming: must end with `Extraction`
- Validates MODEL is in pipeline's registry

### 3.8 PipelineTransformation (`llm_pipeline/transformation.py`)

- ABC with `INPUT_TYPE`, `OUTPUT_TYPE` ClassVars
- Smart method dispatch similar to extraction
- Input/output type validation

### 3.9 PipelineDatabaseRegistry (`llm_pipeline/registry.py`)

- `MODELS: ClassVar[List[Type[SQLModel]]]` - ordered by FK dependencies
- `get_models()` classmethod

### 3.10 State Models (`llm_pipeline/state.py`)

- `PipelineStepState` - audit trail per step execution (input_hash, result_data, context_snapshot, prompt keys, timing)
- `PipelineRunInstance` - links created DB instances to pipeline runs
- `PipelineRun` - run lifecycle (status: running/completed/failed, timing)

### 3.11 Prompt Model (`llm_pipeline/db/prompt.py`)

- `Prompt(SQLModel, table=True)` - prompt templates stored in DB
- Fields: prompt_key, prompt_name, prompt_type (system/user), category, step_name, content, required_variables, version, is_active

### 3.12 LLMProvider (`llm_pipeline/llm/provider.py`)

- ABC with `call_structured()` method
- Implementation: `GeminiProvider` in `llm_pipeline/llm/gemini.py`
- Not relevant to introspection (introspection is class-level, no LLM calls)

---

## 4. Existing Frontend State

### 4.1 Current Route (`src/routes/pipelines.tsx`)

Empty placeholder:
```tsx
function PipelinesPage() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold text-card-foreground">Pipelines</h1>
      <p className="mt-2 text-muted-foreground">Pipeline configuration</p>
    </div>
  )
}
```

### 4.2 Root Layout (`src/routes/__root.tsx`)

- Sidebar (60px, placeholder for task 41) + main content area
- TanStack Router with file-based routing
- Dark theme with `bg-background text-foreground`

### 4.3 Other Routes (for navigation context)

- `/` - index (runs list, task 33)
- `/pipelines` - pipeline structure (THIS TASK)
- `/prompts` - prompt browser
- `/live` - live execution view
- `/runs/$runId` - run detail

---

## 5. Data Flow Summary

```
PipelineConfig subclass (class-level)
  -> PipelineIntrospector.get_metadata() [cached, no side effects]
    -> GET /api/pipelines/{name} [FastAPI, reads app.state.introspection_registry]
      -> usePipeline(name) [TanStack Query hook]
        -> PipelinesPage component [NEEDS BUILDING - task 40]

Prompt content:
  -> GET /api/pipelines/{name}/steps/{step_name}/prompts [requires DB session]
    -> useStepInstructions(pipelineName, stepName) [TanStack Query, staleTime: Infinity]
```

---

## 6. Key Observations for Implementation

1. **All backend APIs exist and are tested** (20 tests in `tests/ui/test_pipelines.py`).
2. **All frontend hooks exist** with correct query keys and enabled guards.
3. **TS types need updating** - 4 fields missing, 4 nullability mismatches (documented in Section 2.3).
4. **Pipeline data is static** - `staleTime: Infinity` on prompt content is correct; pipeline structure itself changes only on server restart.
5. **instructions_schema is full JSON Schema** - `model_json_schema()` output from Pydantic, includes `properties`, `type`, `required`, `$defs` etc.
6. **Error handling exists** - broken strategies have `error` field, list endpoint isolates per-pipeline errors, detail endpoint returns 404/500.
7. **Cross-pipeline prompt leakage prevented** - step prompts endpoint only returns keys declared in the specific pipeline's introspection metadata.
8. **No existing introspection gaps** - all metadata from class-level attributes is surfaced. No hidden data that could be exposed but isn't.

---

## 7. Out of Scope

- Task 51 (Visual Pipeline Editor) - depends on tasks 40 + 50, uses drag-and-drop, compile-to-validate
- Any backend changes to introspection APIs
- Any new backend endpoints
- Sidebar navigation (task 41)
