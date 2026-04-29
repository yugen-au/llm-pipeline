"""
Instruction and context schemas for the meta-pipeline step generator.

Defines 4 Instructions classes (LLMResultMixin subclasses) and 4 step-output
data classes (plain BaseModel subclasses) corresponding to the 4-step creator
pipeline: RequirementsAnalysis, CodeGeneration, PromptGeneration,
CodeValidation.

Note: the ``*Context`` classes here predate the Bind+StepInputs contract and
are pending migration alongside the ``register_agent`` removal. They retain
their names for now because creator's own ``steps.py`` still references them
under the legacy contract.
"""
from typing import ClassVar

from pydantic import BaseModel

from llm_pipeline.graph.instructions import LLMResultMixin

from .models import ExtractionTarget, FieldDefinition


# ---------------------------------------------------------------------------
# Instructions
# ---------------------------------------------------------------------------


class RequirementsAnalysisInstructions(LLMResultMixin):
    """Structured output from requirements analysis of a step description."""

    step_name: str = ""
    step_class_name: str = ""
    description: str = ""
    instruction_fields: list[FieldDefinition] = []
    context_fields: list[FieldDefinition] = []
    extraction_targets: list[ExtractionTarget] = []
    input_variables: list[str] = []
    output_context_keys: list[str] = []

    example: ClassVar[dict] = {
        "step_name": "sentiment_analysis",
        "step_class_name": "SentimentAnalysisStep",
        "description": "Analyze sentiment of input text",
        "instruction_fields": [
            {
                "name": "sentiment",
                "type_annotation": "str",
                "description": "Detected sentiment label",
                "default": '""',
                "is_required": True,
            },
            {
                "name": "explanation",
                "type_annotation": "str",
                "description": "Reasoning for the sentiment label",
                "default": '""',
                "is_required": True,
            },
        ],
        "context_fields": [
            {
                "name": "sentiment",
                "type_annotation": "str",
                "description": "Sentiment value passed to downstream steps",
                "default": None,
                "is_required": True,
            },
        ],
        "extraction_targets": [],
        "input_variables": ["text"],
        "output_context_keys": ["sentiment"],
        "confidence_score": 0.92,
    }


class CodeGenerationInstructions(LLMResultMixin):
    """Structured output containing method bodies for generated step code."""

    imports: list[str] = []
    prepare_calls_body: str = ""
    process_instructions_body: str = ""
    extraction_method_body: str | None = None
    should_skip_condition: str | None = None

    example: ClassVar[dict] = {
        "imports": [
            "from llm_pipeline.step import LLMStep, step_definition",
        ],
        "prepare_calls_body": (
            'return [{"variables": {"text": self.pipeline.validated_input.text}}]'
        ),
        "process_instructions_body": (
            "return SentimentAnalysisContext(sentiment=instructions[0].sentiment)"
        ),
        "extraction_method_body": None,
        "should_skip_condition": None,
        "confidence_score": 0.88,
    }


class PromptGenerationInstructions(LLMResultMixin):
    """Structured output for generated system and user prompts."""

    system_prompt_content: str = ""
    user_prompt_template: str = ""
    required_variables: list[str] = []
    prompt_category: str = ""

    example: ClassVar[dict] = {
        "system_prompt_content": (
            "You are an expert sentiment analyst. Analyze the sentiment of "
            "the provided text and return a structured result."
        ),
        "user_prompt_template": "Analyze the sentiment of: {text}",
        "required_variables": ["text"],
        "prompt_category": "text_analysis",
        "confidence_score": 0.90,
    }


class CodeValidationInstructions(LLMResultMixin):
    """Structured output from LLM code review of generated artifacts."""

    is_valid: bool = False
    issues: list[str] = []
    suggestions: list[str] = []
    naming_valid: bool = False
    imports_valid: bool = False
    type_annotations_valid: bool = False

    example: ClassVar[dict] = {
        "is_valid": True,
        "issues": [],
        "suggestions": ["Consider adding a docstring to process_instructions"],
        "naming_valid": True,
        "imports_valid": True,
        "type_annotations_valid": True,
        "confidence_score": 0.95,
    }


# ---------------------------------------------------------------------------
# Contexts
# ---------------------------------------------------------------------------


class RequirementsAnalysisContext(BaseModel):
    """Context produced by the requirements analysis step."""

    step_name: str
    step_class_name: str
    instruction_fields: list[dict]
    context_fields: list[dict]
    extraction_targets: list[dict]
    input_variables: list[str]
    output_context_keys: list[str]


class CodeGenerationContext(BaseModel):
    """Context produced by the code generation step."""

    step_code: str
    instructions_code: str
    extraction_code: str | None


class PromptGenerationContext(BaseModel):
    """Context produced by the prompt generation step."""

    system_prompt: str
    user_prompt_template: str
    required_variables: list[str]
    prompt_yaml: str


class CodeValidationContext(BaseModel):
    """Context produced by the code validation step."""

    is_valid: bool
    syntax_valid: bool
    llm_review_valid: bool
    issues: list[str]
    all_artifacts: dict[str, str]
    sandbox_valid: bool = False
    sandbox_skipped: bool = True
    sandbox_output: str | None = None


__all__ = [
    "RequirementsAnalysisInstructions",
    "CodeGenerationInstructions",
    "PromptGenerationInstructions",
    "CodeValidationInstructions",
    "RequirementsAnalysisContext",
    "CodeGenerationContext",
    "PromptGenerationContext",
    "CodeValidationContext",
]
