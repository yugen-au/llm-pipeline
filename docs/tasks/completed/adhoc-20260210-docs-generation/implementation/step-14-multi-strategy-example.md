# IMPLEMENTATION - STEP 14: MULTI STRATEGY EXAMPLE

**Status:** completed

## Summary

Created comprehensive Multi-Strategy Pipeline Example guide at `docs/guides/multi-strategy.md`. Guide demonstrates strategy selection via `can_handle()`, strategy-specific extraction methods, priority ordering, and context-driven execution flow. Based on real-world rate card parser from logistics-intelligence consumer project.

## Files

**Created:**
- `docs/guides/multi-strategy.md` (15.2KB, 686 lines)

**Modified:** none

**Deleted:** none

## Changes

### File: `docs/guides/multi-strategy.md`

Created tutorial-style guide with progressive learning structure:

**Learning Objectives:**
- Define multiple strategies for data variants
- Implement context-based strategy selection
- Create strategy-specific extraction methods
- Configure strategy priority order
- Build runtime-adaptive pipelines

**Structure:**
1. **Introduction**: Why multi-strategy, what you'll build (3 strategies: lane-based, destination-based, global rates)
2. **Strategy Definition**: `can_handle()` logic with context checking, complete example for all 3 strategies
3. **Strategy Registration**: Declarative `PipelineStrategies` syntax with priority ordering
4. **Strategy-Specific Extractions**: Method detection priority (default → strategy-name → single → error), 3 common patterns
5. **Pipeline Configuration**: Connect registry + strategies, explain execution flow
6. **Execution Flow**: Step-by-step strategy selection walkthrough showing per-step can_handle() calls
7. **Context-Driven Selection**: Detection step pattern that populates context for later filtering
8. **Complete Example**: Full working code with file structure, models, pipeline, usage
9. **Troubleshooting**: Multiple strategies match, no strategy matches, wrong extraction method called
10. **Best Practices**: Strategy organization, context keys, selection timing, extraction method naming

**Key Features:**
- Progressive disclosure from simple to complex
- Real-world example from consumer project (rate_card_parser)
- Hands-on code with complete working pipeline
- Troubleshooting section with common errors
- Best practices with good/bad examples
- Cross-references to API docs and other guides

**Pedagogical Elements:**
- "What You'll Learn" learning objectives
- "Prerequisites" with links to basic guide
- "Time Estimate" for planning
- "Final Result" preview
- "Key Points" callouts after code blocks
- "Notice" annotations for important details
- "Common Patterns" with multiple approaches
- "Debug" tips for troubleshooting
- "Summary" reinforcing key concepts
- "Next Steps" for continued learning

## Decisions

### Decision: Use Rate Card Parser as Primary Example
**Choice:** Base all examples on logistics-intelligence rate_card_parser with 3 strategies (LaneBasedStrategy, DestinationBasedStrategy, GlobalRatesStrategy)
**Rationale:** Real consumer project provides validated patterns. Shows actual strategy selection logic (`context['table_type']`), strategy-specific steps (ItemIdentificationDef vs LocationIdentificationDef), and extraction method routing (lane_based() vs destination_based()). More credible than synthetic examples.

### Decision: Tutorial-Style Progressive Structure
**Choice:** Follow tutorial engineering principles: learning objectives → concepts → guided practice → complete example → troubleshooting → best practices
**Rationale:** Step 14 plan specifies "tutorial-engineer" agent. Contract requires hands-on learning experience. Progressive disclosure prevents overwhelming readers. Matches existing guides pattern.

### Decision: Emphasize Per-Step Strategy Selection
**Choice:** Dedicated "Execution Flow" section with step-by-step walkthrough showing can_handle() called before EACH step
**Rationale:** Common misconception is strategy selected once at start. VALIDATED_RESEARCH.md confirms step-by-step selection is core pattern. Explicit walkthrough prevents misunderstanding.

### Decision: Include Method Detection Priority Table
**Choice:** Document 4-level priority: explicit default → strategy-specific → single method → error
**Rationale:** Validated research confirms PipelineExtraction.extract() uses this priority. Critical for understanding when lane_based() vs destination_based() methods are called. Matches source code in extraction.py lines 213-280.

### Decision: Troubleshooting Section with Common Errors
**Choice:** Three scenarios: multiple strategies match, no strategy matches, wrong extraction method called
**Rationale:** Tutorial best practice. Anticipates common mistakes. Provides actionable solutions (reorder strategies, add fallback, check method naming).

### Decision: Cross-Reference to API Docs
**Choice:** "Next Steps" and inline links to strategy.md, extraction.md, patterns.md
**Rationale:** Guides provide practical examples, API docs provide complete reference. Cross-references support different learning paths.

## Verification

- [x] Guide covers all Plan.md Step 14 requirements (strategy selection, strategy-specific extractions, priority order, can_handle() logic)
- [x] Examples match consumer project patterns (rate_card_parser pipeline.py, constraint_extraction.py)
- [x] Strategy selection shows context-based filtering (context['table_type'])
- [x] Extraction method routing documented with priority order (default → strategy → single → error)
- [x] Complete working example included (models, pipeline, strategies, usage)
- [x] Tutorial structure follows pedagogical principles (objectives, prerequisites, progressive steps, troubleshooting)
- [x] Corrections from VALIDATED_RESEARCH.md applied (per-step selection, method detection priority)
- [x] Cross-references to related docs included (basic-pipeline.md, API references)
- [x] Code examples are runnable and complete
- [x] Best practices section with good/bad examples
