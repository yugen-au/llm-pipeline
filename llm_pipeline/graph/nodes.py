"""Node base classes for pydantic-graph-native pipelines.

Three node kinds are siblings in the graph:

- ``LLMStepNode`` — declares ``INPUTS`` (a ``StepInputs`` subclass),
  ``INSTRUCTIONS`` (a Pydantic model that the LLM call validates against),
  ``inputs_spec`` (a ``SourcesSpec`` declaring how each input field is
  sourced), and an optional per-step ``prompt_name`` overriding the
  default snake-cased class name. ``run()`` is left abstract so each
  step controls the next-node return type — pydantic-graph reads the
  return annotation to build the edge graph.

- ``ExtractionNode`` — declares ``MODEL`` (the SQLModel target),
  ``INPUTS`` (the pathway inputs class), ``source_step`` (the
  ``LLMStepNode`` whose output it reads), and ``inputs_spec``. Each
  subclass implements ``extract(self, inputs) -> list[MODEL]`` to
  shape the rows. ``run()`` resolves the inputs spec, calls
  ``extract``, persists the rows on the session, and writes them
  into ``state.extractions``.

- ``ReviewNode`` — declares ``target_step`` and an optional
  ``condition``. Phase 1 records the review request in
  ``state.metadata`` and falls through to the next node; Phase 2
  wires the actual pause via the persistence backend so the graph
  resumes from the snapshot when the reviewer responds.

Each node's ``inputs_spec`` is a ``SourcesSpec`` produced by
``INPUTS.sources(...)``. The compile-time validator (``validator.py``)
walks every node's spec at class-definition time.
"""
from __future__ import annotations

import logging
from abc import abstractmethod
from typing import Any, Callable, ClassVar, TYPE_CHECKING

from pydantic import BaseModel
from pydantic_graph import BaseNode, End, GraphRunContext
from pydantic_graph.exceptions import GraphSetupError
from pydantic_graph.nodes import NodeDef

from llm_pipeline.graph.state import PipelineDeps, PipelineState
from llm_pipeline.naming import to_snake_case

if TYPE_CHECKING:
    from sqlmodel import SQLModel

    from llm_pipeline.inputs import StepInputs
    from llm_pipeline.wiring import SourcesSpec


__all__ = [
    "ExtractionNode",
    "LLMStepNode",
    "PipelineDeps",
    "ReviewNode",
]


# ---------------------------------------------------------------------------
# Shared edge-resolution helper
# ---------------------------------------------------------------------------


def _build_node_def(cls: type, local_ns: dict[str, Any] | None) -> NodeDef:
    """Resolve only the return annotation of ``cls.run`` to build a NodeDef.

    pydantic-graph's default ``BaseNode.get_node_def`` runs
    ``typing.get_type_hints`` on the entire ``run`` signature — which
    forces every parameter annotation (including ``GraphRunContext``,
    ``PipelineState``, ``PipelineDeps``) to resolve at class-load time.
    User node modules legitimately keep those imports under
    ``TYPE_CHECKING`` for clarity. This shim resolves only the return
    annotation, so user code stays free of forced runtime imports.

    The localns we pass spans pydantic-graph's parent-frame namespace
    plus the framework types (``GraphRunContext``, ``End``, the state
    + deps types) — that combined namespace is enough to evaluate any
    typical return annotation.
    """
    import typing

    return_annotation = cls.run.__annotations__.get("return")
    if return_annotation is None:
        raise GraphSetupError(
            f"Node {cls} is missing a return type hint on its `run` method."
        )

    if isinstance(return_annotation, str):
        eval_globals = dict(getattr(cls.run, "__globals__", {}))
        eval_locals: dict[str, Any] = {
            "GraphRunContext": GraphRunContext,
            "End": End,
            "PipelineState": PipelineState,
            "PipelineDeps": PipelineDeps,
        }
        # Sibling node namespace populated by Pipeline.__init_subclass__
        # so forward references like ``-> "TopicExtractionStep"`` resolve
        # even when the referenced class lives in a different module
        # imported only via ``TYPE_CHECKING``.
        sibling_ns = getattr(cls, "_pipeline_namespace", None)
        if sibling_ns:
            eval_locals.update(sibling_ns)
        if local_ns:
            eval_locals.update(local_ns)
        try:
            return_annotation = eval(  # noqa: S307 — controlled expression
                return_annotation, eval_globals, eval_locals,
            )
        except NameError as exc:
            raise GraphSetupError(
                f"{cls.__name__}.run return type {return_annotation!r} "
                f"could not be resolved: {exc}. Ensure the referenced "
                f"node class is in scope when the Pipeline is declared."
            ) from exc

    next_node_edges: dict[str, Any] = {}
    end_edge = None
    returns_base_node = False

    from pydantic_graph import _utils  # type: ignore[attr-defined]
    from pydantic_graph.nodes import Edge

    for return_type in _utils.get_union_args(return_annotation):
        return_type, annotations = _utils.unpack_annotated(return_type)
        edge = next(
            (a for a in annotations if isinstance(a, Edge)), Edge(None),
        )
        return_type_origin = typing.get_origin(return_type) or return_type
        if return_type_origin is End:
            end_edge = edge
        elif return_type_origin is BaseNode:
            returns_base_node = True
        elif isinstance(return_type_origin, type) and issubclass(return_type_origin, BaseNode):
            next_node_edges[return_type.get_node_id()] = edge
        else:
            raise GraphSetupError(f"Invalid return type: {return_type}")

    return NodeDef(
        node=cls,
        node_id=cls.get_node_id(),
        note=cls.get_note(),
        next_node_edges=next_node_edges,
        end_edge=end_edge,
        returns_base_node=returns_base_node,
    )


