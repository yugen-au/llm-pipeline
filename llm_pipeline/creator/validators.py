"""
Validator factories for the meta-pipeline's code generation output.

Provides python_syntax_validator() and naming_convention_validator() which
return callables compatible with agent.output_validator(). Each factory
follows the same pattern as llm_pipeline/validators.py: async inner
function with __name__/__qualname__ set, returned by the outer factory.
"""
from __future__ import annotations

import ast
import re
from typing import Any

from pydantic_ai import ModelRetry, RunContext

from llm_pipeline.agent_builders import StepDeps

_STEP_SUFFIX_RE = re.compile(r"Step$")


def python_syntax_validator() -> Any:
    """Factory: returns an output validator that checks Python syntax.

    Parses string code-body fields (prepare_calls_body,
    process_instructions_body, extraction_method_body) via ast.parse().
    Each body is wrapped in ``def f():\\n{indented_body}`` before parsing
    to provide valid syntax context for method-level snippets.

    Raises ModelRetry on SyntaxError with a descriptive message including
    the field name and the parser error details.
    """

    _BODY_FIELDS = (
        "prepare_calls_body",
        "process_instructions_body",
        "extraction_method_body",
    )

    async def _python_syntax_validator(
        ctx: RunContext[StepDeps], output: Any
    ) -> Any:
        for field_name in _BODY_FIELDS:
            body = getattr(output, field_name, None)
            if body is None or not isinstance(body, str) or not body.strip():
                continue

            # Indent each line of the body by 4 spaces inside a stub function
            indented = "\n".join(
                f"    {line}" for line in body.splitlines()
            )
            stub = f"def f():\n{indented}"

            try:
                ast.parse(stub, mode="exec")
            except SyntaxError as exc:
                raise ModelRetry(
                    f"SyntaxError in {field_name} (line {exc.lineno}, "
                    f"offset {exc.offset}): {exc.msg}. "
                    f"Please fix the Python syntax and try again."
                ) from exc

        return output

    _python_syntax_validator.__name__ = "python_syntax_validator"
    _python_syntax_validator.__qualname__ = "python_syntax_validator"
    return _python_syntax_validator


def naming_convention_validator() -> Any:
    """Factory: returns an output validator that checks naming conventions.

    Validates that step_class_name ends with "Step" and that the derived
    prefix would produce valid {Prefix}Instructions and {Prefix}Context
    class names (i.e., the prefix is non-empty and a valid Python
    identifier).

    Raises ModelRetry on any naming violation.
    """

    async def _naming_convention_validator(
        ctx: RunContext[StepDeps], output: Any
    ) -> Any:
        class_name = getattr(output, "step_class_name", None)
        if class_name is None or not isinstance(class_name, str):
            return output

        # Must end with "Step"
        if not class_name.endswith("Step"):
            raise ModelRetry(
                f"step_class_name {class_name!r} must end with 'Step'. "
                f"Example: 'DataProcessingStep'."
            )

        # Derive the prefix (everything before "Step")
        prefix = class_name[: -len("Step")]
        if not prefix:
            raise ModelRetry(
                f"step_class_name {class_name!r} has an empty prefix before "
                f"'Step'. Provide a descriptive prefix, e.g. 'DataProcessingStep'."
            )

        # Check that derived class names would be valid identifiers
        instructions_name = f"{prefix}Instructions"
        context_name = f"{prefix}Context"

        if not instructions_name.isidentifier():
            raise ModelRetry(
                f"Derived instructions class name {instructions_name!r} "
                f"is not a valid Python identifier. Adjust step_class_name."
            )

        if not context_name.isidentifier():
            raise ModelRetry(
                f"Derived context class name {context_name!r} "
                f"is not a valid Python identifier. Adjust step_class_name."
            )

        return output

    _naming_convention_validator.__name__ = "naming_convention_validator"
    _naming_convention_validator.__qualname__ = "naming_convention_validator"
    return _naming_convention_validator


__all__ = ["python_syntax_validator", "naming_convention_validator"]
