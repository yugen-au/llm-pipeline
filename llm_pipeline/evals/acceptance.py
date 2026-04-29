"""Accept a Phoenix experiment's variant into production.

The variant delta has up to three surfaces. Each is independent;
``accept_experiment`` walks them in order and records what changed
under a single ``EvaluationAcceptance`` row:

1. ``variant.model`` -> upsert :class:`StepModelConfig` keyed by
   ``(pipeline_name, step_name)``.

2. ``variant.prompt_overrides[step_name]`` -> POST a new Phoenix
   prompt version preserving the existing system message + swapping
   the user message; tag the new version ``production`` and demote
   the prior ``production`` tag.

3. ``variant.instructions_delta`` -> AST-rewrite the step's
   ``INSTRUCTIONS`` source file (resolved via
   ``inspect.getsourcefile``) using
   :func:`llm_pipeline.creator.ast_modifier.apply_instructions_delta_to_file`.
   Writes a ``.bak`` next to the source.

After all three accept paths succeed, an ``EvaluationAcceptance`` row
is inserted as the audit record.
"""
from __future__ import annotations

import inspect
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from llm_pipeline.evals.phoenix_client import (
    DatasetNotFoundError,
    ExperimentNotFoundError,
    PhoenixDatasetClient,
)
from llm_pipeline.evals.variants import Variant

if TYPE_CHECKING:
    from sqlalchemy import Engine

    from llm_pipeline.graph.nodes import LLMStepNode
    from llm_pipeline.graph.pipeline import Pipeline
    from llm_pipeline.prompts.phoenix_client import PhoenixPromptClient
    from llm_pipeline.state import EvaluationAcceptance


__all__ = ["accept_experiment", "AcceptanceError"]


logger = logging.getLogger(__name__)


class AcceptanceError(RuntimeError):
    """Anything went wrong while walking the accept paths."""


