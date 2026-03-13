# Research Summary

## Executive Summary

Cross-referenced all 3 domain research files against actual source code in llm_pipeline/. Found 3 critical contradictions that would cause runtime errors, 2 naming inconsistencies across research files, and 5 architectural decisions resolved via CEO Q&A. All open items now resolved. The core framework patterns (PipelineConfig subclassing, entry point discovery, context merging, WebSocket streaming, prompt seeding) are accurately documented and verified against source. Implementation can proceed with the consolidated decisions below.

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

Correct pattern: `return SentimentAnalysisContext(sentiment=...)`.

### Extraction Method Name (MODERATE)
**Source:** step-3 L511, step-1 L243-248, extraction.py L213-280

Step 3 shows `TopicExtraction.extract()` as a direct override. The base class `extract()` is the auto-dispatch method that calls `default()` (or strategy-named method) and then runs `_validate_instances()`. Overriding `extract()` directly bypasses instance validation (NaN, NULL checks). Should use `def default(self, results)` instead, as Step 1 and Step 2 correctly document.

### Context Field Name Inconsistency (RESOLVED)
**Source:** step-1 L361, step-3 L477-478, L497

Step 1 uses `sentiment_score` for the context field from sentiment analysis. Step 3 uses `sentiment_confidence`. CEO decision: reuse LLMResultMixin's built-in `confidence_score` field -- no custom confidence field needed. SentimentAnalysisContext exposes `sentiment: str` and `confidence_score: float` (inherited from LLMResultMixin on the instruction output).

### Topic SQLModel Schema (RESOLVED)
**Source:** step-1 L218-223, step-2 L444, step-3 L537-542

CEO decision on Topic SQLModel fields: `name: str`, `relevance: float`, `run_id: str` (for traceability). TopicItem nested Pydantic model (LLM output shape): `name: str`, `relevance: float`. TopicExtraction.default() bridges TopicItem -> Topic by copying name/relevance and attaching run_id from pipeline context.

### Strategy Naming (RESOLVED)
**Source:** step-1 L92-111, step-2 L83-108, tests/test_pipeline.py

CEO decision: `DefaultStrategy` (NAME = "default"). Follows test conventions, generic for single-strategy pipelines. Prompt auto-discovery will try `{step_name}.default` first (not found), then fall back to `{step_name}` (found). Using explicit prompt keys avoids this lookup entirely.

### Pipeline-Specific Table Creation (RESOLVED)
**Source:** step-1 L232-237

CEO decision: create `demo_topics` table in `seed_prompts(engine)` alongside prompt seeding. Single setup entry point -- seed_prompts already has the engine reference and runs at discovery time via `_discover_pipelines`. Use `SQLModel.metadata.create_all(engine, tables=[Topic.__table__])` to create only the pipeline-specific table.

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
| Strategy naming: DefaultStrategy vs TextAnalyzerStrategy? | DefaultStrategy (NAME="default"), follows test conventions | Prompt auto-discovery falls back to {step_name}; explicit keys recommended |
| Topic SQLModel fields beyond name? | name + relevance (float) + run_id (str) | Defines DB schema and extraction bridge logic |
| Context field from sentiment step: sentiment_score vs sentiment_confidence? | Reuse LLMResultMixin's built-in confidence_score | No custom confidence field needed; SentimentAnalysisContext has sentiment only, confidence accessed on Instructions output |
| TopicItem nested model fields? | name (str) + relevance (float) | Matches Topic SQLModel minus run_id; extraction adds run_id |
| Table creation: seed_prompts or pipeline __init__? | seed_prompts(engine) alongside prompt seeding | Single setup entry point; already has engine and runs at discovery |

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
- [x] Strategy naming: DefaultStrategy (NAME="default") per CEO decision
- [x] Topic SQLModel: name (str) + relevance (float) + run_id (str) per CEO decision
- [x] TopicItem nested model: name (str) + relevance (float) per CEO decision
- [x] Sentiment context field: SentimentAnalysisContext has sentiment only; confidence accessed via LLMResultMixin.confidence_score on Instructions output per CEO decision
- [x] Table creation: in seed_prompts(engine) alongside prompt seeding per CEO decision

## Open Items
- Prompt content for 6 prompts (3 system + 3 user) not drafted -- implementation detail, not architectural blocker

## Recommendations for Planning
1. Standardize ALL instruction class names to {StepPrefix}Instructions per framework enforcement -- Step 3 research names are wrong, use Step 1/2 names
2. process_instructions must return PipelineContext subclass instance (not dict) when context= is declared on step_definition
3. TopicExtraction must use `def default(self, results)` not `def extract()` -- preserves framework validation
4. Create demo_topics table in seed_prompts(engine) via `SQLModel.metadata.create_all(engine, tables=[Topic.__table__])`
5. Use explicit prompt keys in step_definition (simpler than auto-discovery, no DB lookup at step creation)
6. Give instruction custom fields safe defaults for create_failure support (e.g. `sentiment: str = ""`)
7. SentimentAnalysisContext: `sentiment: str` only -- confidence is accessible via LLMResultMixin.confidence_score on the Instructions output, not passed through context
8. TopicItem (Pydantic BaseModel, not SQLModel): `name: str` + `relevance: float` -- used as nested list in TopicExtractionInstructions
9. Topic (SQLModel, table="demo_topics"): `name: str` + `relevance: float` + `run_id: str` -- TopicExtraction.default() bridges TopicItem -> Topic by attaching run_id
10. DefaultStrategy with NAME="default" for single-strategy pipeline
