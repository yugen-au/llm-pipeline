"""
Step definitions for the meta-pipeline step generator.

4 steps chained sequentially:
  RequirementsAnalysis -> CodeGeneration -> PromptGeneration -> CodeValidation

Each step reads prior step results from self.pipeline.context (flat dict keyed
by field names of prior PipelineContext subclasses).
"""
import ast
from datetime import datetime, timezone

from llm_pipeline.extraction import PipelineExtraction
from llm_pipeline.step import LLMStep, step_definition

from .models import GenerationRecord
from .schemas import (
    CodeGenerationContext,
    CodeGenerationInstructions,
    CodeValidationContext,
    CodeValidationInstructions,
    PromptGenerationContext,
    PromptGenerationInstructions,
    RequirementsAnalysisContext,
    RequirementsAnalysisInstructions,
)
from .templates import render_template


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


class GenerationRecordExtraction(PipelineExtraction, model=GenerationRecord):
    """Persists one GenerationRecord per code validation result."""

    def default(self, results: list[CodeValidationInstructions]) -> list[GenerationRecord]:
        """Convert CodeValidationInstructions into GenerationRecord instances."""
        return [
            GenerationRecord(
                run_id=self.pipeline.run_id,
                step_name_generated=self.pipeline.context.get("step_name", ""),
                files_generated=list(
                    self.pipeline.context.get("all_artifacts", {}).keys()
                ),
                is_valid=results[0].is_valid,
                created_at=datetime.now(timezone.utc),
            )
        ]


# ---------------------------------------------------------------------------
# Step 1: RequirementsAnalysis
# ---------------------------------------------------------------------------


@step_definition(
    instructions=RequirementsAnalysisInstructions,
    default_system_key="requirements_analysis",
    default_user_key="requirements_analysis",
    context=RequirementsAnalysisContext,
)
class RequirementsAnalysisStep(LLMStep):
    """Parse a natural language step description into structured specification."""

    def prepare_calls(self):
        return [
            {
                "variables": {
                    "description": self.pipeline.validated_input.description,
                }
            }
        ]

    def process_instructions(self, instructions):
        inst = instructions[0]
        return RequirementsAnalysisContext(
            step_name=inst.step_name,
            step_class_name=inst.step_class_name,
            instruction_fields=[f.model_dump() for f in inst.instruction_fields],
            context_fields=[f.model_dump() for f in inst.context_fields],
            extraction_targets=[t.model_dump() for t in inst.extraction_targets],
            input_variables=inst.input_variables,
            output_context_keys=inst.output_context_keys,
        )


# ---------------------------------------------------------------------------
# Step 2: CodeGeneration
# ---------------------------------------------------------------------------


@step_definition(
    instructions=CodeGenerationInstructions,
    default_system_key="code_generation",
    default_user_key="code_generation",
    context=CodeGenerationContext,
)
class CodeGenerationStep(LLMStep):
    """Generate Python method bodies for prepare_calls and process_instructions."""

    def prepare_calls(self):
        ctx = self.pipeline.context
        return [
            {
                "variables": {
                    "step_name": ctx.get("step_name", ""),
                    "step_class_name": ctx.get("step_class_name", ""),
                    "instruction_fields": ctx.get("instruction_fields", []),
                    "context_fields": ctx.get("context_fields", []),
                    "input_variables": ctx.get("input_variables", []),
                    "output_context_keys": ctx.get("output_context_keys", []),
                }
            }
        ]

    def process_instructions(self, instructions):
        inst = instructions[0]
        ctx = self.pipeline.context

        step_name = ctx.get("step_name", "")
        step_class_name = ctx.get("step_class_name", "")
        instruction_fields = ctx.get("instruction_fields", [])
        context_fields = ctx.get("context_fields", [])
        extraction_targets = ctx.get("extraction_targets", [])

        # Derive prefix and class names from step_class_name
        # e.g. "SentimentAnalysisStep" -> prefix "SentimentAnalysis"
        prefix = step_class_name[:-4] if step_class_name.endswith("Step") else step_class_name
        instructions_class_name = f"{prefix}Instructions"
        context_class_name = f"{prefix}Context"

        step_code = render_template(
            "step.py.j2",
            step_class_name=step_class_name,
            instructions_class_name=instructions_class_name,
            context_class_name=context_class_name,
            step_name=step_name,
            imports=inst.imports,
            prepare_calls_body=inst.prepare_calls_body,
            process_instructions_body=inst.process_instructions_body,
            should_skip_condition=inst.should_skip_condition,
        )

        instructions_code = render_template(
            "instructions.py.j2",
            class_name=instructions_class_name,
            fields=instruction_fields,
            example_dict={},
        )

        extraction_code: str | None = None
        if self.pipeline.validated_input.include_extraction and extraction_targets:
            first_target = extraction_targets[0]
            extraction_code = render_template(
                "extraction.py.j2",
                class_name=f"{first_target['model_name']}Extraction",
                model_name=first_target["model_name"],
                instructions_class_name=instructions_class_name,
                extraction_method_body=inst.extraction_method_body,
                fields=first_target.get("fields", []),
            )

        return CodeGenerationContext(
            step_code=step_code,
            instructions_code=instructions_code,
            extraction_code=extraction_code,
        )


