# Step Inputs + Pipeline Adapters

## Context

Today, a step's behaviour is coupled to pipeline-level data flow in ways that prevent restructuring its output (e.g. renaming/splitting LLM output fields) without cascading breakage. The coupling points:

1. **Steps write to pipeline context** via `process_instructions()` returning a `{StepName}Context(PipelineContext)` subclass. Downstream steps and extractions then read `self.pipeline.context.<field>` — a name-level dependency on the step's internal output shape.
2. **Steps read pipeline context ambiently** via `self.pipeline.validated_input` and `self.pipeline.context.get(...)` in `prepare_calls()`, making input dependencies invisible and untyped.
3. **Extractions read pipeline context ambiently** the same way, plus chain via `self.pipeline.get_extractions(Model)`.

Net effect: restructuring a step's instructions class (a high-leverage lever for LLM behaviour — field names and descriptions are part of the prompt) requires coordinated edits across multiple files, cannot be tested in isolation, and cannot be expressed cleanly as a variant delta in evals.

This refactor moves inter-step data flow from implicit context-reads to explicit, declarative adapters owned by the pipeline strategy. Each step declares a typed `inputs` class listing everything its methods (prepare_calls, process_instructions, extractions, transformations) need. Strategies declare adapters that read from pipeline input + prior step outputs to produce these inputs — pure read-wiring, no computation except via an explicit `Computed` escape hatch.

## Architecture

### Data Flow

```
Pipeline input (INPUT_DATA, enriched by execute() override)
        │
        │  Strategy: List[Bind]
        ▼
    Step N Bind
        │
        │  inputs = {StepName}Inputs.sources(
        │      field_a=FromInput("..."),
        │      field_b=FromOutput(StepM),
        │      field_c=Computed(fn, FromOutput(StepK, "x"), FromInput("y")),
        │  )
        ▼
    Adapter resolution
        │
        │  walks source sentinels → materializes from ctx → constructs typed inputs
        ▼
    self.inputs → step executes (prepare_calls, LLM, process_instructions)
                │
                │  step produces list[Instructions]
                ▼
        Extraction N Bind (nested under step)
                │
                │  inputs = Extraction.From{Source}Inputs.sources(
                │      result=FromOutput(ThisStep),
                │      ...
                │  )
                ▼
        Adapter resolution → typed pathway inputs → dispatch to matching method
                                                      │
                                                      ▼
                                          list[MODEL] → pipeline registry
```

### Ownership

| Concern | Owner |
|---|---|
| What a step needs | Step (via `{StepName}Inputs` class) |
| How to produce a step's inputs | Strategy (via `Bind` + `.sources()`) |
| What an extraction pathway needs | Extraction (via nested `From{X}Inputs`) |
| How to produce an extraction's inputs | Strategy (via nested `Bind` + `.sources()`) |
| Pipeline-level input shape | Pipeline (`INPUT_DATA` unchanged) |
| Pipeline-level setup (DB lookups, resource construction) | Pipeline (`execute()` override, enriches input_data) |
| Framework ambient (session, logger) | Pipeline (`self.pipeline.session` etc. — unchanged) |

### Source Types (closed set)

- `FromInput(path: str)` — reads a field from validated pipeline input.
- `FromOutput(step_cls, index: int = 0, field: str | None = None)` — reads a prior step's output. `field=None` returns the whole instructions instance; otherwise returns `instructions.field`.
- `FromPipeline(attr: str)` — reads an ambient pipeline attribute (session, logger). Used rarely; prefer `FromInput` for pipeline-specific resources.
- `Computed(fn: Callable, *sources: Source)` — deferred function call. Sources resolve first, then `fn(*resolved)` produces the value.

## Implementation Phases

### Phase 1: Framework Foundations

**1a. New module `llm_pipeline/inputs.py`:**

- `PipelineInputs(BaseModel)` — base class for both step inputs and extraction pathway inputs.
- `__init_subclass__` hook:
  - Auto-generate a companion "sources" model via `pydantic.create_model()` with the same field names but all typed as `Source` (union of source types). Stored as `cls._sources_cls`.
  - Expose `.sources(**kwargs) -> _SourcesSpec` classmethod. Runtime validation: required fields present, values are Source instances, no unknown fields.
