"""Session wrappers for pipeline database access control."""

from .readonly import ReadOnlySession

__all__ = ["ReadOnlySession"]
