"""Prompt constants and seeding for the StepCreator meta-pipeline."""
from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING

from sqlmodel import Session, SQLModel

from llm_pipeline.db.prompt import Prompt

if TYPE_CHECKING:
    from sqlalchemy import Engine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared framework reference prepended to all system prompts
# ---------------------------------------------------------------------------

FRAMEWORK_REFERENCE = """\
## llm-pipeline Framework Reference

Architecture: a Pipeline chains Steps. Each Step makes one LLM call and produces a Context that downstream steps can read.

### Instructions = Output Schema (NOT input instructions)
An `LLMResultMixin` subclass defines the **structured data the LLM returns**. pydantic-ai automatically parses the LLM response into this model. You never describe JSON output format in the prompts -- the framework handles that.

```python
class SentimentInstructions(LLMResultMixin):
    sentiment: str       # LLM fills this
    confidence: float    # LLM fills this
```

### Prompts != Output Schema
- **System prompt**: sets the LLM's role, task, and domain constraints. Must NOT describe JSON fields or output structure.
- **User prompt**: a `{variable}` template rendered at runtime with `str.format()`. Presents the input data.

### Step Class Pattern
Method bodies are inserted into a Jinja2 template that already provides the class shell, imports, and decorator. You only write the method **bodies** (no `def` line, no class).

The rendered file looks like:
```python
from llm_pipeline.step import LLMStep, step_definition
from .schemas import SentimentInstructions, SentimentContext

@step_definition(
    instructions=SentimentInstructions,
    default_system_key="sentiment_analysis",
    default_user_key="sentiment_analysis",
    context=SentimentContext,
)
class SentimentAnalysisStep(LLMStep):
    def prepare_calls(self):
        # --- your prepare_calls_body is inserted here ---
        return [{"variables": {"text": self.pipeline.validated_input.text}}]

    def process_instructions(self, instructions):
        # --- your process_instructions_body is inserted here ---
        inst = instructions[0]
        return SentimentContext(sentiment=inst.sentiment, confidence=inst.confidence)
```

### Access Patterns
- `self.pipeline.validated_input.<field>` -- pipeline input data
- `self.pipeline.context["<key>"]` or `self.pipeline.context.get("<key>")` -- prior step outputs (flat dict)

### Key Rules
- `prepare_calls()` returns `list[dict]`, each dict has a `"variables"` key mapping to template variable values
- `process_instructions(instructions)` receives `list[InstructionsClass]`, returns a Context instance
- Imports in the generated code must reference sibling files: `from .schemas import ...`, `from .models import ...`
"""

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

REQUIREMENTS_ANALYSIS_SYSTEM: dict = {
    "prompt_key": "requirements_analysis",
    "prompt_name": "Requirements Analysis System",
    "prompt_type": "system",
    "category": "step_creator",
    "step_name": "requirements_analysis",
    "content": (
        FRAMEWORK_REFERENCE + "\n"
        "## Your Task: Requirements Analysis\n\n"
        "Parse a natural language description of a pipeline step into a structured specification.\n\n"
        "Extract:\n"
        "- step_name: snake_case (e.g. 'sentiment_analysis')\n"
        "- step_class_name: PascalCase ending in 'Step' (e.g. 'SentimentAnalysisStep')\n"
        "- description: one-sentence summary\n"
        "- instruction_fields: fields the LLM will OUTPUT as structured data. "
        "These become fields on the LLMResultMixin subclass. Each field has: "
        "name, type_annotation, description, default (if optional), is_required\n"
        "- context_fields: fields passed to downstream steps via PipelineContext subclass\n"
        "- extraction_targets: SQLModel targets if persisting to DB (empty list if not)\n"
        "- input_variables: variable names that fill {placeholders} in the user prompt template. "
        "These come from pipeline.validated_input or prior step context\n"
        "- output_context_keys: keys the step writes into pipeline context\n\n"
        "IMPORTANT: instruction_fields are what the LLM RETURNS, not what it receives. "
        "For a sentiment classifier, instruction_fields would be [sentiment, topic], "
        "and input_variables would be [text].\n\n"
        "Naming: Instructions class = '{Prefix}Instructions', Context = '{Prefix}Context'. "
        "Use Python type annotations (str, int, float, bool, list[str], etc)."
    ),
    "required_variables": [],
    "description": "System prompt for requirements analysis - parses NL into structured step specs",
}

