<!-- YOUR CONTRACT - DO NOT IGNORE - FOLLOW RULES EXACTLY AS SHOWN -->

## Context
- Task folder: docs\tasks\in-progress\adhoc-20260420-versioning-snapshots
- Graphiti group_id: llm-pipeline
- Phase: implementation
- Output Files: implementation\step-2-versioning-helper-module.md (if already exists, APPEND to file)
- Plan: PLAN.md
- Step: 2 - implement ONLY this step, not others
- Skills to invoke: python-development:python-testing-patterns

## BEFORE Reading Codebase
1. Query Graphiti memory MCP (group_id above) for existing codebase context
2. Check Context7 MCP for latest library/framework docs based on tech stack
3. Context7 library IDs to query: /websites/sqlmodel_tiangolo,/websites/sqlalchemy_en_20_orm
4. If skills listed: invoke each with Skill(skill='[plugin:skill]') BEFORE implementation

## Instructions
1. Read plan for full context
2. Implement ONLY the specified step (not others)
3. Write all code to appropriate project locations
4. Document decisions in implementation\step-2-versioning-helper-module.md
5. Failure handling: after 3 attempts at same issue, document in ISSUES.md and return Status: needs-input

## Output Document Format
~~~markdown
# IMPLEMENTATION - STEP 2: VERSIONING HELPER MODULE
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