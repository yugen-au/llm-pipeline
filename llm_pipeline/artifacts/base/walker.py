"""``Walker`` ABC — per-module iteration scaffold for discovery.

Each kind subclasses :class:`Walker`, pinning :attr:`KIND` and
:attr:`BUILDER` and overriding :meth:`qualifies` and :meth:`name_for`.
The base :meth:`walk` walks every module's members, applies the
qualify filter, computes the registry key, builds the spec, and
inserts into ``registries[KIND][name]``.

Helpers ``_is_locally_defined_class`` / ``_is_table`` /
``_to_registry_key`` are imported by per-kind walker subclasses.
"""
from __future__ import annotations

import inspect
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from types import ModuleType
from typing import Any, ClassVar, TYPE_CHECKING

from llm_pipeline.cst_analysis import ResolverHook, analyze_imports
from llm_pipeline.artifacts.base.registration import ArtifactRegistration

if TYPE_CHECKING:
    from llm_pipeline.artifacts.base.builder import SpecBuilder


__all__ = [
    "Walker",
    "_imports_for_module",
    "_is_locally_defined_class",
    "_is_table",
    "_module_path",
    "_module_source",
    "_to_registry_key",
]


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level helpers used by Walker.walk and by per-kind walker subclasses
# ---------------------------------------------------------------------------


def _module_source(mod: ModuleType) -> str:
    """Read ``mod.__file__`` and return its text, or "" if unavailable."""
    path = getattr(mod, "__file__", None)
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def _module_path(mod: ModuleType) -> str:
    """Filesystem path of ``mod.__file__`` as a string, or "" if unavailable."""
    path = getattr(mod, "__file__", None)
    return str(path) if path else ""


def _is_locally_defined_class(value: object, mod: ModuleType, base: type) -> bool:
    """``True`` iff ``value`` is a strict subclass of ``base`` defined in ``mod``."""
    return (
        inspect.isclass(value)
        and issubclass(value, base)
        and value is not base
        and getattr(value, "__module__", None) == mod.__name__
    )


def _is_table(cls: type) -> bool:
    """``True`` iff ``cls`` is a SQLModel class with ``table=True``.

    SQLModel only sets ``__table__`` on classes declared with
    ``table=True``; non-table SQLModel subclasses leave it unset.
    """
    return getattr(cls, "__table__", None) is not None


def _imports_for_module(source_text: str, resolver: ResolverHook) -> list:
    """Analyse imports for a module's source. Empty when source unavailable."""
    if not source_text:
        return []
    try:
        return analyze_imports(source=source_text, resolver=resolver)
    except Exception:  # noqa: BLE001 — analysis is best-effort
        return []


def _to_registry_key(identifier: str, *, strip_suffix: str | None = None) -> str:
    """Snake-case the Python identifier into the registry key."""
    from llm_pipeline.naming import to_snake_case

    if strip_suffix is None:
        return to_snake_case(identifier)
    return to_snake_case(identifier, strip_suffix=strip_suffix)


# ---------------------------------------------------------------------------
# Walker ABC
# ---------------------------------------------------------------------------


class Walker(ABC):
    """Per-kind discovery walker base.

    Subclasses pin :attr:`BUILDER`, override :meth:`qualifies` and
    :meth:`name_for`, and (when value-based) override
    :meth:`build_spec`. The discriminator key is read from
    ``BUILDER.SPEC_CLS.KIND``. The iteration scaffold is inherited.
    """

    BUILDER: ClassVar[type["SpecBuilder"]]

    @property
    def kind(self) -> str:
        """Discriminator value for the registry slot this walker fills."""
        return self.BUILDER.SPEC_CLS.KIND

    @abstractmethod
    def qualifies(self, value: Any, mod: ModuleType) -> bool:
        """Return ``True`` if ``value`` is a member of this kind in ``mod``."""

    @abstractmethod
    def name_for(self, attr_name: str, value: Any) -> str:
        """Return the registry key for ``value`` (snake_case)."""

    def build_spec(
        self,
        *,
        name: str,
        attr_name: str,
        value: Any,
        mod: ModuleType,
        source_text: str,
        resolver: ResolverHook,
    ):
        """Construct the per-kind spec via :attr:`BUILDER`.

        Default implementation: standard class-based call. Value-based
        kinds (constants) override to supply their own builder kwargs.
        """
        return self.BUILDER(
            name=name,
            cls=value,
            source_path=_module_path(mod),
            source_text=source_text,
            resolver=resolver,
        ).build()

    def walk(
        self,
        modules: list[ModuleType],
        registries: dict[str, dict[str, ArtifactRegistration]],
        resolver: ResolverHook,
    ) -> None:
        for mod in modules:
            source_text = _module_source(mod)
            imports = _imports_for_module(source_text, resolver)
            for attr_name, value in inspect.getmembers(mod):
                if attr_name.startswith("_"):
                    continue
                if not self.qualifies(value, mod):
                    continue
                name = self.name_for(attr_name, value)
                spec = self.build_spec(
                    name=name,
                    attr_name=attr_name,
                    value=value,
                    mod=mod,
                    source_text=source_text,
                    resolver=resolver,
                )
                spec.imports = imports
                registries[self.kind][name] = ArtifactRegistration(
                    spec=spec, obj=value,
                )
