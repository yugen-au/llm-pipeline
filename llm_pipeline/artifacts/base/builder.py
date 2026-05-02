"""``SpecBuilder`` ABC — class introspection ⇒ per-kind ``ArtifactSpec``.

Each kind subclasses :class:`SpecBuilder`, pinning :attr:`KIND` and
:attr:`SPEC_CLS` and overriding :meth:`kind_fields`. The base
:meth:`build` wraps the kind-specific fields with identity (kind,
name, cls qualname, source_path, description) and chains
:meth:`ArtifactSpec.attach_class_captures` so per-class
``_init_subclass_errors`` route onto the matching sub-component.

Builders never raise — partial state surfaces via the spec's
``issues`` field on the relevant component. Schema-generation
failures, missing class state, and analyser parse errors are all
captured.

Helpers ``json_schema_with_refs`` / ``build_code_body`` /
``_class_to_artifact_ref`` are imported by per-kind builder
subclasses.
"""
from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from llm_pipeline.cst_analysis import (
    AnalysisError,
    ResolverHook,
    analyze_class_fields,
    analyze_code_body,
)
from llm_pipeline.artifacts.base import ArtifactRef, SymbolRef
from llm_pipeline.artifacts.base.blocks import (
    CodeBodySpec,
    JsonSchemaWithRefs,
)


__all__ = [
    "SpecBuilder",
    "_class_to_artifact_ref",
    "_docstring",
    "_qualified",
    "_safe_model_json_schema",
    "build_code_body",
    "json_schema_with_refs",
]


def _qualified(cls: type) -> str:
    """Return ``cls``'s fully-qualified ``module.qualname``."""
    return f"{cls.__module__}.{cls.__qualname__}"


def _docstring(cls: type | None) -> str:
    """Return ``cls``'s cleaned docstring, or empty string."""
    if cls is None:
        return ""
    return inspect.getdoc(cls) or ""


def _class_to_artifact_ref(
    cls: type | None,
    resolver: ResolverHook,
) -> ArtifactRef | None:
    """Build an :class:`ArtifactRef` from a Python class.

    ``ArtifactRef.name`` is the source-side Python identifier;
    ``ArtifactRef.ref`` is populated when the resolver maps
    ``(cls.__module__, cls.__name__)`` to a registered ``(kind, registry_key)``.
    """
    if cls is None:
        return None
    module_path = getattr(cls, "__module__", "") or ""
    symbol = cls.__name__
    resolved = resolver(module_path, symbol) if module_path else None
    ref = (
        SymbolRef(symbol=symbol, kind=resolved[0], name=resolved[1])
        if resolved is not None else None
    )
    return ArtifactRef(name=symbol, ref=ref)


def _safe_model_json_schema(cls: type) -> dict[str, Any] | None:
    """Call ``cls.model_json_schema()``; ``None`` on any failure."""
    try:
        return cls.model_json_schema()  # type: ignore[no-any-return,attr-defined]
    except Exception:  # noqa: BLE001 — uniform fallback
        return None


def json_schema_with_refs(
    *,
    cls: type | None,
    source_text: str,
    resolver: ResolverHook,
) -> JsonSchemaWithRefs | None:
    """Build a :class:`JsonSchemaWithRefs` for a Pydantic-shaped class.

    Returns ``None`` when ``cls`` is None or its schema can't be
    generated. Source-side ref analysis is best-effort.
    """
    if cls is None:
        return None
    schema = _safe_model_json_schema(cls)
    if schema is None:
        return None
    refs: dict[str, list] = {}
    field_source: dict[str, str] = {}
    try:
        analysis = analyze_class_fields(
            source=source_text,
            class_qualname=cls.__qualname__,
            resolver=resolver,
        )
    except AnalysisError:
        pass
    else:
        refs = analysis.refs_by_pointer
        field_source = analysis.field_source
    return JsonSchemaWithRefs(
        json_schema=schema,
        refs=refs,
        field_source=field_source,
        description=_docstring(cls),
    )


def build_code_body(
    *,
    function_qualname: str,
    source_text: str,
    resolver: ResolverHook,
) -> CodeBodySpec | None:
    """Analyse a function body and return a :class:`CodeBodySpec`.

    ``None`` when the function isn't found in ``source_text``.
    """
    try:
        return analyze_code_body(
            source=source_text,
            function_qualname=function_qualname,
            resolver=resolver,
        )
    except AnalysisError:
        return None


class SpecBuilder(ABC):
    """Per-kind builder base — universal entrypoint for every kind.

    Subclasses pin :attr:`SPEC_CLS` and override :meth:`kind_fields`.
    The discriminator value is read from ``SPEC_CLS.KIND`` (set
    automatically by :meth:`ArtifactSpec.__pydantic_init_subclass__`).
    Convenience helpers :meth:`json_schema` and :meth:`code_body`
    pre-fill ``source_text`` + ``resolver``.
    """

    SPEC_CLS: ClassVar[type]

    def __init__(
        self,
        *,
        name: str,
        cls: type,
        source_path: str,
        source_text: str = "",
        resolver: ResolverHook | None = None,
    ) -> None:
        self.name = name
        self.cls = cls
        self.source_path = source_path
        self.source_text = source_text
        # Default resolver is a null lookup — kinds that don't consult
        # cst_analysis (constants, enums) leave it alone.
        self.resolver: ResolverHook = resolver or (lambda _m, _s: None)

    def json_schema(self, cls: type | None) -> JsonSchemaWithRefs | None:
        """Convenience wrapper: pre-fills ``source_text`` + ``resolver``."""
        return json_schema_with_refs(
            cls=cls,
            source_text=self.source_text,
            resolver=self.resolver,
        )

    def code_body(self, method_name: str) -> CodeBodySpec | None:
        """Convenience: builds the function qualname from ``self.cls``."""
        return build_code_body(
            function_qualname=f"{self.cls.__qualname__}.{method_name}",
            source_text=self.source_text,
            resolver=self.resolver,
        )

    @abstractmethod
    def kind_fields(self) -> dict[str, Any]:
        """Return per-kind keyword arguments for the spec constructor."""

    def build(self):
        # ``kind`` flows from the spec's Literal default — no need to
        # pass it explicitly.
        return self.SPEC_CLS(
            name=self.name,
            cls=_qualified(self.cls),
            source_path=self.source_path,
            description=_docstring(self.cls),
            **self.kind_fields(),
        ).attach_class_captures(self.cls)
