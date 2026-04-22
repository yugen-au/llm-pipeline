# IMPLEMENTATION - STEP 2: SYNC FRONTEND TS TYPES
**Status:** completed

## Summary
Added snapshot fields to RunListItem and case_id to CaseResultItem in frontend TS types, mirroring backend models from the versioning-snapshots feature.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/src/api/evals.ts
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/api/evals.ts`
Added 4 snapshot fields to `RunListItem` interface and `case_id` to `CaseResultItem`.

```
# Before (RunListItem)
  variant_id: number | null
  delta_snapshot: Record<string, unknown> | null
}

# After (RunListItem)
  variant_id: number | null
  delta_snapshot: Record<string, unknown> | null
  case_versions: Record<string, string> | null
  prompt_versions: Record<string, unknown> | null
  model_snapshot: Record<string, unknown> | null
  instructions_schema_snapshot: Record<string, unknown> | null
}
```

```
# Before (CaseResultItem)
  id: number
  case_name: string

# After (CaseResultItem)
  id: number
  case_id: number
  case_name: string
```

## Decisions
### case_versions typed as Record<string, string>
**Choice:** Used `Record<string, string>` instead of `Record<string, unknown>` for `case_versions`
**Rationale:** Backend stores `{str(case_id): version_string}` -- both keys and values are strings. Stronger typing enables direct version comparison in Step 6 without casts.

## Verification
[x] RunListItem has all 4 new fields with correct nullable types
[x] CaseResultItem has case_id: number
[x] RunDetail extends RunListItem -- inherits new fields automatically, no change needed