CODE_GENERATION_SYSTEM: dict = {
    "prompt_key": "code_generation",
    "prompt_name": "Code Generation System",
    "prompt_type": "system",
    "category": "step_creator",
    "step_name": "code_generation",
    "content": (
        FRAMEWORK_REFERENCE + "\n"
        "## Your Task: Code Generation\n\n"
        "Generate Python method **bodies** for a pipeline step. These bodies are inserted "
        "into a Jinja2 template -- you do NOT write the full file, class definition, "
        "or method signatures.\n\n"
        "### What you output:\n"
        "- imports: additional import statements needed BEYOND the template defaults "
        "(the template already provides `from llm_pipeline.step import LLMStep, step_definition`). "
        "Include cross-file imports like `from .schemas import {Prefix}Context` if referenced in method bodies.\n"
        "- prepare_calls_body: body of prepare_calls(). Returns list[dict] with 'variables' key. "
        "Access input via self.pipeline.validated_input.<field>, prior context via "
        "self.pipeline.context.get('<key>'). Do NOT include the `def` line.\n"
        "- process_instructions_body: body of process_instructions(self, instructions). "
        "Receives list[InstructionsClass], returns a Context instance. "
        "Access first result via instructions[0]. Do NOT include the `def` line.\n"
        "- extraction_method_body: optional body for PipelineExtraction.default() (None if not needed)\n"
        "- should_skip_condition: optional boolean expression for should_skip() (None if never skip)\n\n"
        "### Template context\n"
        "The step.py.j2 template already imports:\n"
        "- `from llm_pipeline.step import LLMStep, step_definition`\n"
        "- Your `imports` list items are inserted below that\n\n"
        "The instructions.py.j2 template is a SEPARATE file. If your method bodies "
        "reference the Context class (e.g. `return SentimentContext(...)`), you MUST include "
        "`from .schemas import SentimentContext` in your imports list.\n\n"
        "### Example\n"
        "For a sentiment analysis step:\n"
        "```\n"
        "imports: ['from .schemas import SentimentAnalysisContext']\n"
        "prepare_calls_body: 'return [{\"variables\": {\"text\": self.pipeline.validated_input.text}}]'\n"
        "process_instructions_body: |\n"
        "  inst = instructions[0]\n"
        "  return SentimentAnalysisContext(sentiment=inst.sentiment, confidence=inst.confidence)\n"
        "```\n\n"
        "You have access to Context7 tools for looking up library documentation. "
        "Use primarily for llm-pipeline framework docs, but also available for other libraries."
    ),
    "required_variables": [],
    "description": "System prompt for code generation - generates method bodies for step templates",
}

