<!-- YOUR CONTRACT - DO NOT IGNORE - FOLLOW RULES EXACTLY AS SHOWN -->

## Context
- Task folder: docs\tasks\in-progress\pipeline-discovery-2-cli-flags
- Graphiti group_id: llm-pipeline
- Phase: research
- Output Files: research\step-1-cli-module-loading-research.md (if already exists, APPEND to file)
- Work: Extend CLI with --pipelines and --model flags for manual pipeline module specification and default LLM model
- Project: llm-pipeline
- Plugins: python-development, backend-development
- Task Master tag: cli-flags
- Task Master ID: 2
- Upstream task IDs: 1(done)
- Downstream task IDs: none

## BEFORE Reading Codebase
1. Query Graphiti memory MCP (group_id above) for existing codebase context
2. Check Context7 MCP for latest library/framework docs based on tech stack
3. [custom.context7_docs]
4. Scope boundaries: Fetch upstream tasks (get_task for each ID: 1(done)) for previous work context, check upstream task folders for deviations, fetch downstream tasks (get_task for each ID: none) to see what's OUT OF SCOPE

## Instructions
1. Read .claude/CLAUDE.md for project context
2. Research codebase using Read, Grep, Glob, Serena tools to find existing patterns, reusable components, security posture, architectural constraints
3. ALWAYS use sequential thinking MCP before returning to identify ANY questions or ambiguities that need CEO input
4. If questions exist: return Status: needs-input with numbered questions
5. If no questions: create step-1-cli-module-loading-research.md with all findings and return Status: complete

## Escalation Rules
- NEVER make architectural assumptions - if unclear, return Status: needs-input
- For any ambiguity, ASK THE CEO FIRST via needs-input

## AFTER Completing Work
- Do NOT commit step-1-cli-module-loading-research.md (auto-committed on phase transition)

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