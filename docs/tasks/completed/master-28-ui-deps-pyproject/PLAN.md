# PLANNING

## Summary
Update `pyproject.toml` to add `[ui]` optional dependency group with FastAPI, uvicorn[standard], and python-multipart; add `[project.scripts]` CLI entry point; bump existing dev group bounds to match. Add import guard in `llm_pipeline/ui/cli.py` so `llm-pipeline ui` prints a friendly error when [ui] deps are missing.

## Plugin & Agents
**Plugin:** python-development, dependency-management
**Subagents:** [available agents]
**Skills:** none

## Phases
1. **Implementation**: Update pyproject.toml and cli.py with all required changes

## Architecture Decisions

### Import Guard Placement
**Choice:** Wrap the `import uvicorn` / `from llm_pipeline.ui.app import create_app` calls in `_run_ui()` and its callees with a module-level try/except in `_run_ui()` that catches ImportError and exits with a helpful message.
**Rationale:** `_run_ui()` is the single dispatch point for the `ui` subcommand. All FastAPI/uvicorn imports are already deferred inside `_run_ui`, `_run_prod_mode`, `_run_dev_mode`, and `_create_dev_app`. A guard at `_run_ui` entry catches any ImportError from those deferred imports without touching `main()` -- so `llm-pipeline --help` continues to work with zero deps.
**Alternatives:** Guard each individual import site (more verbose, redundant); guard at top of file (breaks --help without [ui] deps).

### Dev Group Version Bumps
**Choice:** Bump `fastapi>=0.100` to `fastapi>=0.115.0`, `uvicorn[standard]>=0.20` to `uvicorn[standard]>=0.32.0` in `[dev]`, and add `python-multipart>=0.0.9` to both `[ui]` and `[dev]`.
**Rationale:** CEO decision. Keeps `[dev]` in sync with `[ui]` per existing project pattern. `fastapi>=0.115.0` internally requires python-multipart but explicit listing provides clarity.
**Alternatives:** Keep lower bounds (rejected by CEO); use self-referencing `llm-pipeline[ui]` in dev (out of scope, deferred).

### No hatch Build Config
**Choice:** Do not add `[tool.hatch.build]` section.
**Rationale:** Hatchling auto-discovers `llm_pipeline/` package tree. No `frontend/dist/` exists yet (task 29+). Exclusion rules deferred until frontend artifacts exist.
**Alternatives:** Add build config now (premature, creates noise).

## Implementation Steps

### Step 1: Update pyproject.toml
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Replace `[project.optional-dependencies]` `ui` line: change `["fastapi>=0.100", "uvicorn[standard]>=0.20"]` to `["fastapi>=0.115.0", "uvicorn[standard]>=0.32.0", "python-multipart>=0.0.9"]`
2. Add `[project.scripts]` section between `[project]` block end and `[project.optional-dependencies]` block: `llm-pipeline = "llm_pipeline.ui.cli:main"`
3. In `[dev]` optional group: bump `fastapi>=0.100` to `fastapi>=0.115.0`, bump `uvicorn[standard]>=0.20` to `uvicorn[standard]>=0.32.0`, add `python-multipart>=0.0.9`

### Step 2: Add import guard to cli.py
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. In `_run_ui()` (line 38), wrap the entire body in a try/except ImportError block that catches import failures from deferred imports in `_run_prod_mode`, `_run_dev_mode`, and `_create_dev_app`
2. On ImportError, print to stderr: `"ERROR: UI dependencies not installed. Run: pip install llm-pipeline[ui]"` then `sys.exit(1)`
3. Ensure `sys` is already imported at top of file (it is -- line 9 confirms this)

Note: Steps 1 and 2 are in the same group (A) because they touch different files with no overlap.

## Risks & Mitigations
| Risk | Impact | Mitigation |
| --- | --- | --- |
| Import guard catches ImportError from non-dep code (e.g. app logic bug) | Medium | Catch only at `_run_ui` entry, re-raise if error message doesn't mention known missing packages, or keep catch broad -- acceptable since any ImportError here indicates missing [ui] deps |
| TOML section ordering breaks hatchling parsing | Low | `[project.scripts]` is a standard PEP 621 table; TOML order within document is irrelevant to parsers |
| python-multipart version conflicts with existing installs | Low | `>=0.0.9` is a loose lower bound; fastapi>=0.115.0 already depends on it internally |

## Success Criteria
- [ ] `pyproject.toml` contains `[project.scripts]` with `llm-pipeline = "llm_pipeline.ui.cli:main"`
- [ ] `[project.optional-dependencies].ui` contains exactly: `fastapi>=0.115.0`, `uvicorn[standard]>=0.32.0`, `python-multipart>=0.0.9`
- [ ] `[project.optional-dependencies].dev` contains bumped fastapi/uvicorn bounds and python-multipart>=0.0.9
- [ ] `llm_pipeline/ui/cli.py` `_run_ui()` prints friendly error and exits 1 when [ui] deps missing
- [ ] `llm-pipeline --help` works without [ui] deps installed (import guard only triggers on `ui` subcommand)
- [ ] `pip install -e .[ui]` installs without dependency conflicts
- [ ] Existing tests pass (no regressions)

## Phase Recommendation
**Risk Level:** low
**Reasoning:** Pure config/guard change. No new logic paths, no schema changes, no API surface modifications. Import guard is a defensive pattern with no behavioral change when deps are present. Only risk is minor TOML formatting.
**Suggested Exclusions:** testing, review
