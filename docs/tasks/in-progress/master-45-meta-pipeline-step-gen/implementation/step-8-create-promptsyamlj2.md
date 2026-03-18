# IMPLEMENTATION - STEP 8: CREATE PROMPTS.YAML.J2
**Status:** completed

## Summary
Created `llm_pipeline/creator/templates/prompts.yaml.j2` Jinja2 template that renders Python source code with prompt dict definitions matching the `demo/prompts.py` format.

## Files
**Created:** `llm_pipeline/creator/templates/prompts.yaml.j2`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/creator/templates/prompts.yaml.j2`
New Jinja2 template rendering Python source with two prompt dicts and an ALL_PROMPTS list.

Template uses `{% set %}` blocks to derive `step_upper` (UPPER_SNAKE) and `step_title` (Title Case) from `step_name`. Renders:
- `{STEP_NAME_UPPER}_SYSTEM` dict with `prompt_type: "system"`, empty `required_variables`
- `{STEP_NAME_UPPER}_USER` dict with `prompt_type: "user"`, populated `required_variables` from loop
- `ALL_PROMPTS: list[dict]` referencing both dicts

All 8 schema keys match demo/prompts.py exactly: `prompt_key`, `prompt_name`, `prompt_type`, `category`, `step_name`, `content`, `required_variables`, `description`.

```
# Template variables
step_name: str           # e.g. "sentiment_analysis"
step_class_name: str     # e.g. "SentimentAnalysisStep"
system_content: str      # system prompt text
user_content: str        # user prompt template text
required_variables: list # e.g. ["text", "sentiment"]
category: str            # e.g. "text_analyzer"
```

## Decisions
### prompt_key same for system and user
**Choice:** Both dicts share the same `prompt_key` value (the step_name), differentiated by `prompt_type`
**Rationale:** Matches demo/prompts.py where `SENTIMENT_ANALYSIS_SYSTEM["prompt_key"]` == `SENTIMENT_ANALYSIS_USER["prompt_key"]` == `"sentiment_analysis"`. The `seed_prompts()` function checks uniqueness by `(prompt_key, prompt_type)` pair.

### Title derivation from step_name
**Choice:** Derive `step_title` via `step_name.replace("_", " ").title()` in Jinja2 `{% set %}` block
**Rationale:** Matches demo pattern where `sentiment_analysis` -> `"Sentiment Analysis System"`. Simpler than parsing CamelCase from `step_class_name`.

## Verification
[x] Template renders valid Python (ast.parse passes)
[x] Output matches demo/prompts.py dict schema exactly
[x] Empty required_variables list renders correctly
[x] Multiple required_variables render correctly
[x] StrictUndefined env catches missing vars (template uses all 6 declared variables)
