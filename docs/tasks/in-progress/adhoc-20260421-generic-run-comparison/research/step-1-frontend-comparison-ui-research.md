# Frontend Comparison UI Research

## 1. Current Architecture

### Route Structure
```
/evals                                    -> evals.index.tsx (dataset list)
/evals/$datasetId                         -> evals.$datasetId.tsx (layout)
/evals/$datasetId/                        -> evals.$datasetId.index.tsx (dataset detail)
/evals/$datasetId/runs/$runId             -> evals.$datasetId.runs.$runId.tsx (run detail)
/evals/$datasetId/compare?baseRunId&variantRunId -> evals.$datasetId.compare.tsx (comparison)
/evals/$datasetId/variants/$variantId     -> variant editor
/evals/$datasetId/variants/new            -> new variant
```

### Comparison Page (`evals.$datasetId.compare.tsx`, 1891 lines)

**Search params** (TanStack Router + Zod):
```ts
const compareSearchSchema = z.object({
  baseRunId: fallback(z.coerce.number().int().positive(), 0).default(0),
  variantRunId: fallback(z.coerce.number().int().positive(), 0).default(0),
})
```
Both required; page shows error if either is 0.

**Data hooks used:**
| Hook | Purpose | Blocking? |
|------|---------|-----------|
| `useEvalRun(datasetId, baseRunId)` | Base run detail + case_results | Yes |
| `useEvalRun(datasetId, variantRunId)` | Variant run detail + case_results | Yes |
| `useDataset(datasetId)` | Dataset cases (for input/expected) | Graceful degrade |
| `useVariant(datasetId, variantRun.variant_id)` | Variant name/description | Non-blocking |
| `useDatasetProdPrompts(datasetId)` | Prod prompts for delta diff | Non-blocking |
| `useDatasetProdModel(datasetId)` | Prod model for delta diff | Non-blocking |
| `useInputSchema(targetType, targetName)` | Output schema for export | Non-blocking |
| `useAutoGenerateObjects()` | Enum catalog for export | Non-blocking |

**Case joining logic:**
- Builds `Map<string, CaseResultItem>` for both runs, keyed by `case_name`
- Union of all case names from both maps, sorted alphabetically
- `caseDelta(base, variant)` -> improved/regressed/unchanged/n/a based on `passed` + `error_message`

**Variant-specific coupling points (need changes for generic):**
1. **Delta summary card** - Builds before/after `EffectiveConfig` from prod config + `delta_snapshot`. Only renders when `deltaSnapshot != null` (variant runs only).
2. **UI labels** - "Baseline" / "Variant" hardcoded throughout header, stat cards, table headers, detail panels.
3. **Export META_PROMPT** - Variant iteration context prompt asking for `VariantDelta` JSON.
4. **Export payload shape** - `runs: { baseline: ExportRun, variant: ExportRun }` naming.
5. **Variant name display** - Shows variant name/id in header when `variantRun.variant_id != null`.

**Components (all defined inline in this file):**
| Component | Reusable as-is? | Notes |
|-----------|-----------------|-------|
| `DeltaBadge` | Yes | Generic numeric delta |
| `DeltaPctBadge` | Yes | Generic percentage delta |
| `PassFailBadge` | Yes | Generic pass/fail/error badge |
| `DeltaIndicator` | Yes | improved/regressed/unchanged text |
| `ScoresCell` | Yes | Evaluator scores display |
| `ComparisonStatCard` | Yes | Labels say "Base"/"Variant" (needs rename) |
| `CaseRow` | Mostly | Column headers say Baseline/Variant |
| `CaseDetailCard` | Mostly | Contains `BaselineOutputPanel`/`VariantOutputPanel` |
| `InputExpectedPanel` | Yes | Case input/expected display |
| `BaselineOutputPanel` | Rename needed | Label says "Baseline output" |
| `VariantOutputPanel` | Rename needed | Label says "Variant output", has diff logic |
| `ErrorBlock` | Yes | Generic error display |
| `JsonScroll` | Yes | Scroll wrapper |

