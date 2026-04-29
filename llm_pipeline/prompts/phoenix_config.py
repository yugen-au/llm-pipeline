"""Phoenix backend configuration resolved from environment variables.

Used by both the trace-fetch endpoint and the prompt client. Centralises
the env-var precedence rules so the two stay in sync.
"""
from __future__ import annotations

import os
from typing import Dict, Optional


def get_base_url() -> Optional[str]:
    """Resolve the Phoenix HTTP base URL.

    Order:
      1. Explicit ``PHOENIX_BASE_URL`` (e.g. ``http://localhost:6006``).
      2. Derived from ``OTEL_EXPORTER_OTLP_ENDPOINT`` (strip ``/v1/traces``
         if present) — convenient for self-hosted setups where the same
         host serves OTLP ingest and the Phoenix REST API on one port.

    Returns None when no backend is configured.
    """
    explicit = os.environ.get("PHOENIX_BASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    otlp = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if otlp:
        base = otlp.rstrip("/")
        if base.endswith("/v1/traces"):
            base = base[: -len("/v1/traces")]
        return base
    return None


def get_project() -> str:
    """Project name to query traces under. Phoenix auto-creates ``default``."""
    return os.environ.get("PHOENIX_PROJECT", "default")


def get_headers() -> Dict[str, str]:
    """Auth headers for Phoenix Cloud; empty for self-hosted with no auth."""
    headers: Dict[str, str] = {}
    api_key = os.environ.get("PHOENIX_API_KEY", "").strip()
    if api_key:
        headers["api_key"] = api_key
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def is_configured() -> bool:
    return get_base_url() is not None


__all__ = ["get_base_url", "get_project", "get_headers", "is_configured"]
