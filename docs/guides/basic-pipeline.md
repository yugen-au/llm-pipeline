# Basic Pipeline Example

## What You'll Learn

By the end of this guide, you'll be able to:
- Define a complete LLM pipeline from scratch
- Create domain models with proper foreign key relationships
- Build instruction classes with validation
- Implement pipeline steps that transform data
- Execute the pipeline with automatic caching
- Persist results to a database

## Prerequisites

- Python 3.11+
- Basic understanding of Pydantic models
- Familiarity with SQLAlchemy/SQLModel
- llm-pipeline installed: `pip install llm-pipeline`
- pydantic-ai is included as a core dependency

## Time Estimate

30 minutes for complete walkthrough

## Final Result

A working document classification pipeline that:
1. Detects document type from content
2. Extracts structured metadata
3. Stores results in a database with full audit trail

---

## Building a Document Classifier

We'll build a document classification pipeline that analyzes text documents and extracts structured information. This example demonstrates all core framework patterns.

### Step 1: Define Domain Models

First, create the database models your pipeline will manage. The order matters - models must be listed in foreign key dependency order.

```python
from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional

class Project(SQLModel, table=True):
    """Project that owns documents."""
    __tablename__ = "projects"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Document(SQLModel, table=True):
    """Document being classified."""
    __tablename__ = "documents"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id", index=True)
    title: str
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class DocumentMetadata(SQLModel, table=True):
    """Extracted metadata for a document."""
    __tablename__ = "document_metadata"

    id: Optional[int] = Field(default=None, primary_key=True)
    document_id: int = Field(foreign_key="documents.id", index=True)
    document_type: str = Field(index=True)
    language: str
    topic: str
    confidence: float = Field(ge=0.0, le=1.0)
```

**Key Points:**
- Use `SQLModel` with `table=True` for ORM models
- Declare foreign keys explicitly (`foreign_key="table.column"`)
- Add indexes on commonly queried fields
- Optional primary keys default to auto-increment

### Step 2: Create the Database Registry

The registry declares which models your pipeline manages and enforces foreign key ordering.

```python
from llm_pipeline import PipelineDatabaseRegistry

class DocumentClassifierRegistry(
    PipelineDatabaseRegistry,
    models=[
        Project,           # No dependencies - goes first
        Document,          # Depends on Project
        DocumentMetadata,  # Depends on Document
    ]
):
    """
    Registry for DocumentClassifierPipeline.

    Models must be in FK dependency order. Framework validates this
    at class definition time.
    """
```

**Common Mistakes:**
- Wrong order: Putting `Document` before `Project` would fail validation
- Missing models: If a step extracts a model not in the registry, you'll get a runtime error

### Step 3: Define Instruction Classes

Instruction classes define the structured output your LLM steps return. They must inherit from `LLMResultMixin`.

```python
from typing import ClassVar
from pydantic import Field
from llm_pipeline import LLMResultMixin

class DocumentTypeInstructions(LLMResultMixin):
    """
    Instructions for document type detection.

    Inherits confidence_score and notes from LLMResultMixin.
    """
    document_type: str = Field(
        description="Detected document type (report, article, email, memo)"
    )
    language: str = Field(
        description="Primary language code (en, es, fr, etc.)"
    )

    # Required: example dict for validation
    example: ClassVar[dict] = {
        "document_type": "report",
        "language": "en",
        "notes": "Technical report with structured sections",
        "confidence_score": 0.95
    }
```

**Why the example?** The framework validates your instruction class at definition time by instantiating it with the example dict. This catches schema errors early.

```python
class MetadataExtractionInstructions(LLMResultMixin):
    """Instructions for metadata extraction."""
    topic: str = Field(
        description="Main topic or subject"
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="Key terms and concepts"
    )

    example: ClassVar[dict] = {
        "topic": "Machine Learning Best Practices",
        "keywords": ["neural networks", "training", "validation"],
        "notes": "Focus on practical implementation",
        "confidence_score": 0.90
    }
```

### Step 4: Define Context Classes

Context classes store step results in the pipeline context. They must inherit from `PipelineContext`.

