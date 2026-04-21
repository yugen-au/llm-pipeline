# IMPLEMENTATION - STEP 7: PROMPT WRITE-SITE + YAML SYNC
**Status:** completed

## Summary
Replaced all prompt write sites (create, update, delete) to route through versioning helpers (save_new_version, soft_delete_latest). Upgraded YAML sync to version-aware insert logic with WARNING log on same/older version. Ported write_prompt_to_yaml to atomic temp-file + Path.replace pattern. Updated creator seed and integrator to use versioning helpers. Added is_latest copy-through in sandbox seed.

## Files
**Created:** docs/tasks/in-progress/adhoc-20260420-versioning-snapshots/implementation/step-7-prompt-write-site-yaml-sync.md
**Modified:** llm_pipeline/ui/routes/prompts.py, llm_pipeline/prompts/yaml_sync.py, llm_pipeline/creator/prompts.py, llm_pipeline/creator/integrator.py, llm_pipeline/sandbox.py, tests/prompts/test_yaml_sync.py
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/prompts.py`
W1: create_prompt now builds key_filters + new_fields and calls save_new_version.
W2: update_prompt uses get_latest to find current row, builds new_fields overlay, calls save_new_version (auto-bump or explicit version).
W3: delete_prompt calls soft_delete_latest instead of manual is_active=False mutation.
Removed _increment_version import (no longer needed).

### File: `llm_pipeline/prompts/yaml_sync.py`
W4: sync_yaml_to_db rewritten to use get_latest + save_new_version for inserts/updates; same/older version logs WARNING per A8.
write_prompt_to_yaml ported to atomic temp-file + Path.replace pattern using tempfile.mkstemp in same directory.

### File: `llm_pipeline/creator/prompts.py`
W5: _seed_prompts uses get_latest + save_new_version; content-hash delta gating preserved; removed unused `select` import.

### File: `llm_pipeline/creator/integrator.py`
W6: _insert_prompts uses get_latest + save_new_version with version fallback to "1.0"; removed unused `select` import.

### File: `llm_pipeline/sandbox.py`
W7: Added is_latest copy-through on seeded Prompt rows.

### File: `tests/prompts/test_yaml_sync.py`
Added test #13 (yaml_newer_inserts_version_and_flips_prior) and test #14 (yaml_older_or_equal_logs_warning_noop).
Fixed existing test_yaml_newer_updates_db to query by is_latest=True (new append-only behavior).

## Decisions
### Versioning helper used everywhere
**Choice:** All write sites delegate to save_new_version/soft_delete_latest; no direct Prompt construction in write paths.
**Rationale:** Single mediation point for version writes per architecture decision A4.

### Atomic YAML writer
**Choice:** tempfile.mkstemp in same dir + Path.replace for write_prompt_to_yaml.
**Rationale:** Same pattern as write_dataset_to_yaml; prevents partial-write corruption per PLAN section 6.5.

## Verification
[x] tests/prompts/test_yaml_sync.py -- 27 passed
[x] Full test suite -- no new failures (15 pre-existing failures unrelated to changes)
[x] New tests #13, #14 verify version insert+flip and WARNING log noop
