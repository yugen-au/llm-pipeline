# llm-pipeline Documentation Index

Welcome to the complete reference guide for **llm-pipeline**, a declarative orchestration framework for building LLM-powered data processing pipelines.

## Quick Navigation

### Getting Started
New to llm-pipeline? Start here:

1. **[Getting Started Guide](guides/getting-started.md)** - Installation, setup, and first pipeline
2. **[Architecture Overview](architecture/overview.md)** - High-level system design and concepts
3. **[Basic Pipeline Example](guides/basic-pipeline.md)** - Complete working example with database persistence

### Core Concepts
Understand the foundational design patterns:

- **[Core Concepts](architecture/concepts.md)** - Declarative configuration, strategy pattern, three-tier data model
- **[Design Patterns](architecture/patterns.md)** - Class-level config, step factory pattern, two-phase write, read-only sessions
- **[Known Limitations](architecture/limitations.md)** - Current constraints and workarounds

### Architecture Diagrams
Visual representation of system structure:

- **[C4 Context Diagram](architecture/diagrams/c4-context.mmd)** - System boundaries and external actors
- **[C4 Container Diagram](architecture/diagrams/c4-container.mmd)** - Internal components and containers
- **[C4 Component Diagram](architecture/diagrams/c4-component.mmd)** - Detailed component relationships

## Complete API Reference

### Module Index
Comprehensive API documentation organized by module:

| Module | Purpose | Key Classes |
|--------|---------|-------------|
| **[Pipeline](api/pipeline.md)** | Pipeline orchestration and execution | `PipelineConfig`, `StepKeyDict` |
| **[Step](api/step.md)** | Step definition system | `LLMStep`, `LLMResultMixin`, `@step_definition` |
| **[Strategy](api/strategy.md)** | Strategy pattern and selection | `PipelineStrategy`, `PipelineStrategies`, `StepDefinition` |
| **[Extraction](api/extraction.md)** | Database extraction from LLM results | `PipelineExtraction` |
| **[Transformation](api/transformation.md)** | Data transformation between steps | `PipelineTransformation` |
| **[LLM Provider](api/llm.md)** | LLM provider system | `LLMProvider`, `GeminiProvider`, `RateLimiter` |
| **[Prompts](api/prompts.md)** | Prompt management system | `PromptService`, `Prompt`, `VariableResolver` |
| **[State](api/state.md)** | Execution state tracking | `PipelineStepState`, `PipelineRunInstance` |
| **Events** | Event system for pipeline observability | `InMemoryEventHandler`, `CompositeEmitter`, `LoggingEventHandler` |
| **[Registry](api/registry.md)** | Database registry with FK ordering | `PipelineDatabaseRegistry`, `ReadOnlySession` |

**[API Reference Index](api/index.md)** - Complete import reference and installation details

## Usage Guides

### Learn by Example

- **[Getting Started](guides/getting-started.md)** - Introduction and setup
- **[Basic Pipeline Example](guides/basic-pipeline.md)** - Complete working pipeline with domain models, steps, and strategies
- **[Multi-Strategy Pipeline](guides/multi-strategy.md)** - Context-dependent execution paths (lane-based vs zone-based example)
- **[Prompt Management](guides/prompts.md)** - YAML prompt structure, versioning, and variable resolution

## Cross-Reference Map

### By Use Case

#### "How do I...?"

| Task | Documentation |
|------|---|
| Install llm-pipeline | [Getting Started](guides/getting-started.md) |
| Create my first pipeline | [Basic Pipeline Example](guides/basic-pipeline.md) |
| Define a step | [Step API Reference](api/step.md) + [Design Patterns](architecture/patterns.md) |
| Use strategies for conditional logic | [Multi-Strategy Guide](guides/multi-strategy.md) + [Strategy API](api/strategy.md) |
| Extract data from LLM results | [Extraction API Reference](api/extraction.md) |
| Transform data between steps | [Transformation API Reference](api/transformation.md) |
| Manage prompts | [Prompt Management Guide](guides/prompts.md) + [Prompts API](api/prompts.md) |
| Query saved results | [State API Reference](api/state.md) |
| Configure database | [Getting Started](guides/getting-started.md) + [Registry API](api/registry.md) |
| Understand the architecture | [Architecture Overview](architecture/overview.md) + [Core Concepts](architecture/concepts.md) |
| Learn design patterns | [Design Patterns](architecture/patterns.md) + [Basic Pipeline Example](guides/basic-pipeline.md) |

