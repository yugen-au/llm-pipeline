"""
Pipeline introspection via pure class-level attribute access.

No FastAPI, SQLAlchemy, or LLM provider dependencies. Operates entirely on
class types -- never instantiates PipelineConfig, PipelineExtraction, or
PipelineTransformation. Safe to call without DB connections or LLM providers.

Results are cached per pipeline class (immutable after class definition).
"""
import re
from typing import Any, ClassVar, Dict, List, Optional, Type, TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from llm_pipeline.pipeline import PipelineConfig

from llm_pipeline.extraction import PipelineExtraction


class PipelineIntrospector:
    """Extract pipeline metadata via class-level introspection.

    Instantiate with a PipelineConfig subclass, then call ``get_metadata()``
    to obtain a cached dict describing pipeline name, registry models,
    strategies (with steps), and deduplicated execution order.
    """

    _cache: ClassVar[Dict[int, Dict[str, Any]]] = {}

    def __init__(self, pipeline_cls: Type["PipelineConfig"]) -> None:
        self._pipeline_cls = pipeline_cls

    # ------------------------------------------------------------------
    # Name derivation helpers (exact regex copies from source modules)
    # ------------------------------------------------------------------

    @staticmethod
    def _pipeline_name(cls: Type) -> str:
        """Derive snake_case pipeline name from class name.

        Mirrors ``PipelineConfig.pipeline_name`` property (pipeline.py L244-245):
        single regex ``([a-z0-9])([A-Z])`` on class name minus ``Pipeline`` suffix.
        """
        name = cls.__name__
        if name.endswith("Pipeline"):
            name = name[:-8]
        return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()

    @staticmethod
    def _strategy_name(cls: Type) -> str:
        """Derive snake_case strategy name from class name.

        Mirrors ``PipelineStrategy.__init_subclass__`` (strategy.py L188-191):
        double regex -- first ``([A-Z]+)([A-Z][a-z])`` then ``([a-z\\d])([A-Z])``.
        Handles consecutive capitals correctly (e.g. HTTPStrategy -> http).
        """
        name = cls.__name__
        if name.endswith("Strategy"):
            name = name[:-8]
        s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
        s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
        return s.lower()

    @staticmethod
    def _step_name(cls: Type) -> str:
        """Derive snake_case step name from class name.

        Mirrors ``LLMStep.step_name`` property (step.py L260-261):
        single regex ``([a-z0-9])([A-Z])`` on class name minus ``Step`` suffix.
        """
        name = cls.__name__
        if name.endswith("Step"):
            name = name[:-4]
        return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()

    # ------------------------------------------------------------------
    # Schema / method helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_schema(cls: Optional[Type]) -> Optional[Dict[str, Any]]:
        """Extract JSON schema from a type.

        Returns ``model_json_schema()`` for Pydantic BaseModel subclasses,
        ``{"type": cls.__name__}`` for other non-None types, or None.
        """
        if cls is None:
            return None
        try:
            if isinstance(cls, type) and issubclass(cls, BaseModel):
                return cls.model_json_schema()
        except TypeError:
            pass
        return {"type": cls.__name__}

    @staticmethod
    def _get_extraction_methods(extraction_cls: Type) -> List[str]:
        """Discover custom extraction methods via dir() comparison.

        Mirrors the runtime logic in ``PipelineExtraction.extract()``
        (extraction.py L237-245).
        """
        all_methods = set(dir(extraction_cls))
        base_methods = set(dir(PipelineExtraction))
        return sorted(
            m
            for m in (all_methods - base_methods)
            if callable(getattr(extraction_cls, m, None))
            and not m.startswith("_")
        )

    # ------------------------------------------------------------------
    # Strategy introspection
    # ------------------------------------------------------------------

    def _introspect_strategy(
        self, strategy_cls: Type, step_defs: List[Any],
    ) -> Dict[str, Any]:
        """Build strategy metadata dict from pre-resolved step definitions.

        ``step_defs`` are obtained once in ``get_metadata()`` to avoid
        double-instantiating strategies.
        """
        entry: Dict[str, Any] = {
            "name": getattr(strategy_cls, "NAME", self._strategy_name(strategy_cls)),
            "display_name": getattr(strategy_cls, "DISPLAY_NAME", strategy_cls.__name__),
            "class_name": strategy_cls.__name__,
            "steps": [],
        }

        for step_def in step_defs:
            step_cls = step_def.step_class
            step_entry: Dict[str, Any] = {
                "step_name": self._step_name(step_cls),
                "class_name": step_cls.__name__,
                "system_key": step_def.system_instruction_key,
                "user_key": step_def.user_prompt_key,
                "instructions_class": (
                    step_def.instructions.__name__
                    if step_def.instructions
                    else None
                ),
                "instructions_schema": self._get_schema(step_def.instructions),
                "context_class": (
                    step_def.context.__name__
                    if step_def.context
                    else None
                ),
                "context_schema": self._get_schema(step_def.context),
                "extractions": [],
                "transformation": None,
                "action_after": step_def.action_after,
            }

            # Extractions
            for ext_cls in (step_def.extractions or []):
                ext_entry: Dict[str, Any] = {
                    "class_name": ext_cls.__name__,
                    "model_class": (
                        ext_cls.MODEL.__name__
                        if getattr(ext_cls, "MODEL", None)
                        else None
                    ),
                    "methods": self._get_extraction_methods(ext_cls),
                }
                step_entry["extractions"].append(ext_entry)

            # Transformation
            transformation_cls = step_def.transformation
            if transformation_cls is not None:
                input_type = getattr(transformation_cls, "INPUT_TYPE", None)
                output_type = getattr(transformation_cls, "OUTPUT_TYPE", None)
                step_entry["transformation"] = {
                    "class_name": transformation_cls.__name__,
                    "input_type": (
                        input_type.__name__ if input_type is not None else None
                    ),
                    "input_schema": self._get_schema(input_type),
                    "output_type": (
                        output_type.__name__ if output_type is not None else None
                    ),
                    "output_schema": self._get_schema(output_type),
                }

            entry["steps"].append(step_entry)

        return entry

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_metadata(self) -> Dict[str, Any]:
        """Full pipeline metadata (cached by pipeline class identity).

        Returns dict with keys: ``pipeline_name``, ``registry_models``,
        ``strategies``, ``execution_order``.
        """
        cache_key = id(self._pipeline_cls)
        if cache_key in self._cache:
            return self._cache[cache_key]

        pipeline_name = self._pipeline_name(self._pipeline_cls)

        # Registry models
        registry_cls = getattr(self._pipeline_cls, "REGISTRY", None)
        registry_models: List[str] = []
        if registry_cls is not None:
            models_list = getattr(registry_cls, "MODELS", []) or []
            registry_models = [m.__name__ for m in models_list]

        # Strategies
        strategies_cls = getattr(self._pipeline_cls, "STRATEGIES", None)
        strategy_classes: List[Type] = []
        if strategies_cls is not None:
            strategy_classes = getattr(strategies_cls, "STRATEGIES", []) or []

        # Instantiate each strategy once; reuse step_defs for both
        # strategy metadata and execution_order derivation.
        resolved: List[tuple] = []  # (strategy_cls, step_defs | None, error | None)
        for s_cls in strategy_classes:
            try:
                instance = s_cls()
                step_defs = instance.get_steps()
                resolved.append((s_cls, step_defs, None))
            except Exception as exc:
                resolved.append((s_cls, None, exc))

        strategies: List[Dict[str, Any]] = []
        for s_cls, step_defs, err in resolved:
            if err is not None:
                strategies.append({
                    "name": getattr(s_cls, "NAME", self._strategy_name(s_cls)),
                    "display_name": getattr(s_cls, "DISPLAY_NAME", s_cls.__name__),
                    "class_name": s_cls.__name__,
                    "steps": [],
                    "error": f"{type(err).__name__}: {err}",
                })
            else:
                strategies.append(self._introspect_strategy(s_cls, step_defs))

        # Execution order (deduplicated, first occurrence wins)
        seen_step_classes: set = set()
        execution_order: List[str] = []
        for _s_cls, step_defs, err in resolved:
            if err is not None:
                continue
            for step_def in step_defs:
                sc = step_def.step_class
                if sc not in seen_step_classes:
                    seen_step_classes.add(sc)
                    execution_order.append(self._step_name(sc))

        metadata: Dict[str, Any] = {
            "pipeline_name": pipeline_name,
            "registry_models": registry_models,
            "strategies": strategies,
            "execution_order": execution_order,
        }

        self._cache[cache_key] = metadata
        return metadata


__all__ = ["PipelineIntrospector"]
