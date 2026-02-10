# Getting Started with llm-pipeline

## What You'll Learn

By the end of this guide, you'll be able to:
- Install and configure llm-pipeline
- Set up automatic SQLite database for development
- Configure production database connections
- Create your first working pipeline
- Execute pipeline steps with LLM calls
- Save and query results from the database

**Time Estimate**: 15-20 minutes
**Prerequisites**: Python 3.11+, basic understanding of Pydantic and SQLAlchemy
**Final Result**: A working text classification pipeline with database persistence

## Installation

### Basic Installation

Install llm-pipeline with pip:

```bash
pip install llm-pipeline
```

This installs core dependencies:
- `pydantic>=2.0` - Data validation
- `sqlmodel>=0.0.14` - Database models
- `sqlalchemy>=2.0` - Database operations
- `pyyaml>=6.0` - Prompt file parsing

### Optional: Gemini Provider

To use Google's Gemini LLM provider:

```bash
pip install llm-pipeline[gemini]
```

This adds `google-generativeai>=0.3.0` for Gemini API integration.

### Development Tools

For running tests and development:

```bash
pip install llm-pipeline[dev]
```

Includes `pytest>=7.0` and `pytest-cov>=4.0`.

## Quick Start: Development Mode

llm-pipeline provides automatic SQLite database initialization for rapid prototyping. No database setup required.

### Step 1: Configure API Access

Set your Gemini API key as an environment variable:

```bash
export GEMINI_API_KEY="your-api-key-here"
```

Or set it in your code:

```python
import os
os.environ["GEMINI_API_KEY"] = "your-api-key-here"
```

### Step 2: Import Core Components

```python
from llm_pipeline import (
    PipelineConfig,
    PipelineStrategy,
    PipelineStrategies,
    LLMStep,
    LLMResultMixin,
    step_definition,
    PipelineDatabaseRegistry,
    PipelineExtraction,
)
from llm_pipeline.llm import LLMProvider
from llm_pipeline.llm.gemini import GeminiProvider
from pydantic import BaseModel, Field
from sqlmodel import SQLModel, Field as SQLField
from typing import List, Dict, Any, Optional
```

### Step 3: Define Your Domain Models

Create SQLModel classes for database storage:

```python
class Category(SQLModel, table=True):
    """Database model for text categories."""
    __tablename__ = "categories"

    id: Optional[int] = SQLField(default=None, primary_key=True)
    name: str = SQLField(index=True)
    description: Optional[str] = None

class ClassifiedText(SQLModel, table=True):
    """Database model for classified text entries."""
    __tablename__ = "classified_texts"

    id: Optional[int] = SQLField(default=None, primary_key=True)
    text: str
    category_id: int = SQLField(foreign_key="categories.id")
    confidence: float
```

### Step 4: Create Database Registry

Register your models with FK dependency order:

```python
class TextClassifierRegistry(
    PipelineDatabaseRegistry,
    models=[
        Category,         # No dependencies - must come first
        ClassifiedText,   # Depends on Category
    ]
):
    """Registry defines database models managed by this pipeline."""
    pass
```

The framework validates FK dependencies and ensures extraction order is correct.

### Step 5: Define Instruction Models

Create Pydantic models for LLM structured output:

```python
class CategoryInstructions(BaseModel, LLMResultMixin):
    """LLM output: identified category."""
    category_name: str = Field(description="Name of the category")
    confidence: float = Field(description="Confidence score 0-1")
    reasoning: str = Field(description="Why this category was chosen")

    # Required: example for validation
    example = {
        "category_name": "Technology",
        "confidence": 0.95,
        "reasoning": "Text discusses software development"
    }
```

### Step 6: Create Extraction Classes

Map LLM output to database models:

```python
class CategoryExtraction(PipelineExtraction, extraction_type=Category):
    """Extracts Category instances from LLM instructions."""

    def default(
        self,
        instructions_list: List[CategoryInstructions],
        context: Dict[str, Any]
    ) -> List[Category]:
        """Convert LLM output to Category models."""
        categories = []
        for inst in instructions_list:
            category = Category(
                name=inst.category_name,
                description=inst.reasoning
            )
            categories.append(category)
        return categories
```

### Step 7: Define Pipeline Steps

Create steps that call the LLM:

