"""Prompt utility functions."""
import re
from typing import List


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