**Helper functions:**
| Function | Reusable? | Notes |
|----------|-----------|-------|
| `passRate()` | Yes | |
| `formatPct()` | Yes | |
| `caseDelta()` | Yes | Core comparison logic |
| `isErrored()` | Yes | |
| `extractScoreValues()` | Yes | |
| `buildBefore()/buildAfter()` | No | Variant-specific config diff |
| `normalizeVarDefs()/mergeProdVarDefs()/applyVarDefsDelta()` | No | Variant-specific |
| `buildPayloadJSON()/buildPayloadMarkdown()` | Partially | Variant-coupled export |
| `aggregateComparisonTable()` | Yes | Labels say Baseline/Variant |
| `failingSummaryBanner()` | Yes | |

### Run Detail Page (`evals.$datasetId.runs.$runId.tsx`, 462 lines)

**Compare button logic:**
```ts
const isVariantRun = run?.variant_id != null
const baseline = isVariantRun ? findMostRecentBaseline(runsQ.data, runId) : null
const canCompare = isVariantRun && baseline != null
```
- Button ONLY rendered when `isVariantRun` is true
- Auto-selects baseline: `findMostRecentBaseline()` picks the most recent run where `variant_id == null`, excluding the current run
- Navigation: `{ baseRunId: baseline.id, variantRunId: runId }`

### API Layer (`api/evals.ts`)

**TS types out of sync with backend:**

Backend `RunListItem` includes (added by versioning-snapshots):
- `case_versions: Optional[dict]`
- `prompt_versions: Optional[dict]`
- `model_snapshot: Optional[dict]`
- `instructions_schema_snapshot: Optional[dict]`

Frontend `RunListItem` is missing all four fields. Frontend `RunDetail` extends `RunListItem`, also missing them.

**Hooks:** `useEvalRun` and `useEvalRuns` are generic; no comparison-specific API calls exist. All comparison logic is client-side.

### Query Keys (`api/query-keys.ts`)
Standard hierarchical pattern. No comparison-specific keys. Run data cached at `['evals', datasetId, 'runs', runId]`.

## 2. Backend Context

### EvaluationRun model fields relevant to comparison:
- `case_versions: Optional[dict]` - Maps `str(case_id)` -> version string (e.g. "1.0")
- `prompt_versions: Optional[dict]` - Prompt version snapshot at run time
- `model_snapshot: Optional[dict]` - Model config snapshot
- `instructions_schema_snapshot: Optional[dict]` - Instructions schema snapshot
- `variant_id: Optional[int]` - Non-null for variant runs
- `delta_snapshot: Optional[dict]` - Variant delta at run time

### EvaluationCase model:
- `version: str` - Default "1.0", bumped on case edits
- `name: str` - Used as join key in comparison
- `id: int` - Used as key in `case_versions` dict (as string)

### case_versions resolution path:
`case_versions` maps `str(case_id)` -> version. To check version match between runs for a given `case_name`:
1. Look up case in dataset to get `case_id`
2. Check `runA.case_versions[str(case_id)]` vs `runB.case_versions[str(case_id)]`
OR build a `name -> version` map upfront using dataset cases list.

## 3. Changes Required

### A. Frontend TS Types (api/evals.ts)
- Add to `RunListItem`: `case_versions`, `prompt_versions`, `model_snapshot`, `instructions_schema_snapshot`
- These flow through to `RunDetail` automatically

### B. Run Detail Page - Universal Compare Button
- Remove `isVariantRun` gate on compare button
- Remove `findMostRecentBaseline()` auto-select
- Add run picker: dialog/dropdown listing all completed runs for the dataset (excluding current)
- User selects target run, navigates to compare page
- Button text: "Compare..." (generic) instead of "Compare with baseline"

### C. Compare Page - Search Params
- Rename `baseRunId`/`variantRunId` -> `leftRunId`/`rightRunId` (or keep and treat as generic)
- Recommend: rename for clarity since semantics change

