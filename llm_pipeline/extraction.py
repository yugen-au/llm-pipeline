"""
Base classes for pipeline data extractions.

Extractions convert typed pathway inputs (assembled by the strategy's
adapter from pipeline input + prior step outputs) into database models.
Each extraction is responsible for one model type.

Pathway dispatch contract:
- An extraction subclass declares one or more nested inputs classes named
  ``From{Purpose}Inputs`` (subclass of ``StepInputs``).
- For each pathway class, the extraction defines a method with the
  signature ``(self, inputs: FromPurposeInputs) -> list[MODEL]``.
- At class creation, pathways and methods are validated for 1:1 mapping
  and a dispatch table is built on ``cls._pathway_dispatch``.
- ``extract(self, inputs)`` dispatches by ``type(inputs)`` at runtime.

Example::

    class TopicExtraction(PipelineExtraction, model=Topic):
        class FromTopicExtractionInputs(StepInputs):
            result: TopicExtractionInstructions
            run_id: int

        def from_topic_extraction(
            self, inputs: FromTopicExtractionInputs
        ) -> list[Topic]:
            return [Topic(name=t.name, run_id=inputs.run_id)
                    for t in inputs.result.topics]
"""
import inspect
import re
import typing
from abc import ABC
from decimal import Decimal
from typing import Any, ClassVar, List, TYPE_CHECKING, Type

from sqlmodel import SQLModel

from llm_pipeline.inputs import StepInputs

if TYPE_CHECKING:
    from llm_pipeline.pipeline import PipelineConfig


_FROM_INPUTS_PATTERN = re.compile(r"^From[A-Z][A-Za-z0-9]*Inputs$")
_BASE_EXTRACTION_METHODS = frozenset({"extract", "begin_update"})


