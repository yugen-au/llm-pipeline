"""Models route -- list available LLM models from pydantic-ai."""
from fastapi import APIRouter

router = APIRouter(prefix="/models", tags=["models"])


@router.get("")
def list_models() -> dict[str, list[str]]:
    """Return known LLM models grouped by provider."""
    from pydantic_ai.models import KnownModelName
    from typing import get_args

    models = get_args(KnownModelName.__value__)
    grouped: dict[str, list[str]] = {}
    for m in models:
        if ":" in m:
            provider, name = m.split(":", 1)
        else:
            provider = "openai"
            name = m
        grouped.setdefault(provider, []).append(m)
    return grouped