```python
from llm_pipeline import PipelineContext

class DocumentTypeContext(PipelineContext):
    """Context produced by document type detection step."""
    document_type: str = Field(description="Detected document type")
    language: str = Field(description="Detected language")

class MetadataExtractionContext(PipelineContext):
    """Context produced by metadata extraction step."""
    topic: str = Field(description="Extracted topic")
    keywords: list[str] = Field(description="Extracted keywords")
```

**Instructions vs Context:**
- Instructions: Full LLM response (includes confidence, notes)
- Context: Clean extracted values for use in later steps

### Step 5: Create Extraction Classes

Extraction classes convert instruction data into database models. They use smart method detection.

```python
from llm_pipeline import PipelineExtraction

class DocumentMetadataExtraction(PipelineExtraction):
    """
    Extract DocumentMetadata instances from metadata extraction step.

    Uses default() method - applies to all strategies.
    """

    def default(
        self,
        instructions: MetadataExtractionInstructions,
        index: int
    ) -> DocumentMetadata:
        """
        Create DocumentMetadata from instructions.

        Args:
            instructions: LLM output from metadata extraction step
            index: Call index (0 for single-call steps)

        Returns:
            DocumentMetadata instance with assigned FK
        """
        # Access context from earlier steps
        doc_type = self.pipeline.context.get('document_type', 'unknown')
        language = self.pipeline.context.get('language', 'en')

        # Get document_id from pipeline context
        # (Set during pipeline initialization)
        document_id = self.pipeline.context['document_id']

        return DocumentMetadata(
            document_id=document_id,
            document_type=doc_type,
            language=language,
            topic=instructions.topic,
            confidence=instructions.confidence_score
        )
```

**Method Detection Priority:**
1. `default()` - Used for all strategies
2. `{strategy_name}()` - Strategy-specific (e.g., `report_strategy()`)
3. Single unnamed method - Auto-detected
4. Error if none found

**Two-Phase Write Pattern:**
The framework calls `session.add()` and `session.flush()` during extraction. This assigns database IDs immediately, allowing later extractions to reference them via foreign keys. Final `commit()` happens in `save()`.

### Step 6: Implement Pipeline Steps

Steps are the core logic units. They must extend `LLMStep` and use the `@step_definition` decorator.

```python
from typing import List
from llm_pipeline import LLMStep, step_definition
from llm_pipeline.types import StepCallParams

@step_definition(
    instructions=DocumentTypeInstructions,
    context=DocumentTypeContext,
)
class DocumentTypeStep(LLMStep):
    """
    Step 1: Detect document type and language.

    Makes a single LLM call to classify the document.
    """

    def prepare_calls(self) -> List[StepCallParams]:
        """
        Prepare LLM call parameters.

        Returns list of dicts, one per LLM call to make.
        """
        # Access pipeline data (input or previous transformations)
        content = self.pipeline.get_current_data()

        # Create variable instance for prompt template
        variables = {
            "content": content[:1000],  # First 1000 chars
            "title": self.pipeline.context.get('title', 'Untitled')
        }

        return [{"variables": variables}]

    def process_instructions(
        self,
        instructions: List[DocumentTypeInstructions]
    ) -> DocumentTypeContext:
        """
        Convert instructions to context.

        Args:
            instructions: List of LLM responses (one per prepare_calls entry)

        Returns:
            Context object with extracted values
        """
        # Single call -> single instruction
        instruction = instructions[0]

        return DocumentTypeContext(
            document_type=instruction.document_type,
            language=instruction.language
        )

    def log_instructions(
        self,
        instructions: List[DocumentTypeInstructions]
    ) -> None:
        """Optional: Log results for debugging."""
        instruction = instructions[0]
        print(f"Detected: {instruction.document_type} ({instruction.language})")
```

**Step Lifecycle:**
1. Framework calls `prepare_calls()` to get LLM call parameters
2. Framework executes LLM calls via pydantic-ai agents
3. Framework validates responses against instruction schema
4. Framework calls `process_instructions()` to create context
5. Framework stores context in `pipeline.context[step_name]`
6. Framework calls `log_instructions()` for debugging

