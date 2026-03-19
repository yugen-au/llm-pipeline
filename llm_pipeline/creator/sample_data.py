"""
Auto-generate sample test data from FieldDefinition specs.

Used by sandbox testing to produce realistic input data for
validating LLM-generated step code without manual fixture creation.
"""

from __future__ import annotations

import ast
import copy
import json
import re
from typing import Any, ClassVar

from .models import FieldDefinition


class SampleDataGenerator:
    """Generate sample data dicts from a list of FieldDefinition objects.

    Maps type annotations to sensible defaults. Handles Optional[X],
    X | None, default values (parsed eval-safe), and unknown types
    (string fallback, never raises).
    """

    _TYPE_MAP: ClassVar[dict[str, Any]] = {
        "str": "test_{name}",
        "int": 1,
        "float": 1.0,
        "bool": True,
        "list[str]": ["test_item"],
        "dict[str, str]": {"key": "value"},
        "list[int]": [1],
        "dict[str, Any]": {"key": "value"},
    }

    # Pattern: Optional[X] -> X
    _OPTIONAL_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"^Optional\[(.+)\]$"
    )
    # Pattern: X | None or None | X
    _UNION_NONE_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"^(.+?)\s*\|\s*None$|^None\s*\|\s*(.+)$"
    )

    @staticmethod
    def _strip_optional(type_annotation: str) -> tuple[str, bool]:
        """Strip Optional/None union wrapper, return (inner_type, was_optional)."""
        # Optional[X]
        m = SampleDataGenerator._OPTIONAL_RE.match(type_annotation.strip())
        if m:
            return m.group(1).strip(), True

        # X | None or None | X
        m = SampleDataGenerator._UNION_NONE_RE.match(type_annotation.strip())
        if m:
            inner = (m.group(1) or m.group(2)).strip()
            return inner, True

        return type_annotation.strip(), False

    @staticmethod
    def _parse_default(default: str) -> Any:
        """Parse a default value string safely.

        Handles string literals ('""', "'hello'"), numeric literals,
        None, True, False, lists, dicts. Uses ast.literal_eval for
        safety -- never calls eval().
        """
        stripped = default.strip()

        # Explicit None
        if stripped == "None":
            return None

        try:
            return ast.literal_eval(stripped)
        except (ValueError, SyntaxError):
            # Return as raw string if unparseable
            return stripped

    def generate(self, fields: list[FieldDefinition]) -> dict[str, Any]:
        """Generate a sample data dict from field definitions.

        Priority:
        1. field.default (parsed eval-safe) if present
        2. None for optional non-required fields
        3. _TYPE_MAP lookup (with Optional stripping)
        4. String fallback for unknown types
        """
        result: dict[str, Any] = {}

        for field in fields:
            # 1. Has explicit default
            if field.default is not None:
                result[field.name] = self._parse_default(field.default)
                continue

            # Strip optional wrapper for type lookup
            inner_type, is_optional = self._strip_optional(
                field.type_annotation
            )

            # 2. Optional + not required -> None
            if not field.is_required:
                result[field.name] = None
                continue

            # 3. Type map lookup
            if inner_type in self._TYPE_MAP:
                value = self._TYPE_MAP[inner_type]
                # For str type, interpolate field name
                if isinstance(value, str) and "{name}" in value:
                    value = value.format(name=field.name)
                # Deep-copy mutable values to prevent caller corruption
                elif isinstance(value, (list, dict)):
                    value = copy.deepcopy(value)
                result[field.name] = value
            else:
                # 4. Unknown type -> string fallback
                result[field.name] = f"test_{field.name}"

        return result

    def generate_json(self, fields: list[FieldDefinition]) -> str:
        """Generate sample data as a JSON string.

        Uses default=str to handle any non-serializable values.
        """
        return json.dumps(self.generate(fields), default=str)


__all__ = ["SampleDataGenerator"]
