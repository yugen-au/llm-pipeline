# Research Summary

## Executive Summary

Both research steps are well-aligned and accurate. All key claims verified against actual source code (create_app signature, import guard, pyproject.toml state, absence of cli.py and frontend/). Two contradictions found between research steps (argparse pattern) and between task 27 spec and task 28 scope (pyproject.toml ownership). Three hidden assumptions surfaced requiring clarification. Research is solid foundation for planning once questions are resolved.

## Domain Findings

### Codebase Structure (Verified)
**Source:** step-1-codebase-structure-research.md, actual source files

- `create_app(db_path, cors_origins, pipeline_registry, introspection_registry)` signature confirmed in `llm_pipeline/ui/app.py`
- Import guard in `ui/__init__.py` raises ImportError with install hint -- confirmed
- No `[project.scripts]`, no `cli.py`, no `frontend/` directory exist -- all confirmed via source + glob
- `pyproject.toml` has `ui` optional deps `["fastapi>=0.100", "uvicorn[standard]>=0.20"]` -- confirmed
- DB init: `get_default_db_path()` uses `LLM_PIPELINE_DB` env or `CWD/.llm_pipeline/pipeline.db` -- confirmed
- Upstream task 19 completed with no deviations affecting CLI. create_app signature matches expectations.

### FastAPI + Uvicorn Patterns (Verified)
**Source:** step-2-fastapi-uvicorn-patterns.md

- `uvicorn.run(app, host, port)` for production: simplest blocking approach, handles SIGINT/SIGTERM natively
- Static files via `StaticFiles(directory=dist_path, html=True)` mounted last for SPA catch-all -- correct pattern
- Dev mode: Vite on port+1 proxies /api/* and /ws/* to FastAPI on port -- standard Vite dev proxy pattern
- Subprocess management: `subprocess.Popen` + `atexit` + `try/finally` for cleanup -- sound approach
- Windows: `shell=True` for npx.cmd resolution, no SIGTERM handler needed (atexit + Ctrl+C sufficient)
- Lifespan context manager rejected in favor of try/finally -- correct rationale (CLI concern, not app concern)

### Cross-Cutting Contradiction: argparse Pattern
**Source:** step-1 section 8 vs step-2 section 7

- Step 1 uses `parser.add_argument('command', choices=['ui'])` (positional, matches task spec code sample)
- Step 2 uses `parser.add_subparsers(dest="command")` + `sub.add_parser("ui")` (subparser pattern)
- These produce different UX: subparsers give per-command help, are more extensible for future commands
- Task spec code is illustrative. Subparsers is more idiomatic but deviates from spec.

### Scope Boundary: pyproject.toml Ownership
**Source:** task 27 spec vs task 28 spec

- Task 27 spec literally includes "Update pyproject.toml" with `[project.scripts]`
- Task 28 is titled "Update pyproject.toml with UI Dependencies" and also claims `[project.scripts]`
- Research (step 1, section 7) correctly assigns pyproject.toml to task 28
- Dependency chain supports this: task 28 depends on 27, meaning 27 creates the module, 28 wires it in

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| 1. `--dev` without frontend: hard error or fallback to uvicorn reload mode? | PENDING | Determines dev mode implementation complexity |
| 2. Subparsers vs positional command for argparse? | PENDING | Affects CLI UX and extensibility |

## Assumptions Validated
- [x] create_app() accepts db_path and maps cleanly to --db CLI flag
- [x] No existing CLI code, argparse, click, typer, or subprocess usage in codebase
- [x] ui/__init__.py import guard means cli.py must defer FastAPI imports to function bodies
- [x] cors_origins defaults to ["*"] in create_app -- adequate for both dev and prod CLI use
- [x] pipeline_registry/introspection_registry not CLI-configurable (programmatic only) -- correct for inspection-only UI
- [x] Task 28 owns pyproject.toml changes (not task 27), despite task 27 spec including it
- [x] Default port 8642 per task spec
- [x] atexit + try/finally is sufficient for Vite subprocess cleanup on both Unix and Windows
- [x] 127.0.0.1 for dev (Vite proxy only), 0.0.0.0 for prod -- security-appropriate defaults

## Open Items
- Testing strategy for cli.py not addressed in either research step (mocking uvicorn.run, subprocess.Popen)
- No --host flag proposed; hardcoded 0.0.0.0 (prod) / 127.0.0.1 (dev). Acceptable per task spec but noted.
- No --verbose / --log-level flag proposed. Out of scope per task spec.
- Node.js/npm availability not validated before `npx vite` -- should add check with helpful error message
- `proc.kill()` on Windows is same as `proc.terminate()` (no SIGKILL equivalent) -- cleanup timeout is cosmetic on Windows

## Recommendations for Planning
1. Use subparsers pattern for argparse (more extensible, better help output, idiomatic)
2. Implement dev-mode frontend check as hard error with clear message pointing to frontend setup
3. Add Node.js/npx availability check before attempting Vite subprocess launch
4. Plan test file `tests/test_cli.py` with mocked uvicorn.run and subprocess.Popen
5. Mount StaticFiles in cli.py (_run_prod_mode), not in create_app -- keeps factory focused
6. Do NOT modify pyproject.toml -- defer to task 28
