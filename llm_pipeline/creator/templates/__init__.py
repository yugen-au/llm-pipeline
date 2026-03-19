"""Jinja2 template environment and rendering utilities for step code generation."""

from functools import lru_cache

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

    Produces output matching the hand-written style used in the demo::

        {
            "key": "value",
            "nested": [{"a": 1}, {"b": 2}],
        }

    *indent* controls the indentation of entries relative to the opening
    brace.  The closing brace aligns with the opening brace (column 0 of
    the returned string).  Each top-level key gets its own line; nested
    values use ``repr()``.
    """
    if not value:
        return "{}"
    prefix = " " * indent
    lines = ["{"]
    for key, val in value.items():
        lines.append(f"{prefix}{key!r}: {val!r},")
    lines.append("}")
    return "\n".join(lines)


@lru_cache(maxsize=None)
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