- Return type of `.sources(...)` is a `SourcesSpec[TInputs]` — holds the inputs class type + the field-to-source map. Used by adapters at resolve time.

**1b. New module `llm_pipeline/wiring.py`:**

- `Source` protocol/union type covering `FromInput | FromOutput | FromPipeline | Computed`.
- Each source as a frozen dataclass with a `resolve(ctx)` method:
  - `FromInput.resolve(ctx)` → `getattr(ctx.input, self.path)` (or dotted-path access)
  - `FromOutput.resolve(ctx)` → `ctx.outputs[self.step_cls][self.index]` or `.field` if specified
  - `FromPipeline.resolve(ctx)` → `getattr(ctx.pipeline, self.attr)`
  - `Computed.resolve(ctx)` → `self.fn(*[s.resolve(ctx) for s in self.sources])`
- `AdapterContext` — a small object passed to `resolve(ctx)`. Holds `input` (validated INPUT_DATA instance), `outputs` (dict keyed by step class → list of instructions), `pipeline` (for FromPipeline).

**1c. `Bind` dataclass:**

```python
@dataclass
class Bind:
    step: type[LLMStep] | None = None
    extraction: type[PipelineExtraction] | None = None
    inputs: SourcesSpec      # from .sources(...)
    extractions: list[Bind] = field(default_factory=list)  # nested; only valid when step is set
```

Validation at construction: exactly one of `step`/`extraction` set; `extractions` list non-empty only when `step` set; nested `Bind`s must have `extraction` set, not `step`.

**1d. Adapter resolver:**

- `resolve_inputs(spec: SourcesSpec, ctx: AdapterContext) -> PipelineInputs` — walks the field map, resolves each source, constructs the real (validated) inputs instance.
- Raises at adapter resolve time if any source fails (missing step output, missing input field, etc.). Loud failure, not silent None.

**1e. Static analysis hook:**

- `validate_bindings(bindings: list[Bind], input_cls: type[BaseModel]) -> None` — walks all bindings, verifies:
  - Every `FromOutput(step_cls, ...)` references a step that appears earlier in the binding list.
  - Every `FromInput(path)` references a valid field on the pipeline's INPUT_DATA class.
  - Every `FromOutput(step_cls, ..., field=X)` — if `field` specified, `X` is a field on the step's instructions class.
  - Every adapter's field set matches the target inputs class (required fields covered, no extras).
- Called at pipeline class creation time (or first strategy invocation) so errors surface at import, not runtime.

**Tests for Phase 1:**
- `PipelineInputs` companion auto-generation.
- `.sources()` runtime validation (wrong types, missing fields, unknown fields).
- Each `Source` type's `resolve()` behaviour.
- `validate_bindings` catches each failure class.
- `Computed` with stdlib fn (`sum`, `len`) and user fn.

**Files:**
- `llm_pipeline/inputs.py` (new)
- `llm_pipeline/wiring.py` (new)
- `tests/test_inputs.py` (new)
- `tests/test_wiring.py` (new)

---

### Phase 2: Step Contract Changes

**2a. `@step_definition` decorator** ([llm_pipeline/step.py:40-172](llm_pipeline/step.py)):

- Add `inputs: type[PipelineInputs]` kwarg.
- Validate `inputs.__name__ == f"{StepName}Inputs"` — matches existing naming enforcement style ([step.py:76-105](llm_pipeline/step.py)).
- Validate `inputs` is a `PipelineInputs` subclass.
- Store as `step_class.INPUTS` class attribute.
- **Remove `context` kwarg** and `{StepName}Context` naming enforcement ([step.py:91-97](llm_pipeline/step.py)). `PipelineContext` subclasses as a step concept go away.
- `create_definition(...)` carries the INPUTS type forward to `StepDefinition`.

**2b. `LLMStep` base class** ([llm_pipeline/step.py]):

