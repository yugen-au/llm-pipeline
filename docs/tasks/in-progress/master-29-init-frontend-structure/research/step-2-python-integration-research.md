# Step 2: Python Integration Research

## Scope
How to integrate a React/Vite frontend build into the existing llm-pipeline Python package via hatchling, pyproject.toml, entry points, and dev workflow.

## Current State (Post-Task 28)

### pyproject.toml
- Build system: hatchling
- Entry point: `llm-pipeline = "llm_pipeline.ui.cli:main"`
- Optional deps `[ui]`: fastapi>=0.115.0, uvicorn[standard]>=0.32.0, python-multipart>=0.0.9
- No `[tool.hatch.build.targets.*]` sections configured yet

### CLI (llm_pipeline/ui/cli.py)
- `main()` dispatches `ui` subcommand to `_run_ui()`
- Prod mode: mounts `frontend/dist` as Starlette StaticFiles at `/`
- Dev mode: starts Vite subprocess on port+1, FastAPI on port
- Resolves dist via `Path(__file__).resolve().parent / "frontend" / "dist"`
- Already passes `VITE_PORT` and `VITE_API_PORT` env vars to Vite subprocess

### .gitignore
- `dist/` -- matches anywhere (including `llm_pipeline/ui/frontend/dist/`)
- `node_modules/` -- matches anywhere
- Both patterns already present at root level

### UI Module (llm_pipeline/ui/)
- `__init__.py` -- import guard for fastapi, exports `create_app`
- `app.py` -- FastAPI factory with CORS, DB engine, route mounting
- `cli.py` -- CLI with dev/prod modes
- `routes/` -- runs, steps, events, prompts, pipelines, websocket
- `deps.py` -- dependency injection
- No `frontend/` directory yet (task 29 creates it)

---

## Finding 1: Hatchling Build Configuration for Frontend Dist

### Correct Approach: `artifacts` (NOT `shared-data`)

Task 28's plan included `[tool.hatch.build.targets.wheel.shared-data]` for frontend dist inclusion. **This is incorrect.** `shared-data` installs files to `{prefix}/share/{distribution_name}/` -- a global data directory, NOT inside the package. Since `cli.py` resolves dist/ via `Path(__file__).parent / "frontend" / "dist"`, the files MUST be inside `site-packages/llm_pipeline/ui/frontend/dist/`.

The correct mechanism is **`artifacts`**: tells hatchling to include files that would otherwise be excluded by `.gitignore`.

### Recommended pyproject.toml additions

```toml
[tool.hatch.build.targets.wheel]
packages = ["llm_pipeline"]
artifacts = [
    "llm_pipeline/ui/frontend/dist/**",
]
exclude = [
    "llm_pipeline/ui/frontend/node_modules/**",
    "llm_pipeline/ui/frontend/src/**",
    "llm_pipeline/ui/frontend/.vite/**",
    "llm_pipeline/ui/frontend/tsconfig*",
    "llm_pipeline/ui/frontend/vite.config*",
    "llm_pipeline/ui/frontend/tailwind.config*",
    "llm_pipeline/ui/frontend/postcss.config*",
    "llm_pipeline/ui/frontend/components.json",
    "llm_pipeline/ui/frontend/eslint*",
    "llm_pipeline/ui/frontend/.eslint*",
]
```

### How it works
1. `.gitignore` has `dist/` and `node_modules/` -- hatchling respects these by default
2. `artifacts` re-includes `dist/**` despite the gitignore pattern
3. `exclude` removes frontend source/config files that ARE tracked by git but NOT needed at runtime
4. `packages = ["llm_pipeline"]` is explicit (hatchling auto-detects, but explicit is safer)

### Why not other approaches
| Approach | Why Not |
|----------|---------|
| `shared-data` | Installs to `{prefix}/share/`, not inside package. cli.py uses `__file__`-relative path. |
| `force-include` | For files OUTSIDE the package tree. dist/ is already inside `llm_pipeline/`. |
| Custom build hook | Over-engineered. npm build should be a separate CI step. |
| No config (rely on defaults) | dist/ is gitignored, so hatchling would exclude it. |

---

## Finding 2: Build Pipeline Order

### Production build sequence
```
1. cd llm_pipeline/ui/frontend
2. npm ci                          # install locked deps
3. npm run build                   # produces dist/
4. cd ../../..                     # back to project root
5. python -m build                 # or: pip install .
```

Hatchling runs AFTER npm build. The `artifacts` config ensures dist/ is picked up even though it's gitignored.

### No automated build hook recommended
A hatch build hook could auto-run `npm build`, but this:
- Requires Node.js as a build dependency for pip installs
- Breaks `pip install llm-pipeline` for users without Node
- Adds complexity for marginal benefit
- CI/CD naturally sequences these steps

### CI/CD example (GitHub Actions)
```yaml
- uses: actions/setup-node@v4
  with: { node-version: 22 }
- run: cd llm_pipeline/ui/frontend && npm ci && npm run build
- uses: actions/setup-python@v5
  with: { python-version: "3.12" }
- run: pip install build && python -m build
```

