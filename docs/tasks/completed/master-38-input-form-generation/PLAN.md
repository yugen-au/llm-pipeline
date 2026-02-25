# PLANNING

## Summary

End-to-end implementation of InputForm for pipeline runs: a pure React component that renders form fields from a flat JSON Schema prop, backend TriggerRunRequest extension with optional `input_data`, threading of `input_data` as `initial_context` via the factory call, and `pipeline_input_schema` exposure on PipelineMetadata. Hybrid validation: frontend required-field checks + backend Pydantic 422 per-field errors. Zero new dependencies.

## Plugin & Agents

**Plugin:** frontend-mobile-development (frontend steps), python-development (backend steps)
**Subagents:** [available agents]
**Skills:** none

## Phases

1. **Backend + shadcn primitives**: Install missing shadcn UI components; add `input_data` to TriggerRunRequest + `pipeline_input_schema` to PipelineMetadata backend; thread input_data through factory call
2. **TS types + InputForm component**: Update TS interfaces to match new backend shapes; implement InputForm + FormField subcomponents
3. **live.tsx integration**: Replace input-form-placeholder with InputForm; wire input_data into handleRunPipeline; map 422 errors to inline field messages

## Architecture Decisions

### input_data threading via factory kwargs

**Choice:** `trigger_run()` passes `input_data=body.input_data` to factory as a keyword argument. Factory is responsible for merging it into `initial_context` when calling `pipeline.execute(data=..., initial_context=merged_context)`. The background closure changes from `pipeline.execute()` to `pipeline.execute(data=None, initial_context=body.input_data or {})` as a fallback for pipelines whose factory-returned object does not pre-bind args.

**Rationale:** Existing test factories already use `**kw` (confirmed in test_runs.py L161, L211) so passing `input_data=body.input_data` is backwards-compatible. The factory callable signature `(run_id, engine, event_emitter=None, **kw)` already absorbs unknown kwargs. For pipelines using PipelineConfig.execute() directly, the no-arg call `pipeline.execute()` is replaced with `pipeline.execute(data=None, initial_context=body.input_data or {})` -- this requires making `data` optional (default `None`) in `PipelineConfig.execute()`.

**Alternatives:** Restructure factory contract to always accept `input_data` (rejected: too invasive, not minimal). Add a setter `pipeline.set_initial_context(input_data)` before execute (rejected: adds API surface). Keep zero-arg execute and store input_data in app.state per-run (rejected: not thread-safe).

### PipelineConfig.execute() data param default

**Choice:** Make `data: Any = None` and `initial_context: Dict[str, Any] = None` with `initial_context = initial_context or {}` guard inside execute(). This allows trigger_run() to call `pipeline.execute(initial_context=body.input_data or {})` without breaking existing callers that pass explicit args.

**Rationale:** Existing tests all pass `data="test data", initial_context={}` explicitly -- adding defaults does not change their behaviour. trigger_run() currently calls `pipeline.execute()` with zero args (confirmed runs.py L223) which already works in tests via mock factories; making defaults explicit aligns the real signature with the assumed no-arg call.

**Alternatives:** Keep required params and always pass both (requires knowing what `data` value to use at HTTP layer -- not possible generically). Keep zero-arg pattern with a subclass execute (too invasive).

### pipeline_input_schema exposure

**Choice:** Add `pipeline_input_schema: Optional[Dict[str, Any]] = None` to `PipelineMetadata` backend model (pipelines.py) and TS interface (types.ts). The GET /api/pipelines/{name} endpoint already calls `PipelineIntrospector.get_metadata()` and constructs `PipelineMetadata(**metadata)`. For Task 38, the field is always `None` (PipelineInputData not yet implemented by Task 43). The field is present so the TS type and InputForm prop can reference it without future breaking changes.

**Rationale:** Decouples InputForm from schema source. InputForm receives `schema: JsonSchema | null` which maps to `pipeline_input_schema`. When Task 43 lands, only the introspector and response model need updating -- InputForm and live.tsx require no changes.

