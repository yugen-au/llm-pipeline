# Codebase Architecture Review - Post pydantic-ai Migration

## Test Suite Status
- **951 passed, 1 failed, 6 skipped** (121s)
- Failed: `test_events_router_prefix` - pre-existing UI route assertion mismatch, unrelated to migration

## Module Structure (llm_pipeline/)

### Core Orchestration
| Module | Classes/Functions | Lines | Role |
|--------|------------------|-------|------|
| `pipeline.py` | `PipelineConfig`, `StepKeyDict` | 1351 | Main orchestrator, execute() loop, consensus, caching, state |
| `step.py` | `LLMStep`, `LLMResultMixin`, `step_definition` | 397 | Step ABC, result mixin, decorator factory |
| `strategy.py` | `StepDefinition`, `PipelineStrategy`, `PipelineStrategies` | 339 | Step config dataclass, strategy ABCs |
| `context.py` | `PipelineContext`, `PipelineInputData` | 45 | Pydantic base models for context/input |

### pydantic-ai Integration (Tasks 1-5)
| Module | Classes/Functions | Role |
|--------|------------------|------|
| `agent_registry.py` | `AgentRegistry` | ABC mapping step_name -> output type |
| `agent_builders.py` | `StepDeps`, `build_step_agent()` | Dep injection container + Agent factory |
| `validators.py` | `not_found_validator()`, `array_length_validator()` | Output validator factories for pydantic-ai |
| `consensus.py` | `ConsensusStrategy` ABC + 4 concrete strategies | Pluggable consensus (MajorityVote, ConfidenceWeighted, Adaptive, SoftVote) |

### Data Processing
| Module | Classes/Functions | Role |
|--------|------------------|------|
| `extraction.py` | `PipelineExtraction` | ABC for LLM result -> DB model conversion |
| `transformation.py` | `PipelineTransformation` | ABC for data structure transforms |
| `types.py` | `ArrayValidationConfig`, `ValidationContext`, `StepCallParams` | Shared type definitions |
| `registry.py` | `PipelineDatabaseRegistry` | ABC declaring managed DB models |

### State & Persistence
| Module | Classes/Functions | Role |
|--------|------------------|------|
| `state.py` | `PipelineStepState`, `PipelineRunInstance`, `PipelineRun` | SQLModel audit/state tables |
| `db/__init__.py` | `init_pipeline_db()`, migrations | DB init, WAL, index creation |
| `db/prompt.py` | `Prompt` | SQLModel for prompt templates |
| `session/readonly.py` | `ReadOnlySession` | Write-blocking session wrapper |

### Events
| Module | Classes/Functions | Role |
|--------|------------------|------|
| `events/types.py` | 27 frozen dataclass events | Immutable event hierarchy with auto-registry |
| `events/emitter.py` | `PipelineEventEmitter` Protocol, `CompositeEmitter` | Event dispatch |
| `events/handlers.py` | `LoggingEventHandler`, `InMemoryEventHandler`, `SQLiteEventHandler` | Concrete handlers |
| `events/models.py` | `PipelineEventRecord` | SQLModel for event persistence |

### Prompts
| Module | Role |
|--------|------|
| `prompts/service.py` | DB-backed prompt retrieval and template formatting |
| `prompts/loader.py` | YAML prompt sync to DB |
| `prompts/variables.py` | `VariableResolver` Protocol for prompt variable resolution |

### Other
| Module | Role |
|--------|------|
| `naming.py` | `to_snake_case()` utility |
| `introspection.py` | `PipelineIntrospector` - class-level metadata extraction without instantiation |
| `llm/__init__.py` | **DEAD** - single comment, no code |
| `ui/` | FastAPI app, CLI, routes, frontend |

## Class Hierarchy

```
PipelineConfig (ABC)
  |-- __init_subclass__(registry=, strategies=, agent_registry=)
  |-- execute() -> orchestrates steps via pydantic-ai agents
  |-- _execute_with_consensus() -> consensus loop with strategy pattern
  |-- save() -> persist extractions to DB

LLMStep (ABC)
  |-- step_name (auto-derived from class name)
  |-- get_agent(registry) -> output_type lookup
  |-- build_user_prompt(variables, prompt_service)
  |-- prepare_calls() -> List[StepCallParams]  [abstract]
  |-- process_instructions() -> context dict
  |-- extract_data() -> delegates to PipelineExtraction classes

PipelineStrategy (ABC)
  |-- __init_subclass__ auto-generates NAME, DISPLAY_NAME
  |-- can_handle(context) -> bool  [abstract]
  |-- get_steps() -> List[StepDefinition]  [abstract]

ConsensusStrategy (ABC)
  |-- MajorityVoteStrategy
  |-- ConfidenceWeightedStrategy
  |-- AdaptiveStrategy
  |-- SoftVoteStrategy

AgentRegistry (ABC)
  |-- __init_subclass__(agents={step_name: OutputModel})
  |-- get_output_type(step_name) -> Type[BaseModel]

PipelineEvent (frozen dataclass)
  |-- StepScopedEvent (intermediate, _skip_registry)
       |-- 20+ concrete event types across 9 categories
```

