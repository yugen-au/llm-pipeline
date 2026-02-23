<!-- YOUR CONTRACT - DO NOT IGNORE - FOLLOW RULES EXACTLY AS SHOWN -->

## Context
- Task folder: docs\tasks\in-progress\master-22-prompts-api-endpoint
- Graphiti group_id: llm-pipeline
- Phase: fixing-review
- Output Files: implementation\step-1-prompts-endpoints.md (if already exists, APPEND to file)
- Issues source: REVIEW.md
- Step to fix: 1

## BEFORE Reading Codebase
1. Query Graphiti memory MCP (group_id above) for existing codebase context
2. Check Context7 MCP for latest library/framework docs based on tech stack
3. Context7 library IDs to query: /tiangolo/fastapi,/pydantic/pydantic

## Instructions
1. Read REVIEW.md for issues assigned to Step 1
2. Fix each issue for this step only
3. APPEND fix documentation to implementation\step-1-prompts-endpoints.md (do not replace existing content)

## Output Document Format
~~~markdown
## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** [fixed/partial/blocked]

### Issues Addressed
[ ] [issue description from REVIEW.md]
<!-- Add checkbox for each item -->

### Changes Made
#### File: `path/to/file`
description of fix applied
```
# Before
[code showing the fix]

# After
[code showing the fix]
```

<!-- Repeat for each file changed -->

### Verification
[ ] [verification performed]
<!-- Add checkbox for each item -->
~~~

## Escalation Rules
- NEVER make architectural assumptions - if unclear, return Status: needs-input
- For any ambiguity, ASK THE CEO FIRST via needs-input

## AFTER Completing Work
- Stage and commit fixes (format: fix(scope): description)

## Response Format After Completing Work (CRITICAL)
~~~
Status: [in-progress/complete/fixing/needs-input]
Issues: [one-line description or 'none']
Created: implementation\step-1-prompts-endpoints.md
Modified: [file paths or 'none']
Commit: [commit hash or 'none']
~~~
Do NOT return: lengthy code blocks, explanations, reasoning, file contents.
Detailed work goes in FILES, not response.

<!-- END CONTRACT -->