**Alternatives:** No field until Task 43 (rejected: requires live.tsx changes in Task 43 to add new prop). Use a separate endpoint GET /api/pipelines/{name}/input-schema (rejected: over-engineering for a null field stub).

### InputForm component design

**Choice:** `InputForm` is a pure component: `schema: JsonSchema | null`, `onSubmit: (data: Record<string, unknown>) => void`, `isSubmitting: boolean`, `fieldErrors: Record<string, string>`. When `schema` is null, renders nothing (returns null). FormField subcomponents handle type dispatch: `string` -> Input, `integer`/`number` -> Input[type=number], `boolean` -> Checkbox, `object`/`array` -> Textarea (JSON). Required indicator derived from `schema.required` array.

**Rationale:** Pure component with no internal query calls is testable with synthetic schemas (no Task 43 dependency). fieldErrors prop enables parent (live.tsx) to pass mapped 422 error messages without the component knowing about API errors. isSubmitting mirrors createRun.isPending passed from parent.

**Alternatives:** InputForm owns the usePipeline() call internally (rejected: couples component to API, harder to test). Use a single Textarea for all inputs when no schema (rejected: out of scope per research note 9).

### Shadcn component installation approach

**Choice:** Install `input`, `label`, `checkbox`, `textarea` components using `npx shadcn add <component>` from the frontend directory. These are shadcn CLI-generated files written into `src/components/ui/`.

**Rationale:** Consistent with existing shadcn components (badge, button, card, etc.) which are all in src/components/ui/. The project already has `shadcn@3.8.5` as a dev dependency (package.json L55). Install at start of frontend work to unblock InputForm component authoring.

**Alternatives:** Hand-author Input/Label/Checkbox/Textarea without shadcn (rejected: inconsistent with design system, more work, style drift risk).

### 422 error mapping

**Choice:** In live.tsx, `handleRunPipeline` catches `ApiError` with status 422. Pydantic v2 returns `{ detail: [{ loc: [..., "field_name"], msg: "...", type: "..." }] }`. Frontend parses `error.detail` as JSON (or uses the structured payload if already parsed), maps each `{ loc, msg }` to `{ [loc[loc.length - 1]]: msg }`, and stores in `fieldErrors` state passed to InputForm.

**Rationale:** Pydantic v2 native 422 format is `detail` as an array of `{ loc, msg, type }` objects. `loc[-1]` gives the field name. ApiError class already stores `detail: string` -- but for structured 422s the detail is a JSON array. We extend ApiError handling: on 422, attempt `JSON.parse(error.detail)` and extract field errors. No new deps.

**Alternatives:** Display 422 errors as a toast/banner (rejected: CEO specified per-field inline messages). Add a new `ApiValidationError` class (rejected: over-engineering for this scope).

## Implementation Steps

### Step 1: Install shadcn UI primitives

**Agent:** frontend-mobile-development subagent
**Skills:** none
**Context7 Docs:** /shadcn-ui/ui
**Group:** A

1. From `llm_pipeline/ui/frontend/` run `npx shadcn add input label checkbox textarea`
2. Confirm generated files exist: `src/components/ui/input.tsx`, `src/components/ui/label.tsx`, `src/components/ui/checkbox.tsx`, `src/components/ui/textarea.tsx`
3. No manual edits needed -- shadcn CLI generates complete components

### Step 2: Backend model + endpoint changes

**Agent:** python-development subagent
**Skills:** none
**Context7 Docs:** /fastapi/fastapi
**Group:** A

