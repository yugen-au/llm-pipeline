# IMPLEMENTATION - STEP 1: MOVE COMPARE_VERSIONS TO UTILS
**Status:** completed

## Summary
Extracted `compare_versions` from `llm_pipeline/prompts/yaml_sync.py` into a new shared utility module `llm_pipeline/utils/versioning.py`. Updated all imports. Added dedicated unit tests.

## Files
**Created:** `llm_pipeline/utils/__init__.py`, `llm_pipeline/utils/versioning.py`, `tests/test_versioning_helpers.py`
**Modified:** `llm_pipeline/prompts/yaml_sync.py`, `llm_pipeline/prompts/__init__.py`, `tests/prompts/test_yaml_sync.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/utils/versioning.py`
New module containing `compare_versions(a, b) -> int` — dot-separated numeric version comparison with zero-padding for unequal depth.

### File: `llm_pipeline/utils/__init__.py`
New package init with docstring.

### File: `llm_pipeline/prompts/yaml_sync.py`
Removed inline `compare_versions` definition; added `from llm_pipeline.utils.versioning import compare_versions`.

### File: `llm_pipeline/prompts/__init__.py`
Re-export `compare_versions` from `llm_pipeline.utils.versioning` instead of `yaml_sync` (preserves public API).

### File: `tests/prompts/test_yaml_sync.py`
Updated import to `from llm_pipeline.utils.versioning import compare_versions`.

### File: `tests/test_versioning_helpers.py`
New test file with 11 test cases covering: basic ordering, numeric vs lexicographic, major dominance, unequal depth, zero-padding, single/multi segment, large minor versions.

## Decisions
### Re-export from prompts/__init__.py
**Choice:** Keep `compare_versions` in `llm_pipeline.prompts.__all__` re-exported from new location
**Rationale:** Maintains backward compatibility for any downstream code importing from `llm_pipeline.prompts`

## Verification
[x] `compare_versions` removed from yaml_sync.py
[x] `compare_versions` present in utils/versioning.py with identical logic
[x] grep confirms no remaining direct imports from yaml_sync
[x] `uv run pytest tests/test_versioning_helpers.py` — 11 passed
[x] `uv run pytest tests/prompts/test_yaml_sync.py` — 25 passed
[x] All 36 tests pass together
