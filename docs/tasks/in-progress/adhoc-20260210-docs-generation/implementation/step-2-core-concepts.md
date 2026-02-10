# IMPLEMENTATION - STEP 2: CORE CONCEPTS
**Status:** completed

## Summary
Created comprehensive core concepts documentation covering declarative configuration, three-tier data model, strategy pattern, step lifecycle, extraction/transformation, naming conventions, execution order validation, and state tracking.

## Files
**Created:**
- docs/architecture/concepts.md

**Modified:** none
**Deleted:** none

## Changes
### File: `docs/architecture/concepts.md`
Created comprehensive core concepts documentation with the following sections:

1. **Declarative Configuration** - Explains `__init_subclass__` pattern for Pipeline, Registry, Strategies, and Step components with validation rules
2. **Three-Tier Data Model** - Documents separation of context (metadata), data (transformations), and extractions (database models) with access patterns and lifecycle
3. **Strategy Pattern** - Covers strategy selection via `can_handle()`, step definitions, prompt auto-discovery, and auto-generated properties
4. **Step Lifecycle** - Details 6-phase lifecycle: preparation, LLM execution, instruction processing, extraction, transformation, context contribution
5. **Extraction and Transformation** - Documents smart method detection, validation, two-phase write pattern, and method detection priority differences
6. **Naming Conventions and Validation** - Complete reference table of all component naming rules with validation enforcement and escape hatches
7. **Execution Order Validation** - Explains FK dependency validation, extraction order validation, and step position validation
8. **State Tracking and Caching** - Documents PipelineStepState, PipelineRunInstance, cache invalidation, and known limitations

Key corrections applied from VALIDATED_RESEARCH.md:
- Two-phase write pattern documented explicitly (flush during execution for IDs, commit at save)
- Transformation does NOT support strategy-specific routing (only default → single → passthrough → error)
- Documented that LLMStep extends ABC (not LLMResultMixin)
- Covered three-tier separation: context for strategy routing, data for transforms, extractions for DB
- Explained StepKeyDict pattern for Step class key normalization
- Documented FK dependency enforcement and execution order validation
- Added known limitation about clear_cache() bug

## Decisions
### Decision: Structure by progressive complexity
**Choice:** Organize concepts from foundational (declarative config) to advanced (state tracking)
**Rationale:** Mirrors learning path - users need to understand configuration before lifecycle, lifecycle before validation

### Decision: Include comparison tables
**Choice:** Added tables comparing extraction vs transformation method detection, naming conventions reference table
**Rationale:** Quick reference for developers - reduces need to re-read full sections

### Decision: Document two-phase write pattern prominently
**Choice:** Dedicated section in extraction lifecycle explaining flush vs commit
**Rationale:** Critical design decision that enables FK references between extractions. Validated research showed this was misunderstood as "all writes deferred to save()"

### Decision: Explain "why" for strict naming
**Choice:** Added dedicated section explaining rationale (auto-discovery, normalization, consistency, error prevention)
**Rationale:** Developers often resist naming conventions without understanding their purpose

## Verification
[x] All key requirements from PLAN.md Step 2 covered
[x] Declarative configuration explained with examples
[x] Three-tier data model documented (context, data, extractions)
[x] Strategy pattern with can_handle() and prompt auto-discovery
[x] Step lifecycle with 6 phases documented
[x] Extraction/transformation smart method detection explained
[x] Naming conventions reference table complete
[x] Execution order validation (FK dependencies, extraction order)
[x] Two-phase write pattern documented explicitly
[x] Known limitations included (clear_cache bug)
[x] All corrections from VALIDATED_RESEARCH.md applied
[x] No deprecated features documented as working (save_step_yaml excluded)
