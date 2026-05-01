# Per-artifact architecture

A spec-driven, kind-keyed, dispatch-uniform foundation for in-UI editing of every artifact under `llm_pipelines/`.

Diagrams accompany this doc:
- [docs/architecture/diagrams/per-artifact-01-system.mmd](../../docs/architecture/diagrams/per-artifact-01-system.mmd) — code ↔ spec ↔ registry ↔ API ↔ UI
- [docs/architecture/diagrams/per-artifact-02-click-dispatch.mmd](../../docs/architecture/diagrams/per-artifact-02-click-dispatch.mmd) — universal `(kind, name)` resolution
- [docs/architecture/diagrams/per-artifact-03-adding-a-kind.mmd](../../docs/architecture/diagrams/per-artifact-03-adding-a-kind.mmd) — backend (5) + frontend (3) checklist for a new kind

---

## 1. Context

This plan supersedes the original `per-pipeline validation surfacing` plan. That plan was scoped to making each pipeline an independent unit. While working through it we realised pipelines aren't the right granularity — every artifact under `llm_pipelines/` (constants, enums, schemas, tables, tools, steps, extractions, reviews, pipelines, and future kinds like evals) is independently editable in the UI. Pipelines are one workflow on top of a generic per-artifact foundation; evals are another; future verticals (sandboxes, datasets-as-artifacts, scheduled jobs, etc.) plug in the same way.

The shift is from pipeline-first to artifact-first.

The capture/validation foundation we already built (per-class `_init_subclass_errors`, localised issues on spec components, `build_pipeline_spec` never raises) is reusable. The spec layer needs reshaping — currently `PipelineSpec.nodes[i]` mixes a step's class contract with its pipeline-level wiring; for per-step editing those need to be separate.

---

## 2. Principles

1. **Every artifact is independently editable.** Constants, enums, schemas, prompts, steps, etc. each have their own first-class registry, spec, API surface, and UI component.
2. **Spec is the contract for the code ↔ UI translation.** It's the single payload backend hands the UI for rendering and editing; libcst codegen translates UI edits back to code.
3. **Specs compose from a small set of reusable building blocks**, so adding a new kind doesn't require new infrastructure.
4. **Click dispatch is universal.** Any reference inside any component produces a `(kind, name)` payload; one resolver maps that to the kind-keyed component. No special pairing.
5. **`__init_subclass__` captures, never raises.** Class always constructs; framework-rule violations become `ValidationIssue`s on the spec.
6. **Issues live on the spec component they describe.** Pipeline-level on `PipelineSpec.issues`, per-node on `NodeSpec.issues`, per-wiring-field on `SourceSpec.issues`, prompt-class on `PromptData.issues`. Frontend renders error styling on the matching component without string-matching by location.
7. **Heavy validation only on structured artifacts.** `utilities/` is a free-form Python escape hatch — files, no spec, no validation. Keeps `llm_pipelines/` interoperable with the rest of someone's codebase.

---

## 3. Architecture overview

```
CODE ─[libcst parse + class introspection]─> SPEC ─> REGISTRY ─> API ─> RESOLVER ─> COMPONENT_BY_KIND
                                                                                        │
CODE <─[libcst codegen]──────────────────────── API <───────────[user edits]───────────┘
```

- **Code:** `llm_pipelines/<kind>/<file>.py` (plus `_variables/_*.py` and the YAML prompt files for steps).
- **Spec:** typed Pydantic models — one `ArtifactSpec` subclass per kind, composed from building blocks.
- **Registry:** `app.state.registries: dict[str, dict[str, ArtifactRegistration]]` — single nested dict keyed by kind constant then name.
- **API:** generic `GET /api/{kind}` and `GET /api/{kind}/{name}` routes (work for every kind without per-kind handlers); kind-specific edit/run routes where needed.
- **Frontend:** `COMPONENT_BY_KIND[kind] -> Component`. A generic resolver function dispatches `(kind, name)` clicks. Kind-specific components compose generic building-block editors (Monaco wrappers, JsonViewer/JsonEditor) internally.

---

## 4. Primitives

### 4.1 `ArtifactSpec` base

```python
class ArtifactSpec(BaseModel):
    """Common contract for any UI-editable code artifact."""
    kind: str             # KIND_* constant
    name: str             # snake_case (registry key)
    cls: str              # fully-qualified Python identifier
    source_path: str      # filesystem path
    issues: list[ValidationIssue] = []
```

Every per-kind subclass extends this. Per-kind subclasses are the *only* dispatch targets — they are exactly the entries in `COMPONENT_BY_KIND` on the frontend.

