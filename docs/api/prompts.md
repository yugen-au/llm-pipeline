# Prompt System API Reference

## Overview

The prompt system manages LLM prompts through YAML-based storage synced to a database. It provides version-controlled, database-backed prompt templates with variable extraction, formatting, and retrieval services.

**Module:** `llm_pipeline.prompts`

**Key Components:**
- `Prompt` - Database model for prompt storage
- `PromptService` - Service for retrieving and formatting prompts
- `sync_prompts()` - YAML-to-database synchronization
- `VariableResolver` - Protocol for custom variable resolution
- `extract_variables_from_content()` - Variable extraction from templates

---

## Prompt Model

`llm_pipeline.db.prompt.Prompt`

Database model for storing prompt templates with versioning and metadata.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | `Optional[int]` | Primary key (auto-generated) |
| `prompt_key` | `str` | Unique identifier for prompt (max 100 chars, indexed) |
| `prompt_name` | `str` | Human-readable name (max 200 chars) |
| `prompt_type` | `str` | Prompt type: 'system' or 'user' (max 50 chars) |
| `category` | `Optional[str]` | Organization category (max 50 chars) |
| `step_name` | `Optional[str]` | Associated pipeline step (max 50 chars) |
| `content` | `str` | Prompt template content with `{variable}` placeholders |
| `required_variables` | `Optional[List[str]]` | Auto-extracted variable names from content |
| `description` | `Optional[str]` | Documentation for prompt usage |
| `version` | `str` | Semantic version (default: "1.0", max 20 chars) |
| `is_active` | `bool` | Active status (default: True) |
| `created_at` | `datetime` | Creation timestamp (UTC) |
| `updated_at` | `datetime` | Last update timestamp (UTC) |
| `created_by` | `Optional[str]` | Creator identifier (max 100 chars) |

### Constraints and Indexes

```python
# Unique constraint: prevents duplicate prompt_key + prompt_type combinations
UniqueConstraint('prompt_key', 'prompt_type', name='uq_prompts_key_type')

# Composite index: efficient queries by category and step
Index("ix_prompts_category_step", "category", "step_name")

# Single-column index: fast filtering by active status
Index("ix_prompts_active", "is_active")
```

### Example

```python
from llm_pipeline.db.prompt import Prompt

prompt = Prompt(
    prompt_key="semantic_mapping.system_instruction",
    prompt_name="Semantic Mapping System Instruction",
    prompt_type="system",
    category="extraction",
    step_name="semantic_mapping",
    content="Extract {entity_type} from the document: {document_text}",
    required_variables=["entity_type", "document_text"],
    description="System instruction for semantic mapping extraction",
    version="1.2",
    is_active=True
)
```

---

## PromptService

`llm_pipeline.prompts.PromptService`

Service class for retrieving prompts from database with formatting and variable validation.

### Constructor

```python
PromptService(session: Session)
```

**Parameters:**
- `session` - SQLModel/SQLAlchemy session for database access

**Example:**
```python
from sqlmodel import Session
from llm_pipeline.prompts import PromptService

service = PromptService(session)
```

### Methods

#### get_prompt()

```python
def get_prompt(
    prompt_key: str,
    prompt_type: str = 'system',
    context: Optional[dict] = None,
    fallback: Optional[str] = None
) -> str
```

Retrieve raw prompt content by key and type.

**Parameters:**
- `prompt_key` - Unique prompt identifier
- `prompt_type` - Prompt type ('system' or 'user', default: 'system')
- `context` - **NON-FUNCTIONAL** (vestigial parameter, do not use)
- `fallback` - Default content if prompt not found

**Returns:** Prompt content string (unformatted template)

**Raises:** `ValueError` if prompt not found and no fallback provided

**Known Limitation:** The `context` parameter references non-existent `Prompt.context` field. Context-filtering code path is broken and should not be used. The method works correctly when `context=None` (default).

**Example:**
```python
# Basic usage (working)
template = service.get_prompt(
    prompt_key="mapping.system_instruction",
    prompt_type="system"
)

# With fallback (working)
template = service.get_prompt(
    prompt_key="optional.prompt",
    fallback="Default prompt text"
)

# DO NOT USE: context parameter is non-functional
# template = service.get_prompt("key", context={"table_type": "lane"})  # BROKEN
```

#### get_system_instruction()

