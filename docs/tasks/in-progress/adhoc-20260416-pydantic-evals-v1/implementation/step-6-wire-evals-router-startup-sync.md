# IMPLEMENTATION - STEP 6: WIRE EVALS ROUTER + STARTUP SYNC
**Status:** completed

## Summary
Wired evals router into app.py, added YAML eval dataset sync on startup (mirroring prompt sync pattern), created llm-pipeline-evals/ directory, and added --evals-dir CLI arg.

## Files
**Created:** llm-pipeline-evals/.gitkeep, docs/tasks/in-progress/adhoc-20260416-pydantic-evals-v1/implementation/step-6-wire-evals-router-startup-sync.md
**Modified:** llm_pipeline/ui/app.py, llm_pipeline/ui/cli.py
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/app.py`
- Added `evals_dir: Optional[str] = None` param to `create_app()`
- Added evals YAML sync block after prompt sync: scans pkg-level (demo_mode) + project-level dirs, calls `sync_evals_yaml_to_db()`
- Stores `app.state.evals_dir = project_evals` for writeback
- Imported and included evals router with `/api` prefix

```
# Before
from llm_pipeline.ui.routes.reviews import router as reviews_router

# After
from llm_pipeline.ui.routes.reviews import router as reviews_router
from llm_pipeline.ui.routes.evals import router as evals_router
```

### File: `llm_pipeline/ui/cli.py`
- Added `--evals-dir` arg to ui subparser
- Passed `evals_dir=args.evals_dir` to `create_app()` in prod mode
- Added `LLM_PIPELINE_EVALS_DIR` env var passthrough for dev mode (reload)

### Directory: `llm-pipeline-evals/`
- Created at project root (parallel to llm-pipeline-prompts/)
- Contains .gitkeep for git tracking

## Decisions
### Evals sync placement
**Choice:** After prompt sync, before variable_definitions sync
**Rationale:** Evals sync needs DB init and discovery complete (tables + pipeline_registry). Placed after prompt sync for consistency. Before variable_definitions sync since evals don't depend on it.

### Env var naming
**Choice:** `LLM_PIPELINE_EVALS_DIR` (mirrors `LLM_PIPELINE_PROMPTS_DIR`)
**Rationale:** Consistent naming convention with existing env vars.

## Verification
[x] `create_app(db_path=':memory:')` succeeds with evals router registered
[x] `app.state.evals_dir` set to expected path
[x] Evals routes visible in app.routes (/api/evals, /api/evals/{dataset_id}, etc.)
[x] Syntax check passes on both modified files
[x] yaml_sync import works
[x] llm-pipeline-evals/ directory created
