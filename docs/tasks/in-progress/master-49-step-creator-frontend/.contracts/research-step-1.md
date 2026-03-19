<!-- YOUR CONTRACT - DO NOT IGNORE - FOLLOW RULES EXACTLY AS SHOWN -->

## Context
- Task folder: docs\tasks\in-progress\master-49-step-creator-frontend
- Graphiti group_id: llm-pipeline
- Phase: research
- Output Files: research\step-1-frontend-architecture-research.md (if already exists, APPEND to file)
- Work: Step Creator frontend view with input form, Monaco editor (lazy-loaded) for generated code, and results panel. Three-column layout with generate/test/accept workflow.
- Project: llm-pipeline
- Plugins: frontend-mobile-development, ui-design
- Task Master tag: master
- Task Master ID: 49
- Upstream task IDs: 48(done) 35(done)
- Downstream task IDs: none

## BEFORE Reading Codebase
1. Query Graphiti memory MCP (group_id above) for existing codebase context
2. Check Context7 MCP for latest library/framework docs based on tech stack
3. [custom.context7_docs]
4. Scope boundaries: Fetch upstream tasks (get_task for each ID: 48(done) 35(done)) for previous work context, check upstream task folders for deviations, fetch downstream tasks (get_task for each ID: none) to see what's OUT OF SCOPE

## Instructions
1. Read .claude/CLAUDE.md for project context
2. Research codebase using Read, Grep, Glob, Serena tools
3. ALWAYS use sequential thinking MCP before returning to identify ANY questions or ambiguities that need CEO input
4. If questions exist: return Status: needs-input with numbered questions
5. If no questions: create step-1-frontend-architecture-research.md with all findings and return Status: complete

## Escalation Rules
- NEVER make architectural assumptions - if unclear, return Status: needs-input
- For any ambiguity, ASK THE CEO FIRST via needs-input

## AFTER Completing Work
- Do NOT commit step-1-frontend-architecture-research.md (auto-committed on phase transition)

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