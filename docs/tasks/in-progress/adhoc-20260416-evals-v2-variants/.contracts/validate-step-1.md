<!-- YOUR CONTRACT - DO NOT IGNORE - FOLLOW RULES EXACTLY AS SHOWN -->

## Context
- Task folder: docs\tasks\in-progress\adhoc-20260416-evals-v2-variants
- Graphiti group_id: llm-pipeline
- Phase: validate
- Output Files: VALIDATED_RESEARCH.md (if already exists, APPEND to file)
- Input: research\step-1-existing-evals-sandbox-arch.md, research\step-2-frontend-evals-patterns.md, research\step-3-pydantic-createmodel-delta.md
- Minimum Q&A Loops: 1 (current: 0)

## BEFORE Reading Codebase
1. Query Graphiti memory MCP (group_id above) for existing codebase context
2. Check Context7 MCP for latest library/framework docs based on tech stack
3. [custom.context7_docs]
4. You are an assumption checker. Consolidate domain research and surface hidden assumptions

## Instructions
1. Read ALL input files - note patterns, gaps, and implicit assumptions
2. Use sequential thinking MCP to identify: unvalidated assumptions, ambiguities requiring CEO clarification
3. When you have questions for CEO, return 'Status: needs-input'
4. When satisfied: Create VALIDATED_RESEARCH.md based on the required output format
5. CRITICAL: Block yourself from Status: complete if Revisions < 1 (hooks enforce this)

## Output Document Format
~~~markdown
# Research Summary

## Executive Summary
brief overview of consolidated findings and assumption validation

## Domain Findings
### Finding Category
**Source:** [research file(s)]
key findings from this domain area

<!-- Repeat for each major finding category -->

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| [assumption question asked] | [CEO response] | [how this changed understanding] |

## Assumptions Validated
[ ] [validated assumption with supporting evidence]
<!-- Add checkbox for each item -->

## Open Items
- [item requiring further clarification or deferred]
<!-- Continue for each item -->

## Recommendations for Planning
1. [recommendation based on findings]
<!-- Continue numbering... -->
~~~

## Escalation Rules
- NEVER make architectural assumptions - if unclear, return Status: needs-input
- For any ambiguity, ASK THE CEO FIRST via needs-input

## AFTER Completing Work
- Do NOT commit VALIDATED_RESEARCH.md when done

## Response Format After Completing Work (CRITICAL)
~~~
Status: [in-progress/complete/fixing/needs-input]
Issues: [one-line description or 'none']
Created: VALIDATED_RESEARCH.md
Questions: [numbered list or 'none']
~~~
Do NOT return: lengthy code blocks, explanations, reasoning, file contents.
Detailed work goes in FILES, not response.

<!-- END CONTRACT -->