### 4.2 Building blocks (composition pieces; not dispatch targets)

```python
class SymbolRef(BaseModel):
    """A reference to another artifact from inside a code body or schema value."""
    symbol: str           # the identifier as it appears in source
    kind: str             # KIND_* — what artifact it resolves to
    name: str             # registry key (e.g. "max_retries")
    line: int             # for code-body refs (CodeBodySpec)
    col_start: int
    col_end: int

class CodeBodySpec(BaseModel):
    """A Monaco-edited Python code body. Used for prepare/run/extract,
    tool callables, eval scorer functions."""
    source: str
    line_offset_in_file: int
    refs: list[SymbolRef]
    issues: list[ValidationIssue] = []

class JsonSchemaWithRefs(BaseModel):
    """A JSON Schema plus per-location SymbolRefs that produced its values.
    Used for any Pydantic-shaped data (INPUTS, INSTRUCTIONS, OUTPUT,
    schema definitions, prompt variable definitions, etc.)."""
    schema: dict[str, Any]
    refs: dict[str, list[SymbolRef]]   # JSON Pointer (RFC 6901) -> refs
    issues: list[ValidationIssue] = []

class PromptData(BaseModel):
    """Sub-data of a step. Not a first-class artifact — embedded in StepSpec."""
    variables: JsonSchemaWithRefs            # the PromptVariables Pydantic class
    auto_vars: dict[str, str]                # auto_generate expression source
    auto_vars_refs: dict[str, list[SymbolRef]]
    yaml_path: str
    system_template: str | None              # populated by Phoenix sync
    user_template: str | None
    model: str | None
```