class PipelineExtraction(ABC):
    """
    Base class for pathway-dispatched data extractions.

    Each extraction produces instances of one database model (``MODEL``)
    from typed pathway inputs. A concrete extraction declares one or more
    nested ``From{Purpose}Inputs`` classes (subclasses of ``StepInputs``)
    and a matching method per pathway. At class creation, pathways and
    methods are validated for 1:1 mapping and a dispatch table is built
    on ``cls._pathway_dispatch``.

    At runtime, ``extract(self, inputs)`` dispatches by ``type(inputs)``.
    Ambient access (``self.pipeline.session`` etc.) is unchanged.
    """

    MODEL: ClassVar[Type[SQLModel]] = None
    _pathway_dispatch: ClassVar[dict[type, Any]] = {}

    def __init_subclass__(cls, model=None, **kwargs):
        """Validate model binding, naming convention, and pathway dispatch.

        Args:
            model: SQLModel class this extraction produces (required for
                concrete direct subclasses of PipelineExtraction).

        Raises:
            ValueError: If model is missing, naming convention is violated,
                or pathway declarations are inconsistent with method
                signatures.
        """
        super().__init_subclass__(**kwargs)

        is_concrete_direct_subclass = (
            not cls.__name__.startswith("_")
            and cls.__bases__[0] is PipelineExtraction
        )

        if model is not None:
            cls.MODEL = model
        elif is_concrete_direct_subclass:
            raise ValueError(
                f"{cls.__name__} must specify model parameter when defining the class:\n"
                f"class {cls.__name__}(PipelineExtraction, model=YourModel)"
            )

        if is_concrete_direct_subclass:
            if not cls.__name__.endswith("Extraction"):
                raise ValueError(
                    f"{cls.__name__} must follow naming convention: "
                    f"{{ModelName}}Extraction\n"
                    f"Example: LaneExtraction, RateExtraction"
                )
            cls._pathway_dispatch = _build_pathway_dispatch(cls)
    
    def __init__(self, pipeline: 'PipelineConfig'):
        """
        Initialize extraction with pipeline reference.
        
        Validates that the extraction's MODEL is in the pipeline's registry.
        
        Args:
            pipeline: Reference to the pipeline instance
        
        Raises:
            ValueError: If MODEL is not in pipeline's registry
        """
        # Validate that this extraction's model is in the pipeline's registry
        if self.MODEL not in pipeline.REGISTRY.get_models():
            raise ValueError(
                f"{self.__class__.__name__}.MODEL ({self.MODEL.__name__}) "
                f"is not in {pipeline.REGISTRY.__name__}. "
                f"Valid models: {[m.__name__ for m in pipeline.REGISTRY.get_models()]}"
            )
        
        self.pipeline = pipeline
        self._tracked_updates: list[tuple[SQLModel, dict]] = []

    def begin_update(self, instance: SQLModel) -> None:
        """Snapshot instance state before mutation for before/after diffing."""
        self._tracked_updates.append((instance, instance.model_dump()))
    
    def _validate_instance(self, instance: SQLModel, index: int) -> None:
        """
        Validate a single model instance before database insertion.
        
        This catches validation issues that SQLModel with table=True doesn't catch,
        ensuring errors happen at extraction time rather than database insertion time.
        
        Validates:
        - Decimal fields for NaN/Infinity (prevents silent failures)
        - Required fields for NULL (prevents NOT NULL constraint violations)
        - Foreign key fields for NULL (prevents FK constraint violations)
        
        Args:
            instance: Model instance to validate
            index: Index in the list (for error messages)
        
        Raises:
            ValueError: If instance contains invalid data (NaN, Infinity, NULL in required fields)
        """
        from typing import get_origin, get_args
        
        model_name = self.MODEL.__name__
        
        # Get SQLAlchemy table metadata if available (for FK detection)
        foreign_key_fields = set()
        if hasattr(self.MODEL, '__table__'):
            for column in self.MODEL.__table__.columns:
                if column.foreign_keys:
                    foreign_key_fields.add(column.name)
        
        # Validate all fields
        for field_name, field_info in type(instance).model_fields.items():
            value = getattr(instance, field_name, None)
            
            # Check if field is required (not Optional, no default)
            is_required = field_info.is_required()
            is_foreign_key = field_name in foreign_key_fields
            
            # Validate required fields (NOT NULL constraint)
            if is_required and value is None:
                raise ValueError(
                    f"Invalid {model_name} at index {index}: "
                    f"Required field '{field_name}' cannot be None. "
                    f"This would violate NOT NULL constraint on database insertion. "
                    f"Check extraction logic to ensure all required fields are populated."
                )
            
            # Validate foreign key fields (even if Optional, should not be None if set)
            # Special case: primary keys named 'id' are auto-generated, so None is OK
            if is_foreign_key and value is None and field_name != 'id':
                # Only warn if this isn't an optional FK
                if is_required:
                    raise ValueError(
                        f"Invalid {model_name} at index {index}: "
                        f"Foreign key field '{field_name}' cannot be None. "
                        f"This would violate foreign key constraint on database insertion. "
                        f"Check extraction logic to ensure foreign key references are valid."
                    )
            
            # Skip None values for remaining checks
            if value is None:
                continue
                
            # Validate Decimal fields for NaN and Infinity
            if isinstance(value, Decimal):
                if value.is_nan():
                    raise ValueError(
                        f"Invalid {model_name} at index {index}: "
                        f"Field '{field_name}' cannot be NaN. "
                        f"Check extraction logic to filter out NaN values."
                    )
                if value.is_infinite():
                    raise ValueError(
                        f"Invalid {model_name} at index {index}: "
                        f"Field '{field_name}' cannot be Infinity. "
                        f"Check extraction logic to filter out Infinity values."
                    )
    
    def _validate_instances(self, instances: List[SQLModel]) -> List[SQLModel]:
        """
        Validate all extracted instances before returning to pipeline.
        
        SQLModel with table=True doesn't run Pydantic validation, so we manually
        validate critical constraints here to catch errors at extraction time
        rather than at database insertion time.
        
        Args:
            instances: List of model instances from extraction method
        
        Returns:
            Same list of instances (validation raises on error)
        
        Raises:
            ValueError: If any instance contains invalid data
        """
        for i, instance in enumerate(instances):
            self._validate_instance(instance, i)
        
        return instances
    
    def extract(self, inputs: StepInputs) -> List[SQLModel]:
        """Dispatch to the pathway method matching ``type(inputs)``.

        The pathway dispatch table is built at class-creation time from
        the extraction's nested ``From{Purpose}Inputs`` classes and the
        methods that accept them. See ``PipelineExtraction`` class doc
        for the contract.

        Args:
            inputs: Pathway inputs instance produced by the strategy's
                adapter. Must be an instance of a nested inputs class
                declared on this extraction.

        Returns:
            Validated list of ``MODEL`` instances ready for DB insertion.

        Raises:
            TypeError: If ``type(inputs)`` is not a declared pathway on
                this extraction.
        """
        method = self._pathway_dispatch.get(type(inputs))
        if method is None:
            declared = [c.__name__ for c in self._pathway_dispatch.keys()]
            raise TypeError(
                f"{self.__class__.__name__} has no pathway method accepting "
                f"{type(inputs).__name__}; declared pathways: {declared}"
            )
        instances = method(self, inputs)
        return self._validate_instances(instances)


# ---------------------------------------------------------------------------
# Pathway dispatch construction
# ---------------------------------------------------------------------------