```python
@step_definition(
    instructions=MetadataExtractionInstructions,
    context=MetadataExtractionContext,
    default_extractions=[DocumentMetadataExtraction],
)
class MetadataExtractionStep(LLMStep):
    """
    Step 2: Extract structured metadata.

    Uses document type from step 1 context.
    Defines extraction to persist to database.
    """

    def prepare_calls(self) -> List[StepCallParams]:
        """Prepare metadata extraction call."""
        content = self.pipeline.get_current_data()
        doc_type = self.pipeline.context.get('document_type', 'unknown')

        variables = {
            "content": content,
            "document_type": doc_type,
        }

        return [{"variables": variables}]

    def process_instructions(
        self,
        instructions: List[MetadataExtractionInstructions]
    ) -> MetadataExtractionContext:
        """Convert to context."""
        instruction = instructions[0]

        return MetadataExtractionContext(
            topic=instruction.topic,
            keywords=instruction.keywords
        )

    def log_instructions(
        self,
        instructions: List[MetadataExtractionInstructions]
    ) -> None:
        """Log extracted metadata."""
        instruction = instructions[0]
        print(f"Topic: {instruction.topic}")
        print(f"Keywords: {', '.join(instruction.keywords)}")
```

**Naming Convention Enforcement:**
- Step class: `{Name}Step`
- Instructions: `{Name}Instructions`
- Context: `{Name}Context`
- Transformation: `{Name}Transformation`

The framework validates these at class definition time.

### Step 7: Create Step Definition Factories

The `@step_definition` decorator auto-generates a `create_definition()` factory method.

```python
# Module-level factory functions
DocumentTypeDef = DocumentTypeStep.create_definition
MetadataExtractionDef = MetadataExtractionStep.create_definition
```

These factories create `StepDefinition` instances for use in strategies.

### Step 8: Define a Strategy

Strategies define which steps to execute and in what order. They can conditionally handle different scenarios.

```python
from llm_pipeline import PipelineStrategy, StepDefinition
from typing import List, Dict, Any

class DocumentClassificationStrategy(PipelineStrategy):
    """
    Default strategy for document classification.

    Applies to all document types.
    """

    def can_handle(self, context: Dict[str, Any]) -> bool:
        """
        Determine if this strategy should handle the current execution.

        Args:
            context: Pipeline context dict

        Returns:
            True if this strategy can handle
        """
        # This is the only strategy, so always return True
        return True

    def get_steps(self) -> List[StepDefinition]:
        """
        Define the step sequence.

        Returns:
            Ordered list of step definitions
        """
        return [
            DocumentTypeDef(),
            MetadataExtractionDef(),
        ]
```

**Strategy Selection:**
When multiple strategies exist, the framework:
1. Calls `can_handle(context)` on each strategy in order
2. Selects first strategy that returns `True`
3. Uses that strategy's steps for execution

### Step 9: Create Strategy Registry

```python
from llm_pipeline import PipelineStrategies

class DocumentClassifierStrategies(
    PipelineStrategies,
    strategies=[
        DocumentClassificationStrategy,
    ]
):
    """
    Strategies for DocumentClassifierPipeline.

    Strategies are tried in order during can_handle() checks.
    """
```

### Step 10: Define the Pipeline

Bring it all together in the pipeline configuration class.

```python
from llm_pipeline import PipelineConfig

class DocumentClassifierPipeline(
    PipelineConfig,
    registry=DocumentClassifierRegistry,
    strategies=DocumentClassifierStrategies
):
    """
    Pipeline for document classification and metadata extraction.

    Naming convention:
    - Class ends with 'Pipeline'
    - Registry: DocumentClassifierRegistry
    - Strategies: DocumentClassifierStrategies

    Framework validates naming at class definition time.
    """

    def sanitize(self, data: str) -> str:
        """
        Sanitize input data for LLM processing.

        Args:
            data: Raw input (document text)

        Returns:
            Sanitized string for LLM consumption
        """
        # Simple sanitization: trim whitespace, limit length
        sanitized = data.strip()
        if len(sanitized) > 10000:
            sanitized = sanitized[:10000] + "...[truncated]"
        return sanitized
```

**The `sanitize()` method:**
- Called once at pipeline initialization
- Converts input data to LLM-friendly format
- Stored in `pipeline._sanitized_data`
- Accessible via `pipeline.get_sanitized_data()`

