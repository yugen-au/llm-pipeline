# llm-pipeline

## Overview
Declarative LLM pipeline orchestration framework. Extracted from logistics-intelligence as standalone reusable library.

## Tech Stack
- Python 3.11+
- Pydantic v2
- SQLModel / SQLAlchemy 2.0
- PyYAML
- Hatchling (build)

## Architecture
Pipeline + Strategy + Step pattern:
- `PipelineConfig` - declarative pipeline configuration
- `LLMStep` / `step_definition` - individual pipeline steps with LLM calls
- `PipelineStrategy` / `PipelineStrategies` - execution strategies
- `PipelineContext` - runtime context passing between steps
- `PipelineExtraction` / `PipelineTransformation` - data extraction and transformation
- `PipelineDatabaseRegistry` - DB-backed registry for pipeline state
- `PipelineStepState` / `PipelineRunInstance` - execution state tracking
- pydantic-ai Agent system via global `register_agent()` and agent_builders.py
- `ReadOnlySession` - safe DB session wrapper

## Running the UI
- Dev mode (backend + frontend hot reload): `uv run llm-pipeline ui --dev`
- Prod mode (serves built frontend): `uv run llm-pipeline ui`
- Default port: 8642 (backend), 8643 (Vite dev)
- SQLite auto-creates, no DB setup needed
- Custom DB: `uv run llm-pipeline ui --dev --db path/to/db.sqlite`
- Load custom pipelines: `uv run llm-pipeline ui --dev --pipelines my_project.pipelines`

## MCP Servers

### Base (always included)
- Purpose: Core shared tools (fetch, context7, serena, graphiti, taskmaster, sequential-thinking)
- Configured in: Global `~/.claude.json`

## Testing
- Command: `pytest`
- Runner: pytest

## Development Notes
- Build with `hatchling`
- Test deps and pydantic-ai in `[project.optional-dependencies].dev`; pydantic-ai also in core deps
- Pytest configured in `[tool.pytest.ini_options]` in pyproject.toml

## Graphiti Group ID
- group_id: `llm-pipeline` (used for codebase memory storage)
