# Pipeline Discovery & Demo Pipeline

## Problem

The CLI (`llm-pipeline ui`) starts the FastAPI app with empty `pipeline_registry` and `introspection_registry`. No mechanism exists to discover or register pipelines -- consumers must call `create_app()` programmatically. This makes the UI useless out of the box and prevents quick testing.

## Goals

1. Auto-discovery of pipelines via Python entry points (`llm_pipeline.pipelines` group)
2. CLI override to manually specify pipeline modules
3. Ship a built-in demo pipeline for testing the frontend

## Feature 1: Entry Point Auto-Discovery

Pipelines register via `pyproject.toml` entry points:

```toml
[project.entry-points."llm_pipeline.pipelines"]
my_pipeline = "myapp.pipelines:TextAnalyzerPipeline"
```

On startup, `create_app()` scans `importlib.metadata.entry_points(group="llm_pipeline.pipelines")`, loads each entry point, and registers it in both `pipeline_registry` (factory) and `introspection_registry` (class).

### Pipeline contract

Each entry point must resolve to a `PipelineConfig` subclass. The discovery system:
1. Loads the class
2. Registers it in `introspection_registry` under the entry point name
3. Creates a factory closure for `pipeline_registry` that instantiates the class with `(run_id, engine, event_emitter, model)` kwargs
4. Seeds any required prompts via an optional `seed_prompts(engine)` classmethod on the pipeline class (no-op if prompts already exist)

### Discovery order

1. Scan entry points (auto)
2. Apply CLI overrides (manual)
3. Log discovered pipelines at startup

## Feature 2: CLI Override

```bash
# Auto-discover only
llm-pipeline ui

# Auto-discover + additional module
llm-pipeline ui --pipelines myapp.pipelines

# The --pipelines flag imports the module and looks for:
#   PIPELINE_REGISTRY: dict[str, Type[PipelineConfig]]
# Each class is registered the same way as entry points.
```

The `--pipelines` flag accepts a dotted Python module path. The module must export a `PIPELINE_REGISTRY` dict mapping names to `PipelineConfig` subclasses. Multiple `--pipelines` flags allowed.

## Feature 3: Built-in Demo Pipeline

Ship `llm_pipeline/demo/` as a built-in sample pipeline that registers via entry point in llm-pipeline's own `pyproject.toml`:

```toml
[project.entry-points."llm_pipeline.pipelines"]
text_analyzer = "llm_pipeline.demo:TextAnalyzerPipeline"
```

### Demo pipeline: TextAnalyzer

A 3-step pipeline that analyzes input text:

1. **SentimentAnalysisStep** -- classify sentiment (positive/negative/neutral) + confidence score
2. **TopicExtractionStep** -- extract topics/themes using sentiment as context, persist Topic records to DB
3. **SummaryStep** -- generate summary incorporating sentiment + topics

This demonstrates:
- Multi-step context passing (sentiment -> topics -> summary)
- DB extraction (Topic model)
- PipelineInputData schema (structured input for UI form)
- Live event streaming via WebSocket
- Agent-based LLM calls via pydantic-ai

### Demo structure

```
llm_pipeline/demo/
    __init__.py          # exports TextAnalyzerPipeline
    pipeline.py          # models, instructions, steps, strategy, registries, pipeline class
    prompts.py           # seed_prompts() function + prompt content constants
```

### Prompt seeding

The demo pipeline implements `seed_prompts(engine)` classmethod that inserts required Prompt rows if they don't exist (idempotent). Prompts use `{text}`, `{sentiment}`, `{primary_topic}` template variables matching `prepare_calls()` output.

### Default model

`google-gla:gemini-2.0-flash-lite` -- configurable via `--model` CLI flag or `LLM_PIPELINE_MODEL` env var.

## Technical notes

- `create_app()` gains an optional `auto_discover: bool = True` parameter
- Discovery happens inside `create_app()`, before route registration
- Entry point loading errors are logged as warnings, not fatal
- CLI `--model` flag sets default model for all discovered pipelines
- Demo pipeline's `Topic` table uses `__tablename__ = "demo_topics"` to avoid collisions
- Demo prompts are seeded on app startup (idempotent check via prompt_key+prompt_type unique constraint)

## Files to modify

- `llm_pipeline/ui/app.py` -- add discovery logic to `create_app()`
- `llm_pipeline/ui/cli.py` -- add `--pipelines` and `--model` flags
- `llm_pipeline/demo/__init__.py` -- new: exports pipeline class
- `llm_pipeline/demo/pipeline.py` -- new: full demo pipeline definition
- `llm_pipeline/demo/prompts.py` -- new: prompt seeding
- `pyproject.toml` -- add demo entry point
