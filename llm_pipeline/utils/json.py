"""Best-effort JSON coercion for values that may already be parsed.

Langfuse + OTEL semantic conventions store ``input``/``output``
attributes as JSON-encoded strings (OTEL attributes can't carry
arbitrary objects). Frontend renderers and downstream consumers want
the structured value. ``maybe_parse_json`` parses a string when it
plausibly looks like JSON, otherwise returns it unchanged. Non-string
values pass through.
"""
from __future__ import annotations

import json as _json
from typing import Any

__all__ = ["maybe_parse_json"]


def maybe_parse_json(value: Any) -> Any:
    """Return ``value`` parsed from JSON if it's a JSON-encoded string.

    Heuristic: only attempt ``json.loads`` when the stripped string
    starts with a JSON token (``{``, ``[``, ``"``), is exactly a JSON
    literal (``true`` / ``false`` / ``null``), or is purely numeric.
    Everything else is returned as-is so plain text inputs aren't
    mangled.
    """
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return value
    if (
        stripped[0] not in "{[\""
        and stripped not in ("true", "false", "null")
        and not stripped.lstrip("-").replace(".", "", 1).isdigit()
    ):
        return value
    try:
        return _json.loads(stripped)
    except (ValueError, TypeError):
        return value