### By Component

#### PipelineConfig
- **Overview**: [Architecture Overview](architecture/overview.md)
- **API Details**: [Pipeline API Reference](api/pipeline.md)
- **Usage**: [Basic Pipeline Example](guides/basic-pipeline.md), [Multi-Strategy Guide](guides/multi-strategy.md)
- **Design Pattern**: [Design Patterns](architecture/patterns.md)

#### LLMStep & Steps
- **Overview**: [Core Concepts](architecture/concepts.md)
- **API Details**: [Step API Reference](api/step.md)
- **Design Pattern**: [Design Patterns](architecture/patterns.md) - Step factory, class-level config
- **Usage**: [Basic Pipeline Example](guides/basic-pipeline.md), [Multi-Strategy Guide](guides/multi-strategy.md)

#### Strategy Pattern
- **Overview**: [Architecture Overview](architecture/overview.md), [Core Concepts](architecture/concepts.md)
- **API Details**: [Strategy API Reference](api/strategy.md)
- **Usage**: [Multi-Strategy Guide](guides/multi-strategy.md)

#### Data Model (Context, Data, Extractions)
- **Overview**: [Core Concepts](architecture/concepts.md)
- **Extraction**: [Extraction API Reference](api/extraction.md)
- **Transformation**: [Transformation API Reference](api/transformation.md)
- **Usage**: [Basic Pipeline Example](guides/basic-pipeline.md)

#### Prompt Management
- **Overview**: [Getting Started](guides/getting-started.md)
- **API Details**: [Prompts API Reference](api/prompts.md)
- **Guide**: [Prompt Management Guide](guides/prompts.md)

#### Database & State
- **Registry**: [Registry API Reference](api/registry.md)
- **State Tracking**: [State API Reference](api/state.md)
- **Overview**: [Core Concepts](architecture/concepts.md)
- **Setup**: [Getting Started](guides/getting-started.md)

#### LLM Provider
- **API Details**: [LLM Provider API Reference](api/llm.md)
- **Implementation**: Gemini provider included, abstract LLMProvider for custom implementations

### By Concept

#### Declarative Configuration
- [Core Concepts](architecture/concepts.md)
- [Design Patterns](architecture/patterns.md) - Class-level config via `__init_subclass__`
- [Basic Pipeline Example](guides/basic-pipeline.md)

#### Strategy Pattern
- [Architecture Overview](architecture/overview.md)
- [Strategy API Reference](api/strategy.md)
- [Multi-Strategy Guide](guides/multi-strategy.md)

#### Three-Tier Data Model
- [Core Concepts](architecture/concepts.md)
- [Basic Pipeline Example](guides/basic-pipeline.md)
- [Extraction API Reference](api/extraction.md)
- [Transformation API Reference](api/transformation.md)

#### Two-Phase Write Pattern
- [Design Patterns](architecture/patterns.md)
- [Architecture Overview](architecture/overview.md)
- [Registry API Reference](api/registry.md)

#### Read-Only Session Pattern
- [Design Patterns](architecture/patterns.md)
- [Registry API Reference](api/registry.md)

#### Caching & State Tracking
- [Core Concepts](architecture/concepts.md)
- [State API Reference](api/state.md)
- [Basic Pipeline Example](guides/basic-pipeline.md)

#### LLM Integration
- [LLM Provider API Reference](api/llm.md)
- [Getting Started](guides/getting-started.md)
- [API Reference Index](api/index.md) - event system: `InMemoryEventHandler`, `CompositeEmitter` for observability

## Complete Table of Contents

### Architecture Documentation

```
docs/architecture/
├── overview.md           # High-level system design
├── concepts.md           # Core concepts and principles
├── patterns.md           # Design patterns and techniques
├── limitations.md        # Known limitations and workarounds
└── diagrams/
    ├── c4-context.mmd     # System context diagram
    ├── c4-container.mmd   # Container architecture
    └── c4-component.mmd   # Component details
```

### API Reference

```
docs/api/
├── index.md              # API reference overview and imports
├── pipeline.md           # PipelineConfig and orchestration
├── step.md               # LLMStep and step definitions
├── strategy.md           # Strategy pattern classes
├── extraction.md         # Data extraction system
├── transformation.md     # Data transformation system
├── llm.md                # LLM provider system
├── prompts.md            # Prompt management
├── state.md              # State tracking and caching
└── registry.md           # Database registry
```

