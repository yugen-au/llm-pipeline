"""Base class for step and extraction pathway inputs.

``StepInputs`` is the declared contract for what data a step's methods
(``prepare_calls``, ``process_instructions``, extractions, transformations)
need from outside the step. Strategies declare how each field is sourced
via an auto-generated companion class accessed via ``.sources(...)``.

The companion class is generated at subclass-creation time: same field
names as the inputs class (excluding resource fields), each field typed
as ``Source``. At strategy declaration time, ``.sources(**kwargs)``
validates that every required field is provided and that each value is
a Source instance. The returned ``SourcesSpec`` is wired into a ``Bind``.

Resource fields are declared inline via ``= Resource(...)`` (see
``llm_pipeline.resources``). They are NOT part of the sources companion —
the framework resolves them after non-resource fields are populated,
using the explicit mapping on the ``Resource`` marker. Strict
validation at class creation enforces that every input the resource
needs is mapped to a declared field on the ``StepInputs``.

Extraction pathway inputs (nested ``From{Purpose}Inputs`` classes inside
``PipelineExtraction`` subclasses) also inherit from ``StepInputs``. The
name is loose — "step-like thing with typed inputs" — matching the
framework's step-centric naming elsewhere. A separate name was not added
because the machinery is identical.
"""
from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, create_model

from llm_pipeline.resources import PipelineResource, _ResourceFieldInfo
from llm_pipeline.wiring import Source, SourcesSpec

__all__ = ["StepInputs"]


# ---------------------------------------------------------------------------
# Resource spec (frozen metadata recorded at class creation)
# ---------------------------------------------------------------------------


class _ResourceSpec:
    """Immutable record of a resource field's resolution plan."""

    __slots__ = ("resource_cls", "mapping")

    def __init__(self, resource_cls: type, mapping: dict[str, str]) -> None:
        self.resource_cls = resource_cls
        self.mapping = dict(mapping)


