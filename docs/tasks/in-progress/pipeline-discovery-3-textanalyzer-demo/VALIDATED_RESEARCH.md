# Research Summary

## Executive Summary

Cross-referenced all 3 domain research files against actual source code in llm_pipeline/. Found 3 critical contradictions that would cause runtime errors, 2 naming inconsistencies across research files, and 5 unresolved architectural decisions requiring CEO input before planning can proceed. The core framework patterns (PipelineConfig subclassing, entry point discovery, context merging, WebSocket streaming, prompt seeding) are accurately documented and verified against source.

## Domain Findings

### Naming Convention Enforcement (CRITICAL)
**Source:** step-1, step-3, step.py L56-68

Step 3 research proposes instruction class names `SentimentAnalysis`, `TopicExtractionResult`, `SummaryResult`. The `step_definition` decorator (step.py L63-68) enforces `{StepPrefix}Instructions` naming -- it would raise ValueError for any of these names.

Correct names per framework enforcement:
- `SentimentAnalysisInstructions` (Step 1/2 agree)
- `TopicExtractionInstructions` (Step 1/2 agree)
- `SummaryInstructions` (Step 1/2 agree)

Step 3's AgentRegistry mapping (L61-65) uses the wrong value types. Must use the `{Prefix}Instructions` names.

### process_instructions Return Type (CRITICAL)
**Source:** step-3 L567-569, pipeline.py L383-405

Step 3 shows `process_instructions` returning a plain dict when `context=SentimentAnalysisContext` is declared in `step_definition`. Source code at pipeline.py L386-392 enforces: if `step._context` is set, `process_instructions` MUST return that exact PipelineContext subclass instance, not a dict. Returning a dict causes TypeError.

Correct pattern: `return SentimentAnalysisContext(sentiment=..., sentiment_confidence=...)`.

### Extraction Method Name (MODERATE)
**Source:** step-3 L511, step-1 L243-248, extraction.py L213-280

Step 3 shows `TopicExtraction.extract()` as a direct override. The base class `extract()` is the auto-dispatch method that calls `default()` (or strategy-named method) and then runs `_validate_instances()`. Overriding `extract()` directly bypasses instance validation (NaN, NULL checks). Should use `def default(self, results)` instead, as Step 1 and Step 2 correctly document.

### Context Field Name Inconsistency
**Source:** step-1 L361, step-3 L477-478, L497

Step 1 uses `sentiment_score` for the context field from sentiment analysis. Step 3 uses `sentiment_confidence`. These are different fields. The LLMResultMixin already provides `confidence_score` as a built-in field. Need to decide which field to expose in context.

### Topic SQLModel Schema Undefined
**Source:** step-1 L218-223, step-2 L444, step-3 L537-542

No consensus on Topic model fields:
- Step 1: name, confidence, run_id
- Step 2: name, relevance (from TopicItem nested model)
- Step 3: name only (incomplete)

Related: Step 3 introduces `TopicItem` (L289, L630) as a nested Pydantic model in TopicExtractionInstructions but never defines its fields. TopicItem is the LLM output shape; Topic is the SQLModel for DB persistence. The extraction bridges them.

### Strategy Naming Disagreement
**Source:** step-1 L92-111, step-2 L83-108, tests/test_pipeline.py

Step 1 uses `DefaultStrategy` (NAME = "default"). Step 2 uses `TextAnalyzerStrategy` (NAME = "text_analyzer"). The test suite uses `DefaultStrategy`. Both are valid for a single-strategy pipeline.

### Pipeline-Specific Table Creation
**Source:** step-1 L232-237

Framework's `init_pipeline_db()` creates only framework tables (prompts, pipeline_step_states, etc). Pipeline-specific tables like `demo_topics` must be created separately. Research identifies two options (in seed_prompts or in __init__) but none of the 3 files declares a definitive approach.

### Validated Patterns (Correct Across All Research)
**Source:** all three research files, verified against source

- PipelineConfig.__init_subclass__ naming enforcement: confirmed (pipeline.py L112-159)
- Constructor signature and factory pattern: confirmed (pipeline.py L161-171, app.py L24-46)
- Entry point discovery flow: confirmed (app.py L49-102)
- seed_prompts isolated try/except: confirmed (app.py L84-93)
- Prompt unique constraint (prompt_key, prompt_type): confirmed (db/prompt.py L41)
- PipelineContext merge via _validate_and_merge_context: confirmed (pipeline.py L383-413)
- PipelineInputData validation in execute(): confirmed (pipeline.py L483-499)
- ReadOnlySession for steps, _real_session for extractions: confirmed (pipeline.py L243, step.py L312)
- WebSocket streaming fully framework-managed: confirmed (no demo-specific event code needed)
- build_step_agent with defer_model_check=True: confirmed (agent_builders.py L110)
- Dynamic system prompt injection via @agent.instructions: confirmed (agent_builders.py L120-146)
- StepDeps dependency injection: confirmed (agent_builders.py L22-53)

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Pending -- see Questions below | | |

## Assumptions Validated
- [x] PipelineConfig subclass requires Pipeline suffix, matching Registry/Strategies/AgentRegistry prefixes
- [x] step_definition enforces {StepPrefix}Instructions, {StepPrefix}Context, {StepPrefix}Transformation naming
- [x] PipelineExtraction auto-dispatch uses default() method, not extract() override
- [x] _validate_and_merge_context enforces PipelineContext subclass return when context= is declared
- [x] seed_prompts is called during _discover_pipelines with isolated error handling
- [x] Factory closure absorbs **kwargs (input_data flows through execute(), not constructor)
- [x] Prompt auto-discovery checks {step_name}.{strategy_name} then {step_name}
- [x] LLMResultMixin.example is optional (not enforced if not present)
- [x] WebSocket streaming requires zero demo-specific code
- [x] Model string flows from factory closure -> constructor -> agent.run_sync()

## Open Items
- Instruction class naming in Step 3 research is incorrect; must use {StepPrefix}Instructions pattern
- process_instructions must return PipelineContext subclass instance when context= param is set
- TopicExtraction should use def default() not def extract()
- TopicItem nested model fields undefined
- Topic SQLModel fields undefined (need CEO decision)
- Table creation strategy for demo_topics undefined
- Strategy naming convention (DefaultStrategy vs TextAnalyzerStrategy) undecided
- Context field name (sentiment_score vs sentiment_confidence) undecided
- Prompt content for 6 prompts (3 system + 3 user) not drafted

## Recommendations for Planning
1. Standardize ALL instruction class names to {StepPrefix}Instructions per framework enforcement
2. Use PipelineContext subclass returns from process_instructions (not dicts) since context= will be declared
3. Use def default() in TopicExtraction to get framework validation for free
4. Create demo_topics table in seed_prompts(engine) alongside prompt seeding -- it already has the engine and runs at discovery time
5. Use explicit prompt keys in step_definition (simpler, no DB lookup during step creation)
6. Define create_failure safe_defaults by giving instruction custom fields string defaults (e.g. sentiment="" for SentimentAnalysisInstructions)
