# Prompt Management Guide

## What You'll Learn

After completing this guide, you'll understand how to:

- Organize prompts in YAML files
- Sync prompts to the database with version control
- Use automatic prompt key discovery
- Define and validate prompt variables
- Format templates with variable substitution

**Prerequisites:**
- Basic understanding of [Pipeline Architecture](../architecture/overview.md)
- Familiarity with [Step API](../api/step.md)
- Python 3.11+ environment

**Time Estimate:** 15-20 minutes

---

## Overview

llm-pipeline uses a database-backed prompt system that:

1. **Stores prompts as YAML files** - Easy to version control and review
2. **Syncs to database** - Fast retrieval with version management
3. **Auto-discovers prompt keys** - Convention-based prompt resolution
4. **Validates variables** - Type-safe template variable checking
5. **Supports versioning** - Semantic versioning with update tracking

---

## Quick Start

### Step 1: Create Prompt Directory

```bash
mkdir -p prompts/extraction
```

### Step 2: Define a Prompt

Create `prompts/extraction/semantic_mapping.yaml`:

```yaml
prompt_key: semantic_mapping
name: Semantic Mapping System Instruction
type: system
category: extraction
step: semantic_mapping
version: "1.0"
description: Extract semantic entities from document
is_active: true
content: |
  Extract {entity_type} from the following document.

  Document: {document_text}

  Return structured data matching the provided schema.
```

### Step 3: Sync to Database

```python
from sqlalchemy import create_engine
from llm_pipeline.prompts import sync_prompts
from pathlib import Path

engine = create_engine("sqlite:///pipeline.db")
result = sync_prompts(engine, Path("./prompts"))

print(f"Synced: {result['inserted']} inserted, {result['updated']} updated")
```

### Step 4: Use in Pipeline

```python
from llm_pipeline import PipelineConfig, step_definition, LLMStep

@step_definition(
    instructions=SemanticMappingInstructions,
    # Prompt keys auto-discovered from step name
)
class SemanticMappingStep(LLMStep):
    def prepare_calls(self):
        # Framework automatically uses 'semantic_mapping' prompt
        return [StepCallParams(variables=self.variables)]
```

**Output:**
```
Syncing 1 prompts from YAML files...
  + Inserted: semantic_mapping (v1.0) [entity_type, document_text]

Prompt sync complete: 1 inserted, 0 updated, 0 skipped
```

---

## YAML Prompt Structure

### Required Fields

Every prompt YAML file must include these fields:

```yaml
prompt_key: semantic_mapping        # Unique identifier
name: Semantic Mapping Instruction  # Human-readable name
type: system                        # 'system' or 'user'
category: extraction                # Organizational category
step: semantic_mapping              # Associated pipeline step
version: "1.0"                      # Semantic version (always quoted)
content: |                          # Prompt template content
  Your prompt text with {variables}
```

### Optional Fields

```yaml
description: Detailed explanation of prompt usage
is_active: true                     # Default: true (inactive prompts ignored)
```

### Complete Example

```yaml
# prompts/extraction/table_extraction.yaml
prompt_key: table_extraction.lane_based
name: Lane-Based Table Extraction User Prompt
type: user
category: extraction
step: table_extraction
version: "1.2"
description: |
  User prompt for extracting lane-based rate tables.
  Uses schema hints for structured output.
is_active: true
content: |
  Extract rate information from the following table data:

  {table_data}

  Expected columns: {column_hints}

  Return JSON array matching the schema.
```

---

## Prompt Key Conventions

### Naming Patterns

Prompt keys follow these conventions:

1. **Step-level prompts:** `{step_name}`
   - Example: `semantic_mapping`
   - Used by all strategies for that step

2. **Strategy-specific prompts:** `{step_name}.{strategy_name}`
   - Example: `table_extraction.lane_based`
   - Used only when specific strategy is active

3. **Prompt type suffix:** Implicit (stored in `type` field)
   - System prompts: `type: system`
   - User prompts: `type: user`

### Auto-Discovery Order

When you don't provide explicit prompt keys, the framework searches in this order:

```
Priority 1: Strategy-level    →  {step_name}.{strategy_name}  (e.g., "extraction.lane_based")
Priority 2: Step-level        →  {step_name}                  (e.g., "extraction")
Priority 3: Explicit          →  Provided in create_definition()
```

**Example:**

```python
# Step name: SemanticMappingStep → "semantic_mapping"
# Current strategy: "lane_based"

# Search order:
# 1. Look for "semantic_mapping.lane_based" (strategy-specific)
# 2. Look for "semantic_mapping" (step-level fallback)
# 3. Fail if neither found and no explicit key provided
```

