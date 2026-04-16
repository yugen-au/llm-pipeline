<!-- YOUR CONTRACT - DO NOT IGNORE - FOLLOW RULES EXACTLY AS SHOWN -->

## Context
- Task folder: docs\tasks\in-progress\adhoc-20260416-pydantic-evals-v1
- Graphiti group_id: llm-pipeline
- Phase: research
- Output Files: research\step-1-pydantic-evals-api-research.md (if already exists, APPEND to file)
- Work: Integrate pydantic-evals into llm-pipeline: YAML datasets (llm-pipeline-evals/) with bidirectional DB sync, step/pipeline-level evaluation, auto field-match evaluators from instructions schema, custom evaluators on step_definition, live eval runner, new DB tables (EvaluationDataset/Case/Run/CaseResult), backend routes, frontend Evals tab (dataset list, case editor, run history, run detail), CLI command, worked sentiment_analysis example.
- Project: llm-pipeline
- Plugins: llm-application-dev, backend-development, frontend-mobile-development

## BEFORE Reading Codebase
1. Query Graphiti memory MCP (group_id above) for existing codebase context
2. Check Context7 MCP for latest library/framework docs based on tech stack
3. [custom.context7_docs]

## Instructions
1. Read .claude/CLAUDE.md for project context
2. Research codebase using Read, Grep, Glob, Serena tools to find existing patterns, reusable components, security posture, architectural constraints
3. ALWAYS use sequential thinking MCP before returning to identify ANY questions or ambiguities that need CEO input
4. If questions exist: return Status: needs-input with numbered questions
5. If no questions: create step-1-pydantic-evals-api-research.md with all findings and return Status: complete

## Escalation Rules
- NEVER make architectural assumptions - if unclear, return Status: needs-input
- For any ambiguity, ASK THE CEO FIRST via needs-input

## AFTER Completing Work
- Do NOT commit step-1-pydantic-evals-api-research.md (auto-committed on phase transition)

## Response Format After Completing Work (CRITICAL)
~~~
Status: [in-progress/complete/fixing/needs-input]
Issues: [one-line description or 'none']
Questions: [numbered list or 'none']
Research: [one-line summary]
~~~
Do NOT return: lengthy code blocks, explanations, reasoning, file contents.
Detailed work goes in FILES, not response.

<!-- END CONTRACT -->