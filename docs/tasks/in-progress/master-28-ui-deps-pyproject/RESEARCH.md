# Research: UI Dependencies & CLI Entry Point in pyproject.toml

## Current State

### pyproject.toml Structure
- Build system: `hatchling`
- No `[tool.hatch]` build config sections exist
- No `[project.scripts]` section exists

### Existing Optional Dependencies
```toml
[project.optional-dependencies]
gemini = ["google-generativeai>=0.3.0"]
ui = ["fastapi>=0.100", "uvicorn[standard]>=0.20"]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "google-generativeai>=0.3.0",
    "fastapi>=0.100",
    "uvicorn[standard]>=0.20",
    "httpx>=0.24",
]
```

### CLI Entry Point Module
- `llm_pipeline/ui/cli.py` exists with `main()` function (task 27, done)
- Task 27 SUMMARY explicitly recommends adding `[project.scripts]` entry as task 28 scope

### UI Package Structure
```
llm_pipeline/ui/
  __init__.py
  app.py
  cli.py
  deps.py
  routes/
    __init__.py
    events.py
    pipelines.py
    prompts.py
    runs.py
    steps.py
    websocket.py
```

## Changes Required

### 1. Add `[project.scripts]` Entry Point
```toml
[project.scripts]
llm-pipeline = "llm_pipeline.ui.cli:main"
```
After `pip install llm-pipeline[ui]`, the `llm-pipeline` command will be available.

### 2. Add Missing Deps to `[ui]` Group
Current: `fastapi>=0.100`, `uvicorn[standard]>=0.20`
Add: `websockets>=11.0`, `python-multipart>=0.0.5`

- **websockets**: Required by uvicorn for WebSocket protocol support (used by `routes/websocket.py`)
- **python-multipart**: Required by FastAPI for form data / file upload parsing

Resulting:
```toml
ui = [
    "fastapi>=0.100",
    "uvicorn[standard]>=0.20",
    "websockets>=11.0",
    "python-multipart>=0.0.5",
]
```

### 3. Mirror New Deps in `[dev]` Group
Existing pattern: `[dev]` includes all optional deps for testing. Add `websockets>=11.0` and `python-multipart>=0.0.5`.

```toml
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "google-generativeai>=0.3.0",
    "fastapi>=0.100",
    "uvicorn[standard]>=0.20",
    "websockets>=11.0",
    "python-multipart>=0.0.5",
    "httpx>=0.24",
]
```

### 4. Hatch Build Config for Frontend Dist Bundling

**Not needed yet** -- `frontend/dist/` won't exist until task 29+ builds it. When ready, use `force-include` to bundle static assets into the wheel:

```toml
[tool.hatch.build.targets.wheel.force-include]
"llm_pipeline/ui/frontend/dist" = "llm_pipeline/ui/frontend/dist"
```

This is unnecessary if hatchling auto-discovers `llm_pipeline/ui/frontend/dist/` as part of the `llm_pipeline` package tree (it will, since it's inside the package). `force-include` is only needed if the dist directory is outside the package or if specific exclusion rules would otherwise skip it.

**Recommendation**: Defer `[tool.hatch.build]` config to a later task when frontend build artifacts actually exist. Hatchling's auto-discovery will include `frontend/dist/` by default since it's within the `llm_pipeline` package tree. If we later need to exclude `frontend/node_modules/` or `frontend/src/` from the wheel, add:

```toml
[tool.hatch.build.targets.wheel]
exclude = [
    "llm_pipeline/ui/frontend/node_modules",
    "llm_pipeline/ui/frontend/src",
    "llm_pipeline/ui/frontend/package.json",
    "llm_pipeline/ui/frontend/tsconfig*.json",
    "llm_pipeline/ui/frontend/vite.config.*",
]
```

### 5. Package Auto-Discovery
No explicit `[tool.hatch.build.targets.wheel]` packages config needed. Hatchling auto-discovers `llm_pipeline/` at the repo root. Current setup works.

## Upstream Context (Task 27)
- cli.py created with `main()`, subparsers dispatch, prod/dev modes
- Deviation: `_run_dev_mode(args)` takes full Namespace (not `(app, port)`)
- Factory pattern `_create_dev_app` added for uvicorn reload mode
- No pyproject.toml changes were made in task 27

## Downstream Context (Task 29)
- Frontend project init (React 19 + TypeScript + Vite + TanStack Router)
- Depends on task 28 completing first
- Will create `llm_pipeline/ui/frontend/` directory structure
- OUT OF SCOPE for task 28

## Final pyproject.toml (proposed)

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "llm-pipeline"
version = "0.1.0"
description = "Declarative LLM pipeline orchestration framework"
readme = "README.md"
requires-python = ">=3.11"
license = {text = "MIT"}
dependencies = [
    "pydantic>=2.0",
    "sqlmodel>=0.0.14",
    "sqlalchemy>=2.0",
    "pyyaml>=6.0",
]

[project.scripts]
llm-pipeline = "llm_pipeline.ui.cli:main"

[project.optional-dependencies]
gemini = ["google-generativeai>=0.3.0"]
ui = [
    "fastapi>=0.100",
    "uvicorn[standard]>=0.20",
    "websockets>=11.0",
    "python-multipart>=0.0.5",
]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "google-generativeai>=0.3.0",
    "fastapi>=0.100",
    "uvicorn[standard]>=0.20",
    "websockets>=11.0",
    "python-multipart>=0.0.5",
    "httpx>=0.24",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```
