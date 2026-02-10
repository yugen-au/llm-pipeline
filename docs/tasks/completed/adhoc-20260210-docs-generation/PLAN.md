# PLANNING

## Summary
Generate comprehensive project documentation for llm-pipeline framework in docs/ folder. Create architecture docs, complete API reference, usage guides, and corrected C4 diagrams. Apply validated research corrections (5 contradictions, 10 gaps) to ensure accuracy.

## Plugin & Agents
**Plugin:** documentation-generation
**Subagents:** docs-architect, api-documenter, reference-builder, mermaid-expert
**Skills:** none

## Phases
1. **Architecture Documentation**: Create architecture overview, core concepts, design patterns with corrected two-phase write pattern and inheritance relationships
2. **API Reference**: Generate complete module API docs with 10 missing items added, deprecated features excluded
3. **Usage Guides**: Write getting started guide and examples based on consumer project patterns
4. **C4 Diagrams**: Create corrected C4 context/container/component diagrams in Mermaid format
5. **Documentation Index**: Build navigation structure and cross-references

## Architecture Decisions

### Decision: Use documentation-generation plugin
**Choice:** documentation-generation plugin with docs-architect, api-documenter, reference-builder, mermaid-expert
**Rationale:** Covers all deliverables (architecture, API, guides, diagrams). Alternative c4-architecture plugin only handles diagrams, lacks API docs and guide capabilities.
**Alternatives:** c4-architecture (insufficient), code-documentation (wrong focus - generates from code comments not research)

### Decision: Correct research errors in generated docs
**Choice:** Apply all 5 validated corrections from VALIDATED_RESEARCH.md during generation
**Rationale:** Research is 85% accurate with known errors. Must fix: LLMStep inheritance (not from LLMResultMixin), transformation routing (no strategy-specific), save() signature (session, tables), clear_cache() bug, two-phase write pattern. Propagating errors would mislead users.
**Alternatives:** Use research as-is (unacceptable - known factual errors), research from scratch (wasteful - 85% accurate)

### Decision: Add 10 missing API items
**Choice:** Include StepKeyDict, get_raw_data(), get_current_data(), get_sanitized_data(), get_guidance(), _query_prompt_keys(), Prompt constraints, prompts exports, _version_greater(), consensus helpers
**Rationale:** VALIDATED_RESEARCH.md identifies these as missing from step-2 API reference but present in source. Omitting would create incomplete reference.
**Alternatives:** Omit (incomplete docs), add all internal methods (overwhelming)

### Decision: Exclude deprecated/broken features
**Choice:** Exclude save_step_yaml(), document clear_cache() as known limitation, mark get_prompt() context parameter as non-functional
**Rationale:** Validation confirms save_step_yaml() is dead code, clear_cache() has bug (uses ReadOnlySession for writes), context-filtering is vestigial. Documenting as working would mislead.
**Alternatives:** Document as-is (misleading), fix code first (scope creep)

### Decision: Structure docs by concern
**Choice:** docs/architecture/, docs/api/, docs/guides/, docs/architecture/diagrams/
**Rationale:** Standard documentation pattern. Separates conceptual (architecture), reference (API), practical (guides), visual (diagrams). Matches user mental model of information seeking.
**Alternatives:** Flat structure (poor navigation), single-file (overwhelming)

### Decision: Phase recommendation MEDIUM risk
**Choice:** Exclude testing phase, include review phase
**Rationale:** Documentation work with known error patterns. Review critical to verify corrections applied and no missing items. Testing unnecessary (no code logic to validate).
**Alternatives:** Low risk with no review (risky - might propagate errors), High risk with testing (overkill - no code)

## Implementation Steps

### Step 1: Architecture Overview
**Agent:** documentation-generation:docs-architect
**Skills:** none
**Context7 Docs:** -
**Group:** A
1. Create docs/architecture/overview.md with corrected architecture (two-phase write: flush during execution for FK IDs, commit at save)
2. Document Pipeline + Strategy + Step pattern with accurate class relationships
3. Include data flow diagram showing context/data/extractions separation
4. Add design philosophy section (declarative, three-tier, state tracking)