### D. Compare Page - Case Version Matching
New logic needed at the comparison page level:
```ts
type CaseMatchStatus = 'matched' | 'drifted' | 'unmatched'

function classifyCases(
  allCaseNames: string[],
  leftCaseVersions: Record<string, string> | null,
  rightCaseVersions: Record<string, string> | null,
  caseNameToId: Map<string, string>,
): Map<string, CaseMatchStatus>
```
- **matched**: same case_name exists in both runs, same version in both case_versions
- **drifted**: same case_name in both runs, different version
- **unmatched**: case_name only in one run's results
- When `case_versions` is null on a run (old runs before feature): treat as unknown, flag separately

### E. Compare Page - Scoped Aggregates
- Default: compute pass rate / passed / failed / errored only for matched cases
- Toggle: "Include all cases" / "Matched only" to switch scope
- Display total/matched/drifted/unmatched counts prominently

### F. Compare Page - Visual Updates
- Per-case table: add match status column/indicator (badge or icon)
- Drifted cases: visual warning (amber badge)
- Unmatched cases: visual indicator (gray/muted badge)
- Filter/sort by match status
- Rename all "Baseline"/"Variant" labels to "Left"/"Right" or "Run A"/"Run B"

### G. Delta Summary Card
- **Variant runs**: keep current behavior (prod config + delta_snapshot diff)
- **Non-variant runs**: show model_snapshot diff between the two runs, or prompt_versions diff
- If both runs have no snapshots (old runs): hide card or show "no config diff available"

### H. Export Updates
- META_PROMPT: detect variant comparison vs generic, use appropriate prompt
- Payload shape: rename `baseline`/`variant` keys or make generic
- Markdown: update labels throughout

## 4. Reuse Summary

### Fully reusable (no changes):
- `DeltaBadge`, `DeltaPctBadge`, `PassFailBadge`, `DeltaIndicator`
- `ScoresCell`, `ErrorBlock`, `JsonScroll`, `InputExpectedPanel`
- `caseDelta()`, `passRate()`, `formatPct()`, `isErrored()`, `extractScoreValues()`
- All TanStack Query hooks (`useEvalRun`, `useDataset`, etc.)
- Export infrastructure (clipboard, download, warning dialog, size check)
- `aggregateComparisonTable()` (with label param change)

### Needs label/naming changes only:
- `ComparisonStatCard` - "Base"/"Variant" labels
- `CaseRow` table headers
- `BaselineOutputPanel` / `VariantOutputPanel` - rename + label change
- `CaseDetailCard` - pass renamed sub-components
- Compare page header text
- Export payload keys and markdown labels

### Needs functional changes:
- Run detail page: compare button + run picker (new component)
- Compare page: case version matching classification (new logic)
- Compare page: scoped aggregate computation (new logic)
- Compare page: match status display in per-case table (new column)
- Delta summary card: conditional rendering based on run type
- Export: conditional META_PROMPT

### Entirely new:
- Run picker dialog component
- `classifyCases()` utility function
- Match status badge/indicator component
- Aggregate scope toggle UI
- `case_versions` fields in frontend TS types

## 5. Questions for CEO

1. **Search param naming**: Rename `baseRunId`/`variantRunId` to `leftRunId`/`rightRunId`? Or keep existing names to preserve backward compatibility with any bookmarked URLs?

2. **Run labels in comparison**: What should replace "Baseline"/"Variant" for generic comparisons? Options: (a) "Run A"/"Run B", (b) "Left"/"Right", (c) "Older"/"Newer" (based on started_at), (d) keep "Baseline"/"Variant" but make it configurable?

3. **Delta summary card for non-variant runs**: Should we (a) show model_snapshot + prompt_versions diff between the two runs, (b) hide the card entirely, or (c) show a simplified "config diff" if snapshots differ?

4. **Export for non-variant comparisons**: The current META_PROMPT is variant-iteration-focused ("propose a variant delta"). For generic comparison, should we (a) use a neutral comparison prompt, (b) skip the meta-prompt entirely, (c) detect variant vs generic and branch?
