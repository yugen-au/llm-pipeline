"""Task wrappers turning a graph pipeline into a ``pydantic-evals`` task.

A ``pydantic-evals`` task is just a callable ``(case_input) -> output``
that ``Dataset.evaluate`` invokes for each case. This module builds two
shapes:

- :func:`build_step_task` — exercises a single :class:`LLMStepNode` in
  isolation. ``case_input`` is the dict of fields the step's prompt
  template needs (the ``user_prompt_variables`` payload). The task
  builds the agent + prompt the same way ``_run_llm`` does, applies
  variant overrides, and returns the validated instructions as a
  ``model_dump``'d dict.

- :func:`build_pipeline_task` — drives the whole graph end-to-end via
  ``Graph.run`` against a fresh ``SimpleStatePersistence``. Variant
  overrides ride on ``PipelineDeps``. Returns a dict keyed by step
  class name -> instructions dump (matches ``state.outputs`` shape).

Both share the same in-memory sandbox: a SQLite engine the runner
spins up per-evaluation, with a ``Session`` opened per case so DB
writes don't leak across cases.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, TYPE_CHECKING

from llm_pipeline.evals.variants import Variant, apply_instruction_delta

if TYPE_CHECKING:
    from sqlalchemy import Engine

    from llm_pipeline.graph.nodes import LLMStepNode
    from llm_pipeline.graph.pipeline import Pipeline


__all__ = ["build_step_task", "build_pipeline_task"]


# ---------------------------------------------------------------------------
# Step task
# ---------------------------------------------------------------------------


def build_step_task(
    pipeline_cls: type["Pipeline"],
    step_cls: type["LLMStepNode"],
    variant: Variant,
    *,
    model: str,
    engine: "Engine",
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Build a per-case async task for a single step.

    The returned coroutine takes a ``case_input`` dict (the fields the
    step's prompt template references — i.e. the
    ``user_prompt_variables(...)`` payload), runs the step's LLM call
    once, and returns the validated instructions as a dict.

    Variant overrides are applied to the agent build + prompt rendering:

    - ``variant.model`` -> overrides ``model`` for this call.
    - ``variant.prompt_overrides[step_name]`` -> rendered as the user
      prompt; Phoenix prompt fetch skipped.
    - ``variant.instructions_delta`` -> built into a subclass of the
      step's INSTRUCTIONS via ``apply_instruction_delta``; the agent
      validates against the override schema.

    Args:
        pipeline_cls: The pipeline owning ``step_cls`` (used to surface
            a stable ``pipeline_name`` for prompt service / instrumentation).
        step_cls: The :class:`LLMStepNode` subclass under evaluation.
        variant: Overrides to apply (``Variant()`` for baseline).
        model: Production model string. Used when ``variant.model`` is
            ``None``.
        engine: A SQLite (or similar) engine the per-case session
            opens against. Sessions are short-lived; commits roll back
            on the in-memory engine the runner provides.
    """
    from llm_pipeline.agent_builders import StepDeps, build_step_agent
    from llm_pipeline.prompts.service import PromptService

    instructions_cls = step_cls.INSTRUCTIONS
    if instructions_cls is None:
        raise ValueError(
            f"{step_cls.__name__}.INSTRUCTIONS is not set; cannot build step task."
        )

    # Pre-resolve the override class once per task (cheap; done at task
    # build time so each case skips the create_model overhead).
    output_type = apply_instruction_delta(
        instructions_cls, variant.instructions_delta,
    )
    resolved_model = variant.model or model
    step_name = step_cls.step_name()
    prompt_template_override = (variant.prompt_overrides or {}).get(step_name)

    async def _step_task(case_input: dict[str, Any]) -> dict[str, Any]:
        from sqlmodel import Session

        prompt_service = PromptService()
        session = Session(engine)

        # Render the user prompt: variant override -> direct format(**vars);
        # otherwise -> Phoenix-backed prompt service.
        if prompt_template_override is not None:
            try:
                user_prompt = prompt_template_override.format(**case_input)
            except (KeyError, IndexError) as exc:
                raise ValueError(
                    f"prompt override for step {step_name!r} references "
                    f"unknown variable {exc!r}"
                ) from exc
        else:
            user_prompt = prompt_service.get_user_prompt(
                prompt_key=step_cls.step_name(),
                variables=case_input,
            )

        # System prompt is rendered statically and embedded on the agent
        # — no @agent.instructions hook (matches the runtime path in
        # ``LLMStepNode._run_llm`` post-B.5).
        system_prompt = prompt_service.get_system_prompt(
            prompt_key=step_cls.step_name(),
            variables=case_input,
        )

        agent = build_step_agent(
            step_name=step_name,
            output_type=output_type,
            instructions=system_prompt,
            tools=None,
        )

        deps = StepDeps(
            session=session,
            pipeline_context={},
            prompt_service=prompt_service,
            run_id="eval-step-task",
            pipeline_name=pipeline_cls.pipeline_name(),
            step_name=step_name,
        )

        try:
            result = await agent.run(
                user_prompt,
                deps=deps,
                model=resolved_model,
            )
        finally:
            session.rollback()
            session.close()

        out = result.output
        if hasattr(out, "model_dump"):
            return out.model_dump(mode="json")
        return dict(out) if isinstance(out, dict) else {"value": out}

    return _step_task