### Step 2: Core Concepts Documentation
**Agent:** documentation-generation:docs-architect
**Skills:** none
**Context7 Docs:** -
**Group:** A
1. Create docs/architecture/concepts.md covering: declarative configuration, strategy pattern, step lifecycle, extraction/transformation
2. Document naming conventions with validation rules (Pipeline suffix, matching Registry/Strategies names)
3. Explain three-tier data model (context for strategy, data for transforms, extractions for DB)
4. Cover execution order validation and FK dependency enforcement

### Step 3: Design Patterns Documentation
**Agent:** documentation-generation:docs-architect
**Skills:** none
**Context7 Docs:** -
**Group:** A
1. Create docs/architecture/patterns.md documenting: class-level config via __init_subclass__, step factory via @step_definition, smart method detection, StepKeyDict pattern, read-only session pattern
2. Document two-phase write pattern explicitly (Phase 1: _real_session.add() + flush() for IDs, Phase 2: commit() + PipelineRunInstance tracking)
3. Include code examples for each pattern
4. Document extension points: custom provider, custom sanitization, variable resolver, post-actions, extraction validation

### Step 4: API Reference Index
**Agent:** documentation-generation:api-documenter
**Skills:** none
**Context7 Docs:** /pydantic/pydantic, /sqlalchemy/sqlalchemy
**Group:** B
1. Create docs/api/index.md with module listing and installation instructions
2. Document top-level imports from llm_pipeline package
3. Add dependency requirements (Python 3.11+, pydantic>=2.0, sqlmodel>=0.0.14, sqlalchemy>=2.0)
4. Include optional dependencies ([gemini], [dev])

### Step 5: Pipeline API Reference
**Agent:** documentation-generation:api-documenter
**Skills:** none
**Context7 Docs:** /pydantic/pydantic, /sqlalchemy/sqlalchemy
**Group:** B
1. Create docs/api/pipeline.md documenting PipelineConfig class
2. Add missing methods: get_raw_data(), get_current_data(), get_sanitized_data()
3. Add missing StepKeyDict class (custom dict subclass, snake_case normalization)
4. Document consensus helpers: _smart_compare(), _instructions_match(), _get_mixin_fields()
5. Include constructor params, properties, all public methods with signatures and examples

### Step 6: Step API Reference
**Agent:** documentation-generation:api-documenter
**Skills:** none
**Context7 Docs:** /pydantic/pydantic
**Group:** B
1. Create docs/api/step.md documenting LLMStep class (correct: extends ABC, not LLMResultMixin)
2. Document LLMResultMixin separately (extends BaseModel, used by instruction classes)
3. Document @step_definition decorator with naming validation rules
4. Add __init_subclass__ validation logic for naming enforcement
5. Include abstract methods, overridable methods, helper methods

### Step 7: Strategy API Reference
**Agent:** documentation-generation:api-documenter
**Skills:** none
**Context7 Docs:** -
**Group:** B
1. Create docs/api/strategy.md documenting PipelineStrategy, PipelineStrategies, StepDefinition
2. Document strategy selection via can_handle() with context parameter
3. Document StepDefinition dataclass with all attributes
4. Include auto-generated NAME and DISPLAY_NAME properties

### Step 8: Extraction and Transformation API Reference
**Agent:** documentation-generation:api-documenter
**Skills:** none
**Context7 Docs:** /sqlalchemy/sqlalchemy
**Group:** B
1. Create docs/api/extraction.md documenting PipelineExtraction with smart method detection (default -> strategy -> single -> error)
2. Correct: transformation does NOT support strategy-specific routing (only default -> single -> passthrough -> error)
3. Create docs/api/transformation.md documenting PipelineTransformation with INPUT_TYPE/OUTPUT_TYPE validation
4. Document validation methods: _validate_instance() for NaN/NULL/FK checks
5. Include method detection priority tables