```python
def get_system_instruction(
    step_name: str,
    fallback: Optional[str] = None
) -> str
```

Retrieve system instruction for a pipeline step by convention.

**Parameters:**
- `step_name` - Name of pipeline step
- `fallback` - Default content if not found

**Returns:** System instruction content

**Convention:** Automatically constructs prompt key as `{step_name}.system_instruction`

**Example:**
```python
instruction = service.get_system_instruction("semantic_mapping")
# Retrieves prompt with key: "semantic_mapping.system_instruction"
```

#### get_guidance()

```python
def get_guidance(
    step_name: str,
    table_type: Optional[str] = None,
    fallback: str = ""
) -> str
```

Retrieve guidance text for a step, optionally filtered by table type.

**Parameters:**
- `step_name` - Name of pipeline step
- `table_type` - Optional table type for specialized guidance
- `fallback` - Default content if not found (default: empty string)

**Returns:** Guidance content

**Known Limitation:** When `table_type` is provided, this method calls `get_prompt()` with the broken `context` parameter. Context-filtering will fail. The method only works reliably for the fallback path (no table_type or prompt not found).

**Convention:**
- Without table_type: `{step_name}.guidance`
- With table_type: `{step_name}.guidance.{table_type}`

**Example:**
```python
# Works: no table_type filtering
guidance = service.get_guidance("mapping", fallback="Default guidance")

# BROKEN: context-filtering uses non-existent Prompt.context field
# guidance = service.get_guidance("mapping", table_type="lane")
```

#### prompt_exists()

```python
def prompt_exists(prompt_key: str) -> bool
```

Check if an active prompt exists in the database.

**Parameters:**
- `prompt_key` - Unique prompt identifier

**Returns:** `True` if active prompt exists, `False` otherwise

**Example:**
```python
if service.prompt_exists("mapping.system_instruction"):
    template = service.get_prompt("mapping.system_instruction")
```

#### get_system_prompt()

```python
def get_system_prompt(
    prompt_key: str,
    variables: dict,
    variable_instance: Optional[Any] = None,
    context: Optional[dict] = None,
    fallback: Optional[str] = None
) -> str
```

Retrieve system prompt template and format with variables.

**Parameters:**
- `prompt_key` - Unique prompt identifier
- `variables` - Dictionary of variable values for formatting
- `variable_instance` - Optional Pydantic model instance for error reporting
- `context` - **NON-FUNCTIONAL** (see `get_prompt()` limitation)
- `fallback` - Default template if not found

**Returns:** Formatted prompt string with variables replaced

**Raises:** `ValueError` with detailed error if variable missing

**Error Reporting:** When variables are missing, generates helpful error showing:
- Template requirements
- Class-defined fields (if `variable_instance` provided)
- Runtime-provided variables
- Missing variables with action guidance

**Example:**
```python
from pydantic import BaseModel

class MappingVariables(BaseModel):
    entity_type: str
    document_text: str

variables = {"entity_type": "product", "document_text": "..."}
var_instance = MappingVariables(**variables)

prompt = service.get_system_prompt(
    prompt_key="mapping.system_instruction",
    variables=variables,
    variable_instance=var_instance
)

# Error handling example:
# ValueError:
# System prompt template variable {missing_var} not provided.
#
# Template requires:  ['entity_type', 'document_text', 'missing_var']
# Class defines:      ['entity_type', 'document_text']
# Runtime provided:   ['entity_type', 'document_text']
#
# Missing from class: ['missing_var']
# ACTION: Add missing variables to prompts/mapping/system_prompt.yaml and regenerate
```

#### get_user_prompt()

```python
def get_user_prompt(
    prompt_key: str,
    variables: dict,
    variable_instance: Optional[Any] = None,
    context: Optional[dict] = None,
    fallback: Optional[str] = None
) -> str
```

Retrieve user prompt template and format with variables.

**Parameters:** Same as `get_system_prompt()` but retrieves 'user' type prompts

**Returns:** Formatted user prompt string

**Raises:** `ValueError` with detailed error if variable missing

**Example:**
```python
user_prompt = service.get_user_prompt(
    prompt_key="mapping.user_instruction",
    variables={"document": "Invoice text..."},
    variable_instance=var_instance
)
```

---

## Synchronization Functions

### sync_prompts()

`llm_pipeline.prompts.sync_prompts(bind, prompts_dir=None, force=False)`