- At step instance construction (called by the pipeline), the framework resolves the step's inputs via its Bind's adapter and sets `self.inputs: PipelineInputs` before `prepare_calls()` runs.
- `self.inputs` is typed via the INPUTS class attribute; subclasses get correct narrow type via the `@step_definition` decorator's class transform.
- `prepare_calls(self) -> List[StepCallParams]` — no signature change. Implementations read `self.inputs.*` instead of `self.pipeline.validated_input.*` / `self.pipeline.context.*`.
- **Remove `process_instructions` returning `PipelineContext`**. The method can still exist for in-step post-processing if needed, but its return value is no longer stored as pipeline context. Likely just delete the method from the base class entirely.
- `log_instructions` stays (pure side-effect, no return expected).
- `extract_data()` logic ([step.py:310-378](llm_pipeline/step.py)) adjusts to resolve each extraction's pathway inputs via its Bind's adapter rather than calling `extraction.extract(instructions)` with raw results.

**2c. Remove `PipelineContext` usage from step path:**

- `PipelineContext` ([llm_pipeline/context.py]) may survive if the pipeline's ambient dict-style context is still useful for other things (e.g. `execute()` enrichment before validation), but steps no longer read from or write to it.

**Tests for Phase 2:**
- Step declared without `inputs=` kwarg — decorator rejects.
- Step with misnamed inputs class (`ChargeAuditIn` vs `ChargeAuditInputs`) — rejects.
- Step with `context=` kwarg — rejects (deprecated).
- `self.inputs` is populated and typed before `prepare_calls` runs.
- Step no longer has `self.pipeline.context.X` access pattern (grep'd in tests or linted).

**Files:**
- `llm_pipeline/step.py`
- `llm_pipeline/context.py` (possibly reduced scope)
- `tests/test_step_definition.py`

---

### Phase 3: Extraction Contract Changes

**3a. `PipelineExtraction.__init_subclass__`** ([extraction.py:59-89](llm_pipeline/extraction.py)):

- After existing model/naming validation, walk `cls.__dict__` for nested classes that subclass `PipelineInputs`.
- Validate each nested inputs class name matches `From{Purpose}Inputs` pattern (regex `^From[A-Z][A-Za-z0-9]*Inputs$`).
- Walk `cls.__dict__` for public methods (excluding base methods + `extract`). For each:
  - Inspect signature, extract second positional arg's annotation.
  - Annotation must be a nested `PipelineInputs` subclass on this extraction.
  - Return annotation must be `list[cls.MODEL]`.
- Validate bijection: every pathway inputs class maps to exactly one method and vice versa.
- Store dispatch table: `cls._pathway_dispatch = {inputs_cls: method}`.
- Raise at class creation on any violation.

**3b. `PipelineExtraction.extract()`** ([extraction.py:218-285](llm_pipeline/extraction.py)):

- Replace current method-resolution logic (default / strategy-name-match / single-custom) with type dispatch.
- New signature: `extract(self, inputs: PipelineInputs) -> list[MODEL]` — takes resolved pathway inputs, dispatches via `self._pathway_dispatch[type(inputs)]`.
- Method is called with the inputs instance: `method(self, inputs)`.
- Existing validation (`_validate_instances`) still runs on results.

**3c. Extraction construction:**

- Keep `__init__(self, pipeline)` ([extraction.py:91](llm_pipeline/extraction.py)) — extractions still need pipeline reference for ambient access (`session`, etc.) and registry validation.
- No inputs stored on the instance; inputs flow through the `extract()` method parameter.

**Tests for Phase 3:**
- Extraction with correctly-named pathway inputs + methods → class creation succeeds, dispatch table built.
- Extraction with method signature missing inputs annotation → rejected.
- Extraction with two methods accepting the same inputs type → rejected.
- Extraction with pathway inputs class but no matching method → rejected.
- Dispatch routes correctly at runtime given an inputs instance.

**Files:**
- `llm_pipeline/extraction.py`
- `tests/test_extraction.py` (update)

---

### Phase 4: Strategy + Pipeline Contract Changes

**4a. `PipelineStrategy`** ([llm_pipeline/strategy.py]):

- Rename `get_steps()` → `get_bindings() -> list[Bind]`.
- `StepDefinition` dataclass may collapse or simplify — much of what it held (prompts, model, extractions list, transformation, context class) is now carried via the step class's decorator-stored attributes + the Bind's inputs spec. Review whether StepDefinition still adds value or becomes a thin adapter over Bind.
- `PipelineStrategies` unchanged structurally.

**4b. Pipeline execution path** ([llm_pipeline/pipeline.py]):

- Replace "get step definitions → execute each" with "get bindings → for each: resolve step inputs adapter → run step → resolve each extraction's pathway inputs adapter → dispatch extraction".
- `AdapterContext` populated progressively: `input` set from `validated_input` upfront; `outputs` populated after each step completes.
- Variant/eval runner ([evals/runner.py]) probably needs surgical changes — track separately but defer full eval integration to post-refactor.

**4c. Pipeline `execute()` enrichment:**

- Existing pattern (enrich `input_data` dict before super().execute()) is preserved.
- Enriched fields (e.g. `vendor_id` from vendor_code lookup) must be declared fields on `INPUT_DATA` so validated_input picks them up.
- `initial_context` parameter becomes largely unused for inter-step data — may be deprecated or repurposed.

**Tests for Phase 4:**
- Strategy returning bindings → pipeline resolves and executes them.
- Missing input field referenced by adapter → loud failure at pipeline class creation (via `validate_bindings`).
- Adapter producing invalid inputs (wrong types after resolution) → Pydantic validation error with clear context.
- Prior step output correctly flowing to downstream step's adapter.

**Files:**
- `llm_pipeline/strategy.py`
- `llm_pipeline/pipeline.py`
- `tests/test_pipeline_execution.py`

---

### Phase 5: In-Repo Pipelines (llm-pipeline itself)

Identify and migrate any demo/test pipelines that ship with llm-pipeline:
- Demo pipeline (loaded via `--demo` flag).
- Any pipelines in `tests/` that use the full stack.

Per pipeline, the migration is mechanical:
- Create `{StepName}Inputs(PipelineInputs)` in the step file.
- Rewrite `prepare_calls` to read `self.inputs`.
- Remove `{StepName}Context` subclass + `process_instructions` context return.
- Remove `context=` from `@step_definition`; add `inputs=`.
- Remove alias wrapper on instructions if present; inherit `LLMResultMixin` directly.
- In extraction files, convert to nested pathway inputs + typed methods.
- Rewrite strategy `get_steps()` → `get_bindings()` returning `Bind` list.

**Files:** TBD after inventory.

---

### Phase 6: Logistics-Intelligence Pipelines

Migrate each pipeline in `logistics_intelligence/llm_pipelines/pipelines/`:

- `charge_audit.py` — single step, one extraction. **Smallest — start here as the reference migration.**
- `invoice_parse.py` — single step, three chained extractions. Pressure test for nested extractions + DB-registry chaining.
- `discovery.py` — TBD (unread).
- `agentic_extraction.py` — TBD (unread).
- `unstructured_query.py` — TBD (unread).
- `file_resolver.py` — appears to be a utility, may not be a real pipeline.

Same mechanical migration as Phase 5. Expect ~2-4 hours per pipeline.

The two `InvoiceChargeExtraction` classes (in `charge_audit.py` and `invoice_parse.py`) collapse into one extraction with two nested pathway inputs. This is the clean-up of the existing smell.

**Files:** `logistics_intelligence/llm_pipelines/**/*.py`, plus any orchestrator code in `core/services/invoice_audit.py` that touches pipeline plumbing.

---

### Phase 7: Side Investigation — `get_extra()` and Tool Context

Before or during Phase 6, resolve how pipeline-specific tool contexts (e.g. `WorkbookContext`) flow to agents. Today:

- `pipeline.get_extra()` returns `{"workbook_context": <instance>}`.
- The agent system picks this up somewhere (need to trace).
- Under the new model, `workbook_context` is a pipeline input (built in `execute()` enrichment, declared on INPUT_DATA).

Investigation outcomes:
- If rewiring `get_extra()` to read from `self.validated_input` is trivial: do it.
- If it's load-bearing in the agent wiring: document and defer; `get_extra()` can stay temporarily as ambient, reading from validated input internally.

**Files:** `llm_pipeline/agent_builders.py`, `llm_pipeline/pipeline.py`, relevant tool context consumers.

---

### Phase 8: Cleanup + Deprecation

- Remove `PipelineContext` if no remaining consumers. If still used for ambient pipeline-run state, keep but document its narrower scope.
- Remove `context=` kwarg support from `@step_definition` entirely (was removed in Phase 2, verify no lingering references).
- Remove strategy-name-matching and single-method auto-detection in `PipelineExtraction` (replaced by type dispatch in Phase 3).
- Update `.claude/CLAUDE.md` architecture section.
- Update project README examples if they show the old shape.

---

## Sharp Edges / Risks

1. **Variant eval system breakage.** `evals/runner.py` builds a sandbox pipeline and applies variant deltas ([runner.py:382-505](llm_pipeline/evals/runner.py)). Delta shape today targets prompts/model/instructions_schema at the step level. After refactor, the step's contract includes `inputs`, extractions have pathway inputs. Variants that restructure the instructions class may need corresponding adapter updates to stay valid, and pathway identity matters for extraction variants. **Out of scope for this refactor** — flagged for follow-up work. Existing evals may break until that follow-up.

2. **Snapshot/audit layer.** `EvaluationRun.prompt_versions`, `model_snapshot`, `instructions_schema_snapshot` are captured at step granularity. Under new model these still make sense per step, but the snapshot should probably also capture the resolved `inputs` instance for full replay. **Out of scope** — flag for follow-up.

3. **`StepDefinition` dataclass** ([strategy.py]) may become redundant or need reshape. Decide during Phase 4 implementation — shouldn't block but worth an explicit call.

4. **Pipeline `execute()` override** pattern assumes enrichment goes into `input_data` before validation. Any existing enrichment that writes to `initial_context` dict post-validation needs to either move into `INPUT_DATA` as fields, or adapt. Audit during Phase 6.

5. **Test suite coverage.** The framework's own test suite may have pipelines using the old shape. Phase 5 covers this but worth a pre-flight audit to size the churn.

6. **Prompt YAML files.** If any prompt templates reference field names that match instructions-class fields being restructured, those templates need updating in lockstep. Not architecturally tricky, but a coordination point.

---

## Out of Scope

- Flattening extractions (unnest from step's Bind) — deferred per discussion; revisit if coupling pain surfaces post-refactor.
- Resolver/setup node types for pre-step DB lookups — deferred; `execute()` override enrichment handles current cases.
- Variant delta shape updates for eval system — deferred to a follow-up once pathway identity patterns settle.
- Snapshot layer updates to capture resolved inputs — deferred to follow-up.
- UI changes for displaying step inputs in eval comparison views — deferred to follow-up.
- Migrating alias-wrapper instructions classes to direct `LLMResultMixin` inheritance — done opportunistically during Phase 5/6 per-pipeline migration, not a standalone phase.

---

## Open Decisions

These don't block starting but should be nailed during implementation:

1. **`get_steps()` vs `get_bindings()` rename** — decided `get_bindings()` (parallels `Bind`). Confirm during Phase 4.
2. **`StepDefinition` fate** — collapse into `Bind`, keep as thin adapter, or keep as-is. Decide during Phase 4.
3. **`FromOutput` indexing** — current shape `FromOutput(step_cls, index=0, field=None)`. Should `field` support dotted paths (`"mappings.0.invoice_column"`) or only single-field access? Single for now; extend if cases arise.
4. **`.sources()` static hints strategy** — runtime validation only for now, reconsider stubs if autocomplete gap bites in practice.
5. **Where `validate_bindings()` fires** — at pipeline class creation (via metaclass) or at first run. Class creation is loudest/earliest; implement there unless metaclass interaction with existing `PipelineConfig` base is gnarly.