PROMPT_GENERATION_SYSTEM: dict = {
    "prompt_key": "prompt_generation",
    "prompt_name": "Prompt Generation System",
    "prompt_type": "system",
    "category": "step_creator",
    "step_name": "prompt_generation",
    "content": (
        FRAMEWORK_REFERENCE + "\n"
        "## Your Task: Prompt Generation\n\n"
        "Write system and user prompts for an llm-pipeline step.\n\n"
        "### CRITICAL ANTI-PATTERN\n"
        "Do NOT describe JSON output schema, field names, types, or output structure "
        "in the system prompt. pydantic-ai handles structured output automatically from "
        "the Instructions class. The LLM never sees JSON formatting instructions.\n\n"
        "BAD system prompt:\n"
        "```\n"
        "Analyze sentiment. Return JSON with fields: sentiment (str), confidence (float 0-1).\n"
        "```\n\n"
        "GOOD system prompt:\n"
        "```\n"
        "You are a sentiment analysis expert. Classify the sentiment of the provided text "
        "as positive, negative, or neutral. Consider tone, word choice, and context.\n"
        "```\n\n"
        "### What the system prompt SHOULD contain:\n"
        "- LLM role definition (who it is)\n"
        "- Task description (what it does)\n"
        "- Domain constraints and guidelines (how to do it well)\n"
        "- Quality criteria or edge cases\n\n"
        "### What the user prompt SHOULD contain:\n"
        "- Concise presentation of the input data\n"
        "- {variable_name} placeholders for each input variable\n"
        "- Rendered with Python str.format(), so use single braces\n\n"
        "### Your output:\n"
        "- system_prompt_content: role + task + constraints (NO output schema)\n"
        "- user_prompt_template: input template with {placeholders}\n"
        "- required_variables: list of variable names used as {placeholders}\n"
        "- prompt_category: category string (use step_name prefix)\n\n"
        "You will receive the instruction_fields so you know what the Instructions class "
        "already defines. Do NOT duplicate that information in the prompts.\n\n"
        "You have access to Context7 tools for looking up library documentation. "
        "Use primarily for llm-pipeline framework docs, but also available for other libraries."
    ),
    "required_variables": [],
    "description": "System prompt for prompt generation - writes role/task prompts without output schemas",
}

CODE_VALIDATION_SYSTEM: dict = {
    "prompt_key": "code_validation",
    "prompt_name": "Code Validation System",
    "prompt_type": "system",
    "category": "step_creator",
    "step_name": "code_validation",
    "content": (
        FRAMEWORK_REFERENCE + "\n"
        "## Your Task: Code Validation\n\n"
        "Review generated code artifacts for correctness and convention compliance.\n\n"
        "Check for:\n"
        "- Syntax errors or invalid Python\n"
        "- Missing cross-file imports (e.g. step code references Context class but "
        "doesn't import from .schemas)\n"
        "- Incorrect method signatures (prepare_calls, process_instructions)\n"
        "- Wrong return types (prepare_calls -> list[dict], process_instructions -> Context)\n"
        "- Naming convention violations ({Prefix}Instructions, {Prefix}Context, {Prefix}Step)\n"
        "- System prompt describing JSON output schema (anti-pattern: pydantic-ai handles this)\n"
        "- Type annotation errors or missing annotations\n"
        "- Logic errors in method bodies\n\n"
        "Output:\n"
        "- is_valid: true if ready to use, false if blocking issues\n"
        "- issues: list of specific problems (empty if none)\n"
        "- suggestions: optional improvements (non-blocking)\n"
        "- naming_valid, imports_valid, type_annotations_valid: booleans\n\n"
        "Be strict about blocking issues. is_valid=false requires at least one issue."
    ),
    "required_variables": [],
    "description": "System prompt for code validation - reviews code with framework-specific checks",
}

# ---------------------------------------------------------------------------
# User prompts
# ---------------------------------------------------------------------------

REQUIREMENTS_ANALYSIS_USER: dict = {
    "prompt_key": "requirements_analysis",
    "prompt_name": "Requirements Analysis User",
    "prompt_type": "user",
    "category": "step_creator",
    "step_name": "requirements_analysis",
    "content": (
        "Parse the following pipeline step description into a structured specification:\n\n"
        "{description}"
    ),
    "required_variables": ["description"],
    "description": "User prompt for requirements analysis step",
}

CODE_GENERATION_USER: dict = {
    "prompt_key": "code_generation",
    "prompt_name": "Code Generation User",
    "prompt_type": "user",
    "category": "step_creator",
    "step_name": "code_generation",
    "content": (
        "Generate Python method bodies for the following pipeline step:\n\n"
        "Step name: {step_name}\n"
        "Step class name: {step_class_name}\n"
        "Description: {description}\n\n"
        "Instructions fields (what the LLM returns as structured output):\n{instruction_fields}\n\n"
        "Context fields (passed to downstream steps):\n{context_fields}\n\n"
        "Input variables (fill user prompt placeholders):\n{input_variables}\n\n"
        "Output context keys (written to pipeline.context):\n{output_context_keys}"
    ),
    "required_variables": [
        "step_name",
        "step_class_name",
        "description",
        "instruction_fields",
        "context_fields",
        "input_variables",
        "output_context_keys",
    ],
    "description": "User prompt for code generation step",
}