---

## Automatic Prompt Key Discovery

### How It Works

The framework automatically derives prompt keys from your step class name:

```python
from llm_pipeline import step_definition, LLMStep

@step_definition(
    instructions=MappingInstructions,
    # No prompt keys specified - auto-discovery enabled
)
class SemanticMappingStep(LLMStep):
    pass

# Derived step name: "semantic_mapping" (SemanticMappingStep → semantic_mapping)
# Framework searches for:
#   - semantic_mapping.{current_strategy} (if strategy active)
#   - semantic_mapping (fallback)
```

### Explicit Keys Override Auto-Discovery

Provide explicit keys when you need non-standard naming:

```python
@step_definition(
    instructions=MappingInstructions,
    default_system_key="custom.system.prompt",
    default_user_key="custom.user.prompt",
)
class SemanticMappingStep(LLMStep):
    pass

# Or at strategy definition time:
SemanticMappingStep.create_definition(
    system_instruction_key="custom.system.prompt",
    user_prompt_key="custom.user.prompt"
)
```

### Strategy-Specific Prompts

Create strategy-specific prompts for different execution paths:

**YAML Structure:**
```yaml
# prompts/extraction/lane_based.yaml
prompt_key: extraction.lane_based
type: system
step: extraction
content: |
  Extract lane-based rate information...

# prompts/extraction/zone_based.yaml
prompt_key: extraction.zone_based
type: system
step: extraction
content: |
  Extract zone-based rate information...
```

**Pipeline Code:**
```python
class LaneBasedStrategy(PipelineStrategy):
    NAME = "lane_based"

    def define_steps(self):
        return [
            ExtractionStep.create_definition()
            # Auto-discovers "extraction.lane_based"
        ]

class ZoneBasedStrategy(PipelineStrategy):
    NAME = "zone_based"

    def define_steps(self):
        return [
            ExtractionStep.create_definition()
            # Auto-discovers "extraction.zone_based"
        ]
```

---

## Prompt Variables

### Variable Extraction

Variables are automatically extracted from `{variable_name}` patterns in prompt content:

```yaml
content: |
  Extract {entity_type} from document: {document_text}
  Format output as {output_format}.

# Auto-extracted: required_variables = ['entity_type', 'document_text', 'output_format']
```

**Validation Rules:**

- Variables must follow Python identifier rules: `[a-zA-Z_][a-zA-Z0-9_]*`
- Valid: `entity_type`, `document_text`, `_private_var`
- Invalid: `entity-type` (hyphen), `2nd_var` (starts with digit)

### Defining Variable Classes

Use Pydantic models for type-safe variable validation:

```python
from pydantic import BaseModel, Field

class MappingVariables(BaseModel):
    """Variables for semantic mapping prompts."""

    entity_type: str = Field(
        description="Type of entity to extract"
    )
    document_text: str = Field(
        description="Source document content"
    )
    output_format: str = Field(
        default="JSON",
        description="Output format specification"
    )
```

### Variable Resolution Protocol

Implement custom variable resolution for your project:

```python
from typing import Type, Optional
from pydantic import BaseModel
from llm_pipeline.prompts import VariableResolver

class MyVariableRegistry:
    """Project-specific variable resolver."""

    _registry = {
        ('semantic_mapping', 'system'): MappingVariables,
        ('table_extraction', 'user'): ExtractionVariables,
    }

    def resolve(
        self,
        prompt_key: str,
        prompt_type: str
    ) -> Optional[Type[BaseModel]]:
        return self._registry.get((prompt_key, prompt_type))

# Pass to pipeline
class MyPipeline(PipelineConfig):
    def __init__(self):
        super().__init__(
            provider=GeminiProvider(),
            variable_resolver=MyVariableRegistry()
        )
```

---

## Template Formatting

### Basic Formatting

The framework uses Python's `str.format()` for variable substitution:

```python
from llm_pipeline.prompts import PromptService

service = PromptService(session)

# Get formatted prompt
formatted = service.get_system_prompt(
    prompt_key="semantic_mapping",
    variables={
        "entity_type": "product",
        "document_text": "Invoice #12345..."
    }
)

# Result:
# "Extract product from document: Invoice #12345..."
```

### Error Handling with Variable Instance

Provide `variable_instance` for detailed error messages:

```python
variables = {
    "entity_type": "product",
    # Missing: document_text
}
var_instance = MappingVariables(
    entity_type="product",
    document_text=""  # Will be validated
)

try:
    formatted = service.get_system_prompt(
        prompt_key="semantic_mapping",
        variables=variables,
        variable_instance=var_instance
    )
except ValueError as e:
    print(e)
```

