# llm-pipeline Documentation

Complete reference and guide for the **llm-pipeline** declarative LLM orchestration framework.

## What is llm-pipeline?

llm-pipeline is a Python framework for building declarative, production-ready LLM-powered data processing pipelines. It provides:

- **Declarative Configuration**: Define pipelines as Python classes with automatic validation
- **Strategy Pattern**: Context-dependent execution paths for flexible logic
- **State Tracking & Caching**: Built-in caching with audit trail for reproducibility
- **Database Persistence**: Automatic foreign key ordering and transaction management
- **LLM Integration**: Multi-provider support via pydantic-ai model strings
- **Three-Tier Data Model**: Clear separation between context, data, and database extractions

Transform unstructured or semi-structured data into validated database records through LLM-powered steps—with zero boilerplate.

## Quick Start

### Installation

```bash
pip install llm-pipeline
```

### First Pipeline (5 minutes)

For a complete working example with all components, see [Basic Pipeline Example](guides/basic-pipeline.md).

Here's the essential flow:

```python
from llm_pipeline import PipelineConfig

# 1. Define domain models, registry, strategies (see guides/basic-pipeline.md)
# ...

# 2. Define pipeline with registry and strategies
class MyPipeline(
    PipelineConfig,
    registry=MyRegistry,
    strategies=MyStrategies
):
    def sanitize(self, data: str) -> str:
        return data.strip()[:10000]

# 3. Execute with pydantic-ai model string
pipeline = MyPipeline(model='google-gla:gemini-2.0-flash-lite')
pipeline.execute(
    data="your input data",
    initial_context={'key': 'value'}
)

# 5. Access results
results = pipeline.get_extractions(YourModel)
pipeline.save(engine)  # Persist to database
```

**Learn more**: [Getting Started Guide](guides/getting-started.md) | [Basic Pipeline Example](guides/basic-pipeline.md)

## Documentation Structure

### Where to Find What

**New to llm-pipeline?**
- Start with [Getting Started Guide](guides/getting-started.md)
- Then read [Basic Pipeline Example](guides/basic-pipeline.md)

**Want to understand the architecture?**
- Read [Architecture Overview](architecture/overview.md)
- Explore [Core Concepts](architecture/concepts.md)
- Study [Design Patterns](architecture/patterns.md)
- View [C4 Diagrams](architecture/diagrams/)

**Need API details?**
- Start with [API Reference Index](api/index.md)
- Look up specific modules (Pipeline, Step, Strategy, etc.)

**Building a specific feature?**
- Strategies: [Multi-Strategy Guide](guides/multi-strategy.md) + [Strategy API](api/strategy.md)
- Prompts: [Prompt Management Guide](guides/prompts.md) + [Prompts API](api/prompts.md)
- Database: [Registry API](api/registry.md) + [State API](api/state.md)

**Complete navigation**: [Documentation Index](index.md)

## Documentation Sections

### Architecture (Conceptual)

Understand how llm-pipeline works:

| Document | Purpose |
|----------|---------|
| [Architecture Overview](architecture/overview.md) | High-level system design and core principles |
| [Core Concepts](architecture/concepts.md) | Key terminology and foundational concepts |
| [Design Patterns](architecture/patterns.md) | Implementation patterns (declarative config, two-phase write, etc.) |
| [Known Limitations](architecture/limitations.md) | Current constraints and workarounds |

**Visual Guides**:
- [C4 Context Diagram](architecture/diagrams/c4-context.mmd) - System boundaries
- [C4 Container Diagram](architecture/diagrams/c4-container.mmd) - Internal structure
- [C4 Component Diagram](architecture/diagrams/c4-component.mmd) - Component details

### API Reference (Complete)

Comprehensive API documentation:

| Module | Contains |
|--------|----------|
| [API Index](api/index.md) | Installation, top-level imports, requirements |
| [Pipeline](api/pipeline.md) | `PipelineConfig`, `StepKeyDict`, pipeline orchestration |
| [Step](api/step.md) | `LLMStep`, `LLMResultMixin`, step definitions |
| [Strategy](api/strategy.md) | `PipelineStrategy`, `PipelineStrategies`, strategy selection |
| [Extraction](api/extraction.md) | `PipelineExtraction`, database extraction patterns |
| [Transformation](api/transformation.md) | `PipelineTransformation`, data transformation |
| [Pipeline](api/pipeline.md) | `PipelineConfig`, pipeline orchestration and LLM integration |
| [Prompts](api/prompts.md) | `PromptService`, prompt management, versioning |
| [State](api/state.md) | `PipelineStepState`, `PipelineRunInstance`, caching |
| [Registry](api/registry.md) | `PipelineDatabaseRegistry`, FK ordering, read-only sessions |

### Usage Guides (Practical)

Learn by example:

| Guide | Teaches |
|-------|---------|
| [Getting Started](guides/getting-started.md) | Installation, setup, first pipeline |
| [Basic Pipeline Example](guides/basic-pipeline.md) | Complete working pipeline with all components |
| [Multi-Strategy Pipeline](guides/multi-strategy.md) | Context-based strategy selection |
| [Prompt Management](guides/prompts.md) | YAML prompts, versioning, variable resolution |

## Key Concepts at a Glance

### Pipeline + Strategy + Step Pattern

```
Pipeline (orchestrator)
  ├─ owns: context, data, session
  ├─ manages: execution, caching, state
  └─ delegates to → Strategy (logic selector)
       └─ returns → Steps (LLM workers)
            ├─ prepare_calls() → LLM input
            └─ process_instructions() → structured output
```