### Usage Guides

```
docs/guides/
├── getting-started.md    # Installation and first pipeline
├── basic-pipeline.md     # Complete working example
├── multi-strategy.md     # Strategy selection example
└── prompts.md            # Prompt management guide
```

## Key Features Overview

### Declarative Pipeline Configuration
Define pipelines as Python classes with automatic configuration validation and step discovery.

**Learn more**: [Getting Started](guides/getting-started.md), [Design Patterns](architecture/patterns.md)

### Strategy Pattern for Context-Dependent Execution
Route execution based on runtime context with multiple strategies competing to handle steps.

**Learn more**: [Multi-Strategy Guide](guides/multi-strategy.md), [Strategy API Reference](api/strategy.md)

### Automatic State Tracking & Caching
Cache LLM results based on input hash and prompt version for efficiency and reproducibility.

**Learn more**: [State API Reference](api/state.md), [Core Concepts](architecture/concepts.md)

### Three-Tier Data Model
Separate concerns: context (runtime decisions), data (transformations), extractions (database records).

**Learn more**: [Core Concepts](architecture/concepts.md), [Basic Pipeline Example](guides/basic-pipeline.md)

### Foreign Key Dependency Enforcement
Automatic validation of FK ordering to ensure dependent tables are created in correct order.

**Learn more**: [Registry API Reference](api/registry.md)

### Two-Phase Write Pattern
Database writes during execution (flush for FK IDs) finalized at save (commit and track).

**Learn more**: [Design Patterns](architecture/patterns.md), [Registry API Reference](api/registry.md)

### Read-Only Session Pattern
Prevent accidental writes during step execution with read-only session wrapper.

**Learn more**: [Design Patterns](architecture/patterns.md)

## Troubleshooting

### Common Issues

**I'm getting FK constraint errors**: Check [Registry API Reference](api/registry.md) for FK ordering requirements.

**My extraction isn't finding methods**: Review [Extraction API Reference](api/extraction.md) for method detection priority.

**Caching isn't working as expected**: See [State API Reference](api/state.md) for cache key construction.

**Prompts aren't loading**: Check [Prompt Management Guide](guides/prompts.md) for YAML structure and sync process.

**See also**: [Known Limitations](architecture/limitations.md)

## API Quick Reference

### Most Common Imports

```python
# Core pipeline execution
from llm_pipeline import PipelineConfig, LLMStep, step_definition

# Data handling
from llm_pipeline import PipelineContext, PipelineExtraction, PipelineTransformation

# Strategy pattern
from llm_pipeline import PipelineStrategy, PipelineStrategies

# Database
from llm_pipeline import PipelineDatabaseRegistry, ReadOnlySession

# Events (observability)
from llm_pipeline import InMemoryEventHandler, CompositeEmitter, LoggingEventHandler
from llm_pipeline.events import PipelineStarted, LLMCallStarting  # concrete events

# Prompts
from llm_pipeline.prompts import PromptService, sync_prompts

# LLM Provider (optional)
from llm_pipeline.llm import LLMProvider
from llm_pipeline.llm.gemini import GeminiProvider
```

**Complete import reference**: [API Reference Index](api/index.md)

## Document Relationships Map

```
Getting Started (entry point)
    ↓
    ├─→ Basic Pipeline Example (practical guide)
    │      ├─→ Architecture Overview (conceptual)
    │      ├─→ Core Concepts (terminology)
    │      └─→ API References (detailed)
    │
    ├─→ Multi-Strategy Guide (advanced example)
    │      └─→ Strategy API Reference
    │
    ├─→ Prompt Management Guide (prompt details)
    │      └─→ Prompts API Reference
    │
    └─→ Architecture Overview (conceptual)
           ├─→ Core Concepts
           ├─→ Design Patterns
           ├─→ C4 Diagrams (visual)
           └─→ Known Limitations
```

## Contributing & Feedback

For issues, questions, or improvements to the documentation, please see the project repository.

## Version Information

**Framework Version**: 0.1.0
**Documentation Last Updated**: 2026-02
**Python Version**: 3.11+

## License

MIT License - See project repository for details.
