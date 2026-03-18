"""Jinja2 template environment and rendering utilities for step code generation."""

import pprint as _pprint
import textwrap as _textwrap

try:
    from jinja2 import Environment, PackageLoader, StrictUndefined
except ImportError:
    raise ImportError(
        "llm-pipeline[creator] required: pip install llm-pipeline[creator]"
    )

from llm_pipeline.naming import to_snake_case


def _camel_case(value: str) -> str:
    """Convert snake_case string to CamelCase."""
    return value.title().replace("_", "")


def _indent_code(code: str, width: int = 4) -> str:
    """Add *width* spaces of indentation to each line of *code*.

    Empty lines are preserved without trailing whitespace.
    """
    prefix = " " * width
    lines: list[str] = []
    for line in code.splitlines():
        lines.append(f"{prefix}{line}" if line.strip() else "")
    return "\n".join(lines)


def _format_dict(value: dict, indent: int = 4) -> str:
    """Format a Python dict as a clean, indented literal string.

    Produces output like::

        {
            "key": "value",
            "nested": [1, 2, 3],
        }

    Continuation lines are indented by *indent* spaces so the result
    can be dropped into a class body at a given indentation level.
    """
    raw = _pprint.pformat(value, width=72, sort_dicts=False)
    # pformat may produce single-line or multi-line output.
    # For multi-line, re-indent all lines after the first.
    lines = raw.splitlines()
    if len(lines) <= 1:
        return raw
    prefix = " " * indent
    result_lines = [lines[0]]
    for line in lines[1:]:
        result_lines.append(f"{prefix}{line}")
    return "\n".join(result_lines)


def get_template_env() -> Environment:
    """Build a Jinja2 Environment configured for Python code generation.

    * PackageLoader points at ``llm_pipeline.creator/templates``
    * ``trim_blocks`` / ``lstrip_blocks`` keep generated Python clean
    * ``StrictUndefined`` ensures missing template vars raise immediately
    """
    env = Environment(
        loader=PackageLoader("llm_pipeline.creator", "templates"),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )

    env.filters["snake_case"] = to_snake_case
    env.filters["camel_case"] = _camel_case
    env.filters["indent_code"] = _indent_code
    env.filters["format_dict"] = _format_dict

    return env


def render_template(template_name: str, **context: object) -> str:
    """Render *template_name* with the given context variables."""
    return get_template_env().get_template(template_name).render(**context)


__all__ = ["get_template_env", "render_template"]
