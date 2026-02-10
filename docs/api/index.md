# API Reference

Comprehensive API documentation for the llm-pipeline framework.

## Installation

### Basic Installation

Install the core framework with required dependencies:

```bash
pip install llm-pipeline
```

### Optional Dependencies

#### Gemini Provider Support

Add Google Gemini LLM provider integration:

```bash
pip install llm-pipeline[gemini]
```

#### Development Tools

Install testing and development dependencies:

```bash
pip install llm-pipeline[dev]
```

#### All Features

Install all optional dependencies:

```bash
pip install llm-pipeline[gemini,dev]
```

## Requirements

### Python Version

- **Python 3.11+** required

### Core Dependencies

The framework requires these core libraries:

- **pydantic >= 2.0** - Data validation and settings management
- **sqlmodel >= 0.0.14** - SQL database integration with Pydantic models
- **sqlalchemy >= 2.0** - SQL toolkit and ORM
- **pyyaml >= 6.0** - YAML parsing for prompt management

### Optional Dependencies

- **google-generativeai >= 0.3.0** - Gemini LLM provider (with `[gemini]` extra)
- **pytest >= 7.0** - Testing framework (with `[dev]` extra)
- **pytest-cov >= 4.0** - Code coverage (with `[dev]` extra)

## Top-Level Imports

The main `llm_pipeline` package exports the following core components:

### Core Classes

```python
from llm_pipeline import (
    PipelineConfig,       # Main pipeline orchestration class
    LLMStep,              # Abstract base for step definitions
    LLMResultMixin,       # Mixin for instruction result models
    step_definition,      # Decorator for step factory registration
)
```

### Strategy Pattern

```python
from llm_pipeline import (
    PipelineStrategy,     # Abstract base for execution strategies
    PipelineStrategies,   # Strategy registry and selection
    StepDefinition,       # Step metadata configuration
)
```

### Data Handling

```python
from llm_pipeline import (
    PipelineContext,            # Runtime context for strategy selection
    PipelineExtraction,         # Database extraction from LLM results
    PipelineTransformation,     # Data transformation between steps
    PipelineDatabaseRegistry,   # Registry with FK ordering
)
```

### State Management

```python
from llm_pipeline import (
    PipelineStepState,      # Step execution state and caching
    PipelineRunInstance,    # Pipeline run tracking and traceability
)
```

### Validation Types

```python
from llm_pipeline import (
    ArrayValidationConfig,  # Configuration for array response validation
    ValidationContext,      # Context for validation operations
)
```

### Database Utilities

```python
from llm_pipeline import (
    init_pipeline_db,   # Initialize framework database tables
    ReadOnlySession,    # Read-only session wrapper
)
```

### LLM Provider System

```python
from llm_pipeline.llm import (
    LLMProvider,            # Abstract LLM provider base
    RateLimiter,            # API rate limiting utility
    flatten_schema,         # Schema flattening helper
    format_schema_for_llm,  # Schema formatting for LLM consumption
)

# Optional: Gemini provider (requires [gemini] extra)
from llm_pipeline.llm.gemini import GeminiProvider
```

### Prompt Management

```python
from llm_pipeline.prompts import (
    PromptService,                  # Prompt retrieval and management
    VariableResolver,               # Variable extraction and resolution
    sync_prompts,                   # Sync YAML prompts to database
    load_all_prompts,               # Load all YAML prompts
    get_prompts_dir,                # Get prompts directory path
    extract_variables_from_content, # Extract template variables
)
```

### Database Models

```python
from llm_pipeline.db import (
    Prompt,          # Prompt storage model
    get_engine,      # Get current database engine
    get_session,     # Get new database session
    get_default_db_path,  # Get default SQLite path
)
```

## Module Reference

Detailed API documentation organized by module:

- **[Pipeline](pipeline.md)** - `PipelineConfig`, pipeline orchestration, and execution
- **[Step](step.md)** - `LLMStep`, `LLMResultMixin`, and step definition system
- **[Strategy](strategy.md)** - `PipelineStrategy`, `PipelineStrategies`, and strategy selection
- **[Extraction](extraction.md)** - `PipelineExtraction` and database extraction patterns
- **[Transformation](transformation.md)** - `PipelineTransformation` and data transformation
- **[LLM Provider](llm.md)** - `LLMProvider`, `GeminiProvider`, and LLM integration
- **[Prompts](prompts.md)** - `PromptService`, prompt loading, and variable resolution
- **[State](state.md)** - `PipelineStepState`, `PipelineRunInstance`, and execution tracking
- **[Registry](registry.md)** - `PipelineDatabaseRegistry` and FK ordering

## Package Structure

```
llm_pipeline/
├── __init__.py           # Top-level exports
├── pipeline.py           # PipelineConfig orchestration
├── step.py               # LLMStep and step definitions
├── strategy.py           # Strategy pattern implementation
├── context.py            # PipelineContext for runtime data
├── extraction.py         # Database extraction logic
├── transformation.py     # Data transformation logic
├── registry.py           # Database registry with FK ordering
├── state.py              # State tracking models
├── types.py              # Validation and type definitions
├── db/                   # Database initialization
│   ├── __init__.py       # DB utilities
│   └── prompt.py         # Prompt model
├── llm/                  # LLM provider system
│   ├── __init__.py       # Provider exports
│   ├── provider.py       # Abstract LLMProvider
│   ├── gemini.py         # GeminiProvider implementation
│   ├── rate_limiter.py   # Rate limiting
│   ├── schema.py         # Schema utilities
│   └── executor.py       # LLM execution logic
├── prompts/              # Prompt management
│   ├── __init__.py       # Prompt exports
│   ├── service.py        # PromptService
│   ├── loader.py         # YAML loading and syncing
│   └── variables.py      # Variable resolution
└── session/              # Session management
    ├── __init__.py       # Session exports
    └── readonly.py       # ReadOnlySession wrapper
```

## Usage Pattern

Typical usage flow:

1. **Define domain models** using Pydantic/SQLModel
2. **Create registry** with `PipelineDatabaseRegistry` (FK-ordered tables)
3. **Define instruction classes** extending `LLMResultMixin`
4. **Define context classes** extending `PipelineContext`
5. **Define extraction classes** extending `PipelineExtraction`
6. **Create step classes** extending `LLMStep` with `@step_definition`
7. **Create strategy** extending `PipelineStrategy`
8. **Build pipeline** with `PipelineConfig`
9. **Execute** and **save** results to database

See [Getting Started Guide](../guides/getting-started.md) for detailed walkthrough.

## Version

Current version: **0.1.0**

## License

MIT License
