# PLANNING

## Summary

Build TextAnalyzerPipeline as a clean reference demo of the llm-pipeline framework. Creates `llm_pipeline/demo/` package with 3 sequential LLMSteps (sentiment analysis -> topic extraction -> summary), a DefaultStrategy, prompt seeding with demo_topics table creation, and entry point registration in pyproject.toml. All decisions are resolved via VALIDATED_RESEARCH.md with no open architectural questions.

## Plugin & Agents

**Plugin:** python-development, backend-development, llm-application-dev
**Subagents:** [available agents]
**Skills:** [available skills]

## Phases

1. **Foundation**: Create demo package structure, Topic SQLModel, input data model, registry, agent registry, strategy
2. **Steps & Instructions**: Implement 3 LLMStep classes with Instructions, Context, and Extraction models
3. **Wiring**: Assemble TextAnalyzerPipeline, implement seed_prompts with table creation, register entry point

## Architecture Decisions

### Strategy Naming
**Choice:** `DefaultStrategy` with `NAME = "default"`
**Rationale:** Follows test conventions (tests/test_pipeline.py uses DefaultStrategy); NAME auto-generated from snake_case of prefix so explicit set clarifies intent; prompt auto-discovery falls back to `{step_name}` key (no `.default` suffix lookup needed)
**Alternatives:** `TextAnalyzerStrategy` (more verbose, unnecessary for single-strategy pipeline)

### Context Field for Sentiment Confidence
**Choice:** Reuse `LLMResultMixin.confidence_score` - no custom confidence field
**Rationale:** CEO decision; `SentimentAnalysisInstructions.confidence_score` (from LLMResultMixin) is already structured output from the LLM. `SentimentAnalysisContext` carries only `sentiment: str`; confidence_score is already accessible from instructions directly
**Alternatives:** Custom `confidence_score: float` on SentimentAnalysisContext (redundant duplication)

### Topic SQLModel Fields
**Choice:** `Topic(SQLModel, table=True)` with fields: `id: Optional[int]` (PK), `name: str`, `relevance: float`, `run_id: str`; `__tablename__ = "demo_topics"`
**Rationale:** CEO decision; run_id enables per-run traceability; TopicItem (Pydantic, not SQLModel) bridges LLM output to Topic via TopicExtraction.default()
**Alternatives:** No relevance field (loses LLM-scored ranking); no run_id (loses traceability)

### Table Creation Location
**Choice:** `seed_prompts(engine)` creates demo_topics table via `SQLModel.metadata.create_all(engine, tables=[Topic.__table__])`
**Rationale:** CEO decision; single setup entry point; engine is already available; called at discovery time by `_discover_pipelines()`
**Alternatives:** Pipeline `__init__` (called per run - wasteful); separate migration

### Extraction Method
**Choice:** `def default(self, results)` on `TopicExtraction` - not overriding `extract()`
**Rationale:** VALIDATED_RESEARCH critical finding; base `extract()` auto-dispatches to `default()` and runs `_validate_instances()` (NaN/NULL checks); overriding `extract()` bypasses validation
**Alternatives:** Override `extract()` directly (WRONG - skips framework validation)

### Instruction Class Names
**Choice:** `SentimentAnalysisInstructions`, `TopicExtractionInstructions`, `SummaryInstructions`
**Rationale:** `step_definition` decorator enforces `{StepPrefix}Instructions` naming at class definition time; raises ValueError otherwise
**Alternatives:** `SentimentAnalysis`, `TopicExtractionResult`, `SummaryResult` (WRONG per framework enforcement)

### process_instructions Return Type
**Choice:** Return `PipelineContext` subclass instance when `context=` is declared on `step_definition`
**Rationale:** `_validate_and_merge_context()` enforces PipelineContext subclass when `step._context` is set; returning dict causes TypeError
**Alternatives:** Return dict (WRONG - causes runtime TypeError)

### Prompt Key Strategy
**Choice:** Explicit prompt keys in `step_definition` (`default_system_key="sentiment_analysis"`, `default_user_key="sentiment_analysis"`)
**Rationale:** Simpler than auto-discovery; avoids DB lookup at step creation; keys match prompt seeding constants exactly; no ambiguity with strategy-name suffix lookup
**Alternatives:** None (auto-discovery from DB by step_name) - requires exact DB state at step instantiation

### File Separation
**Choice:** `pipeline.py` contains all classes (steps, instructions, context, extraction, models, registries, strategy, pipeline); `prompts.py` contains prompt constants + `seed_prompts` classmethod helper; `__init__.py` exports `TextAnalyzerPipeline`
**Rationale:** Research file map (step-2 section 13) confirms this split; prompts.py keeps all DB-insertion logic isolated; pipeline.py is the single import for the framework
**Alternatives:** Single file (too large for reference demo); more files (unnecessary fragmentation)

