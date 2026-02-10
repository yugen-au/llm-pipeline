# Research Summary

## Executive Summary

Cross-validated three research files (step-1 architecture, step-2 API reference, step-3 C4 mapping) against the full source tree and the real consumer project (logistics-intelligence rate_card_parser). Research is approximately 85% accurate overall. Step-2 (API reference) is strongest at ~90%. Step-3 (C4) has the most factual errors at ~80%. Five critical contradictions found, ten documentation gaps identified. All five open questions from the previous validation pass have been resolved using the consumer project as ground truth.

## Domain Findings

### Factual Contradictions Between Research and Source Code
**Source:** step-1, step-3 vs actual source

1. **LLMStep does NOT extend LLMResultMixin** - Step-3 Mermaid diagram declares `LLMStep --|> LLMResultMixin`. Wrong. `LLMStep` extends `ABC`. `LLMResultMixin` extends `BaseModel` and is used for instruction classes (e.g., `SemanticMappingInstructions`), not step classes.

2. **PipelineTransformation does NOT support strategy-specific method routing** - Step-1 claims transformation has Priority 2 (strategy-name matching) like extraction. Actual code in `transformation.py` does NOT check `self.pipeline._current_strategy`. Only `PipelineExtraction.extract()` has strategy-name routing. Transformation supports: `default()` -> single method -> passthrough -> error.

3. **`save()` signature is `save(session, tables)` not `save(session, engine)`** - Step-3 C4 doc says `save(session, engine)`. Actual: `save(self, session: Session = None, tables: Optional[List[Type[SQLModel]]] = None)`.

4. **`clear_cache()` is buggy** - Calls `self.session.delete()` and `self.session.commit()` but `self.session` is `ReadOnlySession` which raises `RuntimeError`. Should use `self._real_session`. Confirmed bug exists in both llm-pipeline and consumer project. Never triggered because clear_cache() is rarely called (use_cache defaults to False).

5. **Two-phase write pattern, not "deferred to save()"** - Research presents "all writes deferred to save()". Inaccurate. The actual pattern is a two-phase write:
   - **Phase 1 (execution):** `extract_data()` calls `_real_session.add()` + `_real_session.flush()` to assign database IDs during step execution. This enables later extractions to reference FKs to already-extracted models.
   - **Phase 2 (save):** `save()` calls `session.commit()` to finalize the transaction, plus tracks instances via `PipelineRunInstance`.

   Consumer project comments confirm this is intentional (step.py lines 632-639): "Add instances to session and flush to assign IDs / This allows later extractions to reference these IDs / Transaction is not committed until save() is called".

### Documentation Gaps
**Source:** step-2 API reference vs actual source

1. **Missing class: `StepKeyDict`** - Custom dict subclass in `pipeline.py` (lines 45-70) that normalizes Step class keys to snake_case. Used for `pipeline.data` and `pipeline._instructions`. Not in step-2 API reference.

2. **Missing methods on PipelineConfig**: `get_raw_data()`, `get_current_data()`, `get_sanitized_data()` are public convenience methods undocumented in step-2.

3. **Missing method: `PromptService.get_guidance()`** - Exists in `service.py` (lines 58-75). Takes step_name and optional table_type. Not in any research file. Note: this method calls `get_prompt()` with a context parameter, which triggers broken `Prompt.context` code path (see Q3 below).

4. **Missing function: `save_step_yaml()`** - Legacy utility in `executor.py` (lines 127-137). Not part of current pipeline architecture (see Q4 resolution).

5. **Missing function: `_query_prompt_keys()`** - In `step.py` (lines 27-70). Queries DB for prompt keys by step name and strategy.

6. **Missing Prompt model constraints** - `UniqueConstraint('prompt_key', 'prompt_type')` and indexes `ix_prompts_category_step`, `ix_prompts_active` exist in actual code but not in step-1 schema diagram.

7. **Missing: `prompts/__init__.py` exports** - Re-exports `sync_prompts`, `load_all_prompts`, `get_prompts_dir`, `extract_variables_from_content`, `VariableResolver`, `PromptService`. Not documented as module API.

8. **Missing: `_version_greater()` in loader** - Semantic version comparison logic for prompt sync undocumented.

9. **Missing: `LLMResultMixin.__init_subclass__` validation** - Validates `example` dict at class definition time by instantiating the class with it. Not documented.

10. **Missing: Consensus helper methods** - `_smart_compare()`, `_instructions_match()`, `_get_mixin_fields()` on PipelineConfig are undocumented. These implement comparison logic for consensus polling.

### Research Accuracy by File
**Source:** all three research files