**Error Output:**
```
System prompt template variable {document_text} not provided.

Template requires:  ['entity_type', 'document_text']
Class defines:      ['entity_type', 'document_text']
Runtime provided:   ['entity_type']

Missing from class: ['document_text']
ACTION: Add missing variables to prompts/semantic_mapping/system_prompt.yaml and regenerate
```

### Special Characters in Templates

Escape curly braces for literal text:

```yaml
content: |
  Extract data matching pattern: {{literal_curly_braces}}
  But replace this: {actual_variable}

# Results in:
# "Extract data matching pattern: {literal_curly_braces}"
# "But replace this: <value>"
```

---

## Version Management

### Semantic Versioning

Use semantic versioning (`major.minor.patch`) for all prompts:

```yaml
version: "1.0"      # Initial version
version: "1.1"      # Minor update (backward compatible)
version: "2.0"      # Major update (breaking change)
version: "1.2.1"    # Patch (bug fix)
```

### Version Comparison

`sync_prompts()` only updates prompts when version increases:

```python
# Database has: semantic_mapping v1.0
# YAML has:     semantic_mapping v1.1

result = sync_prompts(engine, prompts_dir)
# Updates prompt to v1.1

result = sync_prompts(engine, prompts_dir)
# Skips (already at v1.1)
```

**Comparison Algorithm:**

1. Split version by `.` and convert to integers
2. Pad shorter version with zeros
3. Compare as tuples: `[1, 2, 1] > [1, 2, 0]`
4. On parsing error, assume new version is greater

```python
from llm_pipeline.prompts.loader import _version_greater

_version_greater("1.2.1", "1.2.0")   # True
_version_greater("2.0.0", "1.9.9")   # True
_version_greater("1.2", "1.2.0")     # False (equal after padding)
```

### Force Update

Override version checking with `force=True`:

```python
# Update all prompts regardless of version
result = sync_prompts(engine, prompts_dir, force=True)
```

---

## Complete Example: Multi-Strategy Prompts

This example shows a complete prompt management setup with strategy-specific variations.

### Directory Structure

```
prompts/
├── extraction/
│   ├── semantic_mapping.yaml          # Step-level fallback
│   ├── table_extraction.yaml          # Step-level fallback
│   ├── table_extraction_lane.yaml     # Lane strategy
│   └── table_extraction_zone.yaml     # Zone strategy
└── validation/
    └── schema_check.yaml
```

### YAML Files

**prompts/extraction/table_extraction.yaml** (fallback):
```yaml
prompt_key: table_extraction
name: Table Extraction (Generic)
type: system
category: extraction
step: table_extraction
version: "1.0"
is_active: true
content: |
  Extract rate information from table: {table_data}
  Return structured data matching schema.
```

**prompts/extraction/table_extraction_lane.yaml** (strategy-specific):
```yaml
prompt_key: table_extraction.lane_based
name: Lane-Based Table Extraction
type: system
category: extraction
step: table_extraction
version: "1.0"
is_active: true
content: |
  Extract lane-based rates from: {table_data}

  Expected structure:
  - Origin lane
  - Destination lane
  - Rate per unit

  Column hints: {column_hints}
```

**prompts/extraction/table_extraction_zone.yaml** (strategy-specific):
```yaml
prompt_key: table_extraction.zone_based
name: Zone-Based Table Extraction
type: system
category: extraction
step: table_extraction
version: "1.0"
is_active: true
content: |
  Extract zone-based rates from: {table_data}

  Expected structure:
  - Pickup zone
  - Delivery zone
  - Base rate
  - Zone multiplier

  Column hints: {column_hints}
```

### Pipeline Implementation

