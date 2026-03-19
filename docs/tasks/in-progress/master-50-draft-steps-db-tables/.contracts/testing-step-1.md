<!-- YOUR CONTRACT - DO NOT IGNORE - FOLLOW RULES EXACTLY AS SHOWN -->

## Context
- Task folder: docs\tasks\in-progress\master-50-draft-steps-db-tables
- Graphiti group_id: llm-pipeline
- Phase: testing
- Output Files: TESTING.md (if already exists, APPEND to file)
- Plan: PLAN.md
- Implementation: implementation\step-1-add-draft-models.md

## BEFORE Reading Codebase
1. Query Graphiti memory MCP (group_id above) for existing codebase context
2. Check Context7 MCP for latest library/framework docs based on tech stack
3. [custom.context7_docs]

## Instructions
1. Verify: build/compile succeeds, no runtime errors/warnings, PLAN.md success criteria met
2. Manual verification of functionality and edge cases
3. Create TESTING.md with: build status, errors/warnings, success criteria checklist, issues with step numbers
4. CRITICAL: Every issue MUST reference implementation step number (e.g., 'Step 2: Button click handler missing')

## Output Document Format
~~~markdown
# Testing Results

## Summary
**Status:** [passed/failed]
brief overall summary of testing results

## Automated Testing
### Test Scripts Created
| Script | Purpose | Location |
| --- | --- | --- |
| [script name] | [what it tests] | [file path] |

### Test Execution
**Pass Rate:** [X/Y tests]
```
[test output]
```

### Failed Tests
#### Test Name
**Step:** [implementation step number]
**Error:** [error message]

<!-- Repeat for each failed test, or write 'None' if all tests pass -->

## Build Verification
[ ] [build check performed]
<!-- Add checkbox for each item -->

## Success Criteria (from PLAN.md)
[ ] [criterion with verification evidence]
<!-- Add checkbox for each item -->

## Human Validation Required
### Validation Name
**Step:** [implementation step affected]
**Instructions:** [specific steps for PM to verify]
**Expected Result:** [what PM should see]

<!-- Repeat for each human validation needed -->

## Issues Found
### Issue Description
**Severity:** [critical/high/medium/low]
**Step:** [implementation step number]
**Details:** [description of the issue]

<!-- Repeat for each issue, or write 'None' if no issues -->

## Recommendations
1. [recommendation for next steps]
<!-- Continue numbering... -->
~~~

## Escalation Rules
- NEVER make architectural assumptions - if unclear, return Status: needs-input
- For any ambiguity, ASK THE CEO FIRST via needs-input

## AFTER Completing Work
- Do NOT commit TESTING.md (auto-committed on phase transition)

## Response Format After Completing Work (CRITICAL)
~~~
Status: [in-progress/complete/fixing/needs-input]
Issues: [one-line description or 'none']
Created: TESTING.md
Pass: [passed/failed]
~~~
Do NOT return: lengthy code blocks, explanations, reasoning, file contents.
Detailed work goes in FILES, not response.

<!-- END CONTRACT -->