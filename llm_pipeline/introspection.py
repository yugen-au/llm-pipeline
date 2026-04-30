"""Pipeline introspection over graph-native ``Pipeline`` subclasses.

Pure class-level access — never instantiates a pipeline. Walks
``cls.nodes`` to surface step + extraction metadata for the UI's
pipeline detail / editor / evals views. Results are cached per
pipeline class.

Response shape (preserved from the legacy
``PipelineConfig``/``PipelineStrategy`` introspector for frontend
compatibility): one synthetic ``"default"`` strategy holding every
``LLMStepNode`` in declaration order, with sibling ``ExtractionNode``
classes attached to their ``source_step`` for rendering.
"""
from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Optional, Type, TYPE_CHECKING

from pydantic import BaseModel

from llm_pipeline.naming import to_snake_case

if TYPE_CHECKING:
    from llm_pipeline.graph import ExtractionNode, LLMStepNode, Pipeline, ReviewNode


__all__ = ["PipelineIntrospector", "enrich_with_prompt_readiness"]


def _is_llm_step(node: type) -> bool:
    from llm_pipeline.graph import LLMStepNode

    return isinstance(node, type) and issubclass(node, LLMStepNode) and node is not LLMStepNode


def _is_extraction(node: type) -> bool:
    from llm_pipeline.graph import ExtractionNode

    return isinstance(node, type) and issubclass(node, ExtractionNode) and node is not ExtractionNode


def _is_review(node: type) -> bool:
    from llm_pipeline.graph import ReviewNode

    return isinstance(node, type) and issubclass(node, ReviewNode) and node is not ReviewNode


class PipelineIntrospector:
    """Extract pipeline metadata via class-level introspection.

    Instantiate with a graph ``Pipeline`` subclass, then call
    ``get_metadata()`` to obtain a cached dict describing pipeline
    name, registry models, the synthetic strategy, and execution order.
    """

    _cache: ClassVar[Dict[int, Dict[str, Any]]] = {}

    def __init__(self, pipeline_cls: Type["Pipeline"]) -> None:
        self._pipeline_cls = pipeline_cls

    @staticmethod
    def _step_name(cls: type) -> str:
        return to_snake_case(cls.__name__, strip_suffix="Step")

    @staticmethod
    def _extraction_name(cls: type) -> str:
        return to_snake_case(cls.__name__, strip_suffix="Extraction")

    @staticmethod
    def _get_schema(cls: Optional[type]) -> Optional[Dict[str, Any]]:
        if cls is None:
            return None
        try:
            if isinstance(cls, type) and issubclass(cls, BaseModel):
                return cls.model_json_schema()
        except TypeError:
            pass
        return {"type": cls.__name__}

    def _step_entry(
        self,
        node: Type["LLMStepNode"],
        extractions_by_source: Dict[type, List[Type["ExtractionNode"]]],
    ) -> Dict[str, Any]:
        prompt_name = node.resolved_prompt_name()
        return {
            "step_name": self._step_name(node),
            "class_name": node.__name__,
            "prompt_name": prompt_name,
            "instructions_class": (
                node.INSTRUCTIONS.__name__ if node.INSTRUCTIONS else None
            ),
            "instructions_schema": self._get_schema(node.INSTRUCTIONS),
            "inputs_class": (
                node.INPUTS.__name__ if node.INPUTS else None
            ),
            "inputs_schema": self._get_schema(node.INPUTS),
            "extractions": [
                {
                    "class_name": ext.__name__,
                    "model_class": (
                        ext.MODEL.__name__
                        if getattr(ext, "MODEL", None) is not None else None
                    ),
                    "methods": ["extract"],
                }
                for ext in extractions_by_source.get(node, [])
            ],
            "transformation": None,
            "tools": [t.__name__ for t in (node.DEFAULT_TOOLS or [])],
            "action_after": None,
            "model": None,
        }

    def get_metadata(self) -> Dict[str, Any]:
        """Full pipeline metadata (cached by pipeline class identity)."""
        cache_key = id(self._pipeline_cls)
        if cache_key in self._cache:
            return self._cache[cache_key]

        cls = self._pipeline_cls
        pipeline_name = cls.pipeline_name() if hasattr(cls, "pipeline_name") else cls.__name__

        nodes = list(getattr(cls, "nodes", []))
        step_nodes: List[Type["LLMStepNode"]] = [n for n in nodes if _is_llm_step(n)]
        extraction_nodes: List[Type["ExtractionNode"]] = [
            n for n in nodes if _is_extraction(n)
        ]

        extractions_by_source: Dict[type, List[Type["ExtractionNode"]]] = {}
        for ext in extraction_nodes:
            src = getattr(ext, "source_step", None)
            if src is not None:
                extractions_by_source.setdefault(src, []).append(ext)

        registry_models = sorted({
            ext.MODEL.__name__
            for ext in extraction_nodes
            if getattr(ext, "MODEL", None) is not None
        })

        steps = [
            self._step_entry(node, extractions_by_source)
            for node in step_nodes
        ]

        strategies = [{
            "name": "default",
            "display_name": "Default",
            "class_name": "DefaultStrategy",
            "steps": steps,
        }]

        execution_order = [s["step_name"] for s in steps]

        pipeline_input_schema = self._get_schema(getattr(cls, "INPUT_DATA", None))

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

    Phase E: prompts live in Phoenix. We probe Phoenix once for the
    set of prompt names referenced by the metadata; readiness is
    determined by Phoenix membership, not by a local DB row. When
    Phoenix is unreachable we mark every step as ``prompts_ready=True``
    so the frontend doesn't paint a sea of warnings on a healthy
    system. ``session`` is accepted (and ignored) for API compat.
    """
    del session

    from llm_pipeline.prompts.phoenix_client import (
        PhoenixError,
        PhoenixPromptClient,
    )

    referenced: set[str] = set()
    for strategy in metadata.get("strategies", []):
        for step in strategy.get("steps", []):
            name = step.get("prompt_name")
            if isinstance(name, str) and name:
                referenced.add(name)

    phoenix_names: set[str] | None
    try:
        client = PhoenixPromptClient()
        cursor: str | None = None
        phoenix_names = set()
        while True:
            page = client.list_prompts(limit=200, cursor=cursor)
            for record in page.get("data") or []:
                n = record.get("name")
                if isinstance(n, str):
                    phoenix_names.add(n)
            cursor = page.get("next_cursor")
            if not cursor:
                break
    except PhoenixError:
        phoenix_names = None

    for strategy in metadata.get("strategies", []):
        for step in strategy.get("steps", []):
            name = step.get("prompt_name")
            if not name:
                ready = True
            elif phoenix_names is None:
                ready = True
            else:
                ready = name in phoenix_names
            step["system_prompt_exists"] = ready
            step["user_prompt_exists"] = ready
            step["prompts_ready"] = ready

    return metadata