1. In `llm_pipeline/ui/routes/runs.py`: extend `TriggerRunRequest` to add `input_data: Optional[Dict[str, Any]] = None` (import `Dict`, `Any` from `typing` -- already imported via existing `Optional`)
2. In `llm_pipeline/ui/routes/runs.py` `run_pipeline()` closure: change `pipeline.execute()` to `pipeline.execute(data=None, initial_context=body.input_data or {})` and pass `input_data=body.input_data` in the factory call: `factory(run_id=run_id, engine=engine, event_emitter=bridge, input_data=body.input_data or {})`
3. In `llm_pipeline/pipeline.py` `PipelineConfig.execute()`: change `data: Any` to `data: Any = None` and `initial_context: Dict[str, Any]` to `initial_context: Optional[Dict[str, Any]] = None`, add guard `if initial_context is None: initial_context = {}` as first line of execute body
4. In `llm_pipeline/ui/routes/pipelines.py`: add `pipeline_input_schema: Optional[Any] = None` field to `PipelineMetadata` model. In `get_pipeline()` endpoint the existing `PipelineMetadata(**metadata)` call works as-is since the new field defaults to None (introspector does not return it yet)

### Step 3: TS types update

**Agent:** frontend-mobile-development subagent
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. In `llm_pipeline/ui/frontend/src/api/types.ts`: extend `TriggerRunRequest` interface to add `input_data?: Record<string, unknown>`
2. In `llm_pipeline/ui/frontend/src/api/types.ts`: extend `PipelineMetadata` interface to add `pipeline_input_schema: Record<string, unknown> | null`
3. In `llm_pipeline/ui/frontend/src/api/types.ts`: add `JsonSchema` type alias: `export type JsonSchema = Record<string, unknown>` (used by InputForm prop type; kept minimal since full JSON Schema typing is out of scope)

### Step 4: InputForm component

**Agent:** frontend-mobile-development subagent
**Skills:** none
**Context7 Docs:** /shadcn-ui/ui
**Group:** B

1. Create `llm_pipeline/ui/frontend/src/components/live/InputForm.tsx` -- pure component, no internal API calls
   - Props: `schema: JsonSchema | null`, `values: Record<string, unknown>`, `onChange: (field: string, value: unknown) => void`, `fieldErrors: Record<string, string>`, `isSubmitting: boolean`
   - When `schema` is null, return null
   - Render a `<form>` with `onSubmit` prevented (submission is via Run button in parent, not form submit)
   - Iterate `Object.entries(schema.properties ?? {})` to render fields
   - Required indicator: `(schema.required ?? []).includes(fieldName)`
2. Create `llm_pipeline/ui/frontend/src/components/live/FormField.tsx` -- renders a single field
   - Dispatch on `schema.type`: `string` -> `<Input>`, `integer`/`number` -> `<Input type="number">`, `boolean` -> `<Checkbox>`, default (object/array/unknown) -> `<Textarea>` with JSON hint
   - Props: `name: string`, `fieldSchema: JsonSchema`, `value: unknown`, `onChange: (value: unknown) => void`, `error: string | undefined`, `required: boolean`
   - Use `<Label>` for field label with required asterisk when required
   - Show `error` as `<p className="text-sm text-destructive">` below field when present
   - Derive label from `fieldSchema.title ?? name` (Pydantic v2 sets `title` from field name)
   - Derive description from `fieldSchema.description` if present, render as `<p className="text-xs text-muted-foreground">`
3. Frontend required validation: InputForm exports a `validateForm(schema, values)` helper that returns `Record<string, string>` with error messages for missing required fields. Called by parent before invoking onSubmit. Returns `{}` when valid.

### Step 5: live.tsx integration

**Agent:** frontend-mobile-development subagent
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. In `llm_pipeline/ui/frontend/src/routes/live.tsx`: add import for `InputForm` and `validateForm` from `@/components/live/InputForm`
2. Add import for `usePipeline` from `@/api/pipelines`
3. Add state: `const [inputValues, setInputValues] = useState<Record<string, unknown>>({})` and `const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})`
4. Add: `const { data: pipelineDetail } = usePipeline(selectedPipeline ?? '')` -- disabled when null via `enabled: Boolean(selectedPipeline)` (already handled in usePipeline hook)
5. Extract schema: `const inputSchema = pipelineDetail?.pipeline_input_schema ?? null`
6. Update `handleRunPipeline` callback:
   - Run `validateForm(inputSchema, inputValues)` and set field errors if non-empty, return early
   - Clear field errors before submit
   - Pass `input_data: inputSchema ? inputValues : undefined` in `createRun.mutate({ pipeline_name: selectedPipeline, input_data: ... })`
   - In `onSuccess` callback: also call `setInputValues({})` and `setFieldErrors({})` to reset form
   - Add `onError` callback: on `ApiError` with status 422, attempt to parse structured field errors from `error.detail` (try `JSON.parse(error.detail)`, extract `loc[-1]` -> msg pairs), call `setFieldErrors(...)`
