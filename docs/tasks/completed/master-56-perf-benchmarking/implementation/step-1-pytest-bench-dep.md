# IMPLEMENTATION - STEP 1: PYTEST-BENCH-DEP
**Status:** completed

## Summary
Added pytest-benchmark>=4.0 to dev dependencies and configured pytest to skip benchmarks by default via --benchmark-skip addopts.

## Files
**Created:** none
**Modified:** pyproject.toml
**Deleted:** none

## Changes
### File: `pyproject.toml`
Added pytest-benchmark to dev deps and --benchmark-skip to pytest config.
```
# Before
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "google-generativeai>=0.3.0",
    ...
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]

# After
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "pytest-benchmark>=4.0",
    "google-generativeai>=0.3.0",
    ...
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "--benchmark-skip"
```

## Decisions
None

## Verification
[x] pytest-benchmark 5.2.3 installed successfully via pip install -e ".[dev]"
[x] pytest --co collects all 804 tests with no errors (--benchmark-skip active)
[x] No existing tests broken by new addopts setting