```python
from llm_pipeline import (
    PipelineConfig,
    PipelineStrategy,
    step_definition,
    LLMStep,
)
from llm_pipeline.llm import GeminiProvider
from pydantic import BaseModel

# Variable definitions
class ExtractionVariables(BaseModel):
    table_data: str
    column_hints: str

# Step definition
@step_definition(
    instructions=ExtractionInstructions,
    default_extractions=[RateExtraction],
    # No explicit keys - auto-discovery enabled
)
class TableExtractionStep(LLMStep):
    def prepare_calls(self):
        return [StepCallParams(
            variables=ExtractionVariables(
                table_data=self.pipeline.data['table_text'],
                column_hints=self.pipeline.context['column_info']
            )
        )]

# Strategy definitions
class LaneBasedStrategy(PipelineStrategy):
    NAME = "lane_based"
    DISPLAY_NAME = "Lane-Based Extraction"

    def can_handle(self, context):
        return context.get('table_type') == 'lane'

    def define_steps(self):
        return [
            TableExtractionStep.create_definition()
            # Auto-discovers: "table_extraction.lane_based"
        ]

class ZoneBasedStrategy(PipelineStrategy):
    NAME = "zone_based"
    DISPLAY_NAME = "Zone-Based Extraction"

    def can_handle(self, context):
        return context.get('table_type') == 'zone'

    def define_steps(self):
        return [
            TableExtractionStep.create_definition()
            # Auto-discovers: "table_extraction.zone_based"
        ]

class FallbackStrategy(PipelineStrategy):
    NAME = "fallback"
    DISPLAY_NAME = "Generic Extraction"

    def can_handle(self, context):
        return True  # Always handles (lowest priority)

    def define_steps(self):
        return [
            TableExtractionStep.create_definition()
            # Auto-discovers: "table_extraction" (step-level)
        ]

# Pipeline configuration
class RateExtractionPipeline(PipelineConfig):
    registry = RateExtractionRegistry
    strategies = [LaneBasedStrategy, ZoneBasedStrategy, FallbackStrategy]

    def __init__(self):
        super().__init__(
            provider=GeminiProvider(),
            variable_resolver=MyVariableRegistry()
        )
```

### Execution

```python
from pathlib import Path

# 1. Sync prompts
engine = create_engine("sqlite:///rates.db")
result = sync_prompts(engine, Path("./prompts"))
print(f"Synced: {result}")

# 2. Execute pipeline with lane strategy
pipeline = RateExtractionPipeline()
results = pipeline.execute(
    context={'table_type': 'lane'},
    data={'table_text': '...'}
)
# Uses prompt: "table_extraction.lane_based"

# 3. Execute with zone strategy
results = pipeline.execute(
    context={'table_type': 'zone'},
    data={'table_text': '...'}
)
# Uses prompt: "table_extraction.zone_based"

# 4. Execute with unknown type
results = pipeline.execute(
    context={'table_type': 'custom'},
    data={'table_text': '...'}
)
# Falls back to: "table_extraction"
```

---

## Troubleshooting

### Common Issues

#### 1. Prompt Not Found Error

**Error:**
```
ValueError: No prompts found for SemanticMappingStep.
Searched for:
  - semantic_mapping.lane_based
  - semantic_mapping
Please provide explicit keys or ensure prompts exist in database.
```

**Solution:**

Check prompt exists and is active:

```python
from sqlmodel import Session, select
from llm_pipeline.db.prompt import Prompt

with Session(engine) as session:
    prompt = session.exec(select(Prompt).where(
        Prompt.prompt_key == "semantic_mapping",
        Prompt.is_active == True
    )).first()

    if not prompt:
        print("Prompt not found or inactive")
        # Re-sync prompts
        sync_prompts(engine, prompts_dir)
```

#### 2. Variable Missing Error

**Error:**
```
KeyError: 'document_text'
System prompt template variable {document_text} not provided.
```

**Solution:**

Ensure all template variables are provided:

```python
# Check what template requires
from llm_pipeline.prompts import extract_variables_from_content

template = service.get_prompt("semantic_mapping")
required = extract_variables_from_content(template)
print(f"Required variables: {required}")

# Provide all required variables
variables = {var: value for var in required}
formatted = service.get_system_prompt("semantic_mapping", variables)
```

#### 3. Version Not Updating

**Error:**
Prompt content in database doesn't match YAML after sync.

**Solution:**

Increment version number in YAML:

```yaml
# Before
version: "1.0"

# After
version: "1.1"  # Increment to trigger update
```

Or force update:

```python
sync_prompts(engine, prompts_dir, force=True)
```

#### 4. YAML Parse Error

**Error:**
```
Warning: Failed to load prompts/extraction/mapping.yaml: ...
```

**Solution:**

Validate YAML syntax:

```bash
# Install PyYAML if needed
pip install pyyaml

# Test loading
python -c "import yaml; yaml.safe_load(open('prompts/extraction/mapping.yaml'))"
```

Common YAML issues:
- Inconsistent indentation (use spaces, not tabs)
- Missing quotes around version: `version: "1.0"`
- Incorrect pipe syntax for multi-line: `content: |`

---

## Best Practices

### 1. Version Every Change

Always increment version when updating prompt content:

```yaml
# DON'T: Change content without version bump
content: Updated text...
version: "1.0"  # Same version

# DO: Increment version with content change
content: Updated text...
version: "1.1"  # Version bumped
```

