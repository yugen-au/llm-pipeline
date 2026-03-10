<!-- YOUR CONTRACT - DO NOT IGNORE - FOLLOW RULES EXACTLY AS SHOWN -->

## Context
- Task folder: docs\tasks\in-progress\master-55-frontend-component-tests
- Graphiti group_id: llm-pipeline
- Phase: implementation
- Output Files: implementation\step-7-promptlist-tests.md (if already exists, APPEND to file)
- Plan: PLAN.md
- Step: 7 - implement ONLY this step, not others
- [custom.skills_to_invoke]
- [custom.prd_mode_guidance]

## BEFORE Reading Codebase
1. Query Graphiti memory MCP (group_id above) for existing codebase context
2. Check Context7 MCP for latest library/framework docs based on tech stack
3. Context7 library IDs to query: /vitest-dev/vitest,/testing-library/react-testing-library
4. If skills listed: invoke each with Skill(skill='[plugin:skill]') BEFORE implementation

## Instructions
1. Read plan for full context
2. Implement ONLY the specified step (not others)
3. Write all code to appropriate project locations
4. Document decisions in implementation\step-7-promptlist-tests.md
5. Failure handling: after 3 attempts at same issue, document in ISSUES.md and return Status: needs-input

## Output Document Format
~~~markdown
# IMPLEMENTATION - STEP 7: PROMPTLIST TESTS
**Status:** [completed/failed/blocked]

## Summary
brief description of what was implemented

## Files
**Created:** [file paths or 'none']
**Modified:** [file paths or 'none']
**Deleted:** [file paths or 'none']

## Changes
### File: `path/to/file`
description of changes made to this file
```
# Before
[code showing the change]

# After
[code showing the change]
```

<!-- Repeat for each file changed -->

## Decisions
### Decision Name
**Choice:** [what was decided]
**Rationale:** [why this choice]

<!-- Repeat for each decision, or write 'None' if no decisions required -->

## Verification
[ ] [verification check performed]
<!-- Add checkbox for each item -->
~~~

## Escalation Rules
- NEVER make architectural assumptions - if unclear, return Status: needs-input
- For any ambiguity, ASK THE CEO FIRST via needs-input

## AFTER Completing Work
- Stage and commit changes (format: type(scope): description)
- Document decisions in step notes file

## Response Format After Completing Work (CRITICAL)
~~~
Status: [in-progress/complete/fixing/needs-input]
Issues: [one-line description or 'none']
Created: implementation\step-[step]-[slug].md
Modified: [file paths or 'none']
Deleted: [file paths or 'none']
Commit: [commit hash or 'none']
~~~
Do NOT return: lengthy code blocks, explanations, reasoning, file contents.
Detailed work goes in FILES, not response.

<!-- END CONTRACT -->