### Step 9: LLM Provider API Reference
**Agent:** documentation-generation:api-documenter
**Skills:** none
**Context7 Docs:** -
**Group:** B
1. Create docs/api/llm.md documenting LLMProvider abstract class and GeminiProvider implementation
2. Document execute_llm_step() function with all parameters
3. Document validation layers: schema structure, array response, Pydantic, extraction instance, database constraints
4. Document RateLimiter for API throttling
5. Include schema formatting utilities: flatten_schema(), format_schema_for_llm()

### Step 10: Prompt System API Reference
**Agent:** documentation-generation:api-documenter
**Skills:** none
**Context7 Docs:** -
**Group:** B
1. Create docs/api/prompts.md documenting PromptService class
2. Correct save() signature: save(session, tables) not save(session, engine)
3. Document Prompt model with constraints: UniqueConstraint('prompt_key', 'prompt_type'), indexes (ix_prompts_category_step, ix_prompts_active)
4. Add missing: prompts/__init__.py exports (sync_prompts, load_all_prompts, get_prompts_dir, extract_variables_from_content, VariableResolver)
5. Add missing: _version_greater() semantic version comparison
6. Document sync_prompts() YAML-to-DB sync process
7. Exclude: get_prompt() context parameter (mark as non-functional vestigial code)
8. Exclude: get_guidance() context filtering (broken, uses non-existent Prompt.context field)

### Step 11: State and Registry API Reference
**Agent:** documentation-generation:api-documenter
**Skills:** none
**Context7 Docs:** /sqlalchemy/sqlalchemy
**Group:** B
1. Create docs/api/state.md documenting PipelineStepState and PipelineRunInstance models
2. Document caching logic: input_hash + prompt_version for cache key
3. Document traceability linking via run_id
4. Create docs/api/registry.md documenting PipelineDatabaseRegistry with FK ordering validation
5. Document ReadOnlySession wrapper (blocks write operations)

### Step 12: Getting Started Guide
**Agent:** documentation-generation:tutorial-engineer
**Skills:** none
**Context7 Docs:** /pydantic/pydantic, /sqlalchemy/sqlalchemy
**Group:** C
1. Create docs/guides/getting-started.md with installation, quickstart, first pipeline example
2. Document auto-SQLite initialization for development
3. Include explicit database setup for production
4. Cover provider configuration (GeminiProvider example)

### Step 13: Basic Pipeline Example
**Agent:** documentation-generation:tutorial-engineer
**Skills:** none
**Context7 Docs:** /pydantic/pydantic, /sqlalchemy/sqlalchemy
**Group:** C
1. Create docs/guides/basic-pipeline.md with complete working example
2. Define domain models, registry (FK order), instruction classes, context classes, extractions, steps, strategy, pipeline
3. Show execution with caching and save() to database
4. Based on consumer project patterns (logistics-intelligence rate_card_parser)

### Step 14: Multi-Strategy Pipeline Example
**Agent:** documentation-generation:tutorial-engineer
**Skills:** none
**Context7 Docs:** /pydantic/pydantic
**Group:** C
1. Create docs/guides/multi-strategy.md showing strategy selection based on context
2. Example: LaneBasedStrategy vs ZoneBasedStrategy selected by context['table_type']
3. Show strategy-specific extraction methods (lane_based(), zone_based())
4. Document strategy priority order and can_handle() logic

### Step 15: Prompt Management Guide
**Agent:** documentation-generation:tutorial-engineer
**Skills:** none
**Context7 Docs:** -
**Group:** C
1. Create docs/guides/prompts.md covering YAML prompt structure, sync_prompts() usage, version management
2. Document prompt key auto-discovery (strategy-level -> step-level -> explicit)
3. Document variable extraction and validation
4. Include template formatting examples

### Step 16: Known Limitations Section
**Agent:** documentation-generation:docs-architect
**Skills:** none
**Context7 Docs:** -
**Group:** C
1. Create docs/architecture/limitations.md documenting: clear_cache() bug (uses ReadOnlySession for delete/commit), Prompt.context vestigial code, single-level inheritance requirement for naming validation, Gemini-only provider
2. Include workarounds where applicable
3. Link to issue tracker for future fixes

