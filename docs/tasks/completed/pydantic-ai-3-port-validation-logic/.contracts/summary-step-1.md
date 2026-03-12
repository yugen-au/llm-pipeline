<!-- YOUR CONTRACT - DO NOT IGNORE - FOLLOW RULES EXACTLY AS SHOWN -->

## Context
- Task folder: docs\tasks\in-progress\pydantic-ai-3-port-validation-logic
- Graphiti group_id: llm-pipeline
- Phase: summary
- Output Files: SUMMARY.md (if already exists, APPEND to file)
- Plan: PLAN.md
- Implementation: implementation/
- Testing: TESTING.md
- Review: REVIEW.md

## BEFORE Reading Codebase
1. Query Graphiti memory MCP (group_id above) for existing codebase context
2. Check Context7 MCP for latest library/framework docs based on tech stack
3. [custom.context7_docs]

## Instructions
1. Create SUMMARY.md with the following sections
2. Work completed - brief description of what was done
3. Files created/modified - list with full paths
4. Commits made - list with hashes and messages
5. Deviations from plan - any changes from original PLAN.md
6. Issues encountered and resolutions - problems hit and how solved
7. Recommendations for follow-up - future improvements or related work

## Output Document Format
~~~markdown
# Task Summary

## Work Completed
brief description of what was accomplished

## Files Changed
### Created
| File | Purpose |
| --- | --- |
| [file path] | [description] |

### Modified
| File | Changes |
| --- | --- |
| [file path] | [description of changes] |

## Commits Made
| Hash | Message |
| --- | --- |
| [commit hash] | [commit message] |

## Deviations from Plan
- [deviation description or 'None']
<!-- Continue for each item -->

## Issues Encountered
### Issue Description
**Resolution:** [how it was resolved]

<!-- Repeat for each issue, or write 'None' -->

## Success Criteria
[ ] [criterion with verification evidence]
<!-- Add checkbox for each item -->

## Recommendations for Follow-up
1. [recommendation for future work]
<!-- Continue numbering... -->
~~~

## Escalation Rules
- NEVER make architectural assumptions - if unclear, return Status: needs-input
- For any ambiguity, ASK THE CEO FIRST via needs-input

## AFTER Completing Work
- Update Graphiti memory MCP with a summary of the work completed
- Do NOT commit SUMMARY.md (auto-committed on phase transition)

## Response Format After Completing Work (CRITICAL)
~~~
Status: [in-progress/complete/fixing/needs-input]
Issues: [one-line description or 'none']
Created: SUMMARY.md
~~~
Do NOT return: lengthy code blocks, explanations, reasoning, file contents.
Detailed work goes in FILES, not response.

<!-- END CONTRACT -->