`SymbolRef` carries position metadata for code bodies; for tree-shaped schema components the equivalent address is JSON Pointer (handled by `JsonSchemaWithRefs.refs`'s dict key). One primitive, two addressing schemes — both resolve to `(kind, name)` for dispatch.

### 4.3 `ArtifactRegistration`

```python
@dataclass(frozen=True)
class ArtifactRegistration:
    """Pairs the contract (spec) with the runtime object."""
    spec: ArtifactSpec
    obj: Any   # class for class-based; value for constants
```

Used as the registry value type. The spec is what the UI consumes; the obj is what runtime/ops consume (running pipelines, instantiating tools, etc.).

---

## 5. Per-kind catalogue

| Kind constant | Folder | Subclass | Notes |
|---|---|---|---|
| `KIND_CONSTANT` | `constants/` | `ConstantSpec` | scalar values; obj is the value |
| `KIND_ENUM` | `enums/` | `EnumSpec` | obj is the Enum class |
| `KIND_SCHEMA` | `schemas/` | `SchemaSpec` | BaseModel data shapes |
| `KIND_TABLE` | `tables/` (renamed from current `schemas/` for SQLModel content) | `TableSpec` | SQLModel persistent tables |
| `KIND_TOOL` | `tools/` | `ToolSpec` | pydantic-ai agent tools |
| `KIND_STEP` | `steps/` | `StepSpec` | LLMStepNode subclass + paired prompt + paired YAML |
| `KIND_EXTRACTION` | `extractions/` | `ExtractionSpec` | ExtractionNode subclass |
| `KIND_REVIEW` | `reviews/` | `ReviewSpec` | ReviewNode subclass |
| `KIND_PIPELINE` | `pipelines/` | `PipelineSpec` | Pipeline subclass |
| _(future)_ `KIND_EVAL` | `evals/` | `EvalSpec` | pydantic-evals driven |
| `(no kind)` | `_variables/` | — | auto-generated from prompts; not first-class |
| `(no kind)` | `utilities/` | — | free-form Python escape hatch; surfaced as raw files in UI |

`StepSpec` skeleton:
```python
class StepSpec(ArtifactSpec):
    kind: Literal[KIND_STEP] = KIND_STEP
    inputs: JsonSchemaWithRefs | None
    instructions: JsonSchemaWithRefs | None
    prepare: CodeBodySpec
    run: CodeBodySpec
    prompt: PromptData                       # embedded
    tool_names: list[str]                    # references into KIND_TOOL registry
```

`PipelineSpec` references nodes; doesn't nest their full specs:
```python
class NodeBindingSpec(BaseModel):
    """Binding inside a pipeline. Not first-class."""
    binding_kind: Literal["step", "extraction", "review"]
    name: str                          # registry key of referenced node
    wiring: WiringSpec                 # the inputs_spec serialised
    issues: list[ValidationIssue] = [] # binding-level (wiring drift, etc.)

class PipelineSpec(ArtifactSpec):
    kind: Literal[KIND_PIPELINE] = KIND_PIPELINE
    input_data: JsonSchemaWithRefs | None
    nodes: list[NodeBindingSpec]
    edges: list[EdgeSpec]
    start_node: str | None
```

---

## 6. Levels and dependency tree

```
Level 1: Constants                       no deps
Level 2: Enums                           may use constants
Level 3: Schemas, Tables, Tools          may use enums + constants
Level 4: Steps, Extractions, Reviews     may use any level ≤3 + (steps embed PromptData)
Level 5: Pipelines                       may use any level ≤4
Level 6: Evals (future)                  may use any level ≤5
```

Encoded as `LEVEL_BY_KIND: dict[str, int]` in `discovery.py`. Used for:
- Build/load order at discovery time
- UI selectors filtering "what can I reference here?"
- Dependency-cycle prevention (a kind cannot reference its own level or higher except where explicitly allowed)

Within-level peer references are allowed (a schema can reference another schema, etc.) so long as no cycle.

---

## 7. Discovery

`llm_pipeline/discovery.py` walks `llm_pipelines/` in dependency order:

```python
DISCOVERY_ORDER = [
    "constants", "enums",
    "schemas", "tables", "tools",
    "_variables",      # imported only; feeds into owning step's prompt
    "extractions", "reviews", "steps",
    "pipelines",
    "evals",           # future
    "utilities",       # imported only; raw files exposed in UI
]
```

Each subfolder has a walker that:
1. Imports the .py file.
2. For framework classes (Pipeline / LLMStepNode / etc. subclasses), the `cls._spec` is already built at `__init_subclass__` time — registration just wraps it in `ArtifactRegistration` and adds to `registries[kind]`.
3. For non-framework artifacts (constants, enums, schemas, tables, tools, eval cases), the walker introspects the class/value at registration time and builds the spec via the libcst static analyser + Pydantic schema generation.

Strict / lenient modes already exist; both flow through the same per-entry capture model.

---

## 8. libcst static analyser

The bridge that produces `SymbolRef`s for code bodies and `JsonSchemaWithRefs.refs` for schema-derived values.

Module: `llm_pipeline/static_analysis.py`.

For a source file:
1. Parse to CST.
2. Use `ScopeProvider` to scope-resolve every `Name` / `Attribute` reference.
3. Cross-reference resolved symbols against `app.state.registries` to determine if the symbol corresponds to a registered artifact.
4. Emit `SymbolRef`s with line/col positions for code bodies, JSON Pointers for schema values.

Cached per-file. Re-run on file change.

External imports (anything not under `llm_pipelines/`) are silently skipped — UI cmd-click on them is a no-op (or a small "external" tooltip).

---

## 9. API surfaces

Generic kind-routes work for every kind — no per-kind handler code:
```
GET /api/{kind}              -> [{name, validation_summary, …}, …]
GET /api/{kind}/{name}       -> ArtifactSpec
POST /api/{kind}/{name}      -> apply edit (libcst codegen ops; per-kind dispatch internally)
```

Pipeline-runtime surface stays pipeline-specific:
```
POST /api/runs               -> gates on transitive_issues(pipeline_spec, registries)
                                 returning empty (i.e. all referenced artifacts also clean)
                                 Returns 422 with full issue list otherwise.
```

Eval-runtime surface (future) sits next to runs:
```
POST /api/evals/{name}/run   -> kicks off a pydantic-evals run
```

---

## 10. Frontend dispatch

```typescript
// COMPONENT_BY_KIND maps each first-class kind to its kind-specific component.
const COMPONENT_BY_KIND: Record<string, Component> = {
  [KIND_CONSTANT]: ConstantModal,
  [KIND_ENUM]: EnumEditor,
  [KIND_SCHEMA]: SchemaEditor,
  [KIND_TABLE]: TableEditor,
  [KIND_TOOL]: ToolEditor,
  [KIND_STEP]: StepEditor,
  [KIND_EXTRACTION]: ExtractionEditor,
  [KIND_REVIEW]: ReviewEditor,
  [KIND_PIPELINE]: PipelineEditor,
};

// Universal resolver — used everywhere a (kind, name) is produced
// (SymbolRef click, JSON-Pointer click, list-page row, navigation, …)
function resolve(kind: string, name: string) {
  const reg = registries[kind][name];          // ArtifactRegistration.spec
  const Component = COMPONENT_BY_KIND[kind];
  return <Component spec={reg.spec} />;
}
```

Generic composition pieces (PrepareEditor, RunEditor, JsonEditor, PromptEditor, etc.) live below the dispatch layer. They render building-block specs (CodeBodySpec, JsonSchemaWithRefs, PromptData) as children of kind-specific components — never as dispatch targets themselves.

---

## 11. What stays vs reshapes from current foundation

### Keeps (no change)
- `ValidationIssue`, `ValidationLocation`, `ValidationSummary` types
- `_init_subclass_errors` capture model on `LLMStepNode` / `ExtractionNode` / `ReviewNode` / `PromptVariables`
- `Step` / `Extraction` / `Review` binding wrappers carrying `_init_post_errors`
- `Pipeline.__init_subclass__` aggregator (it just gathers; doesn't own)
- `is_runnable` concept (re-shaped to `transitive_issues` for cross-artifact checks)
- libcst tooling (already in the codebase)
- `register_auto_generate` machinery (still feeds prompt variable resolution)

### Reshapes
- `NodeSpec` (currently nested in `PipelineSpec.nodes`) splits:
  - Class contract → standalone `StepSpec` / `ExtractionSpec` / `ReviewSpec` (in their own registries)
  - Pipeline binding → new `NodeBindingSpec` (lives only inside `PipelineSpec.nodes`)
- `PipelineSpec.start_node`, `edges` stay; `nodes` becomes `list[NodeBindingSpec]`
- `_PROMPT_VARIABLES_REGISTRY` collapses into the step-discovery flow — prompt data flows into the owning `StepSpec.prompt`, no separate registry
- Two registries on `app.state` (`pipeline_registry` + `introspection_registry`) collapse into one nested `app.state.registries` dict
- `_AUTO_GENERATE_REGISTRY` splits into `registries[KIND_CONSTANT]` and `registries[KIND_ENUM]`
- `schemas/` folder splits: `schemas/` (BaseModel) vs `tables/` (SQLModel)
- `derive_issues(spec)` stays per-spec (recursive flatten); add `transitive_issues(spec, registries)` for cross-artifact runnability gating

### New
- `ArtifactSpec` base + per-kind subclasses
- `ArtifactRegistration` wrapper
- `CodeBodySpec`, `JsonSchemaWithRefs`, `PromptData`, `SymbolRef` building blocks
- `static_analysis.py` libcst module
- Generic `/api/{kind}` and `/api/{kind}/{name}` routes
- Frontend: `COMPONENT_BY_KIND`, generic resolver, per-kind editors

---

## 12. Implementation phases

Each phase is one or more atomic commits. Tests pass at every commit boundary.

### Phase A — Spec base + building blocks
1. Add `ArtifactSpec` base class to `llm_pipeline/graph/spec.py` (or move to `llm_pipeline/specs.py` for clearer scope).
2. Add `CodeBodySpec`, `JsonSchemaWithRefs`, `PromptData`, `SymbolRef` types.
3. `KIND_*` constants and `LEVEL_BY_KIND` mapping in `discovery.py`.
4. Tests: round-trip serialisation of every new type.

No behaviour change yet.

### Phase B — Static analyser
1. `llm_pipeline/static_analysis.py` — libcst-based parser producing `SymbolRef`s + JSON-Pointer ref maps.
2. Tests: parse synthetic source files, assert refs at correct positions.

### Phase C — Per-kind specs (build only the specs; don't wire registries yet)
1. Add `StepSpec`, `ExtractionSpec`, `ReviewSpec` subclasses.
2. Refactor `_build_node_spec` to produce a `StepSpec` / `ExtractionSpec` / `ReviewSpec` standalone (no wiring).
3. Add `ConstantSpec`, `EnumSpec`, `SchemaSpec`, `TableSpec`, `ToolSpec`.
4. Refactor `PipelineSpec` to use `NodeBindingSpec` (references-by-name).
5. Update `derive_issues` for the new shape; add `transitive_issues`.
6. Tests: every spec subclass round-trips; localised issues land on the right component.

### Phase D — Discovery + registries
1. Split `_AUTO_GENERATE_REGISTRY` into per-kind constant/enum registries.
2. Walk each subfolder; build per-kind specs at registration time.
3. `app.state.registries` single nested dict; collapse the two pipeline registries into the new shape.
4. Filename-based name derivation for files that fail to import (kind inferred from folder).
5. Update consumer call sites mechanically.

### Phase E — `schemas/` → `schemas/` + `tables/` split
1. Audit existing `schemas/` content; classify each file.
2. Move SQLModel classes to `tables/`.
3. Update imports in dependent files.
4. Update `_LOAD_ORDER` and add the new walker.

### Phase F — API surface
1. Generic `GET /api/{kind}` + `GET /api/{kind}/{name}` routes.
2. Pipeline-specific `POST /api/runs` gating on `transitive_issues`.
3. Update existing pipeline routes to read from `registries[KIND_PIPELINE]`.
4. Edit-ops endpoints (`POST /api/{kind}/{name}`) — initially per-kind handlers; libcst codegen lands in a follow-up plan.

### Phase G — Frontend
1. Add types: `ArtifactSpec` base + per-kind subclasses + building blocks.
2. `COMPONENT_BY_KIND` registry + generic resolver.
3. Per-kind list pages + detail editors. Reuse existing PromptEditor inside StepEditor (no separate dispatch).
4. Validation-issue rendering at the right component levels.
5. utilities raw editor (Monaco + save plumbing).

### Phase H — Preflight refactor
1. `_preflight_check` never exits; writes `app.state.preflight_report`.
2. UI banner reads from `app.state.preflight_report` independently of per-artifact validation.

### Phase I — Negative tests
1. For each kind, a test where the file has a representative broken state (missing required attribute, naming violation, broken import). Assert spec/issues land in the right place.
2. Cross-artifact test: pipeline references a broken step. Pipeline runnability is `False`; broken-step issues surface via `transitive_issues`.

---

## 13. Out of scope for this plan

- **Modification ops in detail.** The PUT/POST edit endpoints accept a spec diff at the API layer; the libcst codegen that translates spec diffs back to source-file edits is its own follow-up plan.
- **Sandboxes / eval-variant flow.** This plan establishes the foundation: `llm_pipelines/evals/` artifacts work like any other kind; sandbox isolation (separate `LLM_PIPELINES_ROOT`, branch-scoped registries) is a separate plan that builds on this.
- **File-watcher reactivity.** Manual reload is fine for V1.
- **Static analysis for dynamic imports / `getattr` chains.** Refs that can't be statically resolved just don't appear.
- **Tool body editing UI fidelity.** Tools can have arbitrary Python bodies (just like utilities). For V1, ToolEditor's body editor is Monaco + simple metadata; richer structural editing of tool internals is later.
- **Branching runtime (`EdgeSpec.branch`).** Spec shape is already forward-compatible; runtime + demo lands separately.
- **Pipeline-spec migrations / versioning.** The spec is rebuilt on every load; no on-disk persistence to version.

---

## 14. Verification

1. `uv run pytest` — all existing + new tests pass at each phase boundary.
2. `uv run llm-pipeline build --demo` — strict mode still raises on aggregated errors (CI gate preserved).
3. `cd llm_pipeline/ui/frontend && npm run build` — clean.
4. Manual smoke (`uv run llm-pipeline ui --dev`):
   - Each kind surfaces its own list page.
   - Click a constant from inside a step's prepare body → ConstantModal opens with the constant's value.
   - Click a schema reference inside a step's INPUTS via JsonViewer → SchemaEditor opens.
   - Edit a prompt section in StepEditor → save; YAML and `_variables/` regenerated; spec re-fetched.
   - Break a step (delete `INPUTS = ...`); restart UI. App boots. Step shows red badge; pipelines using it show red badge with cross-artifact issue surfacing; other artifacts unaffected.
5. Add a new kind end-to-end (use a throwaway `KIND_DEMO` to validate the recipe in [docs/architecture/diagrams/per-artifact-03-adding-a-kind.mmd](../../docs/architecture/diagrams/per-artifact-03-adding-a-kind.mmd)). Backend changes alone surface it via `/api/demo`; frontend gets a list page + editor by adding to `COMPONENT_BY_KIND`.

---

## 15. Migration commits already landed (for reference)

These commits on `langfuse-migration` have already done parts of the foundation. They stand; this plan builds on them:

- `03b990de` — `ValidationIssue` / `ValidationSummary` types + `EdgeSpec.branch`
- `48dcf743` + `7e0bdb00` — capture model on `LLMStepNode` / `ExtractionNode` / `ReviewNode` / `PromptVariables`
- `de98fc73` — `Step` / `Extraction` / `Review` binding wrappers capture
- `732f9520` — `Pipeline.__init_subclass__` + `validate_pipeline` capture
- `9f69ce6e` — localise issues onto spec components
- `062d7631` — `build_pipeline_spec` never raises (returns shell on failure)

Implementation phases A–I in this plan extend these. Tests at every commit boundary.
