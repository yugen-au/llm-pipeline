# IMPLEMENTATION - STEP 2: STEPS & INSTRUCTIONS
**Status:** completed

## Summary
Implemented all Instructions, Context, Extraction, and Step classes for the TextAnalyzer pipeline's 3 steps (sentiment analysis, topic extraction, summary) in llm_pipeline/demo/pipeline.py.

## Files
**Created:** none
**Modified:** llm_pipeline/demo/pipeline.py
**Deleted:** none

## Changes
### File: `llm_pipeline/demo/pipeline.py`
Added 10 classes after the existing skeleton (TextAnalyzerInputData, TopicItem, Topic, TextAnalyzerRegistry). New imports: ClassVar, List, PipelineContext, PipelineExtraction, LLMResultMixin, LLMStep, step_definition.

```
# Before
# Only contained: TextAnalyzerInputData, TopicItem, Topic, TextAnalyzerRegistry

# After (added)
# 3 Instructions: SentimentAnalysisInstructions, TopicExtractionInstructions, SummaryInstructions
#   - All extend LLMResultMixin with safe defaults and ClassVar example dicts
# 3 Contexts: SentimentAnalysisContext, TopicExtractionContext, SummaryContext
#   - All extend PipelineContext with typed fields
# 1 Extraction: TopicExtraction(PipelineExtraction, model=Topic)
#   - Uses default() method (not extract()) to preserve framework validation
# 3 Steps: SentimentAnalysisStep, TopicExtractionStep, SummaryStep
#   - All decorated with @step_definition, implement prepare_calls() and process_instructions()
#   - process_instructions returns PipelineContext subclass (not dict)
#   - Steps chain context: sentiment -> topic extraction -> summary
```

## Decisions
### TopicExtractionInstructions example content
**Choice:** Used realistic topic items with relevance scores in ClassVar example
**Rationale:** LLMResultMixin.__init_subclass__ validates example by instantiating cls(**example); nested TopicItem dicts must be valid

### Context field for confidence
**Choice:** SentimentAnalysisContext carries only `sentiment: str`, no confidence_score
**Rationale:** Per VALIDATED_RESEARCH CEO decision: reuse LLMResultMixin.confidence_score from instruction output directly; no duplication into context

## Verification
[x] All 10 new classes import successfully
[x] @step_definition naming enforcement passes (no ValueError at import)
[x] LLMResultMixin.example validation passes for all 3 Instructions
[x] pytest: 953 passed, 6 skipped, 1 warning (no regressions)
[x] TopicExtraction uses default() not extract()
[x] All process_instructions return PipelineContext subclass
[x] All instruction fields have safe defaults for create_failure support

## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
[x] VALIDATED_RESEARCH.md recommendation #7 incorrectly listed `confidence_score: float` as a SentimentAnalysisContext field -- should be `sentiment: str` only

### Changes Made
#### File: `docs/tasks/in-progress/pipeline-discovery-3-textanalyzer-demo/VALIDATED_RESEARCH.md`
Updated 4 locations where SentimentAnalysisContext was described as having confidence_score. Confidence is accessed via LLMResultMixin.confidence_score on the Instructions output, not passed through context.

```
# Before (recommendation #7)
7. SentimentAnalysisContext: `sentiment: str` + `confidence_score: float` (reuse from LLMResultMixin output)

# After
7. SentimentAnalysisContext: `sentiment: str` only -- confidence is accessible via LLMResultMixin.confidence_score on the Instructions output, not passed through context
```

```
# Before (process_instructions example)
Correct pattern: `return SentimentAnalysisContext(sentiment=..., confidence_score=...)`.

# After
Correct pattern: `return SentimentAnalysisContext(sentiment=...)`.
```

```
# Before (Q&A table)
No custom confidence field needed; SentimentAnalysisContext has sentiment + confidence_score

# After
No custom confidence field needed; SentimentAnalysisContext has sentiment only, confidence accessed on Instructions output
```

```
# Before (assumptions)
Sentiment context field: reuse LLMResultMixin.confidence_score, no custom field per CEO decision

# After
Sentiment context field: SentimentAnalysisContext has sentiment only; confidence accessed via LLMResultMixin.confidence_score on Instructions output per CEO decision
```

### Verification
[x] All 4 references to confidence_score in SentimentAnalysisContext updated
[x] Doc now consistent with implementation (SentimentAnalysisContext has only `sentiment: str`)
[x] No code changes needed -- documentation-only fix
