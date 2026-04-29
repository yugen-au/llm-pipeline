"""
Pipeline introspection via pure class-level attribute access.

No FastAPI, SQLAlchemy, or pydantic-ai dependencies. Operates entirely on
class types -- never instantiates PipelineConfig, PipelineExtraction, or
PipelineTransformation. Safe to call without DB connections or external LLM dependencies.

Results are cached per pipeline class (immutable after class definition).
"""
import re
from typing import Any, ClassVar, Dict, List, Optional, Type, TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from llm_pipeline.pipeline import PipelineConfig

from llm_pipeline.extraction import PipelineExtraction
from llm_pipeline.wiring import Bind


def _compile_bind_for_introspection(bind: Bind):
    """Compile a Bind to a StepDefinition without requiring a live pipeline.

    Mirrors ``PipelineConfig._compile_bind_to_step_def`` but is pure-class
    (no ``self``) so introspection can run before any pipeline instance
    exists. Resolves consensus from Bind override or step's CONSENSUS_STRATEGY
    decorator default (None if neither set).
    """
    resolved_consensus = (
        bind.consensus_strategy
        if bind.consensus_strategy is not None
        else getattr(bind.step, "CONSENSUS_STRATEGY", None)
    )
    create_kwargs: Dict[str, Any] = {
        "inputs_spec": bind.inputs,
        "extraction_binds": list(bind.extractions),
    }
    if resolved_consensus is not None:
        create_kwargs["consensus_strategy"] = resolved_consensus
    if bind.prompt_name is not None:
        create_kwargs["prompt_name"] = bind.prompt_name
    return bind.step.create_definition(**create_kwargs)


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
            step_name = self._step_name(step_cls)
            # Phase C: a step resolves against a single Phoenix CHAT
            # prompt by name (defaults to the step's snake_case name;
            # overridable per Bind via ``prompt_name``). The legacy
            # ``system_key`` / ``user_key`` columns remain in the
            # introspection payload as ``<name>.system_instruction``
            # / ``<name>.user_prompt`` shims so the frontend keeps
            # rendering until Phase D repoints it.
            resolved_name = step_def.resolved_prompt_name
            step_entry: Dict[str, Any] = {
                "step_name": step_name,
                "class_name": step_cls.__name__,
                "prompt_name": resolved_name,
                "system_key": f"{resolved_name}.system_instruction",
                "user_key": f"{resolved_name}.user_prompt",
                "instructions_class": (
                    step_def.instructions.__name__
                    if step_def.instructions
                    else None
                ),
                "instructions_schema": self._get_schema(step_def.instructions),
                "inputs_class": (
                    step_def.inputs_spec.inputs_cls.__name__
                    if step_def.inputs_spec
                    else None
                ),
                "inputs_schema": self._get_schema(
                    step_def.inputs_spec.inputs_cls
                    if step_def.inputs_spec
                    else None
                ),
                "extractions": [],
                "transformation": None,
                "tools": [],
                "action_after": step_def.action_after,
                "model": step_def.model,
            }

            # Tools from global agent registry
            agent_name = step_def.agent_name
            if agent_name:
                from llm_pipeline.agent_registry import get_agent_tools
                tool_fns = get_agent_tools(agent_name)
                if tool_fns:
                    step_entry["tools"] = [
                        getattr(fn, '__name__', str(fn)) for fn in tool_fns
                    ]

            # Extractions (from nested Binds under this step)
            for ext_bind in (step_def.extraction_binds or []):
                ext_cls = ext_bind.extraction
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
        ``strategies``, ``execution_order``, ``pipeline_input_schema``.
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

        # Instantiate each strategy once; compile each Bind into a
        # StepDefinition for metadata extraction (same helper the pipeline
        # executor uses, but callable without a live pipeline instance).
        resolved: List[tuple] = []  # (strategy_cls, step_defs | None, error | None)
        for s_cls in strategy_classes:
            try:
                instance = s_cls()
                step_defs = [
                    _compile_bind_for_introspection(bind)
                    for bind in instance.get_bindings()
                ]
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

        # Pipeline input schema (from INPUT_DATA ClassVar if declared)
        pipeline_input_schema = self._get_schema(
            getattr(self._pipeline_cls, "INPUT_DATA", None)
        )

        metadata: Dict[str, Any] = {
            "pipeline_name": pipeline_name,
            "registry_models": registry_models,
            "strategies": strategies,
            "execution_order": execution_order,
            "pipeline_input_schema": pipeline_input_schema,
        }

        self._cache[cache_key] = metadata
        return metadata


def enrich_with_prompt_readiness(metadata: dict, session) -> dict:
    """Add prompt readiness flags to each step in introspection metadata.

    Queries DB for active prompts matching each step's system_key/user_key.
    Mutates metadata in-place and returns it.
    """
    from sqlmodel import select
    from llm_pipeline.db.prompt import Prompt

    all_keys = set()
    for strategy in metadata.get("strategies", []):
        for step in strategy.get("steps", []):
            if step.get("system_key"):
                all_keys.add(step["system_key"])
            if step.get("user_key"):
                all_keys.add(step["user_key"])

    if all_keys:
        stmt = select(Prompt.prompt_key, Prompt.prompt_type).where(
            Prompt.prompt_key.in_(all_keys),
            Prompt.is_active == True,  # noqa: E712
            Prompt.is_latest == True,  # noqa: E712
        )
        rows = session.exec(stmt).all()
        existing = {(row[0], row[1]) for row in rows}
    else:
        existing = set()

    for strategy in metadata.get("strategies", []):
        for step in strategy.get("steps", []):
            sys_key = step.get("system_key")
            usr_key = step.get("user_key")
            step["system_prompt_exists"] = (sys_key, "system") in existing if sys_key else True
            step["user_prompt_exists"] = (usr_key, "user") in existing if usr_key else True
            step["prompts_ready"] = step["system_prompt_exists"] and step["user_prompt_exists"]

    return metadata


__all__ = ["PipelineIntrospector", "enrich_with_prompt_readiness"]