Synchronize prompts from YAML files to database with version-aware updates.

**Parameters:**
- `bind` - SQLAlchemy engine or connection for database operations
- `prompts_dir` - Path to prompts directory (default: from `get_prompts_dir()`)
- `force` - If `True`, update all prompts regardless of version (default: `False`)

**Returns:** Dictionary with sync statistics: `{'inserted': int, 'updated': int, 'skipped': int}`

**Behavior:**
1. **New prompts:** Insert into database
2. **Existing prompts:** Update only if version number increased (semantic versioning)
3. **Unchanged versions:** Skip (idempotent operation)
4. **Force mode:** Update all prompts regardless of version
5. **Variable extraction:** Automatically extracts `required_variables` from `{variable}` patterns in content

**YAML Structure:**
```yaml
prompt_key: semantic_mapping.system_instruction
name: Semantic Mapping System Instruction
type: system
category: extraction
step: semantic_mapping
version: "1.2"
description: System instruction for semantic mapping
is_active: true
content: |
  Extract {entity_type} from the following document.
  Document: {document_text}

  Return structured data matching the schema.
```

**Required YAML Fields:**
- `prompt_key`, `name`, `type`, `category`, `step`, `version`, `content`

**Version Comparison:** Uses semantic versioning (e.g., "1.2.1" > "1.2.0"). If version parsing fails, assumes new version is greater.

**Example:**
```python
from sqlalchemy import create_engine
from llm_pipeline.prompts import sync_prompts
from pathlib import Path

engine = create_engine("sqlite:///prompts.db")
prompts_dir = Path("./prompts")

# Normal sync: only update if version increased
result = sync_prompts(engine, prompts_dir)
print(f"Inserted: {result['inserted']}, Updated: {result['updated']}")

# Force sync: update all prompts
result = sync_prompts(engine, prompts_dir, force=True)
```

**Output Example:**
```
Syncing 12 prompts from YAML files...
  + Inserted: mapping.system_instruction (v1.0) [entity_type, document_text]
  [UPDATE] extraction.user_prompt (v1.1 -> v1.2)

Prompt sync complete: 5 inserted, 3 updated, 4 skipped
```

### load_all_prompts()

`llm_pipeline.prompts.load_all_prompts(prompts_dir=None)`

Load all prompts from YAML files without database interaction.

**Parameters:**
- `prompts_dir` - Path to prompts directory (default: from `get_prompts_dir()`)

**Returns:** List of prompt dictionaries parsed from YAML

**Raises:** `FileNotFoundError` if prompts directory doesn't exist

**File Discovery:** Recursively searches for `.yaml` and `.yml` files

**Example:**
```python
from llm_pipeline.prompts import load_all_prompts

prompts = load_all_prompts()
for prompt in prompts:
    print(f"{prompt['prompt_key']}: {prompt['version']}")
```

### get_prompts_dir()

`llm_pipeline.prompts.get_prompts_dir()`

Determine prompts directory from environment or default.

**Returns:** `Path` object pointing to prompts directory

**Resolution:**
1. Check `PROMPTS_DIR` environment variable
2. Fall back to `./prompts` (current working directory)

**Example:**
```python
from llm_pipeline.prompts import get_prompts_dir
import os

# Use environment variable
os.environ['PROMPTS_DIR'] = '/app/config/prompts'
prompts_path = get_prompts_dir()  # Returns: Path('/app/config/prompts')

# Use default
del os.environ['PROMPTS_DIR']
prompts_path = get_prompts_dir()  # Returns: Path('./prompts')
```

### extract_variables_from_content()

`llm_pipeline.prompts.extract_variables_from_content(content)`

Extract variable names from prompt template content.

**Parameters:**
- `content` - Prompt template string with `{variable_name}` placeholders

**Returns:** List of unique variable names (preserves first occurrence order)

**Pattern:** Matches `{variable_name}` where variable_name follows Python identifier rules (`[a-zA-Z_][a-zA-Z0-9_]*`)

**Example:**
```python
from llm_pipeline.prompts import extract_variables_from_content

template = "Extract {entity_type} from {document}. Format: {output_format}. Reference: {document}"
variables = extract_variables_from_content(template)
# Returns: ['entity_type', 'document', 'output_format']
# Note: 'document' appears twice but returned once
```

