<!-- YOUR CONTRACT - DO NOT IGNORE - FOLLOW RULES EXACTLY AS SHOWN -->

## Context
- Task folder: docs\tasks\in-progress\master-8-pipeline-lifecycle-events
- Graphiti group_id: llm-pipeline
- Phase: research
- Output Files: research\step-1-pipeline-execute-architecture.md (if already exists, APPEND to file)
- Work: Emit PipelineStarted, PipelineCompleted, PipelineError events in execute() method of pipeline.py
- Project: llm-pipeline
- Plugins: backend-development, python-development
- Task Master tag: master
- Task Master ID: 8
- Upstream task IDs: 6(done) 7(done)
- Downstream task IDs: 9(pending)

## BEFORE Reading Codebase
1. Query Graphiti memory MCP (group_id above) for existing codebase context
2. Check Context7 MCP for latest library/framework docs based on tech stack
3. [custom.context7_docs]
4. Scope boundaries: Fetch upstream tasks (get_task for each ID: 6(done) 7(done)) for previous work context, check upstream task folders for deviations, fetch downstream tasks (get_task for each ID: 9(pending)) to see what's OUT OF SCOPE

## Instructions
1. Read .claude/CLAUDE.md for project context
2. Research codebase using Read, Grep, Glob, Serena tools
3. ALWAYS use sequential thinking MCP before returning to identify ANY questions or ambiguities that need CEO input
4. If questions exist: return Status: needs-input with numbered questions
5. If no questions: create step-1-pipeline-execute-architecture.md with all findings and return Status: complete

## Escalation Rules
- NEVER make architectural assumptions - if unclear, return Status: needs-input
- For any ambiguity, ASK THE CEO FIRST via needs-input

## AFTER Completing Work
- Update Graphiti memory MCP with new findings/changes
- Do NOT commit step-1-pipeline-execute-architecture.md (auto-committed on phase transition)

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