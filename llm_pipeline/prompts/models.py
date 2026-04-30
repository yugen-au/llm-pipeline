"""Canonical prompt wire model + Phoenix translation helpers.

One ``Prompt`` record carries every message — matches Phoenix's native
CHAT template and what the UI editor renders. Used for both responses
and request bodies (``version_id`` is surfaced from Phoenix and
ignored on writes, since Phoenix auto-versions).

The ``phoenix_to_prompt`` / ``prompt_to_phoenix_payloads`` helpers
are the ONE place we translate between the canonical model and
Phoenix's REST shapes — same role ``phoenix_to_dataset`` plays for
evals.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class PromptMessage(BaseModel):
    role: Literal["system", "user"]
    content: str


class PromptMetadata(BaseModel):
    display_name: str | None = None
    category: str | None = None
    step_name: str | None = None
    variable_definitions: dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class Prompt(BaseModel):
    """Canonical wire shape for a Phoenix prompt / LLMStep.

    Phoenix's prompt and our LLMStep are the same record — same parts:
    system + user messages, ``tools``, ``response_format``, plus
    metadata for things our UI adds on top (auto-generated variables).
    The ``messages``, ``model``, and ``metadata`` slices are
    human-authored (live in YAML); ``response_format`` and ``tools``
    are code-derived from the step's ``INSTRUCTIONS`` class and
    ``DEFAULT_TOOLS`` (set at push time, not in YAML).

    ``model`` is a pydantic-ai-format string (``provider:name``, e.g.
    ``openai:gpt-5``). It maps bidirectionally to Phoenix's
    ``model_provider`` + ``model_name`` pair via :func:`pai_model_to_phoenix`
    / :func:`phoenix_model_to_pai`.
    """

    name: str
    description: str | None = None
    metadata: PromptMetadata = Field(default_factory=PromptMetadata)
    messages: list[PromptMessage]
    model: str | None = None
    response_format: dict[str, Any] | None = None
    tools: dict[str, Any] | None = None
    version_id: str | None = None


# ---------------------------------------------------------------------------
# Phoenix <-> canonical translation
# ---------------------------------------------------------------------------


_NAME_INVALID_RE = re.compile(r"[^a-z0-9_-]+")
_SYSTEM_ROLES = frozenset({"system", "developer"})


# pydantic-ai uses lowercase ``provider:name`` strings; Phoenix's REST
# API expects an uppercase ``model_provider`` enum + ``model_name``.
# Most mappings are direct uppercase, but a few diverge (notably
# ``google-gla`` ↔ ``GEMINI``). The two tables are NOT exact inverses —
# multiple pydantic-ai providers (e.g. google-gla / google-vertex) can
# back the same Phoenix provider, so the Phoenix→pai direction picks
# the most-common variant.
_PAI_TO_PHOENIX_PROVIDER: dict[str, str] = {
    "openai": "OPENAI",
    "azure": "AZURE_OPENAI",
    "anthropic": "ANTHROPIC",
    "google-gla": "GEMINI",
    "google-vertex": "GEMINI",
    "groq": "GROQ",
    "mistral": "MISTRAL",
    "deepseek": "DEEPSEEK",
    "ollama": "OLLAMA",
    "bedrock": "AWS",
}
_PHOENIX_TO_PAI_PROVIDER: dict[str, str] = {
    "OPENAI": "openai",
    "AZURE_OPENAI": "azure",
    "ANTHROPIC": "anthropic",
    "GEMINI": "google-gla",
    "GROQ": "groq",
    "MISTRAL": "mistral",
    "DEEPSEEK": "deepseek",
    "OLLAMA": "ollama",
    "AWS": "bedrock",
}


class ModelStringError(ValueError):
    """Raised when a pydantic-ai model string can't be parsed."""


def pai_model_to_phoenix(pai_model: str) -> tuple[str, str]:
    """Split a pydantic-ai ``provider:name`` string into Phoenix shape.

    Returns ``(model_provider, model_name)`` where ``model_provider`` is
    Phoenix's uppercase enum value. Unknown pydantic-ai providers fall
    through to a direct uppercase conversion (caller should still
    validate the resulting pair against Phoenix on push).
    """
    if ":" not in pai_model:
        raise ModelStringError(
            f"Model string {pai_model!r} must be of the form "
            f"'provider:name' (e.g. 'openai:gpt-5')."
        )
    provider, _, name = pai_model.partition(":")
    if not provider or not name:
        raise ModelStringError(
            f"Model string {pai_model!r} has empty provider or name."
        )
    phoenix_provider = _PAI_TO_PHOENIX_PROVIDER.get(provider, provider.upper())
    return phoenix_provider, name


def phoenix_model_to_pai(provider: str | None, name: str | None) -> str | None:
    """Combine Phoenix ``model_provider`` + ``model_name`` back to pai format.

    Returns ``None`` when either side is missing — caller decides whether
    that's an error. Unknown Phoenix providers fall through to a direct
    lowercase conversion.
    """
    if not provider or not name:
        return None
    pai_provider = _PHOENIX_TO_PAI_PROVIDER.get(provider, provider.lower())
    return f"{pai_provider}:{name}"