def accept_experiment(
    experiment_id: str,
    *,
    pipeline_registry: dict[str, type["Pipeline"]],
    engine: "Engine",
    dataset_client: PhoenixDatasetClient | None = None,
    prompt_client: "PhoenixPromptClient | None" = None,
    accepted_by: str | None = None,
    notes: str | None = None,
) -> "EvaluationAcceptance":
    """Walk the variant delta + record the acceptance.

    Args:
        experiment_id: Phoenix experiment id (its metadata holds the
            variant payload).
        pipeline_registry: ``pipeline_name -> Pipeline subclass`` map.
            Used to resolve target_name → step class for prompt /
            instructions accept paths.
        engine: SQLAlchemy engine for ``StepModelConfig`` upsert +
            ``EvaluationAcceptance`` insert.
        dataset_client: Phoenix dataset client (tests inject a stub).
        prompt_client: Phoenix prompt client (tests inject a stub).
        accepted_by: Free-form user identifier; surfaced on the audit
            row.
        notes: Optional human note attached to the acceptance row.
    """
    dataset_client = dataset_client or PhoenixDatasetClient()
    if prompt_client is None:
        from llm_pipeline.prompts.phoenix_client import PhoenixPromptClient

        prompt_client = PhoenixPromptClient()

    experiment = dataset_client.get_experiment(experiment_id)
    metadata = (experiment or {}).get("metadata") or {}
    variant = _extract_variant(metadata)
    target_type, target_name, dataset_id, pipeline_name = _resolve_target(
        metadata=metadata,
        dataset_client=dataset_client,
        experiment=experiment,
    )

    pipeline_cls, step_cls = _resolve_pipeline_and_step(
        pipeline_registry=pipeline_registry,
        target_type=target_type,
        target_name=target_name,
    )
    pipeline_name = pipeline_name or pipeline_cls.pipeline_name()
    step_name = step_cls.step_name() if step_cls is not None else None

    accept_paths: dict[str, Any] = {}

    if variant.model:
        accept_paths["model"] = _accept_model(
            engine=engine,
            pipeline_name=pipeline_name,
            step_name=step_name,
            model=variant.model,
        )

    if variant.prompt_overrides:
        accept_paths["prompts"] = _accept_prompt_overrides(
            client=prompt_client,
            pipeline_cls=pipeline_cls,
            overrides=variant.prompt_overrides,
        )

    if variant.instructions_delta:
        if step_cls is None:
            raise AcceptanceError(
                "instructions_delta cannot be accepted on a "
                "pipeline-target experiment — variant editor scopes "
                "deltas to a specific step.",
            )
        accept_paths["instructions"] = _accept_instructions_delta(
            step_cls=step_cls,
            delta=variant.instructions_delta,
        )

    return _record_acceptance(
        engine=engine,
        experiment_id=experiment_id,
        dataset_id=dataset_id,
        pipeline_name=pipeline_name,
        step_name=step_name,
        variant=variant,
        accept_paths=accept_paths,
        accepted_by=accepted_by,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Variant + target resolution
# ---------------------------------------------------------------------------


def _extract_variant(metadata: dict) -> Variant:
    """Pull the variant payload out of experiment metadata."""
    payload = metadata.get("variant")
    if not isinstance(payload, dict):
        return Variant()
    try:
        return Variant.model_validate(payload)
    except Exception as exc:
        raise AcceptanceError(
            f"experiment metadata.variant is not a valid Variant: {exc}",
        ) from exc


def _resolve_target(
    *,
    metadata: dict,
    dataset_client: PhoenixDatasetClient,
    experiment: dict,
) -> tuple[str, str, str, str | None]:
    """Resolve target_type, target_name, dataset_id, pipeline_name.

    The experiment metadata persisted by the runner already carries
    ``target_type`` and ``target_name``; for older experiments lacking
    those, fall back to the dataset's metadata.
    """
    target_type = metadata.get("target_type")
    target_name = metadata.get("target_name")
    pipeline_name = metadata.get("pipeline_name")

    dataset_id = (
        experiment.get("dataset_id")
        or experiment.get("dataset")
        or metadata.get("dataset_id")
        or ""
    )
    if not dataset_id:
        raise AcceptanceError(
            f"experiment {experiment.get('id')!r} has no dataset_id",
        )

    if target_type and target_name:
        return target_type, target_name, dataset_id, pipeline_name

    try:
        dataset = dataset_client.get_dataset(dataset_id)
    except DatasetNotFoundError as exc:
        raise AcceptanceError(
            f"dataset {dataset_id!r} not found while resolving "
            f"experiment target",
        ) from exc

    ds_meta = (dataset or {}).get("metadata") or {}
    target_type = target_type or ds_meta.get("target_type")
    target_name = target_name or ds_meta.get("target_name")
    if target_type not in {"step", "pipeline"} or not target_name:
        raise AcceptanceError(
            f"could not resolve target_type/target_name for "
            f"experiment {experiment.get('id')!r}",
        )
    return target_type, target_name, dataset_id, pipeline_name


def _resolve_pipeline_and_step(
    *,
    pipeline_registry: dict[str, type["Pipeline"]],
    target_type: str,
    target_name: str,
) -> tuple[type["Pipeline"], type["LLMStepNode"] | None]:
    if target_type == "pipeline":
        pipeline_cls = pipeline_registry.get(target_name)
        if pipeline_cls is None:
            raise AcceptanceError(
                f"pipeline {target_name!r} not in registry "
                f"({sorted(pipeline_registry)})",
            )
        return pipeline_cls, None

    matches: list[tuple[type["Pipeline"], type]] = []
    for pipeline_cls in pipeline_registry.values():
        for node_cls in pipeline_cls.nodes:
            if node_cls.__name__ == target_name:
                matches.append((pipeline_cls, node_cls))
    if not matches:
        raise AcceptanceError(
            f"step {target_name!r} not found in any registered pipeline",
        )
    if len(matches) > 1:
        owners = sorted({p.__name__ for p, _ in matches})
        raise AcceptanceError(
            f"step {target_name!r} appears in multiple pipelines: {owners}",
        )
    return matches[0]


# ---------------------------------------------------------------------------
# Accept paths
# ---------------------------------------------------------------------------


def _accept_model(
    *,
    engine: "Engine",
    pipeline_name: str,
    step_name: str | None,
    model: str,
) -> dict[str, Any]:
    """Upsert ``StepModelConfig`` for the target step."""
    if step_name is None:
        raise AcceptanceError(
            "model accept path requires a step target; pipeline-level "
            "model overrides are not supported",
        )

    from sqlmodel import Session, select

    from llm_pipeline.db.step_config import StepModelConfig

    with Session(engine) as session:
        existing = session.exec(
            select(StepModelConfig).where(
                StepModelConfig.pipeline_name == pipeline_name,
                StepModelConfig.step_name == step_name,
            ),
        ).first()
        if existing is None:
            existing = StepModelConfig(
                pipeline_name=pipeline_name,
                step_name=step_name,
                model=model,
            )
            session.add(existing)
        else:
            existing.model = model
            existing.updated_at = datetime.now(timezone.utc)
            session.add(existing)
        session.commit()
        session.refresh(existing)

    return {
        "pipeline_name": pipeline_name,
        "step_name": step_name,
        "model": model,
        "step_model_config_id": existing.id,
    }


def _accept_prompt_overrides(
    *,
    client: "PhoenixPromptClient",
    pipeline_cls: type["Pipeline"],
    overrides: dict[str, str],
) -> list[dict[str, Any]]:
    """Cut a new Phoenix prompt version per step, retag ``production``.

    For each ``step_name -> user_prompt`` override:
    1. Resolve the Phoenix prompt name via the step's
       ``resolved_prompt_name()``.
    2. Fetch the current ``production`` (or ``latest``) version's
       system message; preserve it on the new version.
    3. POST a new version with the override as the user message.
    4. Tag the new version ``production`` and detach the prior tag
       so only one version holds the tag at a time.
    """
    step_by_name = {n.step_name(): n for n in _llm_step_classes(pipeline_cls)}

    results: list[dict[str, Any]] = []
    for step_name, override_user_prompt in overrides.items():
        step_cls = step_by_name.get(step_name)
        if step_cls is None:
            raise AcceptanceError(
                f"prompt override step {step_name!r} not found on "
                f"pipeline {pipeline_cls.__name__}",
            )
        prompt_name = step_cls.resolved_prompt_name()
        result = _swap_prompt_version(
            client=client,
            prompt_name=prompt_name,
            new_user_template=override_user_prompt,
        )
        result["step_name"] = step_name
        result["prompt_name"] = prompt_name
        results.append(result)
    return results


def _swap_prompt_version(
    *,
    client: "PhoenixPromptClient",
    prompt_name: str,
    new_user_template: str,
) -> dict[str, Any]:
    """One step's slice of :func:`_accept_prompt_overrides`."""
    from llm_pipeline.prompts.phoenix_client import (
        PhoenixError,
        PromptNotFoundError,
    )

    # Pull the current production version (so we can preserve the
    # system message + know which version's tag to demote).
    prior_version: dict[str, Any] | None = None
    prior_tag = "production"
    try:
        prior_version = client.get_by_tag(prompt_name, prior_tag)
    except PromptNotFoundError:
        # Fall back to latest (e.g. a freshly-created prompt without
        # the production tag yet).
        prior_tag = ""
        try:
            prior_version = client.get_latest(prompt_name)
        except PromptNotFoundError:
            prior_version = None

    system_text = _extract_system_text(prior_version)

    new_messages: list[dict[str, str]] = []
    if system_text:
        new_messages.append({"role": "system", "content": system_text})
    new_messages.append({"role": "user", "content": new_user_template})

    new_version = client.create(
        prompt={
            "name": prompt_name,
            "description": (prior_version or {}).get("description") or "",
            "metadata": (prior_version or {}).get("metadata") or {},
        },
        version={
            "model_provider": (prior_version or {}).get("model_provider")
                or "OPENAI",
            "model_name": (prior_version or {}).get("model_name")
                or "gpt-4o-mini",
            "template": {"type": "chat", "messages": new_messages},
            "template_type": "CHAT",
            "template_format": (prior_version or {}).get("template_format")
                or "F_STRING",
            "invocation_parameters": (
                (prior_version or {}).get("invocation_parameters") or {}
            ),
        },
    )

    new_version_id = new_version.get("id") or new_version.get("version_id")
    if not new_version_id:
        raise AcceptanceError(
            f"Phoenix returned no version id for prompt {prompt_name!r}",
        )

    # Tag the new version production; demote the old.
    try:
        client.add_tag(new_version_id, "production")
    except PhoenixError as exc:
        raise AcceptanceError(
            f"failed to tag new prompt version {new_version_id!r} "
            f"as production: {exc}",
        ) from exc

    prior_id = (prior_version or {}).get("id")
    if prior_id and prior_tag == "production" and prior_id != new_version_id:
        try:
            client.delete_tag(prior_id, "production")
        except PhoenixError:
            logger.warning(
                "failed to demote previous production tag on prompt "
                "version %s; the new tag still wins on lookup.",
                prior_id,
            )

    return {
        "new_version_id": new_version_id,
        "previous_version_id": prior_id,
    }


def _extract_system_text(version: dict | None) -> str | None:
    if not version:
        return None
    template = version.get("template") or {}
    if template.get("type") != "chat":
        body = template.get("template")
        return body if isinstance(body, str) else None
    for msg in template.get("messages") or []:
        if msg.get("role") in {"system", "developer"}:
            content = msg.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = [
                    p.get("text") for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                ]
                return "".join(t for t in parts if isinstance(t, str)) or None
    return None


def _llm_step_classes(pipeline_cls: type["Pipeline"]) -> list[type]:
    from llm_pipeline.graph.nodes import LLMStepNode

    return [
        n for n in pipeline_cls.nodes
        if isinstance(n, type) and issubclass(n, LLMStepNode)
    ]


def _accept_instructions_delta(
    *,
    step_cls: type["LLMStepNode"],
    delta: list[dict],
) -> dict[str, Any]:
    """AST-rewrite the step's INSTRUCTIONS class file."""
    instructions_cls = step_cls.INSTRUCTIONS
    if instructions_cls is None:
        raise AcceptanceError(
            f"{step_cls.__name__}.INSTRUCTIONS is unset; cannot apply delta",
        )
    source_file = inspect.getsourcefile(instructions_cls)
    if source_file is None:
        raise AcceptanceError(
            f"could not locate source file for "
            f"{instructions_cls.__module__}.{instructions_cls.__name__}",
        )

    from llm_pipeline.creator.ast_modifier import apply_instructions_delta_to_file

    return apply_instructions_delta_to_file(
        source_file=Path(source_file),
        class_name=instructions_cls.__name__,
        delta=delta,
    )


# ---------------------------------------------------------------------------
# Audit row
# ---------------------------------------------------------------------------


def _record_acceptance(
    *,
    engine: "Engine",
    experiment_id: str,
    dataset_id: str,
    pipeline_name: str,
    step_name: str | None,
    variant: Variant,
    accept_paths: dict[str, Any],
    accepted_by: str | None,
    notes: str | None,
) -> "EvaluationAcceptance":
    from sqlmodel import Session

    from llm_pipeline.state import EvaluationAcceptance

    row = EvaluationAcceptance(
        experiment_id=experiment_id,
        dataset_id=dataset_id,
        pipeline_name=pipeline_name,
        step_name=step_name,
        delta_summary=variant.model_dump(),
        accept_paths=accept_paths,
        notes=notes,
        accepted_by=accepted_by,
    )
    with Session(engine) as session:
        session.add(row)
        session.commit()
        session.refresh(row)
    return row