---

## Finding 3: Entry Points (Already Complete)

### Current state (no changes needed)
```toml
[project.scripts]
llm-pipeline = "llm_pipeline.ui.cli:main"
```

- `llm-pipeline ui` -- starts prod server (mounts dist/ if present, API-only if not)
- `llm-pipeline ui --dev` -- starts Vite + FastAPI dev servers
- `llm-pipeline ui --port 9000` -- custom port
- `llm-pipeline ui --db /path/to/db` -- custom DB path

### Import guard flow
1. `main()` runs without UI deps (just argparse)
2. `_run_ui()` catches ImportError for known UI packages
3. Unknown ImportErrors re-raised (not swallowed)

No changes needed for task 29.

---

## Finding 4: Development Workflow

### Already implemented in cli.py
```
llm-pipeline ui --dev
  |
  +-- frontend/ exists?
  |     YES -> _start_vite_mode()
  |     |       +-- npx vite --port {port+1}  (VITE_PORT, VITE_API_PORT env vars)
  |     |       +-- uvicorn on port
  |     NO  -> uvicorn with --reload (headless mode)
```

### Vite proxy config needed (task 29 implementation, not research)
```typescript
// vite.config.ts server.proxy
server: {
  port: parseInt(process.env.VITE_PORT || '8643'),
  proxy: {
    '/api': {
      target: `http://127.0.0.1:${process.env.VITE_API_PORT || '8642'}`,
      changeOrigin: true,
    },
    '/ws': {
      target: `http://127.0.0.1:${process.env.VITE_API_PORT || '8642'}`,
      ws: true,
    },
  },
}
```

### Standalone npm dev (without Python CLI)
Developers can also run `npm run dev` inside `frontend/` directly, setting env vars manually. The CLI approach is preferred for full-stack dev since it manages both processes.

---

## Finding 5: .gitignore Updates

### Current coverage (no changes needed)
- `dist/` -- already present, matches `llm_pipeline/ui/frontend/dist/`
- `node_modules/` -- already present, matches `llm_pipeline/ui/frontend/node_modules/`

### Optional: add explicit frontend-specific patterns
```gitignore
# Frontend build artifacts (covered by dist/ and node_modules/ above, but explicit)
# llm_pipeline/ui/frontend/dist/
# llm_pipeline/ui/frontend/node_modules/
```

Not strictly necessary since the global patterns already match. Adding comments could aid clarity but is low priority.

---

## Finding 6: Package Distribution Impact

### Wheel contents with recommended config
```
llm_pipeline/
  __init__.py
  ...
  ui/
    __init__.py
    app.py
    cli.py
    deps.py
    routes/
      ...
    frontend/
      dist/           # Included via artifacts (gitignored but re-included)
        index.html
        assets/
          *.js
          *.css
```

### What's excluded from wheel
- `llm_pipeline/ui/frontend/node_modules/` -- gitignored
- `llm_pipeline/ui/frontend/src/` -- explicit exclude
- `llm_pipeline/ui/frontend/*.config.*` -- explicit exclude
- `llm_pipeline/ui/frontend/package*.json` -- explicit exclude
- `llm_pipeline/ui/frontend/tsconfig*` -- explicit exclude

### Size considerations
- Typical Vite React build: 200KB-2MB (gzipped assets)
- Acceptable for a Python package with bundled UI
- node_modules exclusion is critical (100MB+)

---

## Deviations from Task 28 Plan

| Item | Task 28 Plan | Correct Approach | Reason |
|------|-------------|-----------------|--------|
| Build config | `[tool.hatch.build.targets.wheel.shared-data]` | `[tool.hatch.build.targets.wheel] artifacts = [...]` | shared-data installs to global `{prefix}/share/`, not inside package. cli.py uses `__file__`-relative path requiring dist/ inside package. |

This is a non-breaking deviation -- task 28 did NOT actually implement the shared-data config (it was in the task description as future work). The implementation only added `[project.scripts]` and `[project.optional-dependencies]`.

---

## Downstream Task Impact

### Task 30 (TanStack Router Routes) -- pending
- Depends on task 29 completing frontend scaffold
- No Python integration concerns; purely frontend routing
- No impact from this research

### Task 42 (Dark Mode / Tailwind Theme) -- pending
- Depends on task 29 completing frontend scaffold
- Purely CSS/Tailwind config; no Python integration concerns
- No impact from this research

---

## Summary

| Area | Status | Action Required |
|------|--------|-----------------|
| pyproject.toml build targets | Not configured | Add `[tool.hatch.build.targets.wheel]` with `artifacts` + `exclude` |
| Entry points | Done (task 28) | None |
| CLI dev/prod modes | Done (task 28) | None |
| .gitignore | Already covers dist/ and node_modules/ | None |
| Vite proxy config | Not yet created | Task 29 implementation scope |
| Build pipeline docs | Not documented | Document npm build -> python build order |
| shared-data correction | Task 28 plan was wrong | Use artifacts instead; already not implemented |