PROMPT_GENERATION_USER: dict = {
    "prompt_key": "prompt_generation",
    "prompt_name": "Prompt Generation User",
    "prompt_type": "user",
    "category": "step_creator",
    "step_name": "prompt_generation",
    "content": (
        "Write system and user prompts for the following pipeline step:\n\n"
        "Step name: {step_name}\n"
        "Description: {description}\n"
        "Input variables (for user prompt placeholders): {input_variables}\n\n"
        "The Instructions class already defines these output fields (do NOT describe "
        "them in the system prompt):\n{instruction_fields}"
    ),
    "required_variables": ["step_name", "description", "input_variables", "instruction_fields"],
    "description": "User prompt for prompt generation step",
}

CODE_VALIDATION_USER: dict = {
    "prompt_key": "code_validation",
    "prompt_name": "Code Validation User",
    "prompt_type": "user",
    "category": "step_creator",
    "step_name": "code_validation",
    "content": (
        "Review the following generated code artifacts:\n\n"
        "## Step Code\n```python\n{step_code}\n```\n\n"
        "## Instructions Code\n```python\n{instructions_code}\n```\n\n"
        "## Extraction Code\n```python\n{extraction_code}\n```\n\n"
        "## System Prompt\n{system_prompt}\n\n"
        "## User Prompt Template\n{user_prompt_template}"
    ),
    "required_variables": [
        "step_code",
        "instructions_code",
        "extraction_code",
        "system_prompt",
        "user_prompt_template",
    ],
    "description": "User prompt for code validation step",
}

# All prompts for iteration
ALL_PROMPTS: list[dict] = [
    REQUIREMENTS_ANALYSIS_SYSTEM,
    REQUIREMENTS_ANALYSIS_USER,
    CODE_GENERATION_SYSTEM,
    CODE_GENERATION_USER,
    PROMPT_GENERATION_SYSTEM,
    PROMPT_GENERATION_USER,
    CODE_VALIDATION_SYSTEM,
    CODE_VALIDATION_USER,
]


def _content_hash(content: str) -> str:
    """Short hash of prompt content for change detection."""
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _seed_prompts(cls: type, engine: "Engine") -> None:
    """Create GenerationRecord table and upsert seed prompts.

    Inserts new prompts via save_new_version if missing, or if content hash
    differs from existing latest version. No-op when content unchanged.

    Args:
        cls: The pipeline class (used for logging context only).
        engine: SQLAlchemy engine for DB operations.
    """
    from llm_pipeline.creator.models import GenerationRecord
    from llm_pipeline.db.versioning import get_latest, save_new_version

    SQLModel.metadata.create_all(engine, tables=[GenerationRecord.__table__])

    inserted = 0
    updated = 0
    with Session(engine) as session:
        for prompt_data in ALL_PROMPTS:
            key_filters = {
                "prompt_key": prompt_data["prompt_key"],
                "prompt_type": prompt_data["prompt_type"],
            }
            existing = get_latest(session, Prompt, **key_filters)

            if existing is None:
                new_fields = {
                    k: v for k, v in prompt_data.items()
                    if k not in ("prompt_key", "prompt_type", "version",
                                 "is_active", "is_latest", "created_at", "updated_at")
                }
                save_new_version(session, Prompt, key_filters, new_fields)
                inserted += 1
            elif _content_hash(existing.content) != _content_hash(prompt_data["content"]):
                new_fields = {
                    k: v for k, v in prompt_data.items()
                    if k not in ("prompt_key", "prompt_type", "version",
                                 "is_active", "is_latest", "created_at", "updated_at")
                }
                save_new_version(session, Prompt, key_filters, new_fields)
                updated += 1
        session.commit()
    logger.info(
        "Seed prompts for %s: %d inserted, %d updated, %d total",
        cls.__name__, inserted, updated, len(ALL_PROMPTS),
    )


__all__ = ["ALL_PROMPTS", "_seed_prompts"]