# ---------------------------------------------------------------------------
# Pipeline task
# ---------------------------------------------------------------------------


def build_pipeline_task(
    pipeline_cls: type["Pipeline"],
    variant: Variant,
    *,
    model: str,
    engine: "Engine",
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Build a per-case async task for a whole pipeline.

    The returned coroutine takes a ``case_input`` dict matching the
    pipeline's ``INPUT_DATA`` and runs the full graph in-memory
    (``Graph.run`` with no persistence backend — pydantic-graph
    defaults to ``SimpleStatePersistence``). Variant overrides are
    applied via :class:`PipelineDeps` so every node's ``_run_llm``
    sees them.

    Returns ``state.outputs`` — a dict keyed by step class name with a
    list of per-call instruction dumps. Evaluators referencing a
    specific step's output should index on the step class name.
    """
    import uuid

    from llm_pipeline.graph.state import PipelineDeps, PipelineState
    from llm_pipeline.prompts.service import PromptService

    input_cls = pipeline_cls.INPUT_DATA
    pre_built_overrides = _prebuild_instructions_overrides(pipeline_cls, variant)

    async def _pipeline_task(case_input: dict[str, Any]) -> dict[str, Any]:
        from sqlmodel import Session

        # Validate the case input against the pipeline's INPUT_DATA so
        # evaluator-side schema drift surfaces as an error here rather
        # than deep inside the graph.
        if input_cls is not None:
            validated_input = input_cls.model_validate(case_input)
            input_dump = validated_input.model_dump(mode="json")
        else:
            input_dump = dict(case_input) if case_input else None

        state = PipelineState(input_data=input_dump)
        session = Session(engine)
        deps = PipelineDeps(
            session=session,
            prompt_service=PromptService(),
            run_id=f"eval-{uuid.uuid4()}",
            pipeline_name=pipeline_cls.pipeline_name(),
            model=variant.model or model,
            input_cls=input_cls,
            node_classes=dict(pipeline_cls._node_classes),
            wiring=dict(pipeline_cls._wiring),
            prompt_overrides=dict(variant.prompt_overrides or {}),
            instructions_overrides=dict(pre_built_overrides),
        )

        graph = pipeline_cls.graph()
        start_node_cls = pipeline_cls.start_node
        if start_node_cls is None:
            raise RuntimeError(
                f"{pipeline_cls.__name__}.start_node is None — cannot run.",
            )

        try:
            await graph.run(start_node_cls(), state=state, deps=deps)
        finally:
            session.rollback()
            session.close()

        return dict(state.outputs)

    return _pipeline_task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _prebuild_instructions_overrides(
    pipeline_cls: type["Pipeline"],
    variant: Variant,
) -> dict[type, type]:
    """Apply ``variant.instructions_delta`` against every step's INSTRUCTIONS.

    Today ``Variant.instructions_delta`` is a single delta applied at
    the pipeline level — but on a per-pipeline-target eval we only
    have one INSTRUCTIONS class to mutate (the variant editor scopes
    deltas to a target step). We build the override per step that
    declares INSTRUCTIONS so the eval runner can swap the right one
    without the caller knowing which step the delta targets.

    For a pipeline-target variant with no ``instructions_delta``, the
    resulting map is empty.
    """
    from llm_pipeline.graph.nodes import LLMStepNode

    if not variant.instructions_delta:
        return {}

    overrides: dict[type, type] = {}
    for binding in pipeline_cls.nodes:
        node_cls = binding.cls
        if not isinstance(node_cls, type) or not issubclass(node_cls, LLMStepNode):
            continue
        instructions_cls = node_cls.INSTRUCTIONS
        if instructions_cls is None:
            continue
        if instructions_cls in overrides:
            continue
        overrides[instructions_cls] = apply_instruction_delta(
            instructions_cls, variant.instructions_delta,
        )
    return overrides
