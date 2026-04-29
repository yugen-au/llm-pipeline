"""Thin httpx wrapper over Phoenix's prompt REST API.

The wrapper is intentionally low-level: it transports payloads in the
exact shapes Phoenix's OpenAPI describes (``PromptVersion``,
``PromptData``, etc.). Higher-level mapping — collapsing
``<step>.system_instruction`` keys to a single Phoenix prompt with
multiple messages, picking the right role's content, formatting
template variables — lives in :mod:`llm_pipeline.prompts.service`.

Phoenix prompt REST surface (subset we use):

- ``GET    /v1/prompts``                                 list prompts
- ``POST   /v1/prompts``                                 create prompt (auto-versions)
- ``DELETE /v1/prompts/{name}``                          delete prompt
- ``GET    /v1/prompts/{name}/latest``                   latest version
- ``GET    /v1/prompts/{name}/tags/{tag}``               version pinned to tag
- ``GET    /v1/prompts/{name}/versions``                 list versions
- ``GET    /v1/prompt_versions/{id}``                    one version
- ``POST   /v1/prompt_versions/{id}/tags``               attach tag
- ``DELETE /v1/prompt_versions/{id}/tags/{tag}``         detach tag

Names are validated against Phoenix's ``Identifier`` pattern
``^[a-z0-9]([_a-z0-9-]*[a-z0-9])?$`` — dots are not allowed, so
keys like ``widget_detection.system_instruction`` must be reduced
to a Phoenix-legal name before calling the client.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

import httpx

from llm_pipeline.prompts import phoenix_config


# Phoenix Identifier pattern (from the OpenAPI spec).
_IDENTIFIER_RE = re.compile(r"^[a-z0-9]([_a-z0-9-]*[a-z0-9])?$")


class PhoenixError(Exception):
    """Base for all Phoenix client errors."""


class PhoenixNotConfiguredError(PhoenixError):
    """Phoenix base URL is not set (missing PHOENIX_BASE_URL / OTEL endpoint)."""


class PhoenixUnavailableError(PhoenixError):
    """Phoenix returned a non-404 error or the connection failed."""


class PromptNotFoundError(PhoenixError, LookupError):
    """The requested prompt or version doesn't exist (HTTP 404)."""


def _validate_identifier(name: str) -> None:
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(
            f"Phoenix prompt name {name!r} is not a valid identifier "
            f"(must match {_IDENTIFIER_RE.pattern})"
        )


