# IMPLEMENTATION - STEP 3: DESIGN PATTERNS

**Status:** completed

## Summary

Created comprehensive design patterns documentation covering all core patterns used in llm-pipeline framework. Document includes detailed explanations of 6 major patterns with code examples, usage patterns, and extension points. Validated all patterns against source code and applied corrections from VALIDATED_RESEARCH.md.

## Files

**Created:**
- `docs/architecture/patterns.md` (comprehensive design patterns documentation)
- `docs/tasks/in-progress/adhoc-20260210-docs-generation/implementation/step-3-design-patterns.md` (this file)

**Modified:** none

**Deleted:** none

## Changes

### File: `docs/architecture/patterns.md`

Created comprehensive design patterns documentation with the following sections:

1. **Class-Level Configuration via __init_subclass__**
   - Pipeline naming validation (Pipeline suffix, Registry/Strategies matching)
   - Extraction model configuration (model parameter, Extraction suffix)
   - LLMResultMixin example validation
   - Code examples showing validation at class definition time

2. **Step Factory Pattern via @step_definition**
   - Decorator implementation for step configuration
   - Automatic factory method generation (create_definition)
   - Naming convention enforcement (Step/Instructions/Transformation/Context matching)
   - Usage examples showing declarative step definition

3. **Smart Method Detection Pattern**
   - Extraction priority: default → strategy-specific → single method → error
   - Transformation priority: default → single method → passthrough → error
   - **Correction applied**: Documented that transformation does NOT support strategy-specific routing (only extraction does)
   - Code examples for single method, explicit default, strategy-specific, and passthrough patterns

4. **StepKeyDict Pattern**
   - Custom dict subclass for dual-key access (string and Step class)
   - Snake_case normalization (SemanticMappingStep → "semantic_mapping")
   - Usage in pipeline.data and pipeline._instructions
   - Examples showing both access patterns

5. **Read-Only Session Pattern**
   - ReadOnlySession wrapper blocking write operations during execution
   - Implementation showing allowed (query, exec, get) vs blocked (add, commit, delete, flush) operations
   - Usage pattern showing when read-only vs real session is active
   - Clear error messages guiding correct usage

6. **Two-Phase Write Pattern**
   - **Correction applied**: Documented accurate two-phase pattern (not "all writes deferred to save")
   - Phase 1 (execution): _real_session.add() + flush() for ID assignment
   - Phase 2 (save): commit() + PipelineRunInstance tracking
   - Complete example showing FK references between extractions
   - Consumer project confirmation with code comments (lines 632-639)
   - Common pitfalls and correct approaches

7. **Extension Points**
   - Custom LLM Provider implementation template
   - Custom sanitization override example
   - Custom VariableResolver for prompt variable extraction
   - Post-action hooks for step completion logic
   - Extraction validation override for domain-specific rules

## Decisions

### Decision: Correct two-phase write pattern documentation
**Choice:** Document accurate two-phase pattern (Phase 1: flush during execution, Phase 2: commit at save) instead of research's "all writes deferred" narrative
**Rationale:** VALIDATED_RESEARCH.md contradiction #5 confirmed the actual pattern via consumer project code comments. Accurate documentation of this pattern is critical as it's the foundation for FK integrity between extractions.

### Decision: Exclude strategy-specific routing for transformations
**Choice:** Document that transformations do NOT support strategy-specific method routing, only extraction does
**Rationale:** VALIDATED_RESEARCH.md contradiction #2 confirmed transformation.py does not check _current_strategy. Documenting this incorrectly would mislead users attempting to implement strategy-specific transformations.

### Decision: Include consumer project confirmation
**Choice:** Include direct quote from consumer project comments confirming two-phase write intent
**Rationale:** Validates that the pattern is intentional design, not accidental implementation. Strengthens documentation authority by showing real-world usage.

### Decision: Comprehensive extension point examples
**Choice:** Provide complete, runnable code examples for each extension point
**Rationale:** Extension points are critical for framework adoption. Complete examples reduce integration friction and demonstrate framework flexibility.

### Decision: Pattern interactions section
**Choice:** Add final section showing how all patterns work together in a complete example
**Rationale:** Helps readers understand the holistic design. Shows that patterns aren't isolated techniques but a cohesive system.

## Verification

- [x] All 6 core patterns documented with implementation code
- [x] Two-phase write pattern correction applied (flush vs commit phases explicit)
- [x] Transformation routing correction applied (no strategy-specific routing)
- [x] Code examples match actual source code structure
- [x] StepKeyDict pattern documented with normalization rules
- [x] Read-only session pattern shows both wrapper and usage
- [x] Extension points provide complete, runnable examples
- [x] Pattern interactions section shows holistic usage
- [x] Consumer project confirmation included for two-phase write
- [x] Common pitfalls documented with correct approaches
- [x] All naming conventions documented (Pipeline, Step, Extraction, Instructions, Transformation, Context)
- [x] File created at correct path: docs/architecture/patterns.md
