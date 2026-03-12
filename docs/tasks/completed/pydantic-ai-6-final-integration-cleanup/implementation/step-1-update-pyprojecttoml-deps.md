# IMPLEMENTATION - STEP 1: UPDATE PYPROJECT.TOML DEPS
**Status:** completed

## Summary
Promoted pydantic-ai to core dependency and removed all google-generativeai references from pyproject.toml.

## Files
**Created:** none
**Modified:** pyproject.toml
**Deleted:** none

## Changes
### File: `pyproject.toml`
Added pydantic-ai to core deps, removed gemini and pydantic-ai optional groups, removed google-generativeai from dev deps.

```
# Before - [project.dependencies]
dependencies = [
    "pydantic>=2.0",
    "sqlmodel>=0.0.14",
    "sqlalchemy>=2.0",
    "pyyaml>=6.0",
]

# After - [project.dependencies]
dependencies = [
    "pydantic>=2.0",
    "sqlmodel>=0.0.14",
    "sqlalchemy>=2.0",
    "pyyaml>=6.0",
    "pydantic-ai>=1.0.5",
]
```

```
# Before - [project.optional-dependencies] (first 3 lines)
gemini = ["google-generativeai>=0.3.0"]
pydantic-ai = ["pydantic-ai>=1.0.5"]
ui = [...]

# After - [project.optional-dependencies] (first line)
ui = [...]
```

```
# Before - dev deps included
"google-generativeai>=0.3.0",

# After - line removed entirely
```

## Decisions
None -- all changes specified in plan.

## Verification
[x] pydantic-ai>=1.0.5 present in [project.dependencies]
[x] gemini optional group removed
[x] pydantic-ai optional group removed
[x] google-generativeai removed from dev deps
[x] ui and otel groups unchanged
[x] pydantic-ai still in dev deps
