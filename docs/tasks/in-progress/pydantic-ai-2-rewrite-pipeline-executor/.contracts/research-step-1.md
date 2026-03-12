<!-- YOUR CONTRACT - DO NOT IGNORE - FOLLOW RULES EXACTLY AS SHOWN -->

## Context
- Task folder: docs\tasks\in-progress\pydantic-ai-2-rewrite-pipeline-executor
- Graphiti group_id: llm-pipeline
- Phase: research
- Output Files: research\step-1-architecture-research.md (if already exists, APPEND to file)
- Work: Refactor PipelineConfig.execute() to replace execute_llm_step() with agent.run_sync(), update _execute_with_consensus(), delete obsolete LLM utils (execute_llm_step, call_gemini_with_structured_output, format_schema_for_llm, validate_structured_output, validate_array_response) and RateLimiter, map UnexpectedModelBehavior to create_failure()
- Project: llm-pipeline
- Plugins: backend-development, python-development
- Task Master tag: pydantic-ai
- Task Master ID: 2
- Upstream task IDs: 1(done)
- Downstream task IDs: 3(pending) 4(pending) 5(pending) 6(pending)

## BEFORE Reading Codebase
1. Query Graphiti memory MCP (group_id above) for existing codebase context
2. Check Context7 MCP for latest library/framework docs based on tech stack
3. [custom.context7_docs]
4. Scope boundaries: Fetch upstream tasks (get_task for each ID: 1(done)) for previous work context, check upstream task folders for deviations, fetch downstream tasks (get_task for each ID: 3(pending) 4(pending) 5(pending) 6(pending)) to see what's OUT OF SCOPE

## Instructions
1. Read .claude/CLAUDE.md for project context
2. Research codebase using Read, Grep, Glob, Serena tools
3. ALWAYS use sequential thinking MCP before returning to identify ANY questions or ambiguities that need CEO input
4. If questions exist: return Status: needs-input with numbered questions
5. If no questions: create step-1-architecture-research.md with all findings and return Status: complete

## Escalation Rules
- NEVER make architectural assumptions - if unclear, return Status: needs-input
- For any ambiguity, ASK THE CEO FIRST via needs-input

## AFTER Completing Work
- Do NOT commit step-1-architecture-research.md (auto-committed on phase transition)

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