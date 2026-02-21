<!-- YOUR CONTRACT - DO NOT IGNORE - FOLLOW RULES EXACTLY AS SHOWN -->

## Context
- Task folder: docs\tasks\in-progress\master-29-init-frontend-structure
- Graphiti group_id: llm-pipeline
- Phase: research
- Output Files: research\step-2-python-integration-research.md (if already exists, APPEND to file)
- Work: Initialize React 19 + TypeScript + Vite + TanStack Router frontend in llm_pipeline/ui/frontend/ with TailwindCSS, shadcn/ui, proxy config, and Python package integration
- Project: llm-pipeline
- Plugins: frontend-mobile-development, python-development, javascript-typescript
- Task Master tag: master
- Task Master ID: 29
- Upstream task IDs: 28(done)
- Downstream task IDs: 30(pending) 42(pending)

## BEFORE Reading Codebase
1. Query Graphiti memory MCP (group_id above) for existing codebase context
2. Check Context7 MCP for latest library/framework docs based on tech stack
3. [custom.context7_docs]
4. Scope boundaries: Fetch upstream tasks (get_task for each ID: 28(done)) for previous work context, check upstream task folders for deviations, fetch downstream tasks (get_task for each ID: 30(pending) 42(pending)) to see what's OUT OF SCOPE

## Instructions
1. Read .claude/CLAUDE.md for project context
2. Research codebase using Read, Grep, Glob, Serena tools
3. ALWAYS use sequential thinking MCP before returning to identify ANY questions or ambiguities that need CEO input
4. If questions exist: return Status: needs-input with numbered questions
5. If no questions: create step-2-python-integration-research.md with all findings and return Status: complete

## Escalation Rules
- NEVER make architectural assumptions - if unclear, return Status: needs-input
- For any ambiguity, ASK THE CEO FIRST via needs-input

## AFTER Completing Work
- Do NOT commit step-2-python-integration-research.md (auto-committed on phase transition)

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