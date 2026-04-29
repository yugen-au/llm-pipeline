"""Prompt service — fetches templates from Phoenix and formats them.

Phoenix owns prompt definitions; the framework owns variable rendering.
``PromptService`` collapses framework-style keys
(``<step>.system_instruction`` / ``<step>.user_prompt``) onto Phoenix's
single CHAT prompt per step (with system + user messages inside) and
exposes the same public surface the rest of the framework already
calls.
"""
from __future__ import annotations

import logging
import re
from threading import RLock
from typing import Any, Dict, Optional, Tuple

from llm_pipeline.prompts.phoenix_client import (
    PhoenixPromptClient,
    PromptNotFoundError,
)
from llm_pipeline.prompts.utils import extract_variables_from_content

logger = logging.getLogger(__name__)


# Keys come in as ``<base>.<role_suffix>``. We honour the long-standing
# convention so callers don't change in Phase A; Phase C drops the
# suffixes entirely.
_SUFFIX_TO_ROLE: Dict[str, str] = {
    "system_instruction": "system",
    "system": "system",
    "user_prompt": "user",
    "user": "user",
}

_SYSTEM_ROLES = frozenset({"system", "developer"})
_USER_ROLES = frozenset({"user"})


def _split_key(prompt_key: str, prompt_type: str) -> Tuple[str, str]:
    """Split a framework prompt key into (phoenix_name, role).

    ``widget_detection.system_instruction`` -> ``("widget_detection", "system")``.
    Bare keys like ``widget_detection`` use ``prompt_type`` for the role.
    Keys with unrecognised dotted suffixes (e.g. ``foo.guidance.bar``)
    fold the rest into the name with underscores so a Phoenix-legal
    identifier comes out — guidance prompts are a transitional concern
    and become unreachable once the migration completes in Phase C.
    """
    if "." in prompt_key:
        head, _, tail = prompt_key.rpartition(".")
        if tail in _SUFFIX_TO_ROLE:
            return _sanitise_name(head), _SUFFIX_TO_ROLE[tail]
        # Fold dots into underscores for things like
        # widget_detection.guidance.row_data so the name is still
        # Phoenix-legal.
        return _sanitise_name(prompt_key), prompt_type
    return _sanitise_name(prompt_key), prompt_type


_NAME_INVALID_RE = re.compile(r"[^a-z0-9_-]+")


def _sanitise_name(raw: str) -> str:
    """Coerce a framework key into a Phoenix-legal identifier."""
    s = raw.lower()
    s = _NAME_INVALID_RE.sub("_", s)
    s = re.sub(r"_+", "_", s).strip("_-")
    if not s:
        raise ValueError(f"Cannot derive Phoenix prompt name from {raw!r}")
    return s


def _extract_message_text(version: Dict[str, Any], role: str) -> Optional[str]:
    """Return the first message body that matches ``role``.

    Handles both Phoenix template shapes (``PromptChatTemplate`` and
    ``PromptStringTemplate``) and both content shapes (plain string and
    list of typed content parts).
    """
    template = version.get("template") or {}
    template_type = template.get("type")

    if template_type == "string":
        # STR templates have no role; the body is the whole prompt and
        # callers fetch it via either prompt_type.
        body = template.get("template")
        return body if isinstance(body, str) else None

    if template_type != "chat":
        return None

    target_roles = (
        _SYSTEM_ROLES if role == "system"
        else _USER_ROLES if role == "user"
        else {role}
    )
    for msg in template.get("messages") or []:
        if msg.get("role") not in target_roles:
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            # Typed content parts; concatenate text parts in order.
            parts = [
                p.get("text") for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            ]
            return "".join(t for t in parts if isinstance(t, str)) or None
    return None