# ---------------------------------------------------------------------------
# LLMStepNode
# ---------------------------------------------------------------------------


class LLMStepNode(BaseNode[PipelineState, PipelineDeps, Any]):
    """Base for LLM-call nodes.

    Subclasses declare:

    - ``INPUTS``: a ``StepInputs`` subclass.
    - ``INSTRUCTIONS``: a Pydantic ``BaseModel`` subclass — the
      LLM-call output schema. Conventionally inherits ``LLMResultMixin``.
    - ``inputs_spec``: ``INPUTS.sources(...)`` — the per-field source
      adapter declaration.
    - Optional ``prompt_name``: Phoenix prompt name override. Defaults
      to ``to_snake_case(cls.__name__, strip_suffix='Step')``.
    - Optional ``DEFAULT_TOOLS``: list of ``PipelineTool`` subclasses
      auto-bound to the agent at run time.
    - Optional ``user_prompt_variables(inputs)`` classmethod: returns
      the dict passed to ``prompt_service.get_user_prompt(...)``.
      Default: ``inputs.model_dump()``.

    Subclasses must implement ``run(ctx) -> NextNode | End[...]`` — the
    return annotation drives the edge graph. The body should call
    ``await self._run_llm(ctx)`` then return the next node instance.
    """

    # Class-level config — overridden by each concrete subclass
    INPUTS: ClassVar[type] = None  # type: ignore[assignment]
    INSTRUCTIONS: ClassVar[type[BaseModel]] = None  # type: ignore[assignment]
    inputs_spec: ClassVar[Any] = None  # SourcesSpec
    prompt_name: ClassVar[str | None] = None
    DEFAULT_TOOLS: ClassVar[list[type]] = []

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Skip the abstract base; only validate concrete subclasses.
        if cls.__name__ == "LLMStepNode":
            return
        # Naming convention is enforced at Pipeline class level (so a
        # node defined outside a Pipeline still works in tests). The
        # ``Pipeline`` validator walks ``cls.nodes`` and applies all
        # rules in one place.

    @classmethod
    def get_node_def(cls, local_ns: dict[str, Any] | None) -> NodeDef:
        """Override pydantic-graph's edge resolution to honour TYPE_CHECKING."""
        return _build_node_def(cls, local_ns)

    @classmethod
    def step_name(cls) -> str:
        """``CamelCase`` -> ``snake_case``, dropping the ``Step`` suffix."""
        return to_snake_case(cls.__name__, strip_suffix="Step")

    @classmethod
    def resolved_prompt_name(cls) -> str:
        """Per-class Phoenix prompt name; falls back to ``step_name()``."""
        return cls.prompt_name or cls.step_name()

    @classmethod
    def user_prompt_variables(cls, inputs: Any) -> dict[str, Any]:
        """Build the variables dict passed to the prompt template.

        Default: ``inputs.model_dump()``. Override on a subclass to
        coerce, rename, or add derived fields before rendering.
        """
        if hasattr(inputs, "model_dump"):
            return inputs.model_dump()
        return dict(inputs)

    async def _run_llm(self, ctx: GraphRunContext[PipelineState, PipelineDeps]) -> Any:
        """Resolve inputs, call the LLM, persist output to state.

        Returns the validated instructions instance produced by the
        Pydantic-AI agent. Subclasses can use the returned value for
        branch logic before returning the next node.
        """
        import logging

        from llm_pipeline.agent_builders import StepDeps, build_step_agent
        from llm_pipeline.resources import resolve_resources
        from llm_pipeline.runtime import PipelineContext

        cls = type(self)
        if cls.inputs_spec is None:
            raise TypeError(
                f"{cls.__name__}.inputs_spec must be set "
                f"(call {cls.INPUTS.__name__}.sources(...) and assign)."
            )
        if cls.INSTRUCTIONS is None:
            raise TypeError(
                f"{cls.__name__}.INSTRUCTIONS must be set."
            )

        adapter_ctx = ctx.state.to_adapter_ctx(
            input_cls=ctx.deps.input_cls,
            node_classes=ctx.deps.node_classes,
            pipeline=ctx.deps,
        )
        inputs_instance = cls.inputs_spec.resolve(adapter_ctx)

        # Resolve any resource-typed fields on the inputs (no-op when
        # the inputs class has no resource fields, which is the common
        # case for the demo).
        runtime_ctx = PipelineContext(
            session=ctx.deps.session,
            logger=logging.getLogger(f"llm_pipeline.graph.{cls.step_name()}"),
            run_id=ctx.deps.run_id,
            step_name=cls.step_name(),
        )
        resolve_resources(inputs_instance, runtime_ctx)

        # Build the prompt variables. When the eval runner has
        # threaded a per-step prompt override through PipelineDeps,
        # render that template directly (F_STRING semantics — same
        # as Phoenix's template_format) and skip the Phoenix fetch.
        variables = cls.user_prompt_variables(inputs_instance)
        prompt_override = (ctx.deps.prompt_overrides or {}).get(cls.step_name())
        if prompt_override is not None:
            try:
                user_prompt = prompt_override.format(**variables)
            except (KeyError, IndexError) as exc:
                raise ValueError(
                    f"prompt override for step {cls.step_name()!r} references "
                    f"unknown variable {exc!r}"
                ) from exc
        else:
            user_prompt = ctx.deps.prompt_service.get_user_prompt(
                prompt_key=cls.resolved_prompt_name(),
                variables=variables,
            )

        # Optional review-feedback injection. Cleared after each step.
        review_ctx = ctx.deps.review_context
        if review_ctx:
            user_prompt = _append_review_to_prompt(user_prompt, review_ctx)
            ctx.deps.review_context = None

        # The eval runner can swap the INSTRUCTIONS schema by mapping
        # the production class -> a delta-derived subclass (built via
        # ``apply_instruction_delta``). The override is keyed by the
        # production class itself so multiple variants can coexist
        # across concurrent runs without leaking into class-level
        # state.
        output_type = (
            (ctx.deps.instructions_overrides or {}).get(cls.INSTRUCTIONS)
            or cls.INSTRUCTIONS
        )

        agent = build_step_agent(
            step_name=cls.step_name(),
            output_type=output_type,
            prompt_name=cls.resolved_prompt_name(),
            instrument=ctx.deps.instrumentation_settings,
            tools=None,  # Phase 1: tools deferred to a follow-up
        )

        step_deps = StepDeps(
            session=ctx.deps.session,
            pipeline_context=ctx.state.metadata,
            prompt_service=ctx.deps.prompt_service,
            run_id=ctx.deps.run_id,
            pipeline_name=ctx.deps.pipeline_name,
            step_name=cls.step_name(),
        )

        run_result = await agent.run(
            user_prompt,
            deps=step_deps,
            model=ctx.deps.model,
        )
        instruction = run_result.output

        ctx.state.record_output(cls, [instruction])
        return instruction

    @abstractmethod
    async def run(self, ctx: GraphRunContext[PipelineState, PipelineDeps]) -> Any:
        """Subclasses implement: call ``_run_llm(ctx)``; return next node."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# ExtractionNode
# ---------------------------------------------------------------------------


class ExtractionNode(BaseNode[PipelineState, PipelineDeps, Any]):
    """Base for extraction nodes.

    Reads its source step's output (via ``inputs_spec``), shapes
    SQLModel rows, persists them on the session, and writes them
    to ``state.extractions``.

    Subclasses declare:

    - ``MODEL``: the SQLModel class this extraction produces.
    - ``INPUTS``: the pathway inputs class (a ``StepInputs`` subclass,
      conventionally named ``From{ExtractionName}Inputs``).
    - ``source_step``: the ``LLMStepNode`` whose output this
      extraction reads. The validator asserts ``source_step`` appears
      upstream in the pipeline graph.
    - ``inputs_spec``: ``INPUTS.sources(...)``.

    Subclasses implement ``extract(self, inputs) -> list[MODEL]`` and
    ``run(ctx) -> NextNode | End[...]`` (calls ``_run_extraction(ctx)``
    then returns the next node).
    """

    MODEL: ClassVar[type] = None  # type: ignore[assignment]
    INPUTS: ClassVar[type] = None  # type: ignore[assignment]
    source_step: ClassVar[type[LLMStepNode]] = None  # type: ignore[assignment]
    inputs_spec: ClassVar[Any] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__name__ == "ExtractionNode":
            return

    @classmethod
    def get_node_def(cls, local_ns: dict[str, Any] | None) -> NodeDef:
        """Override pydantic-graph's edge resolution to honour TYPE_CHECKING."""
        return _build_node_def(cls, local_ns)

    @abstractmethod
    def extract(self, inputs: Any) -> list[Any]:
        """Convert pathway inputs into a list of ``MODEL`` instances."""
        raise NotImplementedError

    async def _run_extraction(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> list[Any]:
        """Resolve inputs, run ``extract``, persist rows, update state."""
        cls = type(self)
        if cls.inputs_spec is None:
            raise TypeError(
                f"{cls.__name__}.inputs_spec must be set."
            )
        if cls.MODEL is None:
            raise TypeError(
                f"{cls.__name__}.MODEL must be set."
            )

        adapter_ctx = ctx.state.to_adapter_ctx(
            input_cls=ctx.deps.input_cls,
            node_classes=ctx.deps.node_classes,
            pipeline=ctx.deps,
        )
        pathway_inputs = cls.inputs_spec.resolve(adapter_ctx)

        rows = self.extract(pathway_inputs)

        for row in rows:
            ctx.deps.session.add(row)
        ctx.deps.session.flush()

        ctx.state.record_extraction(cls.MODEL, rows)
        return rows

    @abstractmethod
    async def run(self, ctx: GraphRunContext[PipelineState, PipelineDeps]) -> Any:
        """Subclasses: call ``_run_extraction(ctx)``; return next node."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# ReviewNode
# ---------------------------------------------------------------------------


class ReviewNode(BaseNode[PipelineState, PipelineDeps, Any]):
    """Pause-point for human review.

    Phase 1 stamps a review request into ``state.metadata`` (no actual
    pause — the graph continues). Phase 2 wires the snapshot-and-
    pause flow via the persistence backend so the run resumes when the
    reviewer responds.

    Subclasses declare:

    - ``target_step``: the ``LLMStepNode`` whose output is being reviewed.
    - Optional ``condition(state) -> bool``: when ``False``, skip
      review entirely. Default: always review.
    - Optional ``webhook_url``: webhook to POST when review is requested.

    Subclasses implement ``run(ctx) -> NextNode | End[...]``.
    """

    target_step: ClassVar[type[LLMStepNode]] = None  # type: ignore[assignment]
    condition: ClassVar[Callable[[PipelineState], bool] | None] = None
    webhook_url: ClassVar[str | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__name__ == "ReviewNode":
            return

    @classmethod
    def get_node_def(cls, local_ns: dict[str, Any] | None) -> NodeDef:
        """Override pydantic-graph's edge resolution to honour TYPE_CHECKING."""
        return _build_node_def(cls, local_ns)

    async def _begin_review(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> None:
        """Open a pending ``PipelineReview`` and signal pause to the runtime.

        Sets ``state.metadata["awaiting_review"] = True`` so the
        runtime loop in ``run_pipeline`` breaks out without driving
        the next node. The next-node snapshot is still written by
        pydantic-graph (in ``'created'`` status) — ``resume_pipeline``
        picks it up via ``Graph.iter_from_persistence``.
        """
        import os
        import uuid as _uuid

        from sqlmodel import Session, select

        from llm_pipeline.state import PipelineReview, PipelineRun

        cls = type(self)
        if cls.condition is not None:
            try:
                allow = cls.condition(ctx.state)  # type: ignore[arg-type]
            except Exception:
                allow = True
            if not allow:
                return  # condition says skip — no pause

        token = str(_uuid.uuid4())
        target_name = (
            cls.target_step.__name__ if cls.target_step is not None else cls.__name__
        )
        review_data: dict[str, Any] = {}
        if cls.target_step is not None:
            target_outputs = ctx.state.outputs.get(cls.target_step.__name__) or []
            if target_outputs:
                review_data = {"raw_data": target_outputs[0]}

        engine = ctx.deps.session.get_bind()
        with Session(engine) as session:
            session.add(PipelineReview(
                token=token,
                run_id=ctx.deps.run_id,
                pipeline_name=ctx.deps.pipeline_name,
                step_name=_step_name_for_target(cls.target_step) or cls.__name__,
                step_number=len(ctx.state.outputs),
                status="pending",
                review_data=review_data,
                input_data=ctx.state.input_data,
            ))
            run = session.exec(
                select(PipelineRun).where(
                    PipelineRun.run_id == ctx.deps.run_id,
                )
            ).first()
            if run is not None:
                run.status = "awaiting_review"
                session.add(run)
            session.commit()

        ctx.state.metadata["awaiting_review"] = True
        ctx.state.metadata["review_token"] = token

        # Optional webhook fan-out — fire-and-forget; logged + swallowed on failure.
        webhook_url = (
            cls.webhook_url
            or os.environ.get("LLM_PIPELINE_REVIEW_WEBHOOK")
        )
        if webhook_url:
            try:
                _post_review_webhook(
                    webhook_url, token=token, run_id=ctx.deps.run_id,
                    pipeline_name=ctx.deps.pipeline_name, target=target_name,
                    review_data=review_data,
                )
            except Exception:
                logger.warning(
                    "Review webhook failed for token=%s", token, exc_info=True,
                )

    @abstractmethod
    async def run(self, ctx: GraphRunContext[PipelineState, PipelineDeps]) -> Any:
        """Subclasses: call ``_begin_review(ctx)``; return the post-review node."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


logger = logging.getLogger(__name__)


def _step_name_for_target(target: type | None) -> str | None:
    """Snake-cased step_name for a ``target_step`` class (or ``None``)."""
    if target is None:
        return None
    return to_snake_case(target.__name__, strip_suffix="Step")


def _post_review_webhook(
    url: str,
    *,
    token: str,
    run_id: str,
    pipeline_name: str,
    target: str,
    review_data: dict[str, Any],
) -> None:
    """Fire-and-forget POST to the review webhook.

    Mirrors the legacy ``_send_review_webhook`` shape so existing
    integrations don't need to change. Errors raise — caller logs +
    swallows.
    """
    import os as _os

    import httpx

    base_url = _os.environ.get("LLM_PIPELINE_BASE_URL", "http://localhost:8642")
    httpx.post(
        url,
        json={
            "event": "review_requested",
            "run_id": run_id,
            "pipeline_name": pipeline_name,
            "step_name": target,
            "token": token,
            "review_link": f"{base_url}/review/{token}",
            "callback_url": f"{base_url}/reviews/{token}",
            "callback_method": "POST",
            "review_data": review_data,
        },
        timeout=10,
    )


def _append_review_to_prompt(user_prompt: str, review_ctx: dict[str, Any]) -> str:
    """Append human review feedback to the rendered user prompt.

    Mirrors the legacy ``_append_review_to_prompt`` from ``pipeline.py``
    so the resumed-after-review behaviour stays bit-identical.
    """
    decision = review_ctx.get("decision", "")
    notes = review_ctx.get("notes", "")
    original = review_ctx.get("original_output", "")

    if not notes:
        return user_prompt

    if decision == "minor_revision":
        appendix = (
            "\n\n---\n"
            "Your previous output requires minor revision.\n\n"
            f"Reviewer feedback:\n{notes}\n\n"
            f"Previous output:\n{original}\n\n"
            "Please consider this feedback and make a revision to the "
            "previous output accordingly."
        )
    elif decision == "major_revision":
        appendix = (
            "\n\n---\n"
            "A previous attempt at this step was rejected. "
            f"The reviewer left the following feedback:\n{notes}"
        )
    elif decision == "approved":
        appendix = (
            "\n\n---\n"
            "A reviewer approved the previous step and left these notes "
            f"for context:\n{notes}"
        )
    else:
        return user_prompt

    return user_prompt + appendix
