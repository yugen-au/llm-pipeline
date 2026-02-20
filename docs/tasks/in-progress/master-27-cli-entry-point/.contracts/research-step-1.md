<!-- YOUR CONTRACT - DO NOT IGNORE - FOLLOW RULES EXACTLY AS SHOWN -->

## Context
- Task folder: docs\tasks\in-progress\master-27-cli-entry-point
- Graphiti group_id: llm-pipeline
- Phase: research
- Output Files: research\step-1-codebase-structure-research.md (if already exists, APPEND to file)
- Work: Implement llm-pipeline CLI entry point with ui command, --dev/--port/--db flags, uvicorn prod mode, Vite HMR dev mode
- Project: llm-pipeline
- Plugins: python-development, backend-development
- Task Master tag: master
- Task Master ID: 27
- Upstream task IDs: 19(done)
- Downstream task IDs: 28(pending)

## BEFORE Reading Codebase
1. Query Graphiti memory MCP (group_id above) for existing codebase context
2. Check Context7 MCP for latest library/framework docs based on tech stack
3. [custom.context7_docs]
4. Scope boundaries: Fetch upstream tasks (get_task for each ID: 19(done)) for previous work context, check upstream task folders for deviations, fetch downstream tasks (get_task for each ID: 28(pending)) to see what's OUT OF SCOPE

## Instructions
1. Read .claude/CLAUDE.md for project context
2. Research codebase using Read, Grep, Glob, Serena tools
3. ALWAYS use sequential thinking MCP before returning to identify ANY questions or ambiguities that need CEO input
4. If questions exist: return Status: needs-input with numbered questions
5. If no questions: create step-1-codebase-structure-research.md with all findings and return Status: complete

## Escalation Rules
- NEVER make architectural assumptions - if unclear, return Status: needs-input
- For any ambiguity, ASK THE CEO FIRST via needs-input

## AFTER Completing Work
- Do NOT commit step-1-codebase-structure-research.md (auto-committed on phase transition)

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