## Implementation Steps

### Step 1: Create demo package skeleton and data models
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /pydantic/pydantic, /websites/sqlmodel_tiangolo
**Group:** A

1. Create `llm_pipeline/demo/__init__.py` exporting `TextAnalyzerPipeline`
2. Create `llm_pipeline/demo/pipeline.py` with:
   - `TextAnalyzerInputData(PipelineInputData)` with `text: str` field
   - `TopicItem(BaseModel)` with `name: str`, `relevance: float` (LLM output shape, not a table)
   - `Topic(SQLModel, table=True)` with `__tablename__ = "demo_topics"`, fields: `id: Optional[int] = Field(default=None, primary_key=True)`, `name: str`, `relevance: float`, `run_id: str`
   - `TextAnalyzerRegistry(PipelineDatabaseRegistry, models=[Topic])` class
3. Create `llm_pipeline/demo/prompts.py` as empty file with module docstring (content added in Step 3)

### Step 2: Implement Instructions, Context, and Step classes
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /pydantic/pydantic
**Group:** B

1. In `llm_pipeline/demo/pipeline.py`, add all 3 Instructions classes (must precede step definitions):
   - `SentimentAnalysisInstructions(LLMResultMixin)`: fields `sentiment: str = ""`, `explanation: str = ""`; `example` ClassVar dict
   - `TopicExtractionInstructions(LLMResultMixin)`: fields `topics: list[TopicItem] = []`, `primary_topic: str = ""`; `example` ClassVar dict
   - `SummaryInstructions(LLMResultMixin)`: fields `summary: str = ""`; `example` ClassVar dict
2. Add 3 Context classes:
   - `SentimentAnalysisContext(PipelineContext)`: `sentiment: str`
   - `TopicExtractionContext(PipelineContext)`: `primary_topic: str`, `topics: list[str]`
   - `SummaryContext(PipelineContext)`: `summary: str`
3. Add `TopicExtraction(PipelineExtraction, model=Topic)`:
   - `def default(self, results: list[TopicExtractionInstructions]) -> list[Topic]`: iterate `results[0].topics`, create `Topic(name=t.name, relevance=t.relevance, run_id=self.pipeline.run_id)` for each
4. Add `SentimentAnalysisStep(LLMStep)` with `@step_definition(instructions=SentimentAnalysisInstructions, default_system_key="sentiment_analysis", default_user_key="sentiment_analysis", context=SentimentAnalysisContext)`:
   - `prepare_calls()`: returns `[{"variables": {"text": self.pipeline.validated_input.text}}]`
   - `process_instructions(instructions)`: returns `SentimentAnalysisContext(sentiment=instructions[0].sentiment)`
5. Add `TopicExtractionStep(LLMStep)` with `@step_definition(instructions=TopicExtractionInstructions, default_system_key="topic_extraction", default_user_key="topic_extraction", default_extractions=[TopicExtraction], context=TopicExtractionContext)`:
   - `prepare_calls()`: returns `[{"variables": {"text": self.pipeline.validated_input.text, "sentiment": self.pipeline.context["sentiment"]}}]`
   - `process_instructions(instructions)`: returns `TopicExtractionContext(primary_topic=instructions[0].primary_topic, topics=[t.name for t in instructions[0].topics])`
6. Add `SummaryStep(LLMStep)` with `@step_definition(instructions=SummaryInstructions, default_system_key="summary", default_user_key="summary", context=SummaryContext)`:
   - `prepare_calls()`: returns `[{"variables": {"text": self.pipeline.validated_input.text, "sentiment": self.pipeline.context["sentiment"], "primary_topic": self.pipeline.context["primary_topic"]}}]`
   - `process_instructions(instructions)`: returns `SummaryContext(summary=instructions[0].summary)`

### Step 3: Assemble pipeline, agent registry, strategy, prompts, and entry point
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. In `llm_pipeline/demo/pipeline.py`, add remaining classes after step definitions:
   - `TextAnalyzerAgentRegistry(AgentRegistry, agents={"sentiment_analysis": SentimentAnalysisInstructions, "topic_extraction": TopicExtractionInstructions, "summary": SummaryInstructions})`
   - `DefaultStrategy(PipelineStrategy)` with `NAME = "default"`: `can_handle()` returns `True`; `get_steps()` returns `[SentimentAnalysisStep.create_definition(), TopicExtractionStep.create_definition(), SummaryStep.create_definition()]`
   - `TextAnalyzerStrategies(PipelineStrategies, strategies=[DefaultStrategy])`
   - `TextAnalyzerPipeline(PipelineConfig, registry=TextAnalyzerRegistry, strategies=TextAnalyzerStrategies, agent_registry=TextAnalyzerAgentRegistry)` with `INPUT_DATA = TextAnalyzerInputData` ClassVar and `seed_prompts` classmethod that delegates to `prompts.seed_prompts(cls, engine)`