class PromptService:
    """Resolve prompt templates from Phoenix and render them.

    Construct with no arguments to build a default client from env vars
    (``PHOENIX_BASE_URL`` / ``OTEL_EXPORTER_OTLP_ENDPOINT``,
    ``PHOENIX_API_KEY``). Inject a fake client in tests.

    A small in-memory cache keys ``(name, tag)`` to avoid re-fetching
    every Phoenix prompt on each ``agent.run_sync``. Call
    :meth:`clear_cache` after editing a prompt in the UI to force the
    next fetch.
    """

    def __init__(
        self,
        client: Optional[PhoenixPromptClient] = None,
        *,
        default_tag: str = "production",
    ) -> None:
        # Lazy: only build the default client on first lookup so
        # callers in unconfigured envs (tests that mock the agent and
        # never resolve a prompt) can construct freely.
        self._client: Optional[PhoenixPromptClient] = client
        self._default_tag = default_tag
        self._cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._cache_lock = RLock()

    def _get_client(self) -> PhoenixPromptClient:
        if self._client is None:
            self._client = PhoenixPromptClient()
        return self._client

    # ----- cache --------------------------------------------------------------

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._cache.clear()

    def _fetch_version(self, name: str) -> Dict[str, Any]:
        """Pull the version we should use for ``name`` (tagged, then latest)."""
        cache_key = (name, self._default_tag)
        with self._cache_lock:
            cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        client = self._get_client()
        try:
            version = client.get_by_tag(name, self._default_tag)
        except PromptNotFoundError:
            # Prompt exists but has no version with the configured tag.
            # Fall back to latest so a freshly-created prompt without
            # the production tag still resolves.
            version = client.get_latest(name)

        with self._cache_lock:
            self._cache[cache_key] = version
        return version

    # ----- public surface -----------------------------------------------------

    def get_prompt(
        self,
        prompt_key: str,
        prompt_type: str = "system",
        context: Optional[dict] = None,  # accepted for compat; ignored
        fallback: Optional[str] = None,
    ) -> str:
        """Fetch a raw prompt template by key + role.

        Returns the unrendered template text. Use
        :meth:`get_system_prompt` / :meth:`get_user_prompt` when you
        also need ``.format(**variables)`` substitution.
        """
        del context  # context-filtered prompts go through Phoenix tags now

        name, role = _split_key(prompt_key, prompt_type)
        try:
            version = self._fetch_version(name)
        except PromptNotFoundError:
            if fallback is not None:
                return fallback
            raise ValueError(f"Prompt not found: {prompt_key}")

        text = _extract_message_text(version, role)
        if text is not None:
            return text

        if fallback is not None:
            return fallback
        raise ValueError(
            f"Prompt not found: {prompt_key} "
            f"(no {role!r} message in Phoenix prompt {name!r})"
        )

    def prompt_exists(self, prompt_key: str) -> bool:
        """Cheap existence check — covers both system and user roles."""
        name, _ = _split_key(prompt_key, "system")
        try:
            self._fetch_version(name)
            return True
        except (PromptNotFoundError, ValueError):
            return False

    def get_system_instruction(
        self,
        step_name: str,
        fallback: Optional[str] = None,
    ) -> str:
        """Compatibility wrapper used by older call sites."""
        return self.get_prompt(
            prompt_key=f"{step_name}.system_instruction",
            prompt_type="system",
            fallback=fallback,
        )

    def get_guidance(
        self,
        step_name: str,
        table_type: Optional[str] = None,
        fallback: str = "",
    ) -> str:
        """Best-effort guidance lookup retained for back-compat.

        Phoenix has no ``context``-filtered prompts; if a step needs
        per-variant guidance it should split into named prompts. We
        sanitise the key and fall through to ``fallback`` on miss.
        """
        prompt_key = (
            f"{step_name}.guidance.{table_type}" if table_type
            else f"{step_name}.guidance"
        )
        return self.get_prompt(
            prompt_key=prompt_key, prompt_type="system", fallback=fallback,
        )

    def get_system_prompt(
        self,
        prompt_key: str,
        variables: dict,
        variable_instance: Optional[Any] = None,
        context: Optional[dict] = None,
        fallback: Optional[str] = None,
    ) -> str:
        """Fetch a system prompt template and render with ``variables``."""
        template = self.get_prompt(
            prompt_key=prompt_key,
            prompt_type="system",
            context=context,
            fallback=fallback,
        )
        return _safe_format(template, variables, variable_instance, prompt_key, "System")

    def get_user_prompt(
        self,
        prompt_key: str,
        variables: dict,
        variable_instance: Optional[Any] = None,
        context: Optional[dict] = None,
        fallback: Optional[str] = None,
    ) -> str:
        """Fetch a user prompt template and render with ``variables``."""
        template = self.get_prompt(
            prompt_key=prompt_key,
            prompt_type="user",
            context=context,
            fallback=fallback,
        )
        return _safe_format(template, variables, variable_instance, prompt_key, "User")


def _safe_format(
    template: str,
    variables: dict,
    variable_instance: Any,
    prompt_key: str,
    label: str,
) -> str:
    """Run ``str.format`` on a template and surface a useful diff on KeyError."""
    try:
        return template.format(**variables)
    except KeyError as e:
        template_requires = extract_variables_from_content(template)
        class_defines = None
        if variable_instance is not None and hasattr(variable_instance, "model_fields"):
            class_defines = list(type(variable_instance).model_fields.keys())

        parts = [
            f"{label} prompt template variable {e} not provided.",
            "",
            f"Template requires:  {template_requires}",
        ]
        if class_defines is not None:
            parts.append(f"Class defines:      {class_defines}")
        parts.append(f"Runtime provided:   {list(variables.keys())}")

        if class_defines is not None:
            missing_from_class = [
                v for v in template_requires if v not in class_defines
            ]
            if missing_from_class:
                parts.extend([
                    "",
                    f"Missing from class: {missing_from_class}",
                    f"ACTION: edit the {prompt_key!r} prompt in the prompts UI "
                    "to add these variables to its variable_definitions.",
                ])
        raise ValueError("\n".join(parts))


__all__ = ["PromptService"]