- **step-1-codebase-architecture.md**: ~88% accurate. Strong on architecture patterns, data flow, and design decisions. Errors: transformation strategy routing claim, implied "all writes deferred to save()" narrative.
- **step-2-api-module-reference.md**: ~90% accurate. Most complete API catalog. Missing the gaps listed above but signatures and descriptions match source.
- **step-3-c4-architecture.md**: ~80% accurate. LLMStep inheritance wrong, save() signature wrong, context type wrong (says `PipelineContext` but is `Dict[str, Any]`). Mermaid diagram has relationship errors.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Q1: extract_data() flush during execution vs deferred to save() | Intentional two-phase write design. flush() assigns IDs during execution for FK resolution; commit() in save() finalizes transaction. Consumer project comments confirm: "allows later extractions to reference these IDs". | HIGH - Architecture docs must document the two-phase write pattern accurately. The "all writes deferred" narrative is misleading. |
| Q2: clear_cache() calls delete/commit on ReadOnlySession | Confirmed bug. Both llm-pipeline and consumer project have identical broken code. self.session is ReadOnlySession which raises RuntimeError on delete/commit. Should use self._real_session. Never triggered because clear_cache() is rarely called. | MEDIUM - Document as known limitation. Do not document clear_cache() as working feature until fixed. |
| Q3: PromptService.get_prompt() references Prompt.context | Vestigial dead code. Prompt model has no `context` field in either codebase. The field existed in an earlier version (evidence: _legacy/ folder has Prompt.context queries). Removed from model but PromptService wasn't updated. The context-filtering branch in get_prompt() would fail at runtime if triggered. get_guidance() also passes context, so it is also broken for context-filtered queries. | MEDIUM - Do not document context-filtering as a feature. Note get_guidance() works only for the fallback path (no context match). |
| Q4: save_step_yaml() public or internal | Legacy utility from pre-Strategy architecture. In consumer project, it's used only by the OLD execute_pipeline() function (llm/utils.py). The NEW PipelineConfig.execute() never calls it. Carried over during extraction but dead in current architecture. | LOW - Exclude from public API docs or mark as deprecated/legacy. |
| Q5: Naming validation bypassed by multi-level inheritance | By design. All concrete classes in consumer project directly subclass their base (LaneExtraction -> PipelineExtraction, LaneBasedStrategy -> PipelineStrategy). No multi-level inheritance used. The underscore-prefix convention (_BaseExtraction) exists as escape hatch for intermediate abstract classes. The check is sufficient for intended usage. | LOW - Document that concrete classes must directly subclass the base. Mention underscore prefix as escape hatch for intermediate bases. |

## Assumptions Validated
- [x] Module structure matches physical file layout in all three research files
- [x] `__init__.py` exports match what step-2 documents (verified against actual file)
- [x] `pyproject.toml` dependencies match research claims (pydantic>=2.0, sqlmodel>=0.0.14, sqlalchemy>=2.0, pyyaml>=6.0)
- [x] Gemini is optional dependency via `[gemini]` extra
- [x] Test file structure matches step-1 testing strategy section
- [x] PipelineConfig uses `__init_subclass__` for declarative config (verified)
- [x] Naming convention enforcement works at class definition time (verified in source)
- [x] FK dependency validation uses SQLAlchemy table metadata inspection (verified)
- [x] Smart method detection priority order in PipelineExtraction matches research (default -> strategy -> single -> error)
- [x] ReadOnlySession blocks write operations and allows read operations (verified all methods)
- [x] Caching uses input_hash + prompt_version for cache key (verified)
- [x] PipelineRunInstance provides traceability linking (verified)
- [x] Two-phase write pattern (flush during execution, commit at save) is intentional design (verified via consumer project comments)
- [x] All concrete extraction/strategy classes in consumer use direct subclassing (no multi-level inheritance in practice)
- [x] save_step_yaml() is unused in new pipeline architecture (verified in consumer project)
- [x] Prompt.context is vestigial - field removed from model but service code retained (verified via _legacy/ evidence)

## Open Items

All five previously open items have been resolved. No remaining open items requiring CEO input.

Known issues to address during docs generation:
- `clear_cache()` bug: uses ReadOnlySession instead of `_real_session`. Do not document as working feature.
- `PromptService.get_prompt()` context-filtering: dead code path. Do not document context parameter as functional.
- `save_step_yaml()`: legacy function, not part of current architecture. Exclude from API reference or mark deprecated.

## Recommendations for Planning

1. **Fix the five factual contradictions** before generating architecture docs. The LLMStep/LLMResultMixin inheritance error in the C4 diagram would mislead users significantly.

2. **Document the two-phase write pattern explicitly** in architecture docs. This is a critical design decision:
   - Phase 1 (execution): `_real_session.add()` + `_real_session.flush()` assigns database IDs
   - Phase 2 (save): `session.commit()` finalizes transaction + `PipelineRunInstance` tracking
   - Purpose: enables FK references between extractions within the same step or across steps

3. **Add the ten missing items** to the API reference. Priority items: `StepKeyDict`, `get_raw_data()/get_current_data()/get_sanitized_data()`, consensus helper methods.

4. **Document Prompt model constraints** (unique constraint, indexes) in database architecture section.

5. **Exclude or mark as deprecated**: `save_step_yaml()`, `PromptService.get_prompt()` context parameter, `PromptService.get_guidance()` context-filtering path.

6. **Add a "Known Limitations" section** to docs covering:
   - `clear_cache()` bug (uses ReadOnlySession for writes)
   - `Prompt.context` vestigial code path
   - Single-level inheritance requirement for naming validation
   - Gemini-only provider (no other LLMProvider implementations shipped)

7. **Document consensus polling** as an advanced feature with clear examples showing `_smart_compare()` matching rules (excludes strings, None, mixin fields; exact-matches numbers/booleans/list-lengths).

8. **Consumer project patterns** should inform usage guide examples:
   - Strategy definitions with `can_handle()` dispatching on `context['table_type']`
   - Step definitions using `create_definition()` factory pattern
   - Extraction classes using strategy-specific methods (e.g., `lane_based()`, `destination_based()`)
   - Pipeline configuration with declarative `registry=` and `strategies=` class params
