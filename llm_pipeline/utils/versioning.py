"""Version comparison utilities for dotted numeric version strings."""


def compare_versions(a: str, b: str) -> int:
    """Compare dot-separated version strings numerically.

    Returns -1 if a < b, 0 if equal, 1 if a > b.

    >>> compare_versions("1.10", "1.9")
    1
    """
    parts_a = [int(x) for x in a.split(".")]
    parts_b = [int(x) for x in b.split(".")]
    # Pad shorter list with zeros
    max_len = max(len(parts_a), len(parts_b))
    parts_a += [0] * (max_len - len(parts_a))
    parts_b += [0] * (max_len - len(parts_b))
    for x, y in zip(parts_a, parts_b):
        if x < y:
            return -1
        if x > y:
            return 1
    return 0