### Step 17: C4 Context Diagram
**Agent:** documentation-generation:mermaid-expert
**Skills:** none
**Context7 Docs:** -
**Group:** D
1. Create docs/architecture/diagrams/c4-context.mmd showing system context
2. External actors: User/Application, LLM Provider (Gemini), Database, YAML Prompt Files
3. System boundary: llm-pipeline framework
4. Show data flows between actors and system

### Step 18: C4 Container Diagram
**Agent:** documentation-generation:mermaid-expert
**Skills:** none
**Context7 Docs:** -
**Group:** D
1. Create docs/architecture/diagrams/c4-container.mmd showing internal containers
2. Containers: Pipeline Orchestrator, LLM Integration, Prompt Management, State Tracking, Database Access
3. Show container relationships and data flows
4. Include technology labels (Python, Pydantic, SQLAlchemy)

### Step 19: C4 Component Diagram
**Agent:** documentation-generation:mermaid-expert
**Skills:** none
**Context7 Docs:** -
**Group:** D
1. Create docs/architecture/diagrams/c4-component.mmd showing component details
2. Correct inheritance: LLMStep extends ABC (not LLMResultMixin)
3. Correct inheritance: LLMResultMixin extends BaseModel (used by instruction classes)
4. Show Pipeline Orchestrator components: PipelineConfig, Strategy System, Step Execution, Extraction, Transformation
5. Show relationships: composes, uses, references
6. Include key methods on each component

### Step 20: Documentation Navigation
**Agent:** documentation-generation:reference-builder
**Skills:** none
**Context7 Docs:** -
**Group:** E
1. Create docs/index.md with navigation to all documentation sections
2. Build cross-reference links between related docs
3. Add "See Also" sections to each doc linking related content
4. Create docs/README.md with overview and table of contents

## Risks & Mitigations
| Risk | Impact | Mitigation |
| --- | --- | --- |
| Propagating research errors into docs | High | Use VALIDATED_RESEARCH.md as single source of truth for corrections. Explicitly check 5 contradictions and 10 gaps during generation. |
| Missing critical API items | Medium | Maintain checklist from validation report. Verify all 10 missing items added during Step 4-11 review. |
| C4 diagram inheritance errors | Medium | Validate against source code before rendering. LLMStep extends ABC, LLMResultMixin extends BaseModel. Step 19 must verify. |
| Incomplete examples | Low | Base all examples on consumer project patterns (logistics-intelligence). Reference VALIDATED_RESEARCH.md consumer section. |
| File organization inconsistency | Low | Define structure in Step 1, all agents follow same pattern. |

## Success Criteria
- [ ] All 5 research contradictions corrected in docs (LLMStep inheritance, transformation routing, save() signature, clear_cache() bug, two-phase write)
- [ ] All 10 missing API items added (StepKeyDict, get_raw_data/current/sanitized, get_guidance, _query_prompt_keys, Prompt constraints, prompts exports, _version_greater, consensus helpers, LLMResultMixin __init_subclass__)
- [ ] Deprecated features excluded or marked (save_step_yaml, clear_cache bug, context parameter)
- [ ] C4 diagrams show correct inheritance (LLMStep -> ABC, LLMResultMixin -> BaseModel)
- [ ] Architecture docs document two-phase write pattern accurately (flush for IDs, commit at save)
- [ ] API reference complete for all public modules (pipeline, step, strategy, extraction, transformation, llm, prompts, state, registry)
- [ ] Usage guides include working examples based on consumer project patterns
- [ ] Navigation and cross-references functional across all docs
- [ ] docs/ folder structure: architecture/, api/, guides/, architecture/diagrams/

## Phase Recommendation
**Risk Level:** medium
**Reasoning:** Documentation generation with known research errors (5 contradictions, 10 gaps). Review phase critical to verify all corrections applied and no missing items. Testing phase unnecessary (no code logic to validate, only markdown content).
**Suggested Exclusions:** testing
