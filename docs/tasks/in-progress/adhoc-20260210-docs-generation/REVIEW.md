# Architecture Review

## Overall Assessment
**Status:** partial
The documentation implementation is strong overall. All 20 planned steps were executed, producing comprehensive architecture docs, API references, usage guides, C4 diagrams, and navigation. All 5 research contradictions are corrected in the architecture/API docs. All 10 missing API items are included. Deprecated features are properly excluded or marked. However, several factual inaccuracies and inconsistencies remain in specific files, primarily in the README quick-start example, concepts.md pseudo-code for save/extract_data, and a few minor issues in the C4 component diagram.

## Project Guidelines Compliance
**CLAUDE.md:** C:\Users\SamSG\Documents\claude_projects\llm-pipeline\CLAUDE.md
| Guideline | Status | Notes |
| --- | --- | --- |
| docs/ folder structure (architecture/, api/, guides/, architecture/diagrams/) | pass | All folders exist with correct files |
| All 5 research contradictions corrected | pass | Verified in architecture and API docs (see details below) |
| All 10 missing API items added | pass | All present in appropriate docs |
| Deprecated features excluded or marked | pass | save_step_yaml(), clear_cache() bug, context parameter all noted |
| C4 diagrams show correct inheritance | pass | LLMStep -> ABC, LLMResultMixin -> BaseModel shown correctly in c4-component.mmd |
| Architecture docs document two-phase write accurately | pass | overview.md, patterns.md, concepts.md all describe flush-for-IDs + commit-at-save |
| API reference for all public modules | pass | pipeline, step, strategy, extraction, transformation, llm, prompts, state, registry all present |
| Usage guides with examples | pass | getting-started, basic-pipeline, multi-strategy, prompts guides created |
| Navigation and cross-references | pass | index.md and README.md have comprehensive cross-reference maps |

## Issues Found
### Critical
None

### High
#### README.md Quick Start Example Uses Wrong API
**Step:** 20
**Details:** `docs/README.md` lines 30-61 contain a "First Pipeline (5 minutes)" example that is factually incorrect vs actual source code. It shows `@step_definition(pipeline='ClassifyPipeline')` which is not a valid parameter (the decorator takes `instructions`, `default_system_key`, etc.). It shows `prepare_calls(self, **kwargs)` but actual signature is `prepare_calls(self) -> List[StepCallParams]`. It shows `class ClassifyPipeline(PipelineConfig): steps = [ClassifyStep]` but PipelineConfig requires `registry=` and `strategies=` class parameters. It shows `pipeline.execute()` with no arguments but the method requires `data` and `initial_context`. This example would not run and contradicts the accurate documentation in the rest of the docs.

#### concepts.md Pseudo-Code for extract_data() Has Incorrect Ordering
**Step:** 2
**Details:** In `docs/architecture/concepts.md` around line 500-534 the pseudo-code for `extract_data()` and `save()` has two issues: (1) `extract_data` shows `store_extractions` AFTER `flush()` but actual source (step.py lines 326-330) calls `store_extractions` BEFORE `_real_session.add/flush`. (2) The `save()` pseudo-code shows two separate commits and uses field names `model_name` and `instance_id` for PipelineRunInstance but actual code uses `model_type` and `model_id`. This could mislead developers reading pseudo-code as authoritative.

#### concepts.md PipelineRunInstance Field Names Wrong
**Step:** 2
**Details:** `docs/architecture/concepts.md` lines 1037-1038 list PipelineRunInstance fields as `model_name` and `instance_id`, but actual source (state.py lines 128-133) uses `model_type` and `model_id`. Same wrong names appear in the PipelineRunInstance tracking pseudo-code at lines 1052-1058 and in the query example at lines 1068-1069.

### Medium
#### C4 Container Diagram Shows Non-Existent PromptCache Component
**Step:** 18
**Details:** `docs/architecture/diagrams/c4-container.mmd` line 22 includes a "Prompt Cache" component (`PromptCache["<b>Prompt Cache</b><br/>In-memory prompt cache<br/>[Python]"]`). No such in-memory prompt cache exists in the source code. PromptService does not implement caching; it queries the database each time. This is fabricated.

