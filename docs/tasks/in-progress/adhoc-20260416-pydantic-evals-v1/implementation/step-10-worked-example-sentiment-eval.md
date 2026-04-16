# IMPLEMENTATION - STEP 10: WORKED EXAMPLE SENTIMENT EVAL
**Status:** completed

## Summary
Created worked example eval dataset for sentiment analysis step with 5 labeled cases and a custom SentimentLabelEvaluator wired via `evaluators=` on `@step_definition`.

## Files
**Created:** llm-pipeline-evals/sentiment_analysis.yaml
**Modified:** llm_pipelines/steps/sentiment_analysis.py
**Deleted:** none

## Changes
### File: `llm-pipeline-evals/sentiment_analysis.yaml`
New YAML eval dataset with 5 cases: clear_positive, clear_negative, sarcasm_negative (hard), neutral_factual, mixed_signals (medium). Schema matches `_parse_eval_yaml` expectations (name, target_type, target_name, description, cases with inputs/expected_output/metadata).

### File: `llm_pipelines/steps/sentiment_analysis.py`
Added `SentimentLabelEvaluator` subclassing `FieldMatchEvaluator("sentiment")` and wired it into `@step_definition(evaluators=[SentimentLabelEvaluator])`.

```
# Before
@step_definition(
    instructions=SentimentAnalysisInstructions,
    ...
    review=SentimentAnalysisReview,
)

# After
@step_definition(
    instructions=SentimentAnalysisInstructions,
    ...
    review=SentimentAnalysisReview,
    evaluators=[SentimentLabelEvaluator],
)
```

## Decisions
### Evaluator as FieldMatchEvaluator subclass
**Choice:** Subclass `FieldMatchEvaluator` with hardcoded field_name="sentiment" rather than standalone callable
**Rationale:** Reuses existing skip-when-absent logic, zero duplication, consistent with auto-evaluator pattern

## Verification
[x] YAML parses via `_parse_eval_yaml` -- 5 cases, all fields present
[x] `SentimentLabelEvaluator` imports cleanly
[x] `SentimentAnalysisStep._step_evaluators` contains the evaluator class
[x] Startup sync will pick up `llm-pipeline-evals/sentiment_analysis.yaml` via glob("*.yaml")
