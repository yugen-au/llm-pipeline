"""
Schema flattening and formatting utilities for LLM prompts.

Converts Pydantic JSON schemas into LLM-friendly instructions.
"""
import json
from typing import Any, Dict, Type, TYPE_CHECKING

if TYPE_CHECKING:
    from llm_pipeline.step import LLMResultMixin


def flatten_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten a Pydantic JSON schema by inlining all $ref references.

    Removes the $defs section and replaces all $ref pointers with the actual
    definitions they reference.

    Args:
        schema: Pydantic JSON schema with potential $defs and $ref

    Returns:
        Flattened schema with all references inlined
    """
    defs = schema.get("$defs", {})

    def resolve_ref(ref_path: str) -> Dict[str, Any]:
        if not ref_path.startswith("#/$defs/"):
            return {}
        def_name = ref_path.split("/")[-1]
        return defs.get(def_name, {})

    def inline_refs(obj: Any) -> Any:
        if isinstance(obj, dict):
            if "$ref" in obj:
                resolved = resolve_ref(obj["$ref"])
                return inline_refs(resolved.copy())
            else:
                return {k: inline_refs(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [inline_refs(item) for item in obj]
        else:
            return obj

    flattened = inline_refs(schema.copy())

    if "$defs" in flattened:
        del flattened["$defs"]
    if "examples" in flattened:
        del flattened["examples"]

    return flattened


def format_schema_for_llm(result_class: Type["LLMResultMixin"]) -> str:
    """
    Format a Pydantic model into clear, LLM-friendly instructions.

    Generates the JSON schema from result_class, flattens it by inlining $refs,
    then presents it along with the example from result_class.get_example().

    Args:
        result_class: Pydantic model class (must inherit from LLMResultMixin)

    Returns:
        Formatted string with flattened schema and example
    """
    output = []

    schema = result_class.model_json_schema()
    flattened = flatten_schema(schema)

    output.append("EXPECTED JSON SCHEMA:")
    output.append(json.dumps(flattened, indent=2))
    output.append("")

    example_instance = result_class.get_example()
    if example_instance:
        output.append(
            "RESPONSE FORMAT EXAMPLE (do NOT copy these values - analyze the actual data):"
        )
        output.append(json.dumps(example_instance.model_dump(), indent=2))
        output.append("")

    output.append(
        "IMPORTANT: Respond with ONLY valid JSON matching the schema above. "
        "Do not include explanations, commentary, or any text before or after the JSON object."
    )

    return "\n".join(output)


__all__ = ["flatten_schema", "format_schema_for_llm"]
