# Step 13: Basic Pipeline Example - Implementation Summary

## Deliverable
Created comprehensive tutorial guide: `docs/guides/basic-pipeline.md`

## Overview
Complete working example demonstrating document classification pipeline with all core framework patterns. Tutorial follows pedagogical design principles with progressive skill building from basic concepts to advanced patterns.

## Content Structure

### Core Tutorial (Steps 1-10)
1. **Domain Models** - Project, Document, DocumentMetadata with FK relationships
2. **Database Registry** - FK dependency ordering validation
3. **Instruction Classes** - LLMResultMixin inheritance, example validation
4. **Context Classes** - PipelineContext for step results
5. **Extraction Classes** - Smart method detection (default/strategy/single)
6. **Pipeline Steps** - DocumentTypeStep, MetadataExtractionStep with full lifecycle
7. **Step Factories** - create_definition() pattern
8. **Strategy Definition** - DocumentClassificationStrategy with can_handle()
9. **Strategy Registry** - DocumentClassifierStrategies container
10. **Pipeline Config** - DocumentClassifierPipeline with sanitize()

### Execution Examples
- Basic execution with GeminiProvider
- Caching behavior (input hash + prompt version)
- Two-phase write: flush() during extraction, commit() at save()
- Working with extractions and database persistence

### Advanced Patterns
- Multi-call steps (multiple LLM calls per step)
- Accessing previous step data (context, instructions, raw/current/sanitized)
- Custom variable resolvers

### Troubleshooting
- 4 common errors with fixes (naming, registry order, missing example, strategy)
- Debugging tips (logging, execution order, cached states)

## Key Features
- **30-minute tutorial** with clear learning objectives
- **Complete runnable code** at each stage
- **Progressive disclosure** - simple to complex
- **Error anticipation** - common mistakes documented
- **Validated patterns** - based on logistics-intelligence consumer project

## Corrections Applied
- LLMStep extends ABC (not LLMResultMixin)
- Two-phase write documented (flush for IDs, commit at save)
- FK dependency ordering enforced in registry
- Smart method detection priority explained

## Word Count
~3,200 words, comprehensive coverage suitable for beginners

## File Location
`C:\Users\SamSG\Documents\claude_projects\llm-pipeline\docs\guides\basic-pipeline.md`
