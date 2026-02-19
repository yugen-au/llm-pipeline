"""
UI package for llm-pipeline.

Provides a FastAPI-based web interface for inspecting pipeline runs,
steps, events, and prompts. Requires the 'ui' optional dependency group.
"""
try:
    import fastapi  # noqa: F401
except ImportError:
    raise ImportError(
        "llm_pipeline.ui requires FastAPI. "
        "Install with: pip install llm-pipeline[ui]"
    )

from llm_pipeline.ui.app import create_app

__all__ = ["create_app"]
