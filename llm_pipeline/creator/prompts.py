"""Prompt constants and seeding for the StepCreator meta-pipeline."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlmodel import Session, SQLModel, select

from llm_pipeline.db.prompt import Prompt

if TYPE_CHECKING:
    from sqlalchemy import Engine

logger = logging.getLogger(__name__)

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
        "You are an expert in the llm-pipeline framework. Your task is to parse a "
        "natural language description of a pipeline step and produce a structured "
        "specification.\n\n"
        "From the description, extract:\n"
        "- step_name: snake_case name for the step (e.g. 'sentiment_analysis')\n"
        "- step_class_name: PascalCase class name ending in 'Step' (e.g. 'SentimentAnalysisStep')\n"
        "- description: concise one-sentence description of what the step does\n"
        "- instruction_fields: list of fields for the LLMResultMixin subclass, each with "
        "name, type_annotation, description, default (if optional), and is_required\n"
        "- context_fields: list of fields for the PipelineContext subclass that stores "
        "outputs for downstream steps\n"
        "- extraction_targets: list of SQLModel extraction targets if the step persists "
        "data to DB (empty list if not needed)\n"
        "- input_variables: list of variable names expected from pipeline.validated_input "
        "or prior step context\n"
        "- output_context_keys: list of keys the step will write into pipeline context\n\n"
        "Follow llm-pipeline naming conventions: Instructions class is "
        "'{StepPrefix}Instructions', Context class is '{StepPrefix}Context'. "
        "Use Python type annotations (str, int, float, bool, list[str], dict[str, str], etc). "
        "For optional fields include a sensible default value as a string representation."
    ),
    "required_variables": [],
    "description": "System prompt for requirements analysis step - parses NL descriptions into structured step specs",
}

CODE_GENERATION_SYSTEM: dict = {
    "prompt_key": "code_generation",
    "prompt_name": "Code Generation System",
    "prompt_type": "system",
    "category": "step_creator",
    "step_name": "code_generation",
    "content": (
        "You are an expert Python developer specialising in the llm-pipeline framework. "
        "Your task is to generate Python method bodies for a pipeline step class.\n\n"
        "You will receive the step specification and must output:\n"
        "- imports: list of additional import statements needed (beyond framework defaults)\n"
        "- prepare_calls_body: the body of the prepare_calls() method (indented 8 spaces). "
        "This method returns a list of dicts, each with a 'variables' key containing "
        "template variable values for the LLM prompt. Access input via "
        "self.pipeline.validated_input.<field> and prior context via self.pipeline.context.<field>.\n"
        "- process_instructions_body: the body of the process_instructions(self, instructions) "
        "method (indented 8 spaces). This method receives a list of LLMResultMixin instances "
        "and must return a PipelineContext subclass instance. Access the first result via "
        "instructions[0]. Convert to context using .model_dump() as needed.\n"
        "- extraction_method_body: optional body for a PipelineExtraction.default() method "
        "if the step writes to a database table (None if not needed)\n"
        "- should_skip_condition: optional boolean expression string for should_skip() "
        "(None if the step should never be skipped)\n\n"
        "Framework conventions:\n"
        "- self.pipeline.validated_input gives access to pipeline input fields\n"
        "- self.pipeline.context gives access to accumulated pipeline context\n"
        "- prepare_calls() returns list[dict] where each dict has 'variables' key\n"
        "- process_instructions() receives list[Instructions] and returns a Context instance\n"
        "- All method bodies must be valid Python syntax\n"
        "- Use type annotations throughout\n"
        "- Keep method bodies concise and focused on the step's core logic"
    ),
    "required_variables": [],
    "description": "System prompt for code generation step - generates Python method bodies for prepare_calls/process_instructions",
}

PROMPT_GENERATION_SYSTEM: dict = {
    "prompt_key": "prompt_generation",
    "prompt_name": "Prompt Generation System",
    "prompt_type": "system",
    "category": "step_creator",
    "step_name": "prompt_generation",
    "content": (
        "You are an expert prompt engineer specialising in structured LLM outputs. "
        "Your task is to write system and user prompts for an llm-pipeline step.\n\n"
        "You will receive the step name, description, and input variables, and must output:\n"
        "- system_prompt_content: the system prompt that instructs the LLM on its role and "
        "the structure of its output. Be explicit about every field it must return, including "
        "types and constraints. End with a reminder to return valid JSON.\n"
        "- user_prompt_template: the user-facing prompt template using {variable_name} "
        "placeholders for each input variable. This template is rendered with Python "
        "str.format() so use single braces.\n"
        "- required_variables: list of variable names used as {placeholders} in the user template\n"
        "- prompt_category: the category string for DB storage (use the step_name prefix)\n\n"
        "Prompt quality guidelines:\n"
        "- System prompt must describe the output schema completely so pydantic-ai can "
        "validate the structured response\n"
        "- Be specific about field names, types, and valid values in the system prompt\n"
        "- User prompt template should be concise and present all relevant context clearly\n"
        "- Use markdown formatting (headers, bullet lists) in system prompts for clarity\n"
        "- Avoid ambiguity - the LLM must know exactly what to return"
    ),
    "required_variables": [],
    "description": "System prompt for prompt generation step - writes system/user prompts with variable placeholders",
}

CODE_VALIDATION_SYSTEM: dict = {
    "prompt_key": "code_validation",
    "prompt_name": "Code Validation System",
    "prompt_type": "system",
    "category": "step_creator",
    "step_name": "code_validation",
    "content": (
        "You are an expert Python code reviewer specialising in the llm-pipeline framework. "
        "Your task is to review generated code artifacts for correctness and convention compliance.\n\n"
        "Review the provided step code, instructions code, extraction code, and prompts, then output:\n"
        "- is_valid: true if the code is correct and ready to use, false if there are blocking issues\n"
        "- issues: list of specific problems found (empty list if none). Focus on:\n"
        "  * Syntax errors or invalid Python\n"
        "  * Missing required imports\n"
        "  * Incorrect method signatures (prepare_calls, process_instructions)\n"
        "  * Wrong return types (prepare_calls must return list[dict], process_instructions must return Context)\n"
        "  * Naming convention violations ({StepPrefix}Instructions, {StepPrefix}Context, {StepPrefix}Step)\n"
        "  * Type annotation errors or missing annotations\n"
        "  * Logic errors in method bodies\n"
        "- suggestions: list of optional improvements (non-blocking). Empty list if none.\n"
        "- naming_valid: true if all class names follow llm-pipeline conventions\n"
        "- imports_valid: true if all referenced names have corresponding imports\n"
        "- type_annotations_valid: true if all public methods and fields have type annotations\n\n"
        "Be strict about blocking issues but reasonable about style. "
        "A result with is_valid=false must have at least one entry in issues."
    ),
    "required_variables": [],
    "description": "System prompt for code validation step - reviews generated code for correctness and convention compliance",
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
        "Step class name: {step_class_name}\n\n"
        "Instructions fields (LLMResultMixin):\n{instruction_fields}\n\n"
        "Context fields (PipelineContext):\n{context_fields}\n\n"
        "Input variables (from validated_input or prior context):\n{input_variables}\n\n"
        "Output context keys (written to pipeline.context):\n{output_context_keys}"
    ),
    "required_variables": [
        "step_name",
        "step_class_name",
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
        "Input variables available in user prompt: {input_variables}"
    ),
    "required_variables": ["step_name", "description", "input_variables"],
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


def seed_prompts(cls: type, engine: "Engine") -> None:
    """Create GenerationRecord table and idempotently seed prompts.

    Args:
        cls: The pipeline class (used for logging context only).
        engine: SQLAlchemy engine for DB operations.
    """
    from llm_pipeline.creator.models import GenerationRecord

    SQLModel.metadata.create_all(engine, tables=[GenerationRecord.__table__])

    with Session(engine) as session:
        for prompt_data in ALL_PROMPTS:
            existing = session.exec(
                select(Prompt).where(
                    Prompt.prompt_key == prompt_data["prompt_key"],
                    Prompt.prompt_type == prompt_data["prompt_type"],
                )
            ).first()
            if existing is None:
                session.add(Prompt(**prompt_data))
        session.commit()
    logger.info("Seeded %d prompts for %s", len(ALL_PROMPTS), cls.__name__)


__all__ = ["ALL_PROMPTS", "seed_prompts"]
