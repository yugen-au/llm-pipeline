# IMPLEMENTATION - STEP 5: LIVE.TSX INTEGRATION
**Status:** completed

## Summary
Wired InputForm into live.tsx: replaced placeholder div with real component, added form state management (inputValues, fieldErrors), integrated usePipeline for schema fetch, added frontend validation + 422 error mapping in handleRunPipeline, and reset form on pipeline change and successful run.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/src/routes/live.tsx
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/routes/live.tsx`

Added imports for InputForm, validateForm, usePipeline, and ApiError.

```
# Before
import { useCreateRun } from '@/api/runs'

# After
import { useCreateRun } from '@/api/runs'
import { usePipeline } from '@/api/pipelines'
...
import { ApiError } from '@/api/types'
import { InputForm, validateForm } from '@/components/live/InputForm'
```

Added inputValues/fieldErrors state, usePipeline query, inputSchema derivation.

```
# Before
const [selectedPipeline, setSelectedPipeline] = useState<string | null>(null)
const [activeRunId, setActiveRunId] = useState<string | null>(null)

# After
const [selectedPipeline, setSelectedPipeline] = useState<string | null>(null)
const [activeRunId, setActiveRunId] = useState<string | null>(null)
const [inputValues, setInputValues] = useState<Record<string, unknown>>({})
const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
...
const { data: pipelineDetail } = usePipeline(selectedPipeline ?? '')
const inputSchema = pipelineDetail?.pipeline_input_schema ?? null
```

Updated handleRunPipeline: frontend validation, input_data passing, form reset on success, 422 error mapping on error.

```
# Before
createRun.mutate({ pipeline_name: selectedPipeline }, { onSuccess: ... })

# After
const errors = validateForm(inputSchema, inputValues)
if (Object.keys(errors).length > 0) { setFieldErrors(errors); return }
setFieldErrors({})
createRun.mutate(
  { pipeline_name: selectedPipeline, input_data: inputSchema ? inputValues : undefined },
  { onSuccess: ...(+ reset inputValues/fieldErrors), onError: ...(422 parsing) }
)
```

Replaced placeholder with InputForm component.

```
# Before
<div data-testid="input-form-placeholder" />

# After
<InputForm schema={inputSchema} values={inputValues} onChange={...} fieldErrors={fieldErrors} isSubmitting={createRun.isPending} />
```

Added useEffect to reset form on pipeline selection change.

## Decisions
### 422 error parsing approach
**Choice:** Wrap JSON.parse(error.detail) in try/catch, silently ignore unparseable detail
**Rationale:** ApiError.detail is typed as string; for 422s from Pydantic it contains a JSON array. If parsing fails (non-Pydantic 422), no field errors are shown -- graceful degradation. No new error classes needed.

### Form reset strategy
**Choice:** useEffect on selectedPipeline dependency to reset both inputValues and fieldErrors
**Rationale:** Simplest approach -- when user switches pipeline, previous form data is irrelevant since schema changes. Also reset on successful run creation for clean slate.

## Verification
[x] TypeScript type-check passes (npm run type-check)
[x] InputForm renders null when schema is null (pipeline_input_schema always null until Task 43)
[x] data-testid="input-form-placeholder" replaced with InputForm component
[x] input_data passed in createRun.mutate only when inputSchema is non-null
[x] Form values reset on success and on pipeline change
[x] 422 structured errors parsed and mapped to fieldErrors
[x] Frontend validateForm called before mutation
