# Research Step 1: Codebase Architecture - Consensus Mechanism

## 1. Current Consensus Implementation

### 1.1 _execute_with_consensus() - pipeline.py:1265-1386

Instance method on `PipelineConfig`. Called from the `execute()` loop when `use_consensus=True`.

**Signature:**
```python
def _execute_with_consensus(
    self, agent, user_prompt, step_deps, output_type,
    consensus_threshold, maximum_step_calls, current_step_name
) -> tuple[BaseModel, int | None, int | None, int]:
```

**Return value:** `(selected_result, total_input_tokens, total_output_tokens, total_requests)`
- Token values are `int | None` (None when no usage data available from any attempt)

**Algorithm (majority-vote):**
1. Initialize `results=[]`, `result_groups=[]`, token accumulators
2. Emit `ConsensusStarted` event
3. Loop `attempt in range(maximum_step_calls)`:
   a. Call `agent.run_sync(user_prompt, deps=step_deps, model=self._model)`
   b. On `UnexpectedModelBehavior` -> `output_type.create_failure(str(exc))`
   c. Accumulate per-call token usage
   d. Emit `LLMCallCompleted` per attempt
   e. Group result: iterate `result_groups`, if `_instructions_match(instruction, group[0])` -> append to group
   f. If no group matched -> create new group
   g. Emit `ConsensusAttempt`
   h. If `len(matched_group) >= consensus_threshold` -> emit `ConsensusReached`, return first element of group
4. On loop exhaustion: find `largest_group = max(result_groups, key=len)`, emit `ConsensusFailed`, return first element of largest group

### 1.2 _instructions_match() - pipeline.py:1258-1263

```python
@staticmethod
def _instructions_match(instr1: BaseModel, instr2: BaseModel) -> bool:
    mixin_fields = PipelineConfig._get_mixin_fields(type(instr1))
    dict1 = instr1.model_dump()
    dict2 = instr2.model_dump()
    return PipelineConfig._smart_compare(dict1, dict2, mixin_fields=mixin_fields)
```

Compares two instruction models for "structural equality" by dumping to dict and delegating to `_smart_compare`.

### 1.3 _smart_compare() - pipeline.py:1232-1256

```python
@staticmethod
def _smart_compare(value1, value2, field_name="", mixin_fields=None) -> bool:
```

Recursive comparison with intentional leniency:
- **Mixin fields** (confidence_score, notes): always True (skipped)
- **Strings**: always True (LLM text varies, only structural values matter)
- **None values**: always True
- **Numerics** (int, float, bool): strict equality
- **Lists**: length must match, element-wise recursive compare
- **Dicts**: key sets must match, value-wise recursive compare
- **All other types**: default True

This is the core semantic: consensus compares STRUCTURAL values only (numbers, list lengths, dict shapes). Text, confidence, and notes are ignored.

### 1.4 _get_mixin_fields() - pipeline.py:1225-1230

```python
@staticmethod
def _get_mixin_fields(model_class: Type[BaseModel]) -> set:
    from llm_pipeline.step import LLMResultMixin
    if not issubclass(model_class, LLMResultMixin):
        return set()
    return set(LLMResultMixin.model_fields.keys())
```

Returns `{'confidence_score', 'notes'}` for LLMResultMixin subclasses, empty set otherwise.

## 2. Consensus Configuration (Caller Side)

### 2.1 execute() Consensus Parsing - pipeline.py:482-494

```python
consensus_polling: Optional[Dict[str, Any]] = None  # parameter

if consensus_polling:
    use_consensus = consensus_polling.get("enable", False)
    consensus_threshold = consensus_polling.get("consensus_threshold", 3)
    maximum_step_calls = consensus_polling.get("maximum_step_calls", 5)
    if use_consensus:
        if consensus_threshold < 2:
            raise ValueError("consensus_threshold must be >= 2")
        if maximum_step_calls < consensus_threshold:
            raise ValueError("maximum_step_calls must be >= consensus_threshold")
```