# ---------------------------------------------------------------------------
# Step 3: PromptGeneration
# ---------------------------------------------------------------------------


@step_definition(
    instructions=PromptGenerationInstructions,
    default_system_key="prompt_generation",
    default_user_key="prompt_generation",
    context=PromptGenerationContext,
)
class PromptGenerationStep(LLMStep):
    """Generate system and user prompts for the new step."""

    def prepare_calls(self):
        ctx = self.pipeline.context
        return [
            {
                "variables": {
                    "step_name": ctx.get("step_name", ""),
                    "description": self.pipeline.validated_input.description,
                    "input_variables": ctx.get("input_variables", []),
                    "step_code": ctx.get("step_code", ""),
                    "instructions_code": ctx.get("instructions_code", ""),
                }
            }
        ]

    def process_instructions(self, instructions):
        inst = instructions[0]
        ctx = self.pipeline.context

        prompt_yaml = render_template(
            "prompts.yaml.j2",
            step_name=ctx.get("step_name", ""),
            step_class_name=ctx.get("step_class_name", ""),
            system_content=inst.system_prompt_content,
            user_content=inst.user_prompt_template,
            required_variables=inst.required_variables,
            category=inst.prompt_category,
        )

        return PromptGenerationContext(
            system_prompt=inst.system_prompt_content,
            user_prompt_template=inst.user_prompt_template,
            required_variables=inst.required_variables,
            prompt_yaml=prompt_yaml,
        )


# ---------------------------------------------------------------------------
# Step 4: CodeValidation
# ---------------------------------------------------------------------------


def _syntax_check(code: str | None) -> bool:
    """Return True if code string is syntactically valid Python, False otherwise."""
    if not code:
        return True
    stub = f"def _f():\n"
    indented = "\n".join(f"    {line}" for line in code.splitlines())
    try:
        ast.parse(stub + indented)
        return True
    except SyntaxError:
        return False


@step_definition(
    instructions=CodeValidationInstructions,
    default_system_key="code_validation",
    default_user_key="code_validation",
    default_extractions=[GenerationRecordExtraction],
    context=CodeValidationContext,
)
class CodeValidationStep(LLMStep):
    """Validate generated code via AST parse and LLM review."""

    def prepare_calls(self):
        ctx = self.pipeline.context
        step_name = ctx.get("step_name", "unknown")
        step_code = ctx.get("step_code", "")
        instructions_code = ctx.get("instructions_code", "")
        extraction_code = ctx.get("extraction_code") or ""
        system_prompt = ctx.get("system_prompt", "")
        user_prompt_template = ctx.get("user_prompt_template", "")
        return [
            {
                "variables": {
                    "step_name": step_name,
                    "step_code": step_code,
                    "instructions_code": instructions_code,
                    "extraction_code": extraction_code,
                    "system_prompt": system_prompt,
                    "user_prompt_template": user_prompt_template,
                }
            }
        ]

    def process_instructions(self, instructions):
        inst = instructions[0]
        ctx = self.pipeline.context

        step_name = ctx.get("step_name", "unknown")
        step_code = ctx.get("step_code", "")
        instructions_code = ctx.get("instructions_code", "")
        extraction_code = ctx.get("extraction_code")
        prompt_yaml = ctx.get("prompt_yaml", "")

        # AST syntax checks on the full rendered source files
        step_syntax_ok = _syntax_check(step_code)
        instructions_syntax_ok = _syntax_check(instructions_code)
        extraction_syntax_ok = _syntax_check(extraction_code) if extraction_code else True
        syntax_valid = step_syntax_ok and instructions_syntax_ok and extraction_syntax_ok

        is_valid = syntax_valid and inst.is_valid

        # Build artifact map: filename -> code string
        all_artifacts: dict[str, str] = {
            f"{step_name}_step.py": step_code,
            f"{step_name}_instructions.py": instructions_code,
            f"{step_name}_prompts.py": prompt_yaml,
        }
        if extraction_code:
            all_artifacts[f"{step_name}_extraction.py"] = extraction_code

        return CodeValidationContext(
            is_valid=is_valid,
            syntax_valid=syntax_valid,
            llm_review_valid=inst.is_valid,
            issues=inst.issues,
            all_artifacts=all_artifacts,
        )


__all__ = [
    "RequirementsAnalysisStep",
    "CodeGenerationStep",
    "PromptGenerationStep",
    "CodeValidationStep",
    "GenerationRecordExtraction",
]
