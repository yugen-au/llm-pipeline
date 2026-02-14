<!-- YOUR CONTRACT - DO NOT IGNORE - FOLLOW RULES EXACTLY AS SHOWN -->

## Context
- Task folder: docs\tasks\in-progress\master-11-llm-call-events
- Graphiti group_id: llm-pipeline
- Phase: review
- Output Files: REVIEW.md (if already exists, APPEND to file)
- Plan: PLAN.md
- Implementation: implementation/*.md

## BEFORE Reading Codebase
1. Query Graphiti memory MCP (group_id above) for existing codebase context
2. Check Context7 MCP for latest library/framework docs based on tech stack
3. [custom.context7_docs]

## Instructions
1. Review checklist: architecture patterns, code quality, error handling, no hardcoded values, project conventions, security
2. Create REVIEW.md with: overall assessment, issues with severity AND step number, recommendations, required changes
3. Issue format: 'SEVERITY - Step N: description' (e.g., 'CRITICAL - Step 3: SQL injection vulnerability')
4. CRITICAL: Every issue MUST have severity (CRITICAL/HIGH/MEDIUM/LOW) AND associated step number

## Output Document Format
~~~markdown
# Architecture Review

## Overall Assessment
**Status:** [complete/failed/partial]
brief overall assessment of the implementation

## Project Guidelines Compliance
**CLAUDE.md:** [path or 'not found']
| Guideline | Status | Notes |
| --- | --- | --- |
| [guideline from project CLAUDE.md] | [pass/fail] | [verification evidence] |

## Issues Found
### Critical
#### Issue Description
**Step:** [implementation step number]
**Details:** [description of the issue]

<!-- Repeat for each critical issue, or write 'None' -->

### High
#### Issue Description
**Step:** [implementation step number]
**Details:** [description of the issue]

<!-- Repeat for each high issue, or write 'None' -->

### Medium
#### Issue Description
**Step:** [implementation step number]
**Details:** [description of the issue]

<!-- Repeat for each medium issue, or write 'None' -->

### Low
#### Issue Description
**Step:** [implementation step number]
**Details:** [description of the issue]

<!-- Repeat for each low issue, or write 'None' -->

## Review Checklist
[ ] [Architecture patterns followed]
[ ] [Code quality and maintainability]
[ ] [Error handling present]
[ ] [No hardcoded values]
[ ] [Project conventions followed]
[ ] [Security considerations]
[ ] [Properly scoped (DRY, YAGNI, no over-engineering)]

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| [file path] | [pass/fail] | [observations] |

## New Issues Introduced
- [issue description or 'None detected']
<!-- Continue for each item -->

## Recommendation
**Decision:** [APPROVE/REJECT/CONDITIONAL]
rationale for the decision
~~~

## Escalation Rules
- NEVER make architectural assumptions - if unclear, return Status: needs-input
- For any ambiguity, ASK THE CEO FIRST via needs-input

## AFTER Completing Work
- Update Graphiti memory MCP with new findings/changes
- Do NOT commit REVIEW.md (auto-committed on phase transition)

## Response Format After Completing Work (CRITICAL)
~~~
Status: [in-progress/complete/fixing/needs-input]
Issues: [one-line description or 'none']
Created: REVIEW.md
Pass: [passed/failed]
Severity: [critical/high/medium/low/none]
~~~
Do NOT return: lengthy code blocks, explanations, reasoning, file contents.
Detailed work goes in FILES, not response.

<!-- END CONTRACT -->