---

## Utility Functions

### _version_greater()

`llm_pipeline.prompts.loader._version_greater(new, current)`

Compare semantic version strings.

**Parameters:**
- `new` - New version string (e.g., "1.2.1")
- `current` - Current version string (e.g., "1.2.0")

**Returns:** `True` if new version is greater, `False` otherwise

**Algorithm:**
1. Split versions by `.` and convert to integers
2. Pad shorter version with zeros to equal length
3. Compare as tuples (lexicographic ordering)
4. On parsing error, return `True` (assume new is greater)

**Example:**
```python
from llm_pipeline.prompts.loader import _version_greater

_version_greater("1.2.1", "1.2.0")   # True
_version_greater("2.0.0", "1.9.9")   # True
_version_greater("1.2", "1.2.0")     # False (equal after padding)
_version_greater("1.2.0", "1.2.1")   # False
_version_greater("abc", "1.0.0")     # True (parsing error fallback)
```

---

## VariableResolver Protocol

`llm_pipeline.prompts.VariableResolver`

Protocol for custom variable resolution logic in host projects.

### Protocol Definition

```python
@runtime_checkable
class VariableResolver(Protocol):
    def resolve(
        self,
        prompt_key: str,
        prompt_type: str
    ) -> Optional[Type[BaseModel]]:
        """
        Resolve prompt key and type to a Pydantic variable class.

        Args:
            prompt_key: Prompt identifier (e.g., 'mapping.system_instruction')
            prompt_type: 'system' or 'user'

        Returns:
            Pydantic BaseModel subclass or None if not found
        """
        ...
```

### Purpose

Decouples the pipeline from specific variable class implementations, allowing host projects to provide their own variable resolution strategies without modifying framework code.

### Implementation Example

```python
from typing import Type, Optional
from pydantic import BaseModel
from llm_pipeline.prompts import VariableResolver

class MappingVariables(BaseModel):
    entity_type: str
    document_text: str

class ExtractionVariables(BaseModel):
    table_data: str
    schema_hint: str

class MyVariableRegistry:
    """Host project's variable registry."""

    _registry = {
        ('mapping.system_instruction', 'system'): MappingVariables,
        ('extraction.system_instruction', 'system'): ExtractionVariables,
    }

    def resolve(
        self,
        prompt_key: str,
        prompt_type: str
    ) -> Optional[Type[BaseModel]]:
        return self._registry.get((prompt_key, prompt_type))

# Usage with pipeline
from llm_pipeline import PipelineConfig

class MyPipeline(PipelineConfig):
    def __init__(self):
        super().__init__(
            model='google-gla:gemini-2.0-flash-lite',
            variable_resolver=MyVariableRegistry()
        )
```

### Runtime Checking

The protocol is marked with `@runtime_checkable`, enabling isinstance checks:

```python
from llm_pipeline.prompts import VariableResolver

resolver = MyVariableRegistry()
assert isinstance(resolver, VariableResolver)  # True at runtime
```

---

## Module Exports

`llm_pipeline.prompts.__init__.py`

Public API surface for prompt management.

```python
from llm_pipeline.prompts import (
    PromptService,          # Service for prompt retrieval
    VariableResolver,       # Protocol for variable resolution
    sync_prompts,           # YAML-to-DB synchronization
    load_all_prompts,       # Load prompts from YAML
    get_prompts_dir,        # Get prompts directory path
    extract_variables_from_content,  # Extract template variables
)
```

---

## Complete Usage Example

```python
from pathlib import Path
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel
from pydantic import BaseModel
from llm_pipeline.prompts import (
    PromptService,
    sync_prompts,
    extract_variables_from_content,
)
from llm_pipeline.db.prompt import Prompt

# 1. Database setup
engine = create_engine("sqlite:///prompts.db")
SQLModel.metadata.create_all(engine)

# 2. Sync prompts from YAML
prompts_dir = Path("./prompts")
result = sync_prompts(engine, prompts_dir)
print(f"Synced: {result}")

# 3. Create service
with Session(engine) as session:
    service = PromptService(session)

    # 4. Check if prompt exists
    if service.prompt_exists("mapping.system_instruction"):
        # 5. Get raw template
        template = service.get_prompt("mapping.system_instruction")

        # 6. Extract variables
        variables = extract_variables_from_content(template)
        print(f"Required variables: {variables}")

        # 7. Format with variables
        class MappingVars(BaseModel):
            entity_type: str
            document_text: str

        var_data = {
            "entity_type": "product",
            "document_text": "Invoice data..."
        }
        var_instance = MappingVars(**var_data)

        formatted_prompt = service.get_system_prompt(
            prompt_key="mapping.system_instruction",
            variables=var_data,
            variable_instance=var_instance
        )
        print(f"Formatted prompt: {formatted_prompt}")
```