#### C4 Container Diagram Shows Incorrect Data Flows
**Step:** 18
**Details:** In c4-container.mmd: (1) Lines 59-60 show ExtractionEngine and TransformationEngine querying PromptService, but extractions and transformations do not interact with prompts at all in source. (2) Line 75 shows ExtractionEngine writing to ReadOnlySession, but extraction writes go through `_real_session` not ReadOnlySession. (3) Line 76 shows PipelineStepState persisting to ReadOnlySession, but state persistence uses `_real_session`.

#### C4 Component Diagram: PipelineConfig Shows db_instances Property
**Step:** 19
**Details:** c4-component.mmd line 4 shows `+ db_instances: Dict` as a property of PipelineConfig. The actual property name is `extractions`, not `db_instances`. Same diagram shows `+ session: Session` but actual type is `ReadOnlySession`.

#### C4 Component Diagram: LLMStep Shows Incorrect Methods
**Step:** 19
**Details:** c4-component.mmd line 18 shows LLMStep with methods `+ run() -> Results` and `+ apply_transformation()`. These methods do not exist on LLMStep. The actual abstract/overridable methods are `prepare_calls()`, `process_instructions()`, `should_skip()`, `log_instructions()`, `extract_data()`, `create_llm_call()`, `store_extractions()`.

#### C4 Component Diagram: PipelineStrategies Shows Wrong Method
**Step:** 19
**Details:** c4-component.mmd line 10 shows PipelineStrategies with method `get_strategies()`. Actual methods are `create_instances()` and `get_strategy_names()`.

#### patterns.md create_definition() Simplifies Transformation Override Logic
**Step:** 3
**Details:** In `docs/architecture/patterns.md` line 294, the `create_definition()` implementation shows `if transformation is None: transformation = cls.DEFAULT_TRANSFORMATION`. But actual source (step.py lines 145-146) has a more nuanced check: `if 'transformation' not in kwargs and transformation is None: transformation = cls.DEFAULT_TRANSFORMATION`. This means passing `transformation=None` explicitly in the actual code does override to None, but the docs version would always fallback. Minor logic difference but could confuse someone reading source vs docs.

### Low
#### README.md sync_prompts() Call Signature Wrong
**Step:** 20
**Details:** `docs/README.md` line 198 shows `sync_prompts(session, engine)` but actual signature is `sync_prompts(bind, prompts_dir=None, force=False)`. The first parameter is an engine/connection (named `bind`), not a session.

#### README.md PipelineRunInstance Query Uses Non-Existent Fields
**Step:** 20
**Details:** `docs/README.md` lines 207-210 show querying PipelineRunInstance with `run.pipeline_name` and `run.status` fields. Neither field exists on PipelineRunInstance. Actual fields are `run_id`, `model_type`, `model_id`, `created_at`.

#### index.md Documentation Last Updated Date
**Step:** 20
**Details:** `docs/index.md` line 302 and `docs/README.md` line 332 both state "Documentation Last Updated: 2025-02". Current date is 2026-02-10, so this should be 2026-02.

#### concepts.md clear_cache() Signature Includes step_name Parameter
**Step:** 2
**Details:** `docs/architecture/concepts.md` line 1078 mentions `pipeline.clear_cache(step_name)` but actual signature is `clear_cache(self) -> int` with no parameters. It clears all states for the current run_id.

