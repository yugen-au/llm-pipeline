"""Node base classes for pydantic-graph-native pipelines.

Three node kinds are siblings in the graph:

- ``LLMStepNode`` — declares its *contract* (``INPUTS``, ``INSTRUCTIONS``,
  ``DEFAULT_TOOLS``) and a ``prepare(self, inputs) -> list[XxxPrompt]``
  method whose return-type annotation pins down which
  ``PromptVariables`` subclass it produces. The pipeline's
  ``Step(StepCls, inputs_spec=...)`` binding supplies the wiring
  (where each INPUTS field comes from). Wiring is read from
  ``ctx.deps.wiring[type(self)]`` at runtime; not on the class.

- ``ExtractionNode`` — declares ``INPUTS`` and ``MODEL`` (the SQLModel
  target). ``extract(self, inputs) -> list[MODEL]`` produces rows.
  Wiring lives in the pipeline's ``Extraction(ExtractionCls,
  inputs_spec=...)`` binding. Rows are persisted *and* recorded in
  ``state.outputs[ExtractionCls.__name__]`` so downstream
  ``FromOutput(MyExtraction, field=...)`` works.

- ``ReviewNode`` — declares ``INPUTS`` (what the reviewer sees) and
  ``OUTPUT`` (the structured response shape). Wiring in
  ``Review(ReviewCls, inputs_spec=...)``. Conditional review is
  expressed via graph branching (a prior step's ``run()`` chooses
  whether to return a ReviewNode or skip past it) — no ``condition``
  ClassVar.

All three kinds self-validate at ``__init_subclass__`` (purely
structural — no Phoenix calls). Phoenix-aware checks (prompt
existence, template-vs-PromptVariables drift) run at discovery time.
"""
from __future__ import annotations

import logging
import typing
from abc import abstractmethod
from typing import Any, ClassVar, TYPE_CHECKING

from pydantic import BaseModel
from pydantic_graph import BaseNode, End, GraphRunContext
from pydantic_graph.exceptions import GraphSetupError
from pydantic_graph.nodes import NodeDef

from llm_pipeline.graph.state import PipelineDeps, PipelineState
from llm_pipeline.naming import to_snake_case

if TYPE_CHECKING:
    from sqlmodel import SQLModel

    from llm_pipeline.inputs import StepInputs
    from llm_pipeline.prompts.variables import PromptVariables


__all__ = [
    "ExtractionNode",
    "LLMStepNode",
    "PipelineDeps",
    "ReviewNode",
]