---

## Known Limitations

### 1. Prompt.context Field Removed

**Issue:** `PromptService.get_prompt()` and `get_guidance()` reference `Prompt.context` field for context-based filtering, but this field no longer exists in the `Prompt` model.

**Impact:** Calling `get_prompt(context=...)` or `get_guidance(table_type=...)` will fail at runtime when attempting context filtering.

**Workaround:** Do not use the `context` parameter. The methods work correctly without it.

**Affected Methods:**
- `get_prompt(context=...)`
- `get_guidance(table_type=...)`

### 2. Version Comparison Edge Cases

**Issue:** `_version_greater()` returns `True` on parsing errors, potentially causing unintended updates.

**Impact:** Malformed version strings (e.g., "v1.2", "1.2-beta") will always be considered "greater" than any valid version.

**Workaround:** Use strict semantic versioning format: `"major.minor.patch"`

### 3. No Prompt Deletion

**Issue:** `sync_prompts()` only inserts and updates prompts. Removing a YAML file does not delete the corresponding database record.

**Impact:** Orphaned prompts remain in database after YAML removal.

**Workaround:** Manually set `is_active=False` in database or implement custom deletion logic.

---

## Database Schema

### Table: prompts

```sql
CREATE TABLE prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_key VARCHAR(100) NOT NULL,
    prompt_name VARCHAR(200) NOT NULL,
    prompt_type VARCHAR(50) NOT NULL,
    category VARCHAR(50),
    step_name VARCHAR(50),
    content TEXT NOT NULL,
    required_variables JSON,
    description TEXT,
    version VARCHAR(20) DEFAULT '1.0',
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    created_by VARCHAR(100),

    CONSTRAINT uq_prompts_key_type UNIQUE (prompt_key, prompt_type)
);

CREATE INDEX ix_prompts_prompt_key ON prompts (prompt_key);
CREATE INDEX ix_prompts_category_step ON prompts (category, step_name);
CREATE INDEX ix_prompts_active ON prompts (is_active);
```

---

## Best Practices

### 1. Version Management

Always increment version numbers when updating prompt content:

```yaml
# prompts/mapping/system_instruction.yaml
version: "1.2"  # Increment from "1.1"
content: |
  Updated prompt content...
```

### 2. Variable Naming

Use descriptive, consistent variable names following Python identifier rules:

```yaml
content: |
  Extract {entity_type} from {source_document}.
  # Good: entity_type, source_document
  # Bad: type (too generic), source-document (hyphen invalid)
```

### 3. Prompt Organization

Organize YAML files by category and step:

```
prompts/
├── extraction/
│   ├── semantic_mapping.yaml
│   └── table_extraction.yaml
├── transformation/
│   └── data_normalization.yaml
└── validation/
    └── schema_check.yaml
```

### 4. Testing Prompts

Test prompt formatting before deployment:

```python
# Test variable extraction
template = "Extract {var1} and {var2}"
variables = extract_variables_from_content(template)
assert variables == ['var1', 'var2']

# Test formatting
formatted = template.format(var1="A", var2="B")
assert formatted == "Extract A and B"
```

### 5. Error Handling

Always provide fallbacks for optional prompts:

```python
guidance = service.get_guidance(
    "optional_step",
    fallback="Default guidance text"
)
```

### 6. Variable Validation

Use Pydantic models for type-safe variable validation:

```python
class PromptVariables(BaseModel):
    entity_type: str
    document_text: str
    threshold: float = 0.8  # Optional with default

# Validates at instantiation
variables = PromptVariables(
    entity_type="product",
    document_text="..."
)
```

---

## See Also

- [Pipeline API](pipeline.md) - Integration with pipeline execution
- [Pipeline API](pipeline.md) - Using prompts in pipeline context
- [Step API](step.md) - Step-level prompt integration
- [Database Schema](state.md) - Related database models
