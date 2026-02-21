# IMPLEMENTATION - STEP 10: UPDATE PYPROJECT.TOML
**Status:** completed

## Summary
Added `[tool.hatch.build.targets.wheel]` section to pyproject.toml with `artifacts` directive to include frontend `dist/` in wheel and `exclude` list to omit source/dev files.

## Files
**Created:** none
**Modified:** pyproject.toml
**Deleted:** none

## Changes
### File: `pyproject.toml`
Added hatchling wheel build target config between `[project.optional-dependencies]` and `[tool.pytest.ini_options]`.

```
# Before
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]

# After
[tool.hatch.build.targets.wheel]
packages = ["llm_pipeline"]
artifacts = ["llm_pipeline/ui/frontend/dist/**"]
exclude = [
    "llm_pipeline/ui/frontend/node_modules/**",
    "llm_pipeline/ui/frontend/src/**",
    "llm_pipeline/ui/frontend/.vite/**",
    "llm_pipeline/ui/frontend/tsconfig*",
    "llm_pipeline/ui/frontend/vite.config*",
    "llm_pipeline/ui/frontend/components.json",
    "llm_pipeline/ui/frontend/eslint*",
    "llm_pipeline/ui/frontend/.eslint*",
    "llm_pipeline/ui/frontend/.prettierrc",
    "llm_pipeline/ui/frontend/.prettierignore",
    "llm_pipeline/ui/frontend/package*.json",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

## Decisions
### artifacts vs shared-data
**Choice:** `artifacts` directive
**Rationale:** `shared-data` installs to `{prefix}/share/` which is wrong -- `cli.py` resolves dist via `Path(__file__).parent / "frontend" / "dist"` requiring it inside the package. `artifacts` overrides gitignore so `dist/` (normally gitignored) is included in the wheel at the correct path.

### Exclude list scope
**Choice:** Exclude all frontend dev/source files (node_modules, src, .vite, config files, package.json)
**Rationale:** Only `dist/` output is needed at runtime. Excluding source and tooling files keeps the wheel clean. Per hatch docs, `artifacts` is not affected by `exclude`, so dist/** inclusion is safe.

## Verification
[x] `[tool.hatch.build.targets.wheel]` section added with correct `packages`, `artifacts`, `exclude`
[x] `artifacts` pattern matches plan: `llm_pipeline/ui/frontend/dist/**`
[x] All 11 exclude patterns from plan present
[x] No existing sections overwritten or duplicated
[x] Section did not previously exist (confirmed pre-edit)