class PromptNameError(ValueError):
    """Raised when a prompt name can't be coerced to a Phoenix identifier."""


def sanitise_prompt_name(raw: str) -> str:
    """Coerce ``raw`` into a Phoenix-legal identifier (lowercase, ``[a-z0-9_-]``).

    Empty / unrecoverable input raises ``PromptNameError``.
    """
    s = raw.lower()
    s = _NAME_INVALID_RE.sub("_", s)
    s = re.sub(r"_+", "_", s).strip("_-")
    if not s:
        raise PromptNameError(f"Invalid prompt name {raw!r}")
    return s


def _extract_messages(version: dict[str, Any]) -> list[PromptMessage]:
    """Pull messages out of a Phoenix version's CHAT/STR template."""
    template = version.get("template") or {}
    template_type = template.get("type")
    if template_type == "string":
        body = template.get("template")
        if isinstance(body, str):
            return [PromptMessage(role="system", content=body)]
        return []
    if template_type != "chat":
        return []
    out: list[PromptMessage] = []
    for msg in template.get("messages") or []:
        role = msg.get("role")
        content = msg.get("content")
        if isinstance(content, list):
            content = "".join(
                p.get("text", "")
                for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            )
        if not isinstance(content, str):
            continue
        ui_role = (
            "system" if role in _SYSTEM_ROLES
            else "user" if role == "user"
            else None
        )
        if ui_role is None:
            continue
        out.append(PromptMessage(role=ui_role, content=content))
    return out


def _record_metadata(record: dict[str, Any]) -> dict[str, Any]:
    md = record.get("metadata")
    return md if isinstance(md, dict) else {}


def phoenix_to_prompt(
    record: dict[str, Any], version: dict[str, Any],
) -> Prompt:
    """Build a canonical ``Prompt`` from Phoenix record + version."""
    raw_meta = _record_metadata(record)
    metadata = PromptMetadata.model_validate(raw_meta)
    rf = version.get("response_format")
    tools = version.get("tools")
    return Prompt(
        name=record.get("name") or "",
        description=version.get("description") or record.get("description"),
        metadata=metadata,
        messages=_extract_messages(version),
        model=phoenix_model_to_pai(
            version.get("model_provider"), version.get("model_name"),
        ),
        response_format=rf if isinstance(rf, dict) else None,
        tools=tools if isinstance(tools, dict) else None,
        version_id=version.get("id"),
    )


def prompt_to_phoenix_payloads(
    payload: Prompt,
    *,
    base_version: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Map a ``Prompt`` write payload onto Phoenix's ``prompt`` + ``version`` shapes.

    ``response_format`` / ``tools`` come from the payload (callers fill
    them in from the step before calling — see
    :func:`derive_phoenix_extras_for_step` and
    :mod:`llm_pipeline.prompts.registration`). ``payload.model`` (a
    pydantic-ai ``provider:name`` string) splits into Phoenix's
    ``model_provider`` + ``model_name`` pair when set; otherwise the
    pair carries forward from ``base_version``, falling back to
    ``OPENAI`` / ``gpt-4o-mini`` only when nothing is known.
    ``base_version`` is the existing Phoenix version (for inheriting
    invocation_parameters etc. when the payload is partial).
    """
    name = sanitise_prompt_name(payload.name)
    metadata: dict[str, Any] = payload.metadata.model_dump(exclude_none=True)

    prompt_data: dict[str, Any] = {"name": name, "metadata": metadata}
    if payload.description is not None:
        prompt_data["description"] = payload.description

    base = base_version or {}
    messages = [
        {"role": m.role, "content": m.content} for m in payload.messages
    ]
    messages.sort(key=lambda m: 0 if m["role"] == "system" else 1)

    # Model resolution: payload.model wins; else carry forward from
    # base_version; else last-resort default.
    if payload.model:
        model_provider, model_name = pai_model_to_phoenix(payload.model)
    else:
        model_provider = base.get("model_provider", "OPENAI")
        model_name = base.get("model_name", "gpt-4o-mini")

    version_data: dict[str, Any] = {
        "model_provider": model_provider,
        "model_name": model_name,
        "template": {"type": "chat", "messages": messages},
        "template_type": "CHAT",
        "template_format": base.get("template_format", "F_STRING"),
        "invocation_parameters": base.get(
            "invocation_parameters", {"type": "openai", "openai": {}},
        ),
    }
    if payload.description is not None:
        version_data["description"] = payload.description

    rf = payload.response_format if payload.response_format is not None else base.get("response_format")
    if rf is not None:
        version_data["response_format"] = rf
    tools = payload.tools if payload.tools is not None else base.get("tools")
    if tools is not None:
        version_data["tools"] = tools

    return prompt_data, version_data


__all__ = [
    "ModelStringError",
    "Prompt",
    "PromptMessage",
    "PromptMetadata",
    "PromptNameError",
    "pai_model_to_phoenix",
    "phoenix_model_to_pai",
    "phoenix_to_prompt",
    "prompt_to_phoenix_payloads",
    "sanitise_prompt_name",
]
