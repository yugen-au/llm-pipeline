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

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] Exclude list missing index.html (Vite entry point, dev-only)
[x] Exclude list missing README.md (frontend readme, dev-only)
[x] Exclude list missing .gitignore (frontend gitignore, dev-only)

### Changes Made
#### File: `pyproject.toml`
Added 3 missing dev-only files to the hatchling wheel exclude list.

```
# Before (end of exclude list)
    "llm_pipeline/ui/frontend/package*.json",
]

# After
    "llm_pipeline/ui/frontend/package*.json",
    "llm_pipeline/ui/frontend/index.html",
    "llm_pipeline/ui/frontend/README.md",
    "llm_pipeline/ui/frontend/.gitignore",
]
```

### Verification
[x] All 3 new exclude entries added
[x] Exclude list now has 14 entries total (11 original + 3 new)
[x] artifacts directive unaffected (not impacted by exclude per hatch docs)
