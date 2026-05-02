"""Sync code-derived schemas (response_format, tools) from registered
steps into Phoenix prompts.

Phoenix stores prompt definitions; pydantic remains authoritative for
validation. At UI startup we walk every registered pipeline's steps,
derive each step's response-format JSON schema (from its
``Instructions`` class) and tool schemas (from ``AgentTool.Args``
or legacy ``register_agent`` callables), and POST a new prompt
version when the derived schemas differ from what Phoenix has. The
prompt name is the step's snake_case name.

The sync is one-way (code → Phoenix). Phoenix Playground edits to
``response_format`` / ``tools`` are non-authoritative — the next
startup overwrites them.

**Why only response_format + tools (not variable_definitions):**
Phoenix's prompt-level ``metadata`` blob is set-once on first
``POST /v1/prompts``; subsequent posts under the same name only
create new versions and silently ignore metadata changes. So
variable definitions are owned by the migration script (which sets
metadata on the initial create); the registration sync stays out
of metadata to avoid pretending to update something that won't take.
"""
from __future__ import annotations

import inspect
import logging
from typing import Any, Callable, Dict, List, Optional, Type

from pydantic import BaseModel, create_model

from llm_pipeline.naming import to_snake_case
from llm_pipeline.prompts import phoenix_config
from llm_pipeline.prompts.phoenix_client import (
    PhoenixError,
    PhoenixPromptClient,
    PromptNotFoundError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def sync_pipelines_to_phoenix(
    introspection_registry: Dict[str, Type],
    *,
    client: Optional[PhoenixPromptClient] = None,
    tag: str = "production",
) -> Dict[str, int]:
    """Iterate every registered pipeline and sync each unique step's
    derived schemas to Phoenix.

    Returns a counter dict ``{"updated": n, "skipped": n, "missing": n,
    "error": n}``. ``missing`` counts steps whose Phoenix prompt
    doesn't exist yet (run the migration script to seed them); the
    sync silently skips them rather than auto-creating a stub.
    """
    summary: Dict[str, int] = {"updated": 0, "skipped": 0, "missing": 0, "error": 0}

    if not phoenix_config.is_configured():
        logger.info(
            "Phoenix not configured (PHOENIX_BASE_URL / OTEL endpoint unset); "
            "skipping prompt schema sync."
        )
        return summary

    if client is None:
        try:
            client = PhoenixPromptClient()
        except PhoenixError as exc:
            logger.warning("Phoenix client init failed; skipping sync: %s", exc)
            return summary

    seen: set[Type] = set()
    for pipeline_name, pipeline_cls in introspection_registry.items():
        for step_cls in iter_step_classes(pipeline_cls):
            if step_cls in seen:
                continue
            seen.add(step_cls)
            prompt_name = step_cls.step_name()
            try:
                outcome = sync_step_to_phoenix(
                    step_cls,
                    prompt_name=prompt_name,
                    client=client,
                    tag=tag,
                )
            except PhoenixError as exc:
                logger.warning(
                    "Phoenix sync failed for %s/%s: %s",
                    pipeline_name, prompt_name, exc,
                )
                summary["error"] += 1
                continue
            summary[outcome] = summary.get(outcome, 0) + 1

    if any(v for v in summary.values()):
        logger.info("Phoenix prompt schema sync: %s", summary)
    return summary


def sync_step_to_phoenix(
    step_cls: Type,
    *,
    prompt_name: str,
    client: PhoenixPromptClient,
    tag: str = "production",
) -> str:
    """Push one step's derived schemas to Phoenix as a new prompt version.

    Returns ``"updated" | "skipped" | "missing"``. Raises ``PhoenixError``
    only on transport failures; missing prompts return ``"missing"``.
    """
    response_format = derive_response_format(getattr(step_cls, "INSTRUCTIONS", None))
    tools = derive_tools(step_cls)

    try:
        existing = client.get_latest(prompt_name)
    except PromptNotFoundError:
        logger.warning(
            "Phoenix prompt %r not found — run migrate_prompts_to_phoenix.py "
            "before registration sync to seed templates.",
            prompt_name,
        )
        return "missing"

    new_version = _compose_updated_version(
        existing, response_format=response_format, tools=tools,
    )
    if _equivalent(existing, new_version):
        return "skipped"

    # Phoenix ignores prompt-level metadata after the first create; just
    # send the name to satisfy the required ``prompt`` field.
    payload_prompt: Dict[str, Any] = {"name": prompt_name}
    payload_version = _strip_id(new_version)

    created = client.create(prompt=payload_prompt, version=payload_version)
    version_id = created.get("id") if isinstance(created, dict) else None
    if version_id:
        try:
            client.add_tag(version_id, tag, description="schema sync at startup")
        except PhoenixError as exc:  # pragma: no cover - non-fatal
            logger.warning("Phoenix tag failed for %s: %s", prompt_name, exc)

    logger.info("Phoenix prompt %r updated -> version %s", prompt_name, version_id)
    return "updated"


# ---------------------------------------------------------------------------
# Schema derivation
# ---------------------------------------------------------------------------


def derive_response_format(instructions_cls: Optional[Type]) -> Optional[Dict[str, Any]]:
    if instructions_cls is None:
        return None
    if not (isinstance(instructions_cls, type) and issubclass(instructions_cls, BaseModel)):
        return None
    schema = instructions_cls.model_json_schema()
    description = (instructions_cls.__doc__ or "").strip() or instructions_cls.__name__
    return {
        "type": "json_schema",
        "json_schema": {
            "name": instructions_cls.__name__,
            "description": description,
            "schema": schema,
        },
    }


def derive_tools(step_cls: Type) -> Optional[Dict[str, Any]]:
    pipeline_tools: List[Type] = list(getattr(step_cls, "DEFAULT_TOOLS", None) or [])
    agent_callables: List[Callable[..., Any]] = []
    agent_name = getattr(step_cls, "AGENT", None)
    if agent_name:
        from llm_pipeline.agent_registry import get_agent_tools

        agent_callables = list(get_agent_tools(agent_name))

    if not pipeline_tools and not agent_callables:
        return None

    tools_array: List[Dict[str, Any]] = []
    for tool_cls in pipeline_tools:
        tools_array.append(_agent_tool_to_phoenix(tool_cls))
    for fn in agent_callables:
        tools_array.append(_callable_to_phoenix(fn))

    return {"type": "tools", "tools": tools_array}


def _agent_tool_to_phoenix(tool_cls: Type) -> Dict[str, Any]:
    args_cls = getattr(tool_cls, "ARGS", None)
    parameters = (
        args_cls.model_json_schema()
        if isinstance(args_cls, type) and issubclass(args_cls, BaseModel)
        else {"type": "object", "properties": {}}
    )
    return {
        "type": "function",
        "function": {
            "name": to_snake_case(tool_cls.__name__, strip_suffix="Tool"),
            "description": (tool_cls.__doc__ or "").strip(),
            "parameters": parameters,
        },
    }


def _callable_to_phoenix(fn: Callable[..., Any]) -> Dict[str, Any]:
    """Derive a Phoenix tool entry from a free callable using its signature.

    Handles the legacy ``register_agent("foo", tools=[...])`` path. Skips
    ``self`` / ``cls``. Falls back to ``str`` for unannotated parameters
    so Phoenix gets a renderable shape.
    """
    sig = inspect.signature(fn)
    field_defs: Dict[str, Any] = {}
    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue
        annotation = (
            param.annotation
            if param.annotation is not inspect.Parameter.empty
            else str
        )
        default = (
            param.default if param.default is not inspect.Parameter.empty else ...
        )
        field_defs[param_name] = (annotation, default)

    if field_defs:
        try:
            arg_model = create_model(f"{fn.__name__}_args", **field_defs)
            parameters = arg_model.model_json_schema()
        except Exception:  # pragma: no cover - exotic annotations only
            parameters = {"type": "object", "properties": {}}
    else:
        parameters = {"type": "object", "properties": {}}

    return {
        "type": "function",
        "function": {
            "name": fn.__name__,
            "description": (fn.__doc__ or "").strip(),
            "parameters": parameters,
        },
    }


# ---------------------------------------------------------------------------
# Phoenix payload composition
# ---------------------------------------------------------------------------


def _compose_updated_version(
    existing: Dict[str, Any],
    *,
    response_format: Optional[Dict[str, Any]],
    tools: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build a new ``PromptVersionData`` carrying existing template +
    invocation params with the derived schemas slotted in."""
    new_version = {
        "model_provider": existing.get("model_provider"),
        "model_name": existing.get("model_name"),
        "template": existing.get("template"),
        "template_type": existing.get("template_type"),
        "template_format": existing.get("template_format"),
        "invocation_parameters": existing.get("invocation_parameters"),
    }
    if existing.get("description") is not None:
        new_version["description"] = existing["description"]
    if response_format is not None:
        new_version["response_format"] = response_format
    if tools is not None:
        new_version["tools"] = tools
    return new_version


# ---------------------------------------------------------------------------
# Equivalence checks (avoid version churn on no-op syncs)
# ---------------------------------------------------------------------------


def _equivalent(existing: Dict[str, Any], proposed: Dict[str, Any]) -> bool:
    """True when the bits we sync (response_format + tools) match."""
    return (
        _normalise(existing.get("response_format"))
        == _normalise(proposed.get("response_format"))
        and _normalise(existing.get("tools")) == _normalise(proposed.get("tools"))
    )


def _normalise(value: Any) -> Any:
    """Recursively sort dict keys so equality is order-insensitive."""
    if isinstance(value, dict):
        return {k: _normalise(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return [_normalise(v) for v in value]
    return value


def _strip_id(version: Dict[str, Any]) -> Dict[str, Any]:
    """Phoenix rejects ``id`` on ``POST`` payloads."""
    return {k: v for k, v in version.items() if k != "id"}


# ---------------------------------------------------------------------------
# Pipeline-class step enumeration
# ---------------------------------------------------------------------------


def iter_step_classes(pipeline_cls: Type):
    """Yield every ``LLMStepNode`` subclass reachable from a Pipeline subclass.

    Walks ``pipeline_cls.nodes`` — a list of ``Step | Extraction |
    Review`` bindings — and yields the wrapped ``cls`` for any
    ``Step(...)`` entry. Extractions and reviews are skipped (they're
    not LLM-call nodes).
    """
    from llm_pipeline.graph.nodes import LLMStepNode

    for binding in getattr(pipeline_cls, "nodes", None) or []:
        cls = getattr(binding, "cls", None)
        if not isinstance(cls, type) or not issubclass(cls, LLMStepNode):
            continue
        yield cls


def find_step_for_prompt(
    prompt_name: str,
    introspection_registry: Dict[str, Type],
) -> Optional[Type]:
    """Locate the step class whose ``step_name()`` equals ``prompt_name``.

    Returns ``None`` when no match exists — yaml_sync calls this to
    decide whether to attach code-derived ``response_format`` / ``tools``
    to a Phoenix push, so a missing step just means "no schemas to
    attach", not an error.
    """
    for pipeline_cls in introspection_registry.values():
        for step_cls in iter_step_classes(pipeline_cls):
            if step_cls.step_name() == prompt_name:
                return step_cls
    return None


def derive_step_extras(
    step_cls: Optional[Type],
) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Return ``(response_format, tools)`` derived from a step class.

    Returns ``(None, None)`` when the step is missing or has no
    schemas to derive. Thin wrapper around the two derivers so callers
    don't have to import both.
    """
    if step_cls is None:
        return None, None
    return (
        derive_response_format(getattr(step_cls, "INSTRUCTIONS", None)),
        derive_tools(step_cls),
    )


__all__ = [
    "sync_pipelines_to_phoenix",
    "sync_step_to_phoenix",
    "derive_response_format",
    "derive_tools",
    "find_step_for_prompt",
    "derive_step_extras",
    "iter_step_classes",
]
