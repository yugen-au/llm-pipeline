"""
Shared utility for CamelCase to snake_case conversion.

Uses the double-regex pattern to correctly handle consecutive capitals
(e.g. HTMLParser -> html_parser, not htmlparser).
"""
import re


def to_snake_case(name: str, strip_suffix: str | None = None) -> str:
    """
    Convert CamelCase name to snake_case.

    Uses double-regex to correctly split consecutive capitals:
      1. Insert underscore between consecutive caps and a cap+lower sequence
      2. Insert underscore between lower/digit and a capital

    Args:
        name: CamelCase string to convert.
        strip_suffix: If provided and name ends with it, strip before converting.

    Returns:
        snake_case string.

    Examples:
        >>> to_snake_case("HTMLParser")
        'html_parser'
        >>> to_snake_case("ConstraintExtractionStep", strip_suffix="Step")
        'constraint_extraction'
        >>> to_snake_case("LaneBasedStrategy", strip_suffix="Strategy")
        'lane_based'
    """
    if strip_suffix and name.endswith(strip_suffix):
        name = name[: -len(strip_suffix)]
    result = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return re.sub(r"([a-z\d])([A-Z])", r"\1_\2", result).lower()


__all__ = ["to_snake_case"]
