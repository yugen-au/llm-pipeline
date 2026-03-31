"""Prompt utility functions.

Includes content variable extraction, version helpers, and naming
utilities ported from logistics-intelligence prompt_variables/utils.py.
"""
import re
from typing import List, Tuple, Type


def extract_variables_from_content(content: str) -> List[str]:
    """Extract variable names from prompt content.

    Finds all {variable_name} patterns and returns unique variable names.
    """
    pattern = r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}'
    variables = re.findall(pattern, content)
    seen = set()
    unique_vars = []
    for var in variables:
        if var not in seen:
            seen.add(var)
            unique_vars.append(var)
    return unique_vars


def _increment_version(current: str) -> str:
    """Bump patch version: '1.0' -> '1.1', '2.3.1' -> '2.3.2'."""
    parts = [int(x) for x in current.split(".")]
    parts[-1] += 1
    return ".".join(str(p) for p in parts)


# ---------------------------------------------------------------------------
# Naming utilities (ported from logistics-intelligence)
# ---------------------------------------------------------------------------


def to_pascal_case(snake_str: str) -> str:
    """Convert snake_case to PascalCase.

    >>> to_pascal_case("table_type_detection")
    'TableTypeDetection'
    """
    return ''.join(word.capitalize() for word in snake_str.split('_'))


def parse_key_path(key: str) -> Tuple[str, List[str]]:
    """Parse prompt key into base and nested parts.

    >>> parse_key_path("constraint_extraction.lane_based")
    ('constraint_extraction', ['lane_based'])
    """
    parts = key.split('.')
    return parts[0], parts[1:]


def get_prompt_key_from_class(variable_class: Type) -> Tuple[str, str]:
    """Derive (prompt_key, prompt_type) from a variable class's qualname.

    Reverses the naming convention: class qualname like
    "SemanticMappingVariables.User" -> ("semantic_mapping", "user").

    >>> # For a class with __qualname__ = "SentimentAnalysisVars"
    >>> # This would need actual class input to test
    """
    qualname = variable_class.__qualname__
    parts = qualname.split('.')

    # Last part is System or User
    prompt_type = parts[-1].lower()

    # Everything before is the class hierarchy
    key_parts = []
    for part in parts[:-1]:
        if part.endswith('Variables'):
            part = part[:-9]
        snake = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', part)
        snake = re.sub(r'([a-z\d])([A-Z])', r'\1_\2', snake)
        key_parts.append(snake.lower())

    return '.'.join(key_parts), prompt_type