---

## Executing the Pipeline

### Basic Execution

```python
# Create pipeline with pydantic-ai model string
pipeline = DocumentClassifierPipeline(model='google-gla:gemini-2.0-flash-lite')

# Sample document
document_text = """
# Q4 Sales Report

This report analyzes sales performance for Q4 2024.
Key findings include a 15% increase in revenue and
expansion into three new markets.
"""

# Execute pipeline
pipeline.execute(
    data=document_text,
    context={
        'document_id': 1,
        'title': 'Q4 Sales Report',
        'project_id': 1
    }
)

# Access results
print(f"Type: {pipeline.context['document_type']}")
print(f"Topic: {pipeline.context['topic']}")
print(f"Keywords: {pipeline.context['keywords']}")

# Get extracted database instances
metadata_list = pipeline.get_extractions(DocumentMetadata)
print(f"Extracted {len(metadata_list)} metadata records")
```

**Execution Flow:**
1. `sanitize()` processes input data
2. Strategy selection via `can_handle()`
3. For each step in strategy:
   - Call `prepare_calls()`
   - Execute LLM calls (with caching)
   - Validate responses
   - Call `process_instructions()`
   - Store context
   - Run extractions (if defined)
   - Apply transformations (if defined)
4. Return to caller

### Caching Behavior

The framework automatically caches LLM responses based on:
- Input hash (from sanitized data)
- Prompt version (from database)
- Step name

```python
# First execution - makes LLM calls
pipeline.execute(data=document_text, context={'document_id': 1})

# Second execution - uses cached responses
pipeline2 = DocumentClassifierPipeline(model='google-gla:gemini-2.0-flash-lite')
pipeline2.execute(data=document_text, context={'document_id': 1})
```

**Cache Key Formula:**
```
cache_key = hash(sanitized_data) + prompt_version + step_name
```

To disable caching:
```python
# In step's prepare_calls():
return [{"variables": variables, "use_cache": False}]
```

### Persisting to Database

Save results using the `save()` method.

```python
from sqlmodel import Session, create_engine

# Setup database
engine = create_engine("sqlite:///documents.db")
session = Session(engine)

# Create tables
from llm_pipeline.db import init_pipeline_db
init_pipeline_db(engine)

# Execute pipeline
pipeline = DocumentClassifierPipeline(
    model='google-gla:gemini-2.0-flash-lite',
    session=session
)
pipeline.execute(data=document_text, context={'document_id': 1})

# Save to database
saved_instances = pipeline.save(
    session=session,
    tables=[DocumentMetadata]  # Only save specific tables
)

session.commit()
print(f"Saved {len(saved_instances)} instances")
```

**Two-Phase Write in Action:**

**Phase 1 (during execution):**
```python
# In DocumentMetadataExtraction.default()
metadata = DocumentMetadata(...)
# Framework does:
session.add(metadata)
session.flush()  # Assigns metadata.id
# Later extractions can now reference metadata.id
```

**Phase 2 (during save):**
```python
# In pipeline.save()
session.commit()  # Finalizes transaction
# Also creates PipelineRunInstance for traceability
```

### Working with Extractions

```python
# Get all extractions of a specific type
metadata_list = pipeline.get_extractions(DocumentMetadata)

# Extractions are already added to session
for metadata in metadata_list:
    print(f"ID: {metadata.id}")  # Has ID from flush()
    print(f"Topic: {metadata.topic}")
    print(f"Confidence: {metadata.confidence}")

# Save specific extraction types
pipeline.save(session=session, tables=[DocumentMetadata])

# Save all extractions
pipeline.save(session=session)
```

---

## Advanced Patterns

### Multi-Call Steps

Some steps need multiple LLM calls (e.g., analyzing each section separately).