Config is a plain dict passed to `execute()`. Default threshold=3, default max_calls=5. Applied **uniformly to all steps** in the pipeline.

### 2.2 Consensus Call Site - pipeline.py:817-830

```python
if use_consensus:
    instruction, _c_input, _c_output, _c_requests = (
        self._execute_with_consensus(
            agent, user_prompt, step_deps, output_type,
            consensus_threshold, maximum_step_calls,
            current_step_name,
        )
    )
    _step_input_tokens += _c_input or 0
    _step_output_tokens += _c_output or 0
    _step_total_requests += _c_requests
```

Token totals from consensus are merged into step-level accumulators for the `StepCompleted` event.

## 3. StepDefinition - strategy.py:23-141

Dataclass connecting step class with configuration:

```python
@dataclass
class StepDefinition:
    step_class: Type
    system_instruction_key: str
    user_prompt_key: str
    instructions: Type
    action_after: Optional[str] = None
    extractions: List[Type['PipelineExtraction']] = field(default_factory=list)
    transformation: Optional[Type['PipelineTransformation']] = None
    context: Optional[Type] = None
    agent_name: str | None = None
    not_found_indicators: list[str] | None = None
```

**No consensus-related fields currently.** Task 5 adds `consensus_strategy: ConsensusStrategy | None = None`.

## 4. PipelineContext - context.py

Minimal base class (`PipelineContext(BaseModel): pass`). Steps produce context subclasses via `process_instructions()`. Context is stored in `pipeline._context` dict keyed by field names. Not directly involved in consensus.

## 5. Result Flow Through Pipeline

1. `execute()` iterates step positions
2. Per step: select strategy, create step, check cache
3. Per call_params entry: build agent, build user prompt, call LLM (or consensus)
4. Results collected in `instructions` list
5. `self._instructions[step.step_name] = instructions`
6. `step.process_instructions(instructions)` -> context values
7. `step.extract_data(instructions)` -> DB models
8. Transformation applied if configured
9. State saved to DB

Consensus is **transparent** to the rest of the pipeline. It replaces a single `agent.run_sync()` call with multiple calls + selection logic. The downstream code receives a single instruction regardless.

## 6. Event System - Consensus Events

Defined in `llm_pipeline/events/types.py`:

| Event | Category | Fields |
|-------|----------|--------|
| `ConsensusStarted` | consensus | threshold, max_calls |
| `ConsensusAttempt` | consensus | attempt, group_count |
| `ConsensusReached` | consensus | attempt, threshold |
| `ConsensusFailed` | consensus | max_calls, largest_group_size |

All extend `StepScopedEvent` (adds `step_name`). Events are `frozen=True` dataclasses with auto-registration.

`LLMCallCompleted` events are also emitted per consensus attempt (call_index=attempt, attempt_count=attempt+1).

## 7. LLMResultMixin - step.py:180-229

```python
class LLMResultMixin(BaseModel):
    confidence_score: float = Field(default=0.95, ge=0.0, le=1.0)
    notes: str | None = Field(default=None)
```

All instruction models inherit from this. Provides:
- `create_failure(reason, **safe_defaults)` -> instance with confidence=0.0
- `get_example()` -> example instance from class-level `example` dict

Relevant to consensus: confidence_score is available on every instruction but currently IGNORED during consensus comparison. ConfidenceWeightedStrategy could use it.

## 8. Package Structure

Current structure is flat under `llm_pipeline/`:

```
llm_pipeline/
  __init__.py          # Main exports
  pipeline.py          # PipelineConfig (contains consensus logic)
  strategy.py          # StepDefinition, PipelineStrategy, PipelineStrategies
  step.py              # LLMStep, LLMResultMixin, step_definition
  context.py           # PipelineContext, PipelineInputData
  types.py             # ArrayValidationConfig, ValidationContext, StepCallParams
  agent_builders.py    # StepDeps, build_step_agent
  agent_registry.py    # AgentRegistry
  extraction.py        # PipelineExtraction
  transformation.py    # PipelineTransformation
  registry.py          # PipelineDatabaseRegistry
  state.py             # PipelineStepState, PipelineRunInstance, PipelineRun
  introspection.py     # PipelineIntrospector
  validators.py        # not_found_validator, array_length_validator
  naming.py            # to_snake_case
  events/              # Event infrastructure (types, emitter, handlers, models)
  llm/                 # Gutted (legacy, only __init__.py with comment)
  ...
```