def _build_pathway_dispatch(cls: type) -> dict[type, Any]:
    """Validate pathway/method consistency and return the dispatch table.

    Scans ``cls.__dict__`` for nested ``StepInputs`` subclasses and public
    methods. Enforces:

    - Every nested inputs class is named ``From{Purpose}Inputs``.
    - Every public method (excluding ``extract`` and ``begin_update``)
      has signature ``(self, inputs: FromPurposeInputs) -> list[MODEL]``
      where the inputs annotation matches one of the nested inputs classes.
    - 1:1 mapping between pathway classes and methods. No orphaned
      pathways; no two methods accepting the same inputs type.

    Returns the dispatch map keyed on inputs class with unbound method
    values (call as ``method(self, inputs)``).
    """
    pathway_classes = _collect_pathway_classes(cls)
    candidate_methods = _collect_candidate_methods(cls)

    dispatch: dict[type, Any] = {}
    for method_name, method in candidate_methods.items():
        input_cls, return_hint = _resolve_method_hints(cls, method_name, method)

        if input_cls not in pathway_classes.values():
            pathway_names = sorted(pathway_classes.keys())
            raise ValueError(
                f"{cls.__name__}.{method_name}: inputs parameter must be "
                f"annotated with one of the nested pathway classes "
                f"{pathway_names}, got {input_cls!r}"
            )
        if input_cls in dispatch:
            raise ValueError(
                f"{cls.__name__}: two methods accept {input_cls.__name__} "
                f"as inputs; each pathway must dispatch to exactly one method"
            )

        expected_return = list[cls.MODEL]
        if return_hint != expected_return:
            raise ValueError(
                f"{cls.__name__}.{method_name}: must return "
                f"list[{cls.MODEL.__name__}], got {return_hint!r}"
            )

        dispatch[input_cls] = method

    orphaned = set(pathway_classes.values()) - set(dispatch.keys())
    if orphaned:
        names = sorted(o.__name__ for o in orphaned)
        raise ValueError(
            f"{cls.__name__}: pathway inputs classes without matching "
            f"methods: {names}"
        )

    return dispatch


def _collect_pathway_classes(cls: type) -> dict[str, type]:
    """Return nested StepInputs subclasses defined on ``cls``, keyed by name."""
    pathway_classes: dict[str, type] = {}
    for name, value in vars(cls).items():
        if not isinstance(value, type):
            continue
        if not issubclass(value, StepInputs) or value is StepInputs:
            continue
        if not _FROM_INPUTS_PATTERN.match(value.__name__):
            raise ValueError(
                f"{cls.__name__}: nested inputs class {value.__name__!r} "
                f"must match pattern 'From{{Purpose}}Inputs'"
            )
        pathway_classes[value.__name__] = value
    return pathway_classes


def _collect_candidate_methods(cls: type) -> dict[str, Any]:
    """Return public methods defined on ``cls`` that are pathway candidates.

    Excludes nested classes — they're callable but are pathway inputs
    classes, handled separately by ``_collect_pathway_classes``.
    """
    return {
        name: value
        for name, value in vars(cls).items()
        if callable(value)
        and not isinstance(value, type)
        and not name.startswith("_")
        and name not in _BASE_EXTRACTION_METHODS
    }


def _resolve_method_hints(
    cls: type, method_name: str, method: Any
) -> tuple[Any, Any]:
    """Resolve the inputs-type annotation and return-type annotation for ``method``.

    Returns ``(input_cls, return_hint)``. Raises ``ValueError`` if the
    signature is malformed.
    """
    # Pass the class's own namespace as localns so annotations like
    # ``FromPurposeInputs`` (referencing sibling nested classes) resolve,
    # regardless of whether the module uses ``from __future__ import annotations``.
    try:
        hints = typing.get_type_hints(method, localns=dict(vars(cls)))
    except Exception as exc:  # noqa: BLE001 — surface any hint-resolution failure
        raise ValueError(
            f"{cls.__name__}.{method_name}: failed to resolve type hints: {exc}"
        ) from exc

    sig = inspect.signature(method)
    params = list(sig.parameters.values())
    if len(params) < 2:
        raise ValueError(
            f"{cls.__name__}.{method_name}: must accept an inputs parameter "
            f"in addition to self"
        )

    input_param = params[1]
    input_cls = hints.get(input_param.name)
    if input_cls is None:
        raise ValueError(
            f"{cls.__name__}.{method_name}: parameter "
            f"{input_param.name!r} must have a type annotation"
        )

    return_hint = hints.get("return")
    if return_hint is None:
        raise ValueError(
            f"{cls.__name__}.{method_name}: must have a return type annotation"
        )

    return input_cls, return_hint


__all__ = ["PipelineExtraction"]
