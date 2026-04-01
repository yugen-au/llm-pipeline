# llm-pipeline

Declarative LLM pipeline orchestration framework. Define pipelines as Python classes, execute via REST API, observe in a built-in web UI.

## Installation

```bash
uv add llm-pipeline        # or: pip install llm-pipeline
uv add llm-pipeline[ui]    # includes web UI (FastAPI + React)
```

## Quick Start

### 1. Create a convention directory

```
my-project/
  llm_pipelines/
    pipelines/my_pipeline.py
    steps/classify.py
    schemas/classify.py
    extractions/
    enums/
    constants/
  llm-pipeline-prompts/
    classify.yaml
```

Subfolders are auto-discovered on startup in dependency order:
`enums/` + `constants/` -> `schemas/` -> `extractions/` -> `steps/` -> `pipelines/`

### 2. Define a pipeline

```python
# llm_pipelines/pipelines/my_pipeline.py
from llm_pipeline import PipelineConfig, PipelineStrategy, PipelineStrategies
from llm_pipelines.steps.classify import ClassifyStep

class DefaultStrategy(PipelineStrategy):
    def can_handle(self, context):
        return True
    def get_steps(self):
        return [ClassifyStep.create_definition()]

class MyStrategies(PipelineStrategies, strategies=[DefaultStrategy]):
    pass

class MyPipeline(PipelineConfig, strategies=MyStrategies):
    pass
```

### 3. Start the server

```bash
uv run llm-pipeline ui --dev --model google-gla:gemini-2.0-flash-lite
```

### 4. Publish and trigger

```bash
# Publish pipeline (new pipelines default to draft)
curl -X PUT http://localhost:8642/api/pipelines/my/status \
  -H "Content-Type: application/json" \
  -d '{"status": "published"}'

# Trigger a run
curl -X POST http://localhost:8642/api/runs \
  -H "Content-Type: application/json" \
  -d '{"pipeline_name": "my", "input_data": {"text": "hello"}}'
```

## REST API

External applications interact via these endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/pipelines` | List pipelines (optional `?status=published` filter) |
| `GET` | `/api/pipelines/{name}/status` | Get pipeline visibility status |
| `PUT` | `/api/pipelines/{name}/status` | Set status: `draft` or `published` |
| `POST` | `/api/runs` | Trigger a pipeline run (published only) |
| `GET` | `/api/runs/{run_id}` | Get run status and results |

Full API docs available at `http://localhost:8642/docs` when the server is running.

## Pipeline Visibility

Pipelines have two statuses: **draft** and **published**.

- New pipelines default to `draft` (not callable via API)
- Only `published` pipelines accept `POST /api/runs`
- Both statuses are visible in the UI for building and testing
- Toggle via `PUT /api/pipelines/{name}/status`

## Web UI

The built-in UI at `http://localhost:8643` (dev) or `http://localhost:8642` (prod) provides:

- Pipeline introspection (strategies, steps, schemas)
- Per-step model configuration
- Prompt editor with Monaco (hover info, autocomplete for `{variables}`)
- Variable definitions with structured auto_generate selector
- Run history and real-time execution streaming

## CLI

```bash
uv run llm-pipeline ui [flags]

  --dev              Dev mode (hot reload, Vite frontend)
  --port PORT        Server port (default: 8642)
  --db PATH          SQLite database path
  --model MODEL      Default LLM model (pydantic-ai model string)
  --pipelines MODULE Python module to scan for PipelineConfig subclasses
  --prompts-dir DIR  Directory with prompt YAML files
```

## Prompts

YAML files in `llm-pipeline-prompts/` are bidirectionally synced with the DB:
- Startup: YAML -> DB (newer version wins)
- UI save: DB -> YAML (write-back for git portability)

```yaml
prompt_key: classify
prompt_name: Classify
category: my_pipeline
step_name: classify

system:
  content: |
    You are a classifier. Classify {input} into {categories}.
  version: "1.0"
  variable_definitions:
    input:
      type: str
      description: Text to classify
    categories:
      type: enum
      description: Valid categories
      auto_generate: enum_names(Category)
```

### auto_generate Expressions

Variables can auto-populate from registered Python objects:

| Expression | Output |
|---|---|
| `enum_names(X)` | Member names: `RED, GREEN, BLUE` |
| `enum_values(X)` | Member values: `red, green, blue` |
| `enum_value(X, Y)` | Single value: `red` |
| `constant(X)` | Literal value |

Register objects via `register_auto_generate("Name", obj)` or place in `llm_pipelines/enums/` for auto-registration.

## Registries

```python
from llm_pipeline import register_agent, register_auto_generate

register_agent("search", tools=[query_docs, search_web])
register_auto_generate("Category", Category)
```

## Event System

Observe pipeline execution with 31 event types:

```python
from llm_pipeline import InMemoryEventHandler, CompositeEmitter

handler = InMemoryEventHandler()
pipeline = MyPipeline(model="...", event_emitter=handler)
pipeline.execute(data="...")

for event in handler.get_events(pipeline.run_id):
    print(f"{event['event_type']}: {event['timestamp']}")
```

## Documentation

Full documentation: [docs/](docs/)
