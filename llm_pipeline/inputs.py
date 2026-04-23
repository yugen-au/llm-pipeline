"""Base class for step and extraction pathway inputs.

``StepInputs`` is the declared contract for what data a step's methods
(``prepare_calls``, ``process_instructions``, extractions, transformations)
need from outside the step. Strategies declare how each field is sourced
via an auto-generated companion class accessed via ``.sources(...)``.

The companion class is generated at subclass-creation time: same field
names as the inputs class, each field typed as ``Source``. At strategy
declaration time, ``.sources(**kwargs)`` validates that every required
field is provided and that each value is a Source instance. The returned
``SourcesSpec`` is wired into a ``Bind``.

Extraction pathway inputs (nested ``From{Purpose}Inputs`` classes inside
``PipelineExtraction`` subclasses) also inherit from ``StepInputs``. The
name is loose — "step-like thing with typed inputs" — matching the
framework's step-centric naming elsewhere. A separate name was not added
because the machinery is identical.
"""
from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, create_model

from llm_pipeline.wiring import Source, SourcesSpec

__all__ = ["StepInputs"]


class _SourcesCompanionBase(BaseModel):
    """Base for auto-generated sources companion classes.

    ``arbitrary_types_allowed=True`` lets Pydantic accept ``Source``
    instances (non-BaseModel) as field values. ``extra="forbid"`` makes
    unknown keyword args a loud validation error at strategy-declaration
    time rather than a silent drop.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")


def _build_sources_companion(cls: type["StepInputs"]) -> type[BaseModel]:
    """Build a Pydantic companion where every field of ``cls`` is typed as Source."""
    field_defs: dict[str, Any] = {name: (Source, ...) for name in cls.model_fields}
    return create_model(
        f"{cls.__name__}_Sources",
        __base__=_SourcesCompanionBase,
        **field_defs,
    )


class StepInputs(BaseModel):
    """Base class for typed step and extraction pathway inputs.

    Subclasses declare fields representing data needed from outside. An
    auto-generated sources companion is created per subclass with at
    least one field; use ``.sources(**kwargs)`` at strategy-declaration
    time to declare the Source for each field.

    The base class itself has no fields and no companion. ``.sources()``
    on the base raises ``TypeError``.
    """

    _sources_cls: ClassVar[type[BaseModel] | None] = None

    # NOTE: __pydantic_init_subclass__ fires *after* Pydantic's metaclass has
    # finalised model_fields (including inherited ones); plain __init_subclass__
    # sees an empty model_fields because it runs too early.
    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        if not cls.model_fields:
            return
        cls._sources_cls = _build_sources_companion(cls)

    @classmethod
    def sources(cls, **field_sources: Source) -> SourcesSpec:
        """Declare how each field of this inputs class is sourced.

        All required fields must be provided; each value must be a
        ``Source`` instance. Validation runs at strategy-class creation
        via the auto-generated companion class. Missing required fields,
        unknown field names, or non-Source values raise ``ValidationError``.
        """
        if cls._sources_cls is None:
            raise TypeError(
                f"{cls.__name__} has no fields; cannot declare sources."
            )
        validated = cls._sources_cls(**field_sources)
        return SourcesSpec(
            inputs_cls=cls,
            field_sources={
                name: getattr(validated, name)
                for name in cls.model_fields
            },
        )