logger = logging.getLogger(__name__)


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
    """
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
        sibling_ns = getattr(cls, "_pipeline_namespace", None)
        if sibling_ns:
            eval_locals.update(sibling_ns)
        if local_ns:
            eval_locals.update(local_ns)
        try:
            return_annotation = eval(  # noqa: S307
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
# prepare() return-type resolution
# ---------------------------------------------------------------------------


def _resolve_prompt_variables_cls(cls: type) -> type:
    """Inspect ``cls.prepare`` and resolve its ``list[XxxPrompt]`` return.

    Returns the concrete ``PromptVariables`` subclass declared as the
    list-element type. Raises ``TypeError`` on any deviation:

    - ``cls`` did not override ``prepare`` (still uses the base impl).
    - ``prepare`` has no return-type annotation.
    - Annotation isn't a ``list[...]``.
    - Element type isn't a concrete ``PromptVariables`` subclass.
    """
    from llm_pipeline.prompts.variables import PromptVariables

    if cls.prepare is LLMStepNode.prepare:  # type: ignore[attr-defined]
        raise TypeError(
            f"{cls.__name__} must override `prepare(self, inputs)` and "
            f"declare its return type as list[XxxPrompt] where XxxPrompt "
            f"is a concrete PromptVariables subclass."
        )

    # Resolve the FULL prepare signature. We enforce two things:
    #   1. The ``inputs`` parameter annotation matches ``cls.INPUTS``.
    #   2. The return annotation is ``list[XxxPrompt]`` for some
    #      concrete ``PromptVariables`` subclass.
    # Forward refs are evaluated against the method's defining module;
    # this means inputs/instructions/prompt classes must live at module
    # top-level (not inside a test-method scope), which is consistent
    # with how real step files are authored.
    try:
        hints = typing.get_type_hints(cls.prepare)
    except Exception as exc:
        raise TypeError(
            f"{cls.__name__}.prepare's annotations could not be "
            f"resolved: {exc}. The inputs parameter type and the "
            f"return type must reference classes defined at the "
            f"module top level (not inside a function/method scope)."
        ) from exc

    return_type = hints.get("return")
    if return_type is None:
        raise TypeError(
            f"{cls.__name__}.prepare must declare a return-type "
            f"annotation of the form list[XxxPrompt]."
        )

    declared_inputs = hints.get("inputs")
    if declared_inputs is not None and declared_inputs is not cls.INPUTS:
        raise TypeError(
            f"{cls.__name__}.prepare's inputs parameter annotation is "
            f"{declared_inputs!r}, but {cls.__name__}.INPUTS is "
            f"{cls.INPUTS!r}. The annotation must match the declared "
            f"INPUTS class exactly."
        )

    origin = typing.get_origin(return_type)
    if origin is not list:
        raise TypeError(
            f"{cls.__name__}.prepare return type must be list[XxxPrompt], "
            f"got {return_type!r}."
        )
    args = typing.get_args(return_type)
    if len(args) != 1:
        raise TypeError(
            f"{cls.__name__}.prepare return type must be list[XxxPrompt] "
            f"with exactly one type argument; got {return_type!r}."
        )

    prompt_cls = args[0]
    if not (isinstance(prompt_cls, type) and issubclass(prompt_cls, PromptVariables)):
        raise TypeError(
            f"{cls.__name__}.prepare element type must be a "
            f"PromptVariables subclass; got {prompt_cls!r}."
        )
    if prompt_cls is PromptVariables:
        raise TypeError(
            f"{cls.__name__}.prepare must use a concrete PromptVariables "
            f"subclass, not the base PromptVariables class itself."
        )
    return prompt_cls


# ---------------------------------------------------------------------------
# LLMStepNode
# ---------------------------------------------------------------------------


class LLMStepNode(BaseNode[PipelineState, PipelineDeps, Any]):
    """Base for LLM-call nodes.

    Subclasses declare:

    - ``INPUTS``: a ``StepInputs`` subclass — what the step *needs*.
    - ``INSTRUCTIONS``: a Pydantic ``BaseModel`` subclass — the
      LLM-call output schema. Conventionally inherits ``LLMResultMixin``.
    - ``DEFAULT_TOOLS``: list of ``PipelineTool`` subclasses
      auto-bound to the agent at run time.
    - ``prepare(self, inputs) -> list[XxxPrompt]``: builds one or more
      ``PromptVariables`` instances (one per LLM call) from the
      resolved ``inputs``. Length 1 for the default single-call case;
      multi-call shapes consensus_strategy.

    Subclasses must implement ``run(ctx) -> NextNode | End[...]`` — the
    return annotation drives the edge graph. The body should call
    ``await self._run_llm(ctx)`` then return the next node instance.

    *No* wiring (``inputs_spec``, ``prompt_name``) on the class. Wiring
    lives on the ``Step(StepCls, inputs_spec=...)`` binding in the
    pipeline. Phoenix prompt name is always ``cls.step_name()``.

    *No* ``MODEL`` ClassVar. Model lives on the Phoenix prompt; read
    at runtime.
    """

    # Class-level *contract* — overridden by each concrete subclass.
    INPUTS: ClassVar[type] = None  # type: ignore[assignment]
    INSTRUCTIONS: ClassVar[type[BaseModel]] = None  # type: ignore[assignment]
    DEFAULT_TOOLS: ClassVar[list[type]] = []

    # Resolved at __init_subclass__ from prepare's return-type annotation.
    # Public for introspection / tooling (NodeSpec / Pipeline.inspect()).
    prompt_variables_cls: ClassVar[type | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__name__ == "LLMStepNode":
            return
        if cls.INPUTS is None:
            raise TypeError(
                f"{cls.__name__}.INPUTS must be set to a StepInputs subclass."
            )
        if cls.INSTRUCTIONS is None:
            raise TypeError(
                f"{cls.__name__}.INSTRUCTIONS must be set to a Pydantic BaseModel "
                f"subclass declaring the LLM output schema."
            )
        # Resolve and cache the PromptVariables subclass declared by
        # this step's prepare() return annotation.
        cls.prompt_variables_cls = _resolve_prompt_variables_cls(cls)

    @classmethod
    def get_node_def(cls, local_ns: dict[str, Any] | None) -> NodeDef:
        """Override pydantic-graph's edge resolution to honour TYPE_CHECKING."""
        return _build_node_def(cls, local_ns)

    @classmethod
    def step_name(cls) -> str:
        """``CamelCase`` -> ``snake_case``, dropping the ``Step`` suffix."""
        return to_snake_case(cls.__name__, strip_suffix="Step")

    def prepare(self, inputs: Any) -> list["PromptVariables"]:
        """Build per-call ``PromptVariables`` instances from the resolved inputs.

        Subclasses MUST override this and declare a return-type
        annotation of ``list[XxxPrompt]`` where ``XxxPrompt`` is a
        concrete ``PromptVariables`` subclass. Length 1 = single LLM
        call; length N = consensus / multi-call.

        The validator (``__init_subclass__``) reads the annotation to
        cache ``prompt_variables_cls`` and verify the contract.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must override prepare(self, inputs) "
            f"with a concrete return-type annotation."
        )

    async def _run_llm(self, ctx: GraphRunContext[PipelineState, PipelineDeps]) -> Any:
        """Resolve inputs from wiring, render prompts via ``prepare()``, run LLM.

        Reads the pipeline-level wiring (``inputs_spec``) from
        ``ctx.deps.wiring[type(self)]``. The class itself carries no
        wiring; only the contract.
        """
        from llm_pipeline.agent_builders import StepDeps, build_step_agent
        from llm_pipeline.resources import resolve_resources
        from llm_pipeline.runtime import PipelineContext

        cls = type(self)
        binding = (ctx.deps.wiring or {}).get(cls)
        if binding is None:
            raise RuntimeError(
                f"No pipeline-level binding found for {cls.__name__} "
                f"in deps.wiring. Did the pipeline declare "
                f"`Step({cls.__name__}, inputs_spec=...)`?"
            )

        adapter_ctx = ctx.state.to_adapter_ctx(
            input_cls=ctx.deps.input_cls,
            node_classes=ctx.deps.node_classes,
            pipeline=ctx.deps,
        )
        inputs_instance = binding.inputs_spec.resolve(adapter_ctx)

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

        # prepare() returns one or more PromptVariables instances.
        prompt_calls = self.prepare(inputs_instance)
        if not isinstance(prompt_calls, list) or not prompt_calls:
            raise TypeError(
                f"{cls.__name__}.prepare must return a non-empty list "
                f"of {cls.prompt_variables_cls.__name__ if cls.prompt_variables_cls else 'PromptVariables'} "
                f"instances; got {prompt_calls!r}."
            )

        # Phase: single-call path. Multi-call (consensus) is a follow-up;
        # we run prompt_calls[0] for now and stash a TODO when len > 1.
        if len(prompt_calls) > 1:
            logger.warning(
                "%s.prepare returned %d calls; multi-call dispatch is "
                "not yet implemented. Running the first call only.",
                cls.__name__, len(prompt_calls),
            )
        call = prompt_calls[0]

        # Variables flow into both system and user message templates
        # from the same flat dict (Phoenix's variable_definitions is
        # message-agnostic). prepare()-supplied vars come from the
        # PromptVariables instance; auto_generate-supplied vars are
        # resolved at render time (B.5 follow-up; currently empty for
        # the demo so the merge is a no-op).
        prompt_vars = call.model_dump()
        prompt_override = (ctx.deps.prompt_overrides or {}).get(cls.step_name())
        if prompt_override is not None:
            try:
                user_prompt = prompt_override.format(**prompt_vars)
            except (KeyError, IndexError) as exc:
                raise ValueError(
                    f"prompt override for step {cls.step_name()!r} references "
                    f"unknown variable {exc!r}"
                ) from exc
        else:
            user_prompt = ctx.deps.prompt_service.get_user_prompt(
                prompt_key=cls.step_name(),
                variables=prompt_vars,
            )

        # System prompt is rendered statically here and passed to the
        # agent at construction. The previous @agent.instructions hook
        # (which fetched + rendered at every agent.run) is gone — the
        # static path matches pydantic-ai's canonical case and lets us
        # compose auto_vars + prepare-supplied vars in one place.
        system_prompt = ctx.deps.prompt_service.get_system_prompt(
            prompt_key=cls.step_name(),
            variables=prompt_vars,
        )

        review_ctx = ctx.deps.review_context
        if review_ctx:
            user_prompt = _append_review_to_prompt(user_prompt, review_ctx)
            ctx.deps.review_context = None

        # The eval runner can swap the INSTRUCTIONS schema by mapping
        # the production class -> a delta-derived subclass.
        output_type = (
            (ctx.deps.instructions_overrides or {}).get(cls.INSTRUCTIONS)
            or cls.INSTRUCTIONS
        )

        # Model resolution (B.6): eval-time override on PipelineDeps
        # wins. When unset (production), fall back to the Phoenix
        # prompt's stored model — Phoenix is the runtime source of
        # truth for which LLM each step calls.
        if ctx.deps.model is not None:
            model = ctx.deps.model
        else:
            model = ctx.deps.prompt_service.get_model(cls.step_name())
            if model is None:
                raise RuntimeError(
                    f"No model resolved for step {cls.step_name()!r}: "
                    f"PipelineDeps.model is unset and the Phoenix prompt "
                    f"has no model field. Set the model: line in "
                    f"llm-pipeline-prompts/{cls.step_name()}.yaml or pass "
                    f"a default via PipelineDeps."
                )

        agent = build_step_agent(
            step_name=cls.step_name(),
            output_type=output_type,
            instructions=system_prompt,
            instrument=ctx.deps.instrumentation_settings,
            tools=None,
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
            model=model,
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

    Subclasses declare:

    - ``INPUTS``: a ``StepInputs`` subclass.
    - ``MODEL``: the SQLModel class this extraction produces.

    Subclasses implement ``extract(self, inputs) -> list[MODEL]`` to
    shape rows, and ``run(ctx) -> NextNode | End[...]`` to drive the
    graph. The ``_run_extraction`` body resolves inputs from the
    pipeline binding, runs ``extract``, persists rows to the session,
    AND records them in ``state.outputs[ExtractionCls.__name__]`` so
    downstream ``FromOutput(MyExtraction, ...)`` works.

    *No* ``source_step`` ClassVar. The pipeline's ``Extraction(cls,
    inputs_spec=...)`` binding declares the wiring, including which
    upstream step's output the extraction reads (via FromOutput).
    """

    INPUTS: ClassVar[type] = None  # type: ignore[assignment]
    MODEL: ClassVar[type] = None  # type: ignore[assignment]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__name__ == "ExtractionNode":
            return
        if cls.INPUTS is None:
            raise TypeError(
                f"{cls.__name__}.INPUTS must be set to a StepInputs subclass."
            )
        if cls.MODEL is None:
            raise TypeError(
                f"{cls.__name__}.MODEL must be set to the SQLModel class "
                f"this extraction produces."
            )

    @classmethod
    def get_node_def(cls, local_ns: dict[str, Any] | None) -> NodeDef:
        return _build_node_def(cls, local_ns)

    @abstractmethod
    def extract(self, inputs: Any) -> list[Any]:
        """Convert pathway inputs into a list of ``MODEL`` instances."""
        raise NotImplementedError

    async def _run_extraction(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> list[Any]:
        """Resolve inputs from wiring, run ``extract``, persist + record rows."""
        cls = type(self)
        binding = (ctx.deps.wiring or {}).get(cls)
        if binding is None:
            raise RuntimeError(
                f"No pipeline-level binding found for {cls.__name__} "
                f"in deps.wiring. Did the pipeline declare "
                f"`Extraction({cls.__name__}, inputs_spec=...)`?"
            )

        adapter_ctx = ctx.state.to_adapter_ctx(
            input_cls=ctx.deps.input_cls,
            node_classes=ctx.deps.node_classes,
            pipeline=ctx.deps,
        )
        pathway_inputs = binding.inputs_spec.resolve(adapter_ctx)

        rows = self.extract(pathway_inputs)

        for row in rows:
            ctx.deps.session.add(row)
        ctx.deps.session.flush()

        # Record rows in BOTH state.extractions (existing DB tracking
        # surface) and state.outputs (so FromOutput(ExtractionCls, ...)
        # works uniformly with the rest of the graph).
        ctx.state.record_extraction(cls.MODEL, rows)
        ctx.state.record_output(cls, rows)
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

    Subclasses declare:

    - ``INPUTS``: a ``StepInputs`` subclass — the data the reviewer sees.
    - ``OUTPUT``: a Pydantic ``BaseModel`` subclass — the reviewer's
      structured response shape.
    - Optional ``webhook_url``: target to POST when review is requested.

    Subclasses implement ``run(ctx) -> NextNode | End[...]``. Conditional
    review is expressed via graph branching from a prior step: the
    step's ``run()`` chooses whether to return a ``ReviewNode`` instance
    or skip past it. No ``condition`` ClassVar.

    On resume, the reviewer's response is validated against ``OUTPUT``
    and recorded at ``state.outputs[ReviewCls.__name__]`` (handled by
    the runtime's resume path; not in this body).
    """

    INPUTS: ClassVar[type] = None  # type: ignore[assignment]
    OUTPUT: ClassVar[type[BaseModel]] = None  # type: ignore[assignment]
    webhook_url: ClassVar[str | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__name__ == "ReviewNode":
            return
        if cls.INPUTS is None:
            raise TypeError(
                f"{cls.__name__}.INPUTS must be set (the data the "
                f"reviewer sees)."
            )
        if cls.OUTPUT is None:
            raise TypeError(
                f"{cls.__name__}.OUTPUT must be set (the reviewer's "
                f"structured response shape)."
            )

    @classmethod
    def get_node_def(cls, local_ns: dict[str, Any] | None) -> NodeDef:
        return _build_node_def(cls, local_ns)

    async def _begin_review(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> None:
        """Open a pending ``PipelineReview`` and signal pause to the runtime.

        Resolves INPUTS via the pipeline binding and stores the dump as
        the review payload. Sets ``state.metadata["awaiting_review"] = True``
        so the runtime loop in ``run_pipeline`` breaks out without
        driving the next node.
        """
        import os
        import uuid as _uuid

        from sqlmodel import Session, select

        from llm_pipeline.state import PipelineReview, PipelineRun

        cls = type(self)
        binding = (ctx.deps.wiring or {}).get(cls)
        if binding is None:
            raise RuntimeError(
                f"No pipeline-level binding found for {cls.__name__} "
                f"in deps.wiring. Did the pipeline declare "
                f"`Review({cls.__name__}, inputs_spec=...)`?"
            )

        adapter_ctx = ctx.state.to_adapter_ctx(
            input_cls=ctx.deps.input_cls,
            node_classes=ctx.deps.node_classes,
            pipeline=ctx.deps,
        )
        review_inputs = binding.inputs_spec.resolve(adapter_ctx)
        review_data: dict[str, Any] = {
            "raw_data": review_inputs.model_dump()
            if hasattr(review_inputs, "model_dump") else dict(review_inputs)
        }

        token = str(_uuid.uuid4())
        engine = ctx.deps.session.get_bind()
        with Session(engine) as session:
            session.add(PipelineReview(
                token=token,
                run_id=ctx.deps.run_id,
                pipeline_name=ctx.deps.pipeline_name,
                step_name=cls.__name__,
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

        webhook_url = (
            cls.webhook_url
            or os.environ.get("LLM_PIPELINE_REVIEW_WEBHOOK")
        )
        if webhook_url:
            try:
                _post_review_webhook(
                    webhook_url, token=token, run_id=ctx.deps.run_id,
                    pipeline_name=ctx.deps.pipeline_name,
                    target=cls.__name__,
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


def _post_review_webhook(
    url: str,
    *,
    token: str,
    run_id: str,
    pipeline_name: str,
    target: str,
    review_data: dict[str, Any],
) -> None:
    """Fire-and-forget POST to the review webhook."""
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
    """Append human review feedback to the rendered user prompt."""
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