### Three-Tier Data Model

1. **Context** - Runtime decision data (strategy selection)
2. **Data** - Transformation results (internal intermediate data)
3. **Extractions** - Database records (persistent validated data)

### Two-Phase Write

1. **Phase 1 (execution)**: Add to session + flush → get FK IDs
2. **Phase 2 (save)**: Commit + track in PipelineRunInstance

### Read-Only Session

Prevent accidental writes during step execution using `ReadOnlySession` wrapper.

## Common Tasks

### Configure LLM Model

```python
# Use any pydantic-ai supported model string
pipeline = MyPipeline(model='google-gla:gemini-2.0-flash-lite')
```

### Set Up Development Database

```bash
# Automatic SQLite creation in ~/.llm_pipeline.db
from llm_pipeline import init_pipeline_db
init_pipeline_db()  # Uses default location
```

### Sync Prompts from YAML

```python
from llm_pipeline.prompts import sync_prompts
from sqlmodel import create_engine

engine = create_engine('sqlite:///pipeline.db')
sync_prompts(bind=engine)  # Pass engine as bind parameter
```

### Query Results

```python
from llm_pipeline import PipelineRunInstance
from sqlmodel import Session, select

with Session(engine) as session:
    runs = session.exec(select(PipelineRunInstance)).all()
    for run in runs:
        print(f"Run: {run.run_id}, Model: {run.model_type}#{run.model_id}, Created: {run.created_at}")
```

## Architecture at a Glance

### System Architecture

- **Orchestrator**: `PipelineConfig` manages execution flow
- **Strategy System**: `PipelineStrategy` provides context-based routing
- **Step Execution**: `LLMStep` calls LLM, extracts/transforms data
- **State Tracking**: `PipelineStepState` caches results
- **Database Access**: `PipelineDatabaseRegistry` manages FK ordering
- **Prompt Management**: `PromptService` loads versioned prompts
- **LLM Integration**: pydantic-ai Agent system via AgentRegistry and agent_builders.py

### Data Flow

```
Input Data
    ↓
Pipeline (with context)
    ↓
Strategy (selects execution path)
    ↓
Steps (in sequence):
    ├─ Prepare LLM calls
    ├─ Execute via provider
    ├─ Extract results
    ├─ Transform data
    └─ Update state/cache
    ↓
Save to Database
    ↓
Persisted Results
```

## Finding Documentation

### By Scenario

**"I don't know where to start"**
→ [Getting Started Guide](guides/getting-started.md)

**"I want to understand how it works"**
→ [Architecture Overview](architecture/overview.md) → [Core Concepts](architecture/concepts.md)

**"I need to build a pipeline now"**
→ [Basic Pipeline Example](guides/basic-pipeline.md)

**"I need to do something advanced (strategies, custom extraction, etc.)"**
→ [Multi-Strategy Guide](guides/multi-strategy.md) + relevant API reference

**"I'm stuck or getting errors"**
→ [Known Limitations](architecture/limitations.md) + relevant API reference

**"I need complete API documentation"**
→ [API Reference Index](api/index.md) → look up specific module

### By Component

**PipelineConfig**: [API](api/pipeline.md) | [Example](guides/basic-pipeline.md)

**LLMStep**: [API](api/step.md) | [Example](guides/basic-pipeline.md) | [Patterns](architecture/patterns.md)

**Strategies**: [API](api/strategy.md) | [Example](guides/multi-strategy.md)

**Prompts**: [API](api/prompts.md) | [Guide](guides/prompts.md)

**Database**: [Registry API](api/registry.md) | [State API](api/state.md)

**LLM Providers**: [API](api/llm.md) | [Getting Started](guides/getting-started.md)

## Tech Stack

- **Python**: 3.11+
- **Data Validation**: Pydantic v2
- **Database**: SQLModel / SQLAlchemy 2.0
- **Configuration**: PyYAML
- **Build**: Hatchling
- **LLM Framework**: pydantic-ai (multi-provider support)

## Requirements

### Minimum

- Python 3.11+
- pydantic >= 2.0
- sqlmodel >= 0.0.14
- sqlalchemy >= 2.0
- pyyaml >= 6.0

### Optional

- pytest >= 7.0 (for development)

See [API Reference](api/index.md) for complete dependency information.

## Key Features

✓ **Declarative Configuration** - Define pipelines as Python classes
✓ **Strategy Pattern** - Context-dependent execution paths
✓ **Caching & State Tracking** - Built-in efficiency and reproducibility
✓ **Database Persistence** - Automatic FK validation and transaction management
✓ **Three-Tier Data Model** - Clear separation of concerns
✓ **LLM Integration** - Multi-provider support via pydantic-ai
✓ **Prompt Management** - Versioned YAML-based prompts
✓ **Read-Only Sessions** - Prevent accidental writes
✓ **Consensus Polling** - Support for multi-model decisions
✓ **Zero Boilerplate** - Automatic configuration and validation

## Known Limitations

See [Known Limitations](architecture/limitations.md) for current constraints and workarounds.

Common ones:
- Single-level inheritance required for naming validation
- Some vestigial code (marked in API docs)

## Version & Updates

**Current Version**: 0.1.0
**Documentation Updated**: 2026-02
**Python Support**: 3.11+

## Support & Contributions

For issues, questions, feature requests, or documentation improvements:
- Check [Known Limitations](architecture/limitations.md)
- Review relevant API documentation
- See project repository for issue tracking

## License

MIT License - See project repository for details.

---

**Start here**: [Getting Started Guide](guides/getting-started.md) or [Full Documentation Index](index.md)
