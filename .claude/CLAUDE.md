# llm-pipeline

## Overview
Declarative LLM pipeline orchestration framework. Extracted from logistics-intelligence as standalone reusable library.

## Tech Stack
- Python 3.11+, uv (package manager)
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
- pydantic-ai Agent system via `register_agent()` and agent_builders.py
- `ReadOnlySession` - safe DB session wrapper

### Convention directory (`llm_pipelines/`)
Standard layout for pipeline artifacts, auto-discovered on startup:
- `pipelines/`, `steps/`, `schemas/`, `extractions/` - core pipeline code
- `tools/` - agent tool functions (manual `register_agent()`)
- `enums/`, `constants/` - auto-registered for `auto_generate` expressions
- Discovery: package-internal + CWD, loaded in dependency order

### Prompts
- YAML files in `llm-pipeline-prompts/` (package-level + project-level)
- Bidirectional sync: YAML -> DB on startup (version wins), DB -> YAML on UI save
- `variable_definitions` with `auto_generate` expressions (e.g. `enum_values(X)`)
- Runtime evaluation via `register_auto_generate()`, `set_auto_generate_base_path()`

### Registries
- `register_agent(name, tools)` - agent tools for steps
- `register_auto_generate(name, obj)` - enums/constants for prompt variable expressions
- `register_prompt_variables(key, type, cls)` - code-defined variable classes (optional, DB-driven preferred)

## Running the UI
- Dev mode: `uv run llm-pipeline ui --dev`
- Prod mode: `uv run llm-pipeline ui`
- Default port: 8642 (backend), 8643 (Vite dev)
- SQLite auto-creates, no DB setup needed
- Custom DB: `uv run llm-pipeline ui --dev --db path/to/db.sqlite`
- Custom pipelines: `uv run llm-pipeline ui --dev --pipelines my_project.pipelines`
- Custom prompts dir: `uv run llm-pipeline ui --dev --prompts-dir path/to/prompts`
- Demo mode: `uv run llm-pipeline ui --dev --demo` (loads built-in demo pipeline)
- Default: demo_mode=false, only project-level llm_pipelines/ and prompts loaded

## MCP Servers

### Base (always included)
- Purpose: Core shared tools (fetch, context7, serena, graphiti, taskmaster, sequential-thinking)
- Configured in: Global `~/.claude.json`

## Testing
Philosophy: TDD strict

### Backend (Python)
- Command: `uv run pytest`
- Runner: pytest
- Path: `tests/`

### Frontend (UI)
- No test runner configured yet
- Manual: start UI with `uv run llm-pipeline ui --dev`, verify in browser at Vite port

## Development Notes
- Build with `hatchling`
- Test deps and pydantic-ai in `[project.optional-dependencies].dev`; pydantic-ai also in core deps
- Pytest configured in `[tool.pytest.ini_options]` in pyproject.toml

## Graphiti Group ID
- group_id: `llm-pipeline` (used for codebase memory storage)
