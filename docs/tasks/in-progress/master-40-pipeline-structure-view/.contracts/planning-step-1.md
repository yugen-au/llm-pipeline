<!-- YOUR CONTRACT - DO NOT IGNORE - FOLLOW RULES EXACTLY AS SHOWN -->

## Context
- Task folder: docs\tasks\in-progress\master-40-pipeline-structure-view
- Graphiti group_id: llm-pipeline
- Phase: planning
- Output Files: PLAN.md (if already exists, APPEND to file)
- Work: Create Pipeline Structure view showing introspected pipeline metadata: strategies, steps, schemas, prompts. React frontend component with backend API for pipeline introspection.
- Research: VALIDATED_RESEARCH.md
- Available agents: [available agents]
- Available skills: [available skills]
- Task Master tag: master
- Task Master ID: 40
- Upstream task IDs: 24(done) 31(done)
- Downstream task IDs: 51(pending)

## BEFORE Reading Codebase
1. Query Graphiti memory MCP (group_id above) for existing codebase context
2. Check Context7 MCP for latest library/framework docs based on tech stack
3. [custom.context7_docs]
4. Scope boundaries: Fetch upstream tasks (get_task for each ID: 24(done) 31(done)) for previous work context, check upstream task folders for deviations, fetch downstream tasks (get_task for each ID: 51(pending)) to see what's OUT OF SCOPE

## Instructions
1. RESEARCH VALIDATION (REQUIRED FIRST): Read VALIDATED_RESEARCH.md, verify all questions answered and assumptions validated. If gaps found, return Status: needs-input
2. Create PLAN.md with: Selected plugins, Implementation steps (each with Agent, Skills, Group), Success criteria, Risk mitigations, Phase recommendation
3. Context7 Docs: For each step, query Context7 MCP (resolve-library-id) for step's tech stack. Include resolved IDs in Context7 Docs field (/org/project format). Use '-' if generic context sufficient.
4. Step rules: Implementation is for CODE CHANGES ONLY, match step count to complexity, all steps need group letter, same group = concurrent, no same-group if files overlap
5. Phase recommendation: Risk Level (low/medium/high), Reasoning, Suggested Exclusions. Low=exclude both, Medium=exclude review, High=exclude none

## Output Document Format
~~~markdown
# PLANNING

## Summary
brief description of work and approach

## Plugin & Agents
**Plugin:** [selected plugin name]
**Subagents:** [subagent names to use from [available agents]]
**Skills:** [skill names or 'none' from [available skills]]

## Phases
1. [phase name and brief purpose]
<!-- Continue numbering... -->

## Architecture Decisions
### Decision Name
**Choice:** [what was decided]
**Rationale:** [why this choice]
**Alternatives:** [other options considered or 'none']

<!-- Repeat 'Decision Name' section as needed (min: 1) -->

## Implementation Steps
### Step N: Step Name
**Agent:** [plugin:subagent format from [available agents]]
**Skills:** [skill names or 'none' from [available skills]]
**Context7 Docs:** [comma-separated library IDs or '-']
**Group:** [A/B/C letter for concurrency]
1. [specific substep action]
<!-- Continue numbering... -->

<!-- Repeat 'Step N: Step Name' section as needed (min: 1) -->

## Risks & Mitigations
| Risk | Impact | Mitigation |
| --- | --- | --- |
| [describe risk] | [High/Medium/Low] | [how to mitigate] |

## Success Criteria
[ ] [measurable success criterion]
<!-- Add checkbox for each item -->

## Phase Recommendation
**Risk Level:** [low/medium/high]
**Reasoning:** [brief justification for risk level]
**Suggested Exclusions:** [testing, review, or 'none']
~~~

## Escalation Rules
- NEVER make architectural assumptions - if unclear, return Status: needs-input
- For any ambiguity, ASK THE CEO FIRST via needs-input

## AFTER Completing Work
- Do NOT commit PLAN.md (auto-committed on phase transition)

## Response Format After Completing Work (CRITICAL)
~~~
Status: [in-progress/complete/fixing/needs-input]
Issues: [one-line description or 'none']
Created: PLAN.md
Steps: [count]
~~~
Do NOT return: lengthy code blocks, explanations, reasoning, file contents.
Detailed work goes in FILES, not response.

<!-- END CONTRACT -->