**No `schemas/pipeline/` package exists.** Task description references `logistics_intelligence/core/schemas/pipeline/consensus.py` which is the old monorepo path. New file should be `llm_pipeline/consensus.py`.

## 9. Existing Tests

`tests/events/test_consensus_events.py` (492 lines) covers:
- ConsensusReached path (identical responses)
- ConsensusFailed path (all different responses)
- Event ordering (Started -> Attempt*N -> Reached/Failed)
- Event field validation
- Zero overhead (no emitter)
- Multi-group consensus (group_count evolution, first group hitting threshold)

Test infrastructure in `tests/events/conftest.py`:
- `SuccessPipeline` with 2 `SimpleStep`s (each produces 1 call_params)
- `SimpleInstructions(LLMResultMixin)` with `count: int`
- `make_simple_run_result(count)` builds MagicMock mimicking AgentRunResult
- Consensus tested by controlling `Agent.run_sync` side effects (list of responses)

Consensus comparison relies on `SimpleInstructions.count` field (int) for equality. Same count -> match, different count -> different group.

## 10. Upstream Task 2 Deviations

Task 2 (done) rewrote `_execute_with_consensus` from legacy `execute_llm_step()` to `agent.run_sync()`. Key deviations from original plan:
- `LLMCallCompleted.raw_response` permanently None (pydantic-ai doesn't expose raw response)
- `LLMCallCompleted.attempt_count` always 1 (pydantic-ai manages retries internally)
- Orphaned event types (LLMCallRetry, LLMCallFailed, LLMCallRateLimited) remain defined but never emitted

No deviations that affect Task 5 consensus refactoring.

## 11. Design Decisions Needed (for planning phase)

1. **File location**: `llm_pipeline/consensus.py` (not `schemas/pipeline/consensus.py`)
2. **Per-step vs pipeline-level interaction**: When `StepDefinition.consensus_strategy` is set, does it:
   - (a) Always activate consensus for that step (regardless of pipeline enable flag)?
   - (b) Only activate when pipeline enable=True?
   - (c) Override pipeline-level entirely?
3. **Event emission ownership**: Strategies should be pure selection logic; pipeline.py retains event emission
4. **Token tracking ownership**: Pipeline.py retains token accumulation; strategies receive results, not agent calls
5. **ConsensusResult metadata**: What constitutes "confidence" (agreement_ratio? selected instruction's confidence_score? computed metric?)
6. **ConfidenceWeighted access to scores**: Currently `_smart_compare` SKIPS confidence_score. ConfidenceWeighted would need to read it from instructions. How to weight when using mixin field that majority-vote ignores?

## 12. Integration Points Summary

| Component | Role in Consensus | Refactor Impact |
|-----------|------------------|-----------------|
| `PipelineConfig._execute_with_consensus()` | Orchestration + selection logic | Extract selection to strategy, keep orchestration |
| `PipelineConfig._smart_compare()` | Structural comparison | Move to consensus.py module-level |
| `PipelineConfig._instructions_match()` | Instruction equality | Move to consensus.py module-level |
| `PipelineConfig._get_mixin_fields()` | LLMResultMixin field detection | Move to consensus.py or keep accessible |
| `StepDefinition` | Step configuration | Add consensus_strategy field |
| `execute()` consensus_polling parsing | Config entry point | May need to resolve step-level vs pipeline-level |
| `LLMResultMixin.confidence_score` | Per-result confidence | Used by ConfidenceWeighted/Adaptive |
| Consensus events (4 types) | Observability | May need strategy_name field additions |
| `llm_pipeline/__init__.py` | Public API exports | Add ConsensusStrategy, ConsensusResult, strategy classes |