class _SourcesCompanionBase(BaseModel):
    """Base for auto-generated sources companion classes.

    ``arbitrary_types_allowed=True`` lets Pydantic accept ``Source``
    instances (non-BaseModel) as field values. ``extra="forbid"`` makes
    unknown keyword args a loud validation error at strategy-declaration
    time rather than a silent drop.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")


def _build_sources_companion(
    cls: type["StepInputs"],
    exclude: set[str],
) -> type[BaseModel]:
    """Build a Pydantic companion where each non-resource field of ``cls`` is typed as Source."""
    field_defs: dict[str, Any] = {
        name: (Source, ...)
        for name in cls.model_fields
        if name not in exclude
    }
    return create_model(
        f"{cls.__name__}_Sources",
        __base__=_SourcesCompanionBase,
        **field_defs,
    )


def _collect_resource_specs(
    cls: type["StepInputs"],
) -> dict[str, _ResourceSpec]:
    """Scan ``cls.model_fields`` for resource fields and validate them strictly.

    A resource field is recognised when its ``FieldInfo`` is a
    ``_ResourceFieldInfo`` (produced by ``resources.Resource(...)``). Validation
    enforces:

    1. The field's annotation resolves to a ``PipelineResource`` subclass.
    2. The resource class defines an ``Inputs`` nested ``BaseModel`` subclass.
    3. Every kwarg on ``Resource.Inputs.model_fields`` is explicitly mapped.
    4. Each mapping target is a declared field on the owning ``StepInputs``.

    Violations raise ``TypeError`` with a message that points to the
    specific unresolved kwarg so authors know what to fix.
    """
    specs: dict[str, _ResourceSpec] = {}
    for field_name, info in cls.model_fields.items():
        if not isinstance(info, _ResourceFieldInfo):
            continue

        annotation = info.annotation
        if not (isinstance(annotation, type) and issubclass(annotation, PipelineResource)):
            raise TypeError(
                f"{cls.__name__}.{field_name}: field uses Resource(...) as its "
                f"default but its annotation {annotation!r} is not a "
                f"PipelineResource subclass."
            )

        inputs_cls = getattr(annotation, "Inputs", None)
        if inputs_cls is None or not (
            isinstance(inputs_cls, type) and issubclass(inputs_cls, BaseModel)
        ):
            raise TypeError(
                f"{cls.__name__}.{field_name}: resource {annotation.__name__} "
                f"does not define an Inputs(BaseModel) nested class — every "
                f"PipelineResource subclass must declare its required inputs."
            )

        mapping = info.resource_mapping
        required_args = set(inputs_cls.model_fields.keys())
        mapped_args = set(mapping.keys())

        # Every resource input must be in the mapping. No name-based fallback.
        missing = required_args - mapped_args
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise TypeError(
                f"{cls.__name__}.{field_name}: Resource(...) mapping is missing "
                f"required input(s) {missing_list} from {annotation.__name__}.Inputs. "
                f"Add explicit mapping entries: Resource({', '.join(sorted(required_args))}=...)."
            )

        # No extraneous mapping entries (catches typos early).
        extra = mapped_args - required_args
        if extra:
            extra_list = ", ".join(sorted(extra))
            raise TypeError(
                f"{cls.__name__}.{field_name}: Resource(...) mapping has "
                f"unknown input(s) {extra_list} not declared on "
                f"{annotation.__name__}.Inputs."
            )

        # Every mapping target must be a declared field on the StepInputs.
        for arg_name, target_field in mapping.items():
            if target_field == field_name:
                raise TypeError(
                    f"{cls.__name__}.{field_name}: Resource mapping for "
                    f"'{arg_name}' points at the resource field itself "
                    f"({target_field!r}); map to a non-resource field on "
                    f"{cls.__name__} instead."
                )
            if target_field not in cls.model_fields:
                raise TypeError(
                    f"{cls.__name__}.{field_name}: Resource mapping maps "
                    f"'{arg_name}' to '{target_field}', but "
                    f"{cls.__name__} has no field named '{target_field}'. "
                    f"Declare '{target_field}: <type>' on {cls.__name__}."
                )
            target_info = cls.model_fields[target_field]
            if isinstance(target_info, _ResourceFieldInfo):
                raise TypeError(
                    f"{cls.__name__}.{field_name}: Resource mapping for "
                    f"'{arg_name}' targets '{target_field}', which is itself "
                    f"a resource field; resources cannot depend on other "
                    f"resources in v1 — map to a plain declared field."
                )

        specs[field_name] = _ResourceSpec(
            resource_cls=annotation,
            mapping=mapping,
        )

    return specs


class StepInputs(BaseModel):
    """Base class for typed step and extraction pathway inputs.

    Subclasses declare fields representing data needed from outside. An
    auto-generated sources companion is created per subclass with at
    least one non-resource field; use ``.sources(**kwargs)`` at
    strategy-declaration time to declare the Source for each field.

    Resource fields (defaulted to ``Resource(...)`` and typed as a
    ``PipelineResource`` subclass) are excluded from the sources
    companion — they are resolved by the framework using the explicit
    mapping on the ``Resource`` marker, not by strategy wiring.

    The base class itself has no fields and no companion. ``.sources()``
    on the base raises ``TypeError``.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    _sources_cls: ClassVar[type[BaseModel] | None] = None
    _resource_specs: ClassVar[dict[str, _ResourceSpec]] = {}

    # NOTE: __pydantic_init_subclass__ fires *after* Pydantic's metaclass has
    # finalised model_fields (including inherited ones); plain __init_subclass__
    # sees an empty model_fields because it runs too early.
    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        if not cls.model_fields:
            return
        cls._resource_specs = _collect_resource_specs(cls)
        resource_field_names = set(cls._resource_specs.keys())
        cls._sources_cls = _build_sources_companion(cls, exclude=resource_field_names)

    @classmethod
    def sources(cls, **field_sources: Source) -> SourcesSpec:
        """Declare how each non-resource field of this inputs class is sourced.

        Resource fields are resolved from their inline ``Resource(...)``
        mapping and must not be passed to ``.sources()``. All other
        required fields must be provided; each value must be a ``Source``
        instance. Validation runs at strategy-class creation via the
        auto-generated companion class. Missing required fields, unknown
        field names, or non-Source values raise ``ValidationError``.
        """
        if cls._sources_cls is None:
            raise TypeError(
                f"{cls.__name__} has no non-resource fields; cannot declare sources."
            )
        validated = cls._sources_cls(**field_sources)
        resource_fields = set(cls._resource_specs.keys())
        return SourcesSpec(
            inputs_cls=cls,
            field_sources={
                name: getattr(validated, name)
                for name in cls.model_fields
                if name not in resource_fields
            },
        )

    @classmethod
    def resource_specs(cls) -> dict[str, _ResourceSpec]:
        """Return the resource-field resolution plans declared on this class."""
        return dict(cls._resource_specs)