2. In `llm_pipeline/demo/prompts.py`, implement:
   - 6 prompt constant dicts (3 system + 3 user) for `sentiment_analysis`, `topic_extraction`, `summary` keys
   - System prompt content: role + task instructions for each step
   - User prompt content with template variables: `{text}` (sentiment), `{text}` + `{sentiment}` (topic), `{text}` + `{sentiment}` + `{primary_topic}` (summary)
   - `seed_prompts(cls, engine)` function: creates `demo_topics` table via `SQLModel.metadata.create_all(engine, tables=[Topic.__table__])`, then idempotently inserts prompts using `select(Prompt).where(Prompt.prompt_key == ..., Prompt.prompt_type == ...)` pattern
3. In `pyproject.toml`, add entry point section:
   ```toml
   [project.entry-points."llm_pipeline.pipelines"]
   text_analyzer = "llm_pipeline.demo:TextAnalyzerPipeline"
   ```

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| `step_definition` naming enforcement raises ValueError at import | High | Use exact `{StepPrefix}Instructions` naming; verified in VALIDATED_RESEARCH |
| `process_instructions` returning dict when `context=` set causes TypeError at runtime | High | Always return PipelineContext subclass instance; validated in VALIDATED_RESEARCH |
| `TopicExtraction.extract()` override bypasses `_validate_instances()` | High | Use `def default(self, results)` only; never override `extract()` |
| `Topic.__table__` not created before pipeline runs (demo_topics missing) | Medium | Create in `seed_prompts()` before prompt inserts using `SQLModel.metadata.create_all(engine, tables=[Topic.__table__])` |
| `TopicExtractionContext.topics` as `list[str]` but TopicItem has `.name` | Low | Bridge in `process_instructions`: `[t.name for t in instructions[0].topics]` |
| Entry point not discoverable after adding to pyproject.toml | Low | Requires `pip install -e .` re-run; document in commit message |
| `PipelineConfig.__init_subclass__` rejects `DefaultStrategy` name prefix mismatch | Medium | `DefaultStrategy` prefix is "Default", not "TextAnalyzer"; verify framework allows non-matching prefix for strategy classes (step-1 research L103-106 shows NAME is auto-generated from class name, not pipeline prefix) |
| `TextAnalyzerStrategies` prefix check: strategies class prefix must match pipeline prefix | Medium | Research confirms `TextAnalyzerStrategies` naming is enforced - must use that exact name |
| Prompt content quality insufficient for demo | Low | Write clear, minimal prompts; exact wording is implementation detail, not architectural |

## Success Criteria

- [ ] `llm_pipeline/demo/__init__.py`, `pipeline.py`, `prompts.py` all exist with correct content
- [ ] `TextAnalyzerPipeline` importable from `llm_pipeline.demo`
- [ ] `pyproject.toml` has `[project.entry-points."llm_pipeline.pipelines"]` section with `text_analyzer` key
- [ ] After `pip install -e .`, `importlib.metadata.entry_points(group="llm_pipeline.pipelines")` discovers `text_analyzer`
- [ ] `Topic.__tablename__` is `"demo_topics"` with fields: `id`, `name`, `relevance`, `run_id`
- [ ] All 3 instruction classes named `{StepPrefix}Instructions`, inheriting `LLMResultMixin`, with safe field defaults
- [ ] All 3 context classes named `{StepPrefix}Context`, inheriting `PipelineContext`
- [ ] `SentimentAnalysisStep.prepare_calls()` returns `[{"variables": {"text": ...}}]`
- [ ] `TopicExtractionStep.prepare_calls()` returns `[{"variables": {"text": ..., "sentiment": ...}}]`
- [ ] `SummaryStep.prepare_calls()` returns `[{"variables": {"text": ..., "sentiment": ..., "primary_topic": ...}}]`
- [ ] All 3 `process_instructions` return `PipelineContext` subclass instance (not dict)
- [ ] `TopicExtraction.default()` (not `extract()`) bridges `TopicItem -> Topic` with `run_id`
- [ ] `seed_prompts()` creates `demo_topics` table and inserts 6 prompts idempotently
- [ ] 6 prompts seeded: system + user for `sentiment_analysis`, `topic_extraction`, `summary`
- [ ] `DefaultStrategy.NAME` is `"default"`; `can_handle()` always returns `True`
- [ ] `pytest` passes (existing tests unbroken)

## Phase Recommendation

**Risk Level:** low
**Reasoning:** All architectural decisions resolved in VALIDATED_RESEARCH with CEO approval. Framework patterns well-documented across 3 research files and cross-referenced against source. Critical contradictions identified and corrected. No schema changes to existing tables. New isolated package with no modifications to framework core. Only pyproject.toml and new files.
**Suggested Exclusions:** testing, review
