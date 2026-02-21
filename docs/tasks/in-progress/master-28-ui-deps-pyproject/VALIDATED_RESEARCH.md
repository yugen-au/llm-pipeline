# Research Summary

## Executive Summary

Validated research for task 28 (pyproject.toml [ui] deps + CLI entry point). Three assumptions from research were incorrect or needed CEO decision: websockets is redundant (omit), python-multipart is unused but included per CEO for future use, version bounds bumped to task master values. Import guard for missing [ui] deps added to scope.

## Domain Findings

### CLI Entry Point
**Source:** RESEARCH.md, cli.py
- `[project.scripts] llm-pipeline = "llm_pipeline.ui.cli:main"` -- correct PEP 621 approach, confirmed `main()` exists
- cli.py defers all FastAPI/uvicorn imports to function bodies -- `llm-pipeline --help` works without [ui] deps
- BUT: `llm-pipeline ui` will raise bare ImportError if [ui] deps missing -- needs friendly guard (in scope per CEO)

### Dependency Adjustments vs Research
**Source:** RESEARCH.md, pyproject.toml, codebase grep

**websockets -- OMIT (CEO decision)**
- Research proposed `websockets>=11.0` as explicit dep
- Validation found: `uvicorn[standard]` already includes `websockets` as transitive dep
- Code uses `from fastapi import WebSocket` (Starlette abstraction), not raw `websockets` lib
- No need for explicit version pinning

**python-multipart -- INCLUDE (CEO decision)**
- Research proposed `python-multipart>=0.0.5`
- Validation found: zero usage of Form/File/UploadFile in any route
- CEO decided: include for future file upload support
- Use version `>=0.0.9` per task master (not `>=0.0.5` from research)

**Version bounds -- BUMP (CEO decision)**
- Research kept existing lower bounds: `fastapi>=0.100`, `uvicorn>=0.20`
- CEO decided: use task master bounds: `fastapi>=0.115.0`, `uvicorn[standard]>=0.32.0`
- Bonus: `fastapi>=0.115.0` includes `python-multipart` as required dep (added in 0.109.0), but explicit listing still appropriate for clarity

### Hatch Build Config
**Source:** RESEARCH.md
- Correctly deferred -- no `frontend/dist/` exists yet (task 29+)
- Hatchling auto-discovers `llm_pipeline/` package tree, no explicit config needed
- Exclusion rules for `node_modules/`, `src/` etc. deferred to when frontend exists

### Dev Group Mirroring
**Source:** RESEARCH.md, pyproject.toml
- Existing pattern: `[dev]` duplicates all optional deps
- New deps (python-multipart) must be mirrored into `[dev]`
- websockets omitted from both [ui] and [dev] (transitive)

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| python-multipart not used anywhere -- include or omit? | INCLUDE for future file upload support | Added to [ui] and [dev] groups despite no current usage |
| websockets redundant with uvicorn[standard] -- list explicitly? | OMIT, transitive dep is sufficient | Removed from proposed deps, simplifies [ui] group |
| Version bounds: keep lower (>=0.100) or bump (>=0.115)? | BUMP to task master values | fastapi>=0.115.0, uvicorn>=0.32.0, python-multipart>=0.0.9 |
| Import guard for missing [ui] deps in cli.py? | IN SCOPE for task 28 | cli.py needs try/except ImportError with friendly message |

## Assumptions Validated
- [x] `llm_pipeline.ui.cli:main` is correct entry point path (confirmed cli.py exists with main())
- [x] `[project.scripts]` placed between `[project]` and `[project.optional-dependencies]` is valid TOML
- [x] Hatchling auto-discovers packages without explicit `[tool.hatch.build]` config
- [x] `[dev]` group mirrors all optional deps (existing pattern in pyproject.toml)
- [x] Starlette comes free as FastAPI dependency (no separate dep needed for StaticFiles)
- [x] `uvicorn[standard]` provides websockets transitively (no explicit dep needed)
- [x] CLI defers imports so `llm-pipeline --help` works without [ui] deps installed
- [x] No `[tool.hatch]` build config needed until frontend dist exists (task 29+)

## Open Items
- Import guard implementation details (try/except wrapping, error message wording) deferred to planning phase
- `[tool.hatch.build]` exclusion rules for frontend artifacts deferred to task 29+
- Self-referencing dev deps (`llm-pipeline[ui]` instead of duplicating) considered but out of scope -- follows existing pattern

## Recommendations for Planning

1. Final `[ui]` group: `["fastapi>=0.115.0", "uvicorn[standard]>=0.32.0", "python-multipart>=0.0.9"]`
2. Mirror `python-multipart>=0.0.9` into `[dev]` group; bump existing fastapi/uvicorn bounds in dev too
3. Add `[project.scripts]` section: `llm-pipeline = "llm_pipeline.ui.cli:main"`
4. Add import guard in cli.py `_run_ui()`: wrap the FastAPI/uvicorn import path with try/except ImportError, print message directing user to `pip install llm-pipeline[ui]`, then sys.exit(1)
5. Do NOT add any `[tool.hatch.build]` config -- defer to task 29+
6. Remove `websockets` from both research-proposed dep lists (not needed)
