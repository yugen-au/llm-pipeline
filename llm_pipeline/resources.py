"""Framework-level pipeline resources.

A ``PipelineResource`` is a type that builds itself from a small set of
raw inputs plus ambient pipeline fixtures (session, etc.). Steps declare
resource dependencies by adding a resource-typed field to their
``StepInputs`` with a ``Resource(...)`` field default that maps the
resource's required inputs to fields on the same ``StepInputs``.

Example::

    class WorkbookContext(PipelineResource):
        class Inputs(BaseModel):
            vendor_id: str

        @classmethod
        def build(cls, inputs: "WorkbookContext.Inputs",
                  ctx: ResourceContext) -> "WorkbookContext":
            return cls.for_vendor(inputs.vendor_id, ctx.session)


    class ChargeAuditInputs(StepInputs):
        vendor_id: str
        input_2: bool
        input_3: str
        workbook_context: WorkbookContext = Resource(
            vendor_id="vendor_id",            # every resource kwarg must
            input_2="input_2",                # be explicitly mapped to a
            input_3="input_3",                # field on this StepInputs
        )

Why every mapping is explicit (no name-based auto-discovery):
* resolution is always surface-level and transparent — no magic that
  silently pairs same-named fields
* refactoring a resource's ``Inputs`` cannot silently re-bind a
  field on ``StepInputs`` with a coincidentally matching name
* resource builders that rely on "do something weird to patch unmapped
  inputs" never get a foothold

Why resources live on a standalone class (not on the pipeline subclass
or the strategy):
* step-target eval sandboxes run a single step without re-constructing
  the owning pipeline — the resource's build recipe must travel with
  the step
* strict class-creation validation enforces that every resource input is
  satisfied by an explicit mapping to a declared field on ``StepInputs``,
  with a clear error message pointing to the missing entry
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel
from pydantic.fields import FieldInfo

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.orm import Session

__all__ = [
    "PipelineResource",
    "Resource",
    "ResourceContext",
]


# ---------------------------------------------------------------------------
# ResourceContext
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResourceContext:
    """Ambient context passed to ``PipelineResource.build()``.

    Framework-owned fixtures — same set available to step ``prepare_calls``.
    Resources read from ``inputs`` for domain values and from ``ctx`` for
    infrastructure.
    """

    session: "Session"


# ---------------------------------------------------------------------------
# PipelineResource
# ---------------------------------------------------------------------------


class PipelineResource:
    """Base class for domain-specific pipeline resources.

    Subclasses must define:

    * ``Inputs``: a ``pydantic.BaseModel`` subclass listing the raw
      values the resource needs. Fields on this class are what
      ``Resource(...)`` on a ``StepInputs`` maps to.
    * ``build(cls, inputs, ctx) -> Self``: a classmethod that constructs
      an instance from the typed inputs plus ambient context.

    The framework invokes ``build`` once per run (cached by the
    resource class), after step inputs are resolved.
    """

    #: Schema of raw values this resource needs. Required on subclasses.
    Inputs: ClassVar[type[BaseModel]]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Enforce the Inputs contract at class-creation time.
        inputs_attr = cls.__dict__.get("Inputs")
        if inputs_attr is None:
            # Allow intermediate base classes; only leaf resource classes
            # are expected to define Inputs. A missing Inputs at use
            # time is caught by _validate_resource_mapping.
            return
        if not (isinstance(inputs_attr, type) and issubclass(inputs_attr, BaseModel)):
            raise TypeError(
                f"{cls.__name__}.Inputs must be a pydantic BaseModel "
                f"subclass; got {inputs_attr!r}"
            )

    @classmethod
    def build(
        cls,
        inputs: BaseModel,
        ctx: ResourceContext,
    ) -> "PipelineResource":
        """Construct a resource instance from typed inputs + ambient context.

        Subclasses must override. The concrete signature should narrow
        ``inputs`` to ``cls.Inputs`` and the return type to ``Self``.
        """
        raise NotImplementedError(
            f"{cls.__name__}.build must be implemented by subclasses"
        )


# ---------------------------------------------------------------------------
# Resource field marker
# ---------------------------------------------------------------------------


class _ResourceFieldInfo(FieldInfo):
    """Pydantic ``FieldInfo`` subclass that carries resource mapping metadata.

    Using a ``FieldInfo`` subclass (rather than a plain sentinel) lets
    pydantic treat the field as a normal optional field — default is
    ``None``, so pydantic does not complain about a missing value at
    construction time — while the framework can inspect
    ``model_fields[name]`` and recognise the resource marker.

    The framework populates the actual resource instance on the model
    post-validation via ``_apply_resource_resolutions`` (see
    ``StepInputs``).
    """

    __slots__ = ("_resource_mapping",)

    def __init__(self, mapping: dict[str, str]) -> None:
        super().__init__(default=None)
        self._resource_mapping = dict(mapping)

    @property
    def resource_mapping(self) -> dict[str, str]:
        return self._resource_mapping


def Resource(**mapping: str) -> Any:  # noqa: N802 — public API mirrors pydantic.Field naming
    """Declare a resource dependency as a field default on ``StepInputs``.

    ``mapping`` pairs the resource's ``Inputs`` kwarg names (keys) with
    field names on the same ``StepInputs`` class (values). **Every** kwarg
    on the resource's ``Inputs`` must be present in this mapping — no
    implicit name-matching fallback. Same-name fields are written out
    explicitly (e.g. ``vendor_id="vendor_id"``) so the binding is visible
    at the declaration site.

    Validation is strict: every input the resource needs must resolve
    to a declared field on the ``StepInputs``. Missing mapping entries
    or mapping targets that do not exist on the ``StepInputs`` raise
    ``TypeError`` at class creation with a message pointing at the
    specific unresolved kwarg.

    Example::

        workbook_context: WorkbookContext = Resource(
            vendor_id="our_vendor_id",   # different step field name
            input_2="input_2",           # same-name field, still explicit
        )
    """
    return _ResourceFieldInfo(mapping=mapping)
