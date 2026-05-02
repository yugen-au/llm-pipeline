"""``Constant`` — base class for module-level constant declarations.

Constants under ``llm_pipelines/constants/`` declare each value as a
:class:`Constant` subclass with a ``value`` :data:`typing.ClassVar`::

    from llm_pipeline import Constant

    class MAX_RETRIES(Constant):
        value = 3

    class DEFAULT_LABEL(Constant):
        value = "unknown"

The subclass form puts every kind on the same footing — each
constant has a real Python class with ``__module__`` / ``__qualname__``
the discovery walker can introspect uniformly. The ``value`` slot
holds the runtime value; the value's type is validated in
:meth:`__init_subclass__` so a malformed declaration fails at class-
definition time, not later.

Consumers access the value via ``MAX_RETRIES.value`` (or via the
:func:`int` / :func:`str` / etc. converters when arithmetic / string
context is needed). The class itself is not the value — that
deliberate separation is what lets the framework dispatch to it as
a first-class artifact.
"""
from __future__ import annotations

from typing import Any, ClassVar


__all__ = ["Constant"]


# Allowed runtime types for ``Constant.value``. Mirrors the JSON-
# serialisable scalar/list/dict shape the discovery layer can round-
# trip through ``ConstantSpec``.
_ALLOWED_VALUE_TYPES = (str, int, float, bool, list, dict)


class Constant:
    """Base class for module-level constant declarations.

    Subclass and set the ``value`` ClassVar to a JSON-serialisable
    primitive (``str`` / ``int`` / ``float`` / ``bool`` / ``list`` /
    ``dict``). The subclass name becomes the constant's identifier;
    its module path becomes the dotted ``cls`` path under which the
    resolver and registry index it.

    Validation happens at class-definition time (via
    :meth:`__init_subclass__`) — a missing ``value`` slot or a
    non-allowed type raises :class:`TypeError` immediately, surfacing
    declaration errors at import time rather than later at
    discovery / serialisation.

    The :class:`Constant` base itself is a marker — it has no
    ``value``. The :meth:`__init_subclass__` validator runs only on
    subclasses, never the base.
    """

    # Subclasses pin a concrete runtime value. Annotated as ``ClassVar``
    # (not an instance attribute) so Pydantic and other introspecting
    # libraries don't treat it as a field.
    value: ClassVar[Any]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "value" not in cls.__dict__:
            raise TypeError(
                f"{cls.__name__} must declare a ``value`` ClassVar — "
                f"e.g. ``class {cls.__name__}(Constant): value = 3``."
            )
        if not isinstance(cls.value, _ALLOWED_VALUE_TYPES):
            allowed = ", ".join(t.__name__ for t in _ALLOWED_VALUE_TYPES)
            raise TypeError(
                f"{cls.__name__}.value must be one of [{allowed}]; "
                f"got {type(cls.value).__name__}."
            )