```python
@step_definition
class CategoryDetectionStep(
    LLMStep,
    instruction_class=CategoryInstructions,
    extraction_class=CategoryExtraction
):
    """Detect text category using LLM."""

    def prepare_calls(self, pipeline: PipelineConfig) -> List[Dict[str, Any]]:
        """Prepare LLM calls with input text."""
        text = pipeline.context.get("input_text", "")
        return [{
            "system_instruction": (
                "You are a text classifier. Analyze the text and determine "
                "its category from: Technology, Business, Science, Arts."
            ),
            "prompt": f"Classify this text:\n\n{text}",
        }]

    def process_instructions(
        self,
        pipeline: PipelineConfig,
        instructions_list: List[CategoryInstructions]
    ) -> None:
        """Store results in pipeline context."""
        if instructions_list:
            inst = instructions_list[0]
            pipeline.context["detected_category"] = inst.category_name
            pipeline.context["confidence"] = inst.confidence
```

### Step 8: Create Pipeline Strategy

Define execution flow:

```python
class SimpleClassifierStrategy(PipelineStrategy):
    """Strategy with single classification step."""

    def can_handle(self, context: Dict[str, Any]) -> bool:
        """This strategy handles all inputs."""
        return True

    def get_steps(self) -> List:
        """Return step definitions."""
        return [
            CategoryDetectionStep.create_definition()
        ]

class TextClassifierStrategies(PipelineStrategies):
    """Container for all strategies."""
    strategies = [SimpleClassifierStrategy()]
```

### Step 9: Configure Pipeline

Use declarative configuration:

```python
class TextClassifierPipeline(
    PipelineConfig,
    registry=TextClassifierRegistry,
    strategies=TextClassifierStrategies
):
    """Text classification pipeline."""
    pass
```

### Step 10: Execute Pipeline

Run the pipeline with auto-SQLite:

```python
# Initialize provider
provider = GeminiProvider(model_name="gemini-2.0-flash-lite")

# Create pipeline instance (auto-initializes SQLite database)
pipeline = TextClassifierPipeline(provider=provider)

# Set input
input_text = "Python is a versatile programming language used in web development and data science."
pipeline.context["input_text"] = input_text

# Execute all steps
pipeline.execute()

# Save to database
pipeline.save()

# Check results
print(f"Category: {pipeline.context['detected_category']}")
print(f"Confidence: {pipeline.context['confidence']}")
print(f"Extracted models: {len(pipeline.extractions[Category])} categories")
```

**Output:**
```
Auto-created SQLite database at .llm_pipeline/pipeline.db
Category: Technology
Confidence: 0.95
Extracted models: 1 categories
```

The database file is automatically created at `.llm_pipeline/pipeline.db` in your current directory.

### Step 11: Query Saved Data

Access saved results:

```python
from llm_pipeline.db import get_session

# Get database session
session = get_session()

# Query categories
categories = session.query(Category).all()
for cat in categories:
    print(f"Category: {cat.name} - {cat.description}")

# Query classified texts
texts = session.query(ClassifiedText).all()
for text in texts:
    print(f"Text: {text.text[:50]}... (confidence: {text.confidence})")

session.close()
```

## Database Configuration

### Development: Auto-SQLite

The framework automatically creates a SQLite database when no engine is provided.

**Default location**: `.llm_pipeline/pipeline.db` in current directory

**Custom location via environment variable**:
```bash
export LLM_PIPELINE_DB="/path/to/your/database.db"
```

**Programmatic initialization**:
```python
from llm_pipeline.db import init_pipeline_db

# Create auto-SQLite database
engine = init_pipeline_db()
```

This creates three framework tables:
- `pipeline_step_state` - Caching and execution history
- `pipeline_run_instance` - Traceability linking for extractions
- `prompts` - YAML prompt storage

Your domain models (from the registry) must be created separately:
```python
from sqlmodel import SQLModel

# Create your domain tables
SQLModel.metadata.create_all(engine, tables=[
    Category.__table__,
    ClassifiedText.__table__,
])
```

### Production: Explicit Database Setup

For production, provide your own engine and session:

```python
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel
from llm_pipeline.db import init_pipeline_db

# Create engine
engine = create_engine(
    "postgresql://user:pass@localhost/dbname",
    echo=False
)

# Initialize framework tables
init_pipeline_db(engine)

# Create domain tables
SQLModel.metadata.create_all(engine, tables=[
    Category.__table__,
    ClassifiedText.__table__,
])

# Create session
session = Session(engine)

# Pass session to pipeline
pipeline = TextClassifierPipeline(
    provider=provider,
    session=session
)
```

**Important**: The pipeline wraps your session in `ReadOnlySession` during execution to prevent accidental writes. Writes only occur in:
1. `extract_data()` - Calls `session.add()` + `session.flush()` to assign FK IDs
2. `save()` - Calls `session.commit()` to finalize transaction

This is the **two-phase write pattern**:
- **Phase 1 (execution)**: Flush assigns database IDs for FK resolution
- **Phase 2 (save)**: Commit finalizes transaction + tracks run instances