7. Replace `<div data-testid="input-form-placeholder" />` with:
   ```
   <InputForm
     schema={inputSchema}
     values={inputValues}
     onChange={(field, value) => setInputValues(prev => ({ ...prev, [field]: value }))}
     fieldErrors={fieldErrors}
     isSubmitting={createRun.isPending}
   />
   ```
8. Update `handleRunPipeline` to be disabled when `createRun.isPending` OR when `inputSchema` has required fields not yet filled (frontend required validation gate already covers this)

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| PipelineConfig.execute() data=None causes runtime errors in downstream code that assumes data is non-None | High | Audit execute() body for `data` usages before adding default; add `if data is None: data = {}` guard if needed (step 2 substep 3) |
| Existing factories do not accept `input_data` kwarg and fail on unexpected kwargs | Medium | Existing tests already use `**kw` pattern; document in step 2 that user factories must accept `**kwargs`. Risk only affects user-defined factories outside the test suite |
| shadcn CLI adds conflicting Tailwind config or overwrites existing ui components | Low | Review generated files before accepting; confirm only net-new files are created |
| 422 `error.detail` from ApiError is a string not a parsed object, JSON.parse may fail | Medium | Wrap JSON.parse in try/catch; fall back to displaying `error.message` as a banner if parsing fails |
| usePipeline(selectedPipeline) fires on every pipeline selection change, causing flash of null schema | Low | pipeline_input_schema is always null in Task 38 scope -- InputForm renders nothing either way. No visible regression |
| InputForm renders with no schema when Task 43 is not yet complete | Low | Expected -- InputForm renders null when schema is null. UX is identical to current state (no form fields shown) |

## Success Criteria

- [ ] `TriggerRunRequest` backend accepts `input_data: Optional[dict]` without breaking existing tests
- [ ] `pipeline.execute()` can be called with zero args or with `initial_context` kwarg without errors
- [ ] `input_data` from POST /api/runs body is forwarded to factory call as `input_data` kwarg
- [ ] `PipelineMetadata` backend model and TS interface both have `pipeline_input_schema` field (null for now)
- [ ] shadcn `input`, `label`, `checkbox`, `textarea` components exist in `src/components/ui/`
- [ ] `InputForm` renders null when `schema` is null
- [ ] `InputForm` renders correct field type for string, number, boolean, and default (object/array) JSON Schema types
- [ ] Required fields show visual indicator; submitting with empty required field sets `fieldErrors`
- [ ] `createRun.mutate` call in live.tsx passes `input_data` when schema is non-null
- [ ] Form values reset to `{}` after successful run creation
- [ ] 422 structured field errors from backend are mapped to inline per-field messages in InputForm
- [ ] `data-testid="input-form-placeholder"` div is replaced by `<InputForm>` in live.tsx
- [ ] All existing Python tests pass (`pytest`)
- [ ] No TypeScript errors (`npm run type-check`)

## Phase Recommendation

**Risk Level:** medium
**Reasoning:** The backend changes (execute() default params, factory kwargs threading) touch well-tested core pipeline code and could affect existing tests. The factory threading pattern relies on an assumption about `**kwargs` usage in user factories. 422 structured error parsing adds a fragile JSON.parse dependency. The frontend work is lower risk. Overall medium due to the backend surface changes.
**Suggested Exclusions:** review
