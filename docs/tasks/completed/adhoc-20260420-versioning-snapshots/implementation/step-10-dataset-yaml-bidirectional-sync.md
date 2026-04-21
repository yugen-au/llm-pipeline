# IMPLEMENTATION - STEP 10: DATASET YAML BIDIRECTIONAL SYNC
**Status:** completed

## Summary
Wired DB->YAML writeback trigger to PUT /evals/{dataset_id} and added version field to YAML output in write_dataset_to_yaml. The sync loop (get_latest + save_new_version + WARNING no-op) and CW1/CW2/CW3 triggers were already implemented by Step 8.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/routes/evals.py, llm_pipeline/evals/yaml_sync.py
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/evals.py`
Added `request: Request` param to update_dataset endpoint and called `_trigger_evals_writeback(request, dataset_id)` after commit (section 6.4 PUT /evals/{dataset_id}).

### File: `llm_pipeline/evals/yaml_sync.py`
Added `"version": c.version` to the per-case YAML output dict in write_dataset_to_yaml so the version field round-trips through YAML (section 6.2).

## Decisions
### Minimal diff approach
**Choice:** Only added missing pieces (PUT writeback + version in output)
**Rationale:** Step 8 already implemented the sync loop rewrite, CW1/CW2/CW3 triggers, and version reading from YAML. Avoided duplicating or conflicting with that work.

## Verification
[x] PUT /evals/{dataset_id} now triggers _trigger_evals_writeback
[x] write_dataset_to_yaml includes version field per case
[x] All evals + prompts tests pass (32 passed)
[x] Pre-existing sandbox test failure unrelated to changes