## Provider Configuration

### GeminiProvider

Basic configuration:

```python
from llm_pipeline.llm.gemini import GeminiProvider

provider = GeminiProvider(
    api_key="your-api-key",  # Optional: uses GEMINI_API_KEY env var
    model_name="gemini-2.0-flash-lite"
)
```

Advanced configuration:

```python
from llm_pipeline.llm.gemini import GeminiProvider
from llm_pipeline.llm.rate_limiter import RateLimiter

# Custom rate limiting
rate_limiter = RateLimiter(
    max_requests=15,
    time_window_seconds=60
)

provider = GeminiProvider(
    model_name="gemini-2.0-flash-exp",
    rate_limiter=rate_limiter
)
```

### Custom Provider

Implement the `LLMProvider` abstract class:

```python
from llm_pipeline.llm.provider import LLMProvider
from pydantic import BaseModel
from typing import Dict, Any, Type, Optional, List

class MyCustomProvider(LLMProvider):
    """Custom LLM provider implementation."""

    def call_structured(
        self,
        prompt: str,
        system_instruction: str,
        result_class: Type[BaseModel],
        max_retries: int = 3,
        not_found_indicators: Optional[List[str]] = None,
        strict_types: bool = True,
        array_validation: Optional[Any] = None,
        validation_context: Optional[Any] = None,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """Call your LLM API and return validated JSON."""
        # Your implementation here
        ...
```

## Common Patterns

### Accessing Pipeline Data

llm-pipeline uses a three-tier data model:

1. **Context**: Strategy selection and metadata
```python
pipeline.context["table_type"] = "lane_based"
pipeline.context["detected_category"] = "Technology"
```

2. **Data**: Input data and transformation results
```python
pipeline.data["TableDetectionStep"] = dataframe
pipeline.data["SanitizedStep"] = cleaned_text
```

3. **Extractions**: Database model instances
```python
categories = pipeline.extractions[Category]
texts = pipeline.extractions[ClassifiedText]
```

### Caching

Caching is controlled per-step:

```python
@step_definition
class ExpensiveStep(LLMStep, ...):
    use_cache = True  # Default: False
```

Cache key includes:
- Input hash (from `prepare_calls()`)
- Prompt version (from YAML or code)

### Error Handling

LLM calls include automatic retry logic:

```python
def prepare_calls(self, pipeline: PipelineConfig) -> List[Dict[str, Any]]:
    return [{
        "prompt": "...",
        "system_instruction": "...",
        "max_retries": 5,  # Retry up to 5 times
        "not_found_indicators": ["not found", "no data"],  # Return None if LLM says this
    }]
```

## Next Steps

Now that you have a working pipeline, explore:

1. **[Basic Pipeline Guide](./basic-pipeline.md)** - Complete working example with multiple steps
2. **[Multi-Strategy Guide](./multi-strategy.md)** - Context-based strategy selection
3. **[Prompt Management](./prompts.md)** - YAML prompt configuration and versioning
4. **[API Reference](../api/index.md)** - Complete API documentation
5. **[Architecture Overview](../architecture/overview.md)** - Deep dive into framework design

## Troubleshooting

### "google-generativeai not installed"

Install the Gemini optional dependency:
```bash
pip install llm-pipeline[gemini]
```

### "GEMINI_API_KEY not set"

Set the environment variable or pass directly:
```python
provider = GeminiProvider(api_key="your-key")
```

### "ReadOnlySession cannot execute writes"

This is expected during execution. Writes only occur in:
- `extract_data()` - Assigns FK IDs via flush
- `save()` - Commits transaction

If you need manual writes, use `pipeline._real_session`.

### Database file not created

Check that `.llm_pipeline` directory is writable:
```bash
ls -la .llm_pipeline/
```

Set custom location:
```bash
export LLM_PIPELINE_DB="/tmp/pipeline.db"
```

### FK dependency errors

Ensure registry lists models in dependency order:
```python
class MyRegistry(
    PipelineDatabaseRegistry,
    models=[
        ParentModel,  # No FK dependencies first
        ChildModel,   # Depends on ParentModel second
    ]
):
    pass
```

## Summary

You've learned how to:
- ✓ Install llm-pipeline with optional dependencies
- ✓ Use auto-SQLite for rapid development
- ✓ Configure production databases explicitly
- ✓ Create domain models, registries, and extractions
- ✓ Define steps and strategies
- ✓ Execute pipelines with LLM calls
- ✓ Save and query results from database
- ✓ Configure GeminiProvider with custom settings

The framework handles session management, caching, FK validation, and state tracking automatically. Focus on your domain logic, not infrastructure.
