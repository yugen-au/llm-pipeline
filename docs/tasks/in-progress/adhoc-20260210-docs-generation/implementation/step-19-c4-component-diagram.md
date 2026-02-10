# IMPLEMENTATION - STEP 19: C4 COMPONENT DIAGRAM

**Status:** completed

## Summary

Created C4 Component diagram in Mermaid format showing Pipeline Orchestrator architecture with corrected inheritance relationships, component hierarchy, key methods, and relationships. Diagram visualizes 5 major component groups within the Pipeline Orchestrator container: Pipeline Configuration & Execution, Strategy System, Step Execution, Data Extraction, and Data Transformation. All inheritance corrected per VALIDATED_RESEARCH.md: LLMStep extends ABC (not LLMResultMixin), LLMResultMixin extends BaseModel.

## Files

**Created:** docs/architecture/diagrams/c4-component.mmd

**Modified:** none

**Deleted:** none

## Changes

### File: `docs/architecture/diagrams/c4-component.mmd`

Created new Mermaid C4 component diagram with following structure:

#### Container: Pipeline Orchestrator

**Subgroups:**

1. **Pipeline Configuration & Execution**
   - PipelineConfig: Main orchestrator with context/data/db_instances management, execute(), get_raw_data(), get_current_data(), get_sanitized_data(), save(session, tables)
   - StepKeyDict: Snake_case normalization for step class keys, __getitem__, __setitem__, get(), pop()

2. **Strategy System**
   - PipelineStrategies: Container for strategy collection, get_strategies()
   - PipelineStrategy: Base class with can_handle(context) for selection logic, get_steps()
   - StepDefinition: Configuration dataclass with step_class, instructions, system/user prompt keys, extractions, transformation, context; create_step(pipeline) factory

3. **Step Execution**
   - LLMStep extends ABC: Core step abstraction with pipeline reference, instructions, context; run(), extract_data(), apply_transformation()
   - LLMResultMixin extends BaseModel: Used by instruction classes (e.g., SemanticMappingInstructions), has example dict and __init_subclass__() validation
   - @step_definition decorator: Validates naming (must end with 'Step'), creates factory, enforces configuration

4. **Data Extraction**
   - PipelineExtraction extends ABC: Responsible for model extraction with smart method detection (priority: default() → strategy_name() → single method → error); _validate_instance() for NaN/NULL/FK checks

5. **Data Transformation**
   - PipelineTransformation extends ABC: Data structure changes with INPUT_TYPE/OUTPUT_TYPE validation; smart method detection (priority: default() → single method → passthrough → error)

#### Container: Registry & State

- PipelineRegistry: FK ordering validation
- PipelineStepState: Caching with input_hash + prompt_version key, traceability via run_id
- PipelineRunInstance: Run instance tracking and traceability linking

#### External: LLM & Database

- LLMProvider extends ABC: execute_llm_step() function
- ReadOnlySession: Blocks write operations on session

#### Relationships

**Composition (uses/composes):**
- PipelineConfig composes StepKeyDict, uses Strategy System, Step Execution, Data Extraction, Data Transformation
- Strategy System: PipelineStrategies contains PipelineStrategy, creates StepDefinition
- StepDefinition references LLMStep, PipelineExtraction, PipelineTransformation

**Inheritance (⟵):**
- LLMStep ⟵ ABC (corrected from LLMResultMixin)
- LLMResultMixin ⟵ BaseModel (used by instruction classes)
- PipelineExtraction ⟵ ABC
- PipelineTransformation ⟵ ABC
- PipelineStrategy ⟵ ABC
- LLMProvider ⟵ ABC

**Data Flow:**
- LS produces PipelineStepState
- PipelineStepState tracked by PipelineRunInstance
- PipelineExtraction persists to PipelineRegistry
- PipelineTransformation validates through PipelineExtraction

**Execution:**
- LLMStep calls LLMProvider
- PipelineConfig accesses ReadOnlySession

## Decisions

### Decision: Inheritance Correction
**Choice:** LLMStep extends ABC (not LLMResultMixin), LLMResultMixin extends BaseModel
**Rationale:** VALIDATED_RESEARCH.md identified this as critical contradiction (contradiction #1). Source code verified: LLMStep is abstract base class extending ABC; LLMResultMixin is Pydantic BaseModel used for instruction classes like SemanticMappingInstructions. Propagating wrong inheritance into diagram would mislead users on architecture.

### Decision: Component Grouping
**Choice:** 5 subgroups (Config/Execution, Strategy, Step, Extraction, Transformation)
**Rationale:** Matches PLAN.md Step 19 requirements: "Pipeline Orchestrator components: PipelineConfig, Strategy System, Step Execution, Extraction, Transformation". Groups logically separate concerns while maintaining visibility of relationships.

### Decision: Method Inclusion
**Choice:** Include key methods on each component (execute, extract, transform, can_handle, create_step)
**Rationale:** PLAN.md requires "Include key methods on each component". Methods shown represent public API and demonstrate component responsibility. Smart method detection priority documented inline for extraction/transformation.

### Decision: Relationship Types
**Choice:** Use distinct relationship labels (composes, uses, references, has-a, tracks-by, persists-to, validates, calls, accesses, decorates)
**Rationale:** Improves diagram clarity by explicitly showing relationship semantics. Matches C4 best practices for component-level clarity.

### Decision: Mermaid Styling
**Choice:** Color-coded by component group (e.g., blue for Config, orange for Steps, green for Extraction)
**Rationale:** Improves visual navigation of subgroups. Matches documentation generation plugin style guidelines.

## Verification

- [x] Diagram file created at correct location: docs/architecture/diagrams/c4-component.mmd
- [x] LLMStep inheritance corrected: extends ABC (not LLMResultMixin)
- [x] LLMResultMixin inheritance corrected: extends BaseModel (used by instruction classes)
- [x] Pipeline Orchestrator components all present: PipelineConfig, Strategy System, Step Execution, Extraction, Transformation
- [x] Relationships documented: composes, uses, references, has-a
- [x] Key methods included on each component
- [x] Two-phase write pattern visible through extract_data/save distinction
- [x] Smart method detection priorities documented for extraction and transformation
- [x] Registry & State container separate from Pipeline Orchestrator as per C4 Container diagram
- [x] Mermaid syntax valid and renderable