## Review Checklist
[x] Architecture patterns followed - Pipeline+Strategy+Step correctly documented
[x] Code quality and maintainability - Docs are well-organized and cross-referenced
[ ] Error handling present - README quick-start example has no error handling and uses wrong API
[x] No hardcoded values - No hardcoded secrets or values
[x] Project conventions followed - markdown structure follows PLAN.md specification
[x] Security considerations - Prompt injection warning included in overview.md
[ ] Properly scoped (DRY, YAGNI, no over-engineering) - C4 container diagram includes fabricated PromptCache component

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| docs/architecture/overview.md | pass | Comprehensive, all 5 corrections applied, two-phase write accurate |
| docs/architecture/concepts.md | fail | PipelineRunInstance field names wrong (model_name/instance_id vs model_type/model_id), extract_data pseudo-code ordering wrong, clear_cache signature wrong |
| docs/architecture/patterns.md | pass | Minor simplification in create_definition() logic but acceptable |
| docs/architecture/limitations.md | pass | All known limitations documented accurately |
| docs/architecture/diagrams/c4-context.mmd | pass | Correct system boundaries |
| docs/architecture/diagrams/c4-container.mmd | fail | Fabricated PromptCache component, incorrect data flows (extraction/transformation don't use PromptService, writes don't go through ReadOnlySession) |
| docs/architecture/diagrams/c4-component.mmd | fail | db_instances instead of extractions, non-existent methods on LLMStep, wrong method on PipelineStrategies |
| docs/api/index.md | pass | Complete import reference |
| docs/api/pipeline.md | pass | StepKeyDict documented, get_raw/current/sanitized_data included, consensus helpers documented, save() signature correct |
| docs/api/step.md | pass | LLMStep -> ABC correct, LLMResultMixin -> BaseModel correct, __init_subclass__ validation documented, _query_prompt_keys included |
| docs/api/strategy.md | pass | Accurate strategy, PipelineStrategies, StepDefinition docs |
| docs/api/extraction.md | pass | Smart method detection correct (default->strategy->single->error), validation documented |
| docs/api/transformation.md | pass | No strategy routing correctly documented, passthrough documented |
| docs/api/llm.md | pass | LLMProvider, GeminiProvider, execute_llm_step, RateLimiter, schema utils documented |
| docs/api/prompts.md | pass | save() is sync_prompts(bind,...) correct, Prompt constraints documented, exports documented, _version_greater documented, context parameter marked non-functional |
| docs/api/state.md | pass | PipelineStepState and PipelineRunInstance accurate |
| docs/api/registry.md | pass | PipelineDatabaseRegistry and ReadOnlySession accurate |
| docs/guides/getting-started.md | pass | Installation and setup guide reasonable |
| docs/guides/basic-pipeline.md | pass | Working example pattern |
| docs/guides/multi-strategy.md | pass | Strategy selection documented |
| docs/guides/prompts.md | pass | YAML structure and sync process documented |
| docs/index.md | pass | Comprehensive navigation and cross-references |
| docs/README.md | fail | Quick-start example uses incorrect API, sync_prompts wrong signature, PipelineRunInstance query uses wrong fields |

## New Issues Introduced
- README.md quick-start example introduces new factual errors not present in research (fabricated API usage)
- C4 container diagram introduces fabricated PromptCache component not in source
- concepts.md introduces wrong field names for PipelineRunInstance (model_name/instance_id)
- Date in docs says 2025-02 but should be 2026-02

## Recommendation
**Decision:** CONDITIONAL
The bulk of the documentation is excellent - architecture docs (overview.md, patterns.md, limitations.md), all API reference docs, and usage guides are accurate and comprehensive. All 5 VALIDATED_RESEARCH corrections were properly applied. All 10 missing API items were included. The conditional items that need fixing before approval:

1. **HIGH**: Fix README.md quick-start example to use correct API signatures or remove it entirely
2. **HIGH**: Fix concepts.md PipelineRunInstance field names (model_type/model_id not model_name/instance_id) and extract_data pseudo-code ordering
3. **MEDIUM**: Fix c4-container.mmd to remove fabricated PromptCache and correct data flow arrows
4. **MEDIUM**: Fix c4-component.mmd property/method names to match source code
5. **LOW**: Fix date to 2026-02, fix clear_cache() signature in concepts.md, fix sync_prompts signature in README