```python
@step_definition(
    instructions=SectionAnalysisInstructions,
    context=SectionAnalysisContext,
)
class SectionAnalysisStep(LLMStep):
    """Analyze each document section separately."""

    def prepare_calls(self) -> List[StepCallParams]:
        """Create one call per section."""
        content = self.pipeline.get_current_data()
        sections = content.split('\n\n')  # Simple split

        return [
            {"variables": {"section": section, "index": i}}
            for i, section in enumerate(sections)
        ]

    def process_instructions(
        self,
        instructions: List[SectionAnalysisInstructions]
    ) -> SectionAnalysisContext:
        """Aggregate results from all sections."""
        all_topics = []
        for instruction in instructions:
            all_topics.extend(instruction.topics)

        return SectionAnalysisContext(
            section_count=len(instructions),
            all_topics=list(set(all_topics))
        )
```

### Accessing Previous Step Data

```python
def prepare_calls(self) -> List[StepCallParams]:
    # Access context from any previous step
    doc_type = self.pipeline.context.get('document_type')
    language = self.pipeline.context.get('language')

    # Access instruction objects (includes confidence, notes)
    type_instructions = self.pipeline.get_instructions('document_type')

    # Access raw/current/sanitized data
    raw_data = self.pipeline.get_raw_data()
    current_data = self.pipeline.get_current_data()
    sanitized_data = self.pipeline.get_sanitized_data()

    return [{"variables": {...}}]
```

### Custom Variable Resolvers

For complex prompt variable handling:

```python
from llm_pipeline.prompts import VariableResolver

class CustomVariableResolver(VariableResolver):
    """Custom resolver for document variables."""

    def resolve(self, variable_class, variables_dict):
        # Custom logic to transform variables
        if 'content' in variables_dict:
            # Apply custom formatting
            variables_dict['content'] = self.format_content(
                variables_dict['content']
            )
        return variable_class(**variables_dict)

# Use in pipeline
pipeline = DocumentClassifierPipeline(
    model='google-gla:gemini-2.0-flash-lite',
    variable_resolver=CustomVariableResolver()
)
```

---

## Troubleshooting

### Common Errors

**1. Naming Convention Violation**

```
ValueError: Pipeline class 'DocumentProcessor' must end with 'Pipeline' suffix.
```

**Fix:** Rename to `DocumentProcessorPipeline`

**2. Registry Order Error**

```
ValueError: Model 'Document' references 'Project' which appears later in registry
```

**Fix:** Reorder registry models (dependencies first):
```python
models=[Project, Document, DocumentMetadata]  # Correct order
```

**3. Missing Instruction Example**

```
ValueError: DocumentTypeInstructions.example must be a dict
```

**Fix:** Add class-level example:
```python
example: ClassVar[dict] = {"document_type": "report", ...}
```

**4. Strategy Not Found**

```
RuntimeError: No strategy can handle context: {...}
```

**Fix:** Ensure at least one strategy returns `True` from `can_handle()`:
```python
def can_handle(self, context):
    return True  # Default strategy
```

### Debugging Tips

**Enable logging:**
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

**Check step execution order:**
```python
# After execution
print(pipeline._executed_steps)
print(pipeline._step_order)
```

**Inspect cached states:**
```python
from llm_pipeline.state import PipelineStepState
from sqlmodel import select

states = session.exec(
    select(PipelineStepState)
    .where(PipelineStepState.run_id == pipeline.run_id)
).all()

for state in states:
    print(f"{state.step_name}: {state.status}")
```

---

## Summary

You've learned:
- How to define domain models in FK dependency order
- Creating instruction classes with validation
- Implementing pipeline steps with `prepare_calls()` and `process_instructions()`
- Building extraction classes using method detection
- Defining strategies with `can_handle()` logic
- Executing pipelines with automatic caching
- Persisting results using the two-phase write pattern

## Next Steps

- [Multi-Strategy Pipeline Example](./multi-strategy.md) - Learn conditional strategy selection
- [Prompt Management Guide](./prompts.md) - Master YAML-based prompt configuration
- [API Reference: Pipeline](../api/pipeline.md) - Deep dive into PipelineConfig
- [API Reference: Step](../api/step.md) - Complete LLMStep documentation

## Complete Working Example

Full source code: [examples/document_classifier/](../../examples/document_classifier/)

```bash
# Install dependencies
pip install llm-pipeline

# Run example
cd examples/document_classifier
python run.py
```

The example includes:
- Complete pipeline implementation
- Sample documents
- Database schema
- Prompt templates
- Test suite
