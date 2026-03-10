# Step 2: FastAPI Static File Serving Research

## Summary

StaticFiles mounting for SPA serving is **already implemented** in `cli.py`. This research documents the current approach, confirms its correctness, and identifies what remains for task 44.

---

## Current Implementation

### StaticFiles Mount (cli.py:59-71)

```python
def _run_prod_mode(app: object, port: int) -> None:
    dist_dir = Path(__file__).resolve().parent / "frontend" / "dist"
    if dist_dir.exists():
        app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="spa")
    else:
        print("WARNING: frontend/dist/ not found; running in API-only mode", file=sys.stderr)
    uvicorn.run(app, host="0.0.0.0", port=port)
```

### Key Design Decisions Already Made

1. **Mount location**: `cli.py` (not `app.py`) - keeps `create_app()` testable and clean for programmatic use
2. **Path resolution**: `Path(__file__).resolve().parent / "frontend" / "dist"` - works in both source tree and installed wheel
3. **Graceful fallback**: API-only mode with warning if `dist/` absent

---

## How `html=True` Handles SPA Routing

Starlette's `StaticFiles(html=True)` behavior:

| Request Path | File Exists? | Response |
|---|---|---|
| `/` | n/a | Serves `dist/index.html` |
| `/assets/main.js` | Yes | Serves the JS file |
| `/live` | No file match | Serves `dist/index.html` (SPA catch-all) |
| `/prompts/abc` | No file match | Serves `dist/index.html` (SPA catch-all) |

This fully supports HTML5 History API routing. TanStack Router on the client receives `index.html` and handles route matching.

---

## Route Priority (No Conflicts)

Routes are registered in this order within the FastAPI app:

1. `/api/*` - runs, steps, events, prompts, pipelines routers (registered in `create_app()`)
2. `/ws/*` - websocket router (registered in `create_app()`, no `/api` prefix)
3. `/` - StaticFiles catch-all (mounted in `cli.py` after `create_app()` returns)

FastAPI/Starlette checks mounts in registration order. API and WS routes match first; unmatched requests fall through to StaticFiles. No path conflicts.

---

## Package Inclusion (Hatchling)

`pyproject.toml` already configured:

```toml
[tool.hatch.build.targets.wheel]
packages = ["llm_pipeline"]
artifacts = ["llm_pipeline/ui/frontend/dist/**"]
exclude = [
    "llm_pipeline/ui/frontend/node_modules/**",
    "llm_pipeline/ui/frontend/src/**",
    # ... other dev files
]
```

- `artifacts` directive includes `dist/` in wheel even though it's gitignored
- Excludes ensure no dev files (node_modules, src, configs) leak into package
- `pip install llm-pipeline[ui]` gets pre-built frontend

---

## Dev vs Prod Mode

| Mode | Frontend | Backend | How |
|---|---|---|---|
| `--dev` | Vite dev server (port+1) | FastAPI with reload | Vite proxies `/api` and `/ws` to FastAPI |
| Production | StaticFiles from `dist/` | FastAPI (uvicorn) | Single process serves both |
| API-only | None | FastAPI | dist/ absent, warning printed |

Dev mode: Vite config (`vite.config.ts`) proxies:
```typescript
proxy: {
  '/api': { target: `http://localhost:${apiPort}`, changeOrigin: true },
  '/ws': { target: `ws://localhost:${apiPort}`, ws: true },
}
```

---

## Deviation from Task 44 Spec

Task 44 details suggest mounting StaticFiles in `app.py`:
```python
# Task spec suggests:
def create_app(...):
    dist_dir = Path(__file__).parent / 'frontend' / 'dist'
    if dist_dir.exists():
        app.mount('/', StaticFiles(directory=str(dist_dir), html=True))
```

**Actual implementation** is in `cli.py`'s `_run_prod_mode()`. This is preferable because:
- `create_app()` remains a pure API factory (easier to test with `TestClient`)
- Static file serving is a deployment concern, not an app concern
- Programmatic users who embed the app don't get unwanted static serving

**Recommendation**: Keep current approach in `cli.py`. No change needed.

---

## What Remains for Task 44 (Not This Step's Scope)

These items are identified but belong to other research steps:

1. **Vite chunk splitting** (step 1): `rollupOptions.output.manualChunks` config for vendor/router/query bundles
2. **Bundle size verification** (step 3): Mechanism to verify <500KB gzip target
3. **Build scripts**: `package.json` already has `"build": "tsc -b && vite build"` but lacks `build:analyze`

---

## Conclusion

The FastAPI static file serving infrastructure is complete and correctly implemented. No code changes needed for this aspect of task 44. The `html=True` SPA catch-all, route priority, package inclusion, and dev/prod separation all work as expected.