### 2. Use Descriptive Variable Names

```yaml
# DON'T: Generic or unclear names
content: Extract {data} from {input} using {type}

# DO: Specific, clear names
content: Extract {entity_type} from {document_text} using {extraction_schema}
```

### 3. Organize by Category

```
prompts/
├── extraction/       # Extraction-related prompts
├── transformation/   # Transformation prompts
├── validation/       # Validation prompts
└── common/          # Shared/generic prompts
```

### 4. Document Complex Prompts

Use `description` field for complex logic:

```yaml
description: |
  This prompt handles multi-level nested table extraction.

  Requires pre-processing of {table_data} to normalize whitespace.

  Known limitations:
  - Cannot handle tables with merged cells
  - Assumes column headers in first row
```

### 5. Test Variable Extraction

Validate extracted variables match your expectations:

```python
from llm_pipeline.prompts import extract_variables_from_content

template = "Extract {var1} and {var2} from {var3}"
variables = extract_variables_from_content(template)

assert variables == ['var1', 'var2', 'var3'], f"Expected 3 vars, got {variables}"
```

### 6. Provide Fallbacks

Always have step-level fallback prompts:

```
prompts/extraction/
├── table_extraction.yaml              # Fallback (always works)
├── table_extraction_lane.yaml         # Strategy-specific
└── table_extraction_zone.yaml         # Strategy-specific
```

---

## Advanced Topics

### Custom Prompt Directory

Override default `./prompts` directory:

```bash
export PROMPTS_DIR=/app/config/prompts
```

Or programmatically:

```python
from pathlib import Path
from llm_pipeline.prompts import sync_prompts

custom_dir = Path("/app/config/prompts")
sync_prompts(engine, custom_dir)
```

### Prompt Introspection

Query available prompts:

```python
from sqlmodel import Session, select
from llm_pipeline.db.prompt import Prompt

with Session(engine) as session:
    # Get all active prompts for a step
    prompts = session.exec(select(Prompt).where(
        Prompt.step_name == "semantic_mapping",
        Prompt.is_active == True
    )).all()

    for p in prompts:
        print(f"{p.prompt_key} (v{p.version}): {p.prompt_type}")
        print(f"  Variables: {p.required_variables}")
```

### Inactive Prompts

Mark prompts inactive without deleting:

```yaml
is_active: false  # Prompt exists but won't be used
```

```python
# Check if specific version exists
prompt = session.exec(select(Prompt).where(
    Prompt.prompt_key == "old_mapping",
    Prompt.is_active == False  # Include inactive
)).first()
```

---

## Known Limitations

### 1. Context Parameter Non-Functional

**Issue:** `PromptService.get_prompt(context=...)` references non-existent `Prompt.context` field.

**Impact:** Context-based filtering doesn't work.

**Workaround:** Use strategy-specific prompt keys instead of context filtering.

```python
# DON'T: Use context parameter
template = service.get_prompt("mapping", context={"type": "lane"})  # BROKEN

# DO: Use strategy-specific keys
template = service.get_prompt("mapping.lane_based")  # WORKS
```

### 2. No Prompt Deletion

**Issue:** Removing YAML file doesn't delete database record.

**Impact:** Orphaned prompts remain in database.

**Workaround:** Manually set `is_active=False` or implement cleanup:

```python
# Mark orphaned prompts inactive
yaml_keys = {p['prompt_key'] for p in load_all_prompts(prompts_dir)}
db_prompts = session.exec(select(Prompt)).all()

for prompt in db_prompts:
    if prompt.prompt_key not in yaml_keys:
        prompt.is_active = False

session.commit()
```

### 3. Version Parsing Fallback

**Issue:** Malformed versions (e.g., "v1.2", "1.2-beta") always considered "greater".

**Impact:** May cause unintended updates.

**Workaround:** Use strict semantic versioning: `"major.minor.patch"`

---

## Next Steps

Now that you understand prompt management:

1. **Read [Step API Reference](../api/step.md)** - Learn how steps integrate with prompts
2. **Explore [Multi-Strategy Guide](multi-strategy.md)** - See strategy-specific prompts in action
3. **Review [LLM Provider API](../api/llm.md)** - Understand prompt execution flow
4. **Check [Best Practices](../architecture/patterns.md)** - Design patterns for prompt organization

---

## See Also

- [Prompt System API Reference](../api/prompts.md) - Complete API documentation
- [Step API Reference](../api/step.md) - Step definition and prompt integration
- [Pipeline API Reference](../api/pipeline.md) - Pipeline execution context
- [Architecture Overview](../architecture/overview.md) - System design and data flow