class PhoenixPromptClient:
    """httpx-backed client for Phoenix's prompt REST endpoints.

    A single instance is safe to share across threads — every call
    opens its own short-lived ``httpx.Client``. Construct without
    arguments to pull config from environment; pass explicit
    ``base_url`` / ``headers`` for testing or alternate deployments.
    """

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 5.0,
    ) -> None:
        resolved = base_url if base_url is not None else phoenix_config.get_base_url()
        if not resolved:
            raise PhoenixNotConfiguredError(
                "Phoenix base URL not set. Set PHOENIX_BASE_URL or "
                "OTEL_EXPORTER_OTLP_ENDPOINT."
            )
        self._base_url = resolved.rstrip("/")
        self._headers = (
            dict(headers) if headers is not None else phoenix_config.get_headers()
        )
        self._timeout = timeout

    # ----- low-level transport ------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        url = f"{self._base_url}{path}"
        try:
            with httpx.Client(timeout=self._timeout, headers=self._headers) as client:
                resp = client.request(method, url, params=params, json=json)
        except httpx.HTTPError as exc:
            raise PhoenixUnavailableError(
                f"Phoenix request failed ({method} {path}): {exc}"
            ) from exc

        if resp.status_code == 404:
            raise PromptNotFoundError(f"Phoenix returned 404 for {method} {path}")
        if resp.status_code >= 400:
            raise PhoenixUnavailableError(
                f"Phoenix {method} {path} returned {resp.status_code}: "
                f"{resp.text[:200]}"
            )
        if resp.status_code == 204 or not resp.content:
            return None
        try:
            return resp.json()
        except ValueError as exc:
            raise PhoenixUnavailableError(
                f"Phoenix {method} {path} returned non-JSON body"
            ) from exc

    # ----- prompts ------------------------------------------------------------

    def list_prompts(
        self, *, limit: int = 100, cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """``GET /v1/prompts`` — paginated list of prompt records."""
        params: Dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        return self._request("GET", "/v1/prompts", params=params) or {}

    def create(
        self,
        *,
        prompt: Dict[str, Any],
        version: Dict[str, Any],
    ) -> Dict[str, Any]:
        """``POST /v1/prompts`` — create prompt or new version under existing name.

        ``prompt`` matches Phoenix ``PromptData`` (``name``,
        ``description``, ``metadata``); ``version`` matches
        ``PromptVersionData`` (``model_provider``, ``model_name``,
        ``template``, ``template_type``, ``template_format``,
        ``invocation_parameters``, optional ``tools`` /
        ``response_format``). The response body's ``data`` field carries
        the resulting ``PromptVersion``.
        """
        _validate_identifier(prompt["name"])
        body = {"prompt": prompt, "version": version}
        resp = self._request("POST", "/v1/prompts", json=body)
        return (resp or {}).get("data") or {}

    def delete(self, name: str) -> None:
        """``DELETE /v1/prompts/{name}`` — delete a prompt and all versions."""
        _validate_identifier(name)
        self._request("DELETE", f"/v1/prompts/{name}")

    def get_latest(self, name: str) -> Dict[str, Any]:
        """``GET /v1/prompts/{name}/latest`` — newest version."""
        _validate_identifier(name)
        resp = self._request("GET", f"/v1/prompts/{name}/latest")
        return (resp or {}).get("data") or {}

    def get_by_tag(self, name: str, tag: str) -> Dict[str, Any]:
        """``GET /v1/prompts/{name}/tags/{tag}`` — version pinned to tag."""
        _validate_identifier(name)
        _validate_identifier(tag)
        resp = self._request("GET", f"/v1/prompts/{name}/tags/{tag}")
        return (resp or {}).get("data") or {}

    def list_versions(
        self,
        name: str,
        *,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """``GET /v1/prompts/{name}/versions`` — paginated version history."""
        _validate_identifier(name)
        params: Dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        return self._request(
            "GET", f"/v1/prompts/{name}/versions", params=params,
        ) or {}

    def get_version(self, version_id: str) -> Dict[str, Any]:
        """``GET /v1/prompt_versions/{id}`` — fetch one specific version."""
        resp = self._request("GET", f"/v1/prompt_versions/{version_id}")
        return (resp or {}).get("data") or {}

    # ----- tags ---------------------------------------------------------------

    def add_tag(
        self,
        version_id: str,
        tag_name: str,
        *,
        description: Optional[str] = None,
    ) -> None:
        """``POST /v1/prompt_versions/{id}/tags`` — attach tag to version."""
        _validate_identifier(tag_name)
        body: Dict[str, Any] = {"name": tag_name}
        if description is not None:
            body["description"] = description
        self._request(
            "POST", f"/v1/prompt_versions/{version_id}/tags", json=body,
        )

    def delete_tag(self, version_id: str, tag_name: str) -> None:
        """``DELETE /v1/prompt_versions/{id}/tags/{tag}`` — detach tag."""
        _validate_identifier(tag_name)
        self._request(
            "DELETE", f"/v1/prompt_versions/{version_id}/tags/{tag_name}",
        )

    def list_tags(
        self,
        version_id: str,
        *,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """``GET /v1/prompt_versions/{id}/tags`` — list tags on a version."""
        params: Dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        return self._request(
            "GET", f"/v1/prompt_versions/{version_id}/tags", params=params,
        ) or {}


__all__ = [
    "PhoenixPromptClient",
    "PhoenixError",
    "PhoenixNotConfiguredError",
    "PhoenixUnavailableError",
    "PromptNotFoundError",
]