## Pipeline Step Execution Flow

```
PipelineConfig.execute(data, initial_context)
  1. Create PromptService from session
  2. Validate input_data against INPUT_DATA schema
  3. Create PipelineRun record
  4. For each step_index:
     a. Strategy selection: find strategy where can_handle(context)==True
     b. StepDefinition.create_step(pipeline) - auto-discover prompts from DB
     c. Check should_skip()
     d. Cache check (if use_cache=True)
     e. If cached: load from cache, reconstruct extractions
     f. If fresh:
        - step.prepare_calls() -> List[StepCallParams]
        - build_step_agent(step_name, output_type, validators, instrument)
        - For each call_params:
          - Create StepDeps (per-call validation config)
          - step.build_user_prompt(variables, prompt_service)
          - If consensus_strategy: _execute_with_consensus()
          - Else: agent.run_sync(user_prompt, deps, model)
        - Store instructions
        - step.process_instructions() -> context update
        - Run transformation if defined
        - step.extract_data() -> DB model extraction
        - Save step state with token usage
     g. Emit StepCompleted event
  5. Update PipelineRun status
```

## Architectural Issues Found

### CRITICAL: pydantic-ai Must Be Required Dependency
- `validators.py` line 12: `from pydantic_ai import ModelRetry, RunContext` (top-level import)
- `__init__.py` imports `validators` at module level
- Result: `import llm_pipeline` fails without pydantic-ai installed
- **Action**: Move `pydantic-ai>=1.0.5` from optional to required deps in pyproject.toml

### Dead Code: llm/ Subpackage
- `llm_pipeline/llm/__init__.py` contains only: `# LLM subpackage - provider abstraction removed, use pydantic-ai agents via agent_builders.py`
- Stale `__pycache__` files for 7 deleted modules: rate_limiter, schema, validation, provider, gemini, executor, result
- **Action**: Delete entire `llm_pipeline/llm/` directory

### Dead Code: _query_prompt_keys() in step.py
- Function defined at lines 34-77, never called anywhere in codebase
- StepDefinition.create_step() in strategy.py has its own inline prompt discovery logic
- **Action**: Remove `_query_prompt_keys()` function

### Stale Documentation: variables.py
- Line 26 in docstring example: `provider=GeminiProvider()`
- GeminiProvider no longer exists; should reference model string pattern
- **Action**: Update docstring to use `model='google-gla:gemini-2.0-flash-lite'` pattern

### Optional Dep Cleanup: gemini
- `google-generativeai>=0.3.0` listed under `[project.optional-dependencies].gemini`
- Zero direct imports in llm_pipeline/ source code
- pydantic-ai handles Gemini calls internally via its own google integration
- **Note**: Downstream consumers (logistics-intelligence) may depend on this for data types or direct API usage independent of the pipeline. Needs verification.

### Pre-existing Test Failure
- `tests/test_ui.py::TestRoutersIncluded::test_events_router_prefix`
- Expects prefix `/events` but actual is `/runs/{run_id}/events`
- Not migration-related; likely caused by UI route restructuring

## Patterns Working Well

1. **Agent construction**: `build_step_agent()` correctly uses `defer_model_check=True` and passes model at `run_sync()` time
2. **Consensus Strategy Pattern**: Clean ABC with 4 implementations, well-separated from orchestrator
3. **Event system**: Frozen dataclasses with auto-registration, immutable, well-categorized
4. **Naming conventions enforced at class definition time**: Pipeline, Strategy, Step, Extraction suffixes
5. **ReadOnlySession**: Prevents accidental writes during step execution
6. **Validator factories**: Cleanly compose with pydantic-ai's output_validator system

## Module Export Summary (__init__.py)
- 44 symbols exported across 10 categories
- All exports are used and properly categorized
- No deprecated symbols remain in exports
