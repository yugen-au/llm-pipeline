"""Graph state and runtime deps for pydantic-graph-native pipelines.

``PipelineState`` is the mutable state pydantic-graph carries through
the run. It's pydantic-serialisable so the persistence backend can
snapshot it at every node boundary.

``outputs`` is keyed by step class **name** (string) so the state
serialises cleanly. At adapter-resolve time we rebuild a typed
``AdapterContext`` keyed by class via ``state.to_adapter_ctx(...)``.

``PipelineDeps`` holds graph-level dependencies (DB session, prompt
service, run id, model). Per-step ``StepDeps`` are constructed inside
each ``LLMStepNode.run()`` from the graph deps.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from llm_pipeline.wiring import AdapterContext

if TYPE_CHECKING:
    from sqlmodel import Session

    from llm_pipeline.prompts.service import PromptService


__all__ = ["PipelineDeps", "PipelineState"]


class PipelineState(BaseModel):
    """Mutable state carried through a graph run.

    Snapshot-friendly: every field is JSON-serialisable. Typed
    instances live transiently inside node ``run()`` methods; the
    canonical state representation is plain dicts.

    Fields:
        input_data: The pipeline's validated input, ``model_dump``'d to
            a dict. ``None`` only for input-less pipelines.
        outputs: Maps step class name -> list of model_dumped
            instructions. List shape supports multi-call (consensus)
            steps; single-call steps store a one-element list.
        extractions: Maps SQLModel class name -> list of model_dumped
            rows. Phase 2 wires the actual DB persistence; Phase 1
            keeps in-memory copies here for visibility.
        metadata: Free-form dict for review feedback, branch hints,
            and other per-run signals.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    input_data: dict[str, Any] | None = None
    outputs: dict[str, list[dict[str, Any]]] = {}
    extractions: dict[str, list[dict[str, Any]]] = {}
    metadata: dict[str, Any] = {}

    def record_output(self, node_cls: type, instructions: list[Any]) -> None:
        """Persist a node's instructions list under its class name.

        Each item in ``instructions`` is model_dumped (Pydantic) or
        coerced via ``vars(...)`` as a last resort. The list always
        contains at least one element when this is called.
        """
        dumped: list[dict[str, Any]] = []
        for item in instructions:
            if hasattr(item, "model_dump"):
                dumped.append(item.model_dump(mode="json"))
            elif hasattr(item, "__dict__"):
                dumped.append(dict(vars(item)))
            else:
                dumped.append({"value": item})
        self.outputs[node_cls.__name__] = dumped

    def record_extraction(
        self, model_cls: type, rows: list[Any],
    ) -> None:
        """Persist extracted SQLModel rows under the model class name."""
        dumped: list[dict[str, Any]] = []
        for row in rows:
            if hasattr(row, "model_dump"):
                dumped.append(row.model_dump(mode="json"))
            else:
                dumped.append(dict(vars(row)))
        existing = self.extractions.setdefault(model_cls.__name__, [])
        existing.extend(dumped)

    def to_adapter_ctx(
        self,
        *,
        input_cls: type | None,
        node_classes: dict[str, type],
        pipeline: Any,
    ) -> AdapterContext:
        """Build an ``AdapterContext`` for ``SourcesSpec.resolve()``.

        Rehydrates ``self.outputs`` (string-keyed, dict values) into the
        typed ``dict[type, list[Any]]`` shape ``FromOutput`` expects.
        Each step class in ``node_classes`` provides the ``INSTRUCTIONS``
        class used to validate-back its dumped output.

        Args:
            input_cls: The pipeline's ``INPUT_DATA`` class. Used to
                rehydrate ``self.input_data`` to a typed instance for
                ``FromInput`` resolution. ``None`` for input-less
                pipelines (rare; ``self.input_data`` must also be
                ``None`` then).
            node_classes: Map of class name -> node class for every
                node in the pipeline. Used to look up each step's
                ``INSTRUCTIONS`` class for output rehydration.
            pipeline: The ``FromPipeline`` resolution target — usually
                ``PipelineDeps``. Must expose ``run_id``, ``session``,
                etc. as attributes.
        """
        rehydrated_input: Any = None
        if input_cls is not None and self.input_data is not None:
            rehydrated_input = input_cls.model_validate(self.input_data)

        rehydrated_outputs: dict[type, list[Any]] = {}
        for class_name, dump_list in self.outputs.items():
            node_cls = node_classes.get(class_name)
            if node_cls is None:
                continue
            instructions_cls = getattr(node_cls, "INSTRUCTIONS", None)
            if instructions_cls is None:
                rehydrated_outputs[node_cls] = list(dump_list)
                continue
            rehydrated_outputs[node_cls] = [
                instructions_cls.model_validate(d) for d in dump_list
            ]

        return AdapterContext(
            input=rehydrated_input,
            outputs=rehydrated_outputs,
            pipeline=pipeline,
        )


@dataclass
class PipelineDeps:
    """Graph-level deps injected into every node's ``run(ctx)`` call.

    Per-step ``StepDeps`` (from ``llm_pipeline.agent_builders``) are
    constructed inside each ``LLMStepNode.run()`` from these graph-
    level deps plus per-step metadata.

    ``FromPipeline`` resolution targets this object — any attribute
    declared here is reachable via ``FromPipeline("attr_name")``.

    ``input_cls`` and ``node_classes`` are populated by the runtime
    before the first node fires; node code reads them via
    ``ctx.deps`` to rehydrate state into typed ``AdapterContext`` for
    ``SourcesSpec.resolve()``.
    """

    session: Any  # sqlmodel.Session — runtime type, kept Any to avoid import
    prompt_service: Any  # PromptService
    run_id: str
    pipeline_name: str
    model: str
    input_cls: type | None = None
    node_classes: dict[str, type] = field(default_factory=dict)
    instrumentation_settings: Any | None = None
    review_context: dict[str, Any] | None = field(default=None)
    # Per-run overrides applied by the eval runner (and any other
    # caller threading variant-style mutations through). All three
    # short-circuit production resolution when present:
    #   - ``model`` field above already overrides ``StepModelConfig``
    #     resolution at the runtime layer.
    #   - ``prompt_overrides[step_name]`` -> raw user-prompt template
    #     bypassing Phoenix prompt fetch in ``_run_llm``.
    #   - ``instructions_overrides[INSTRUCTIONS_cls]`` -> use the
    #     mapped class as the agent's output schema instead of the
    #     node's declared ``INSTRUCTIONS``.
    prompt_overrides: dict[str, str] = field(default_factory=dict)
    instructions_overrides: dict[type, type] = field(default_factory=dict)
