"""
Context7 documentation lookup tools for the creator pipeline.

Provides two pydantic-ai compatible tool functions that query the Context7 API
for llm-pipeline framework documentation, giving the code generation agent
access to real framework examples and API details.
"""
import logging
import os

import httpx

logger = logging.getLogger(__name__)

CONTEXT7_BASE_URL = "https://context7.com/api/v2"
CONTEXT7_LIBRARY_ID = "/yugen-au/llm-pipeline"


def _get_api_key() -> str | None:
    return os.environ.get("CONTEXT7_API_KEY")


async def resolve_library_id(library_name: str) -> str:
    """Search Context7 for a library and return its library ID.

    Use this to find the correct library ID before querying docs.
    For llm-pipeline framework docs, use library name 'llm-pipeline'.

    Args:
        library_name: Name of the library to search for.

    Returns:
        JSON string with matching libraries and their IDs.
    """
    api_key = _get_api_key()
    if not api_key:
        return "Context7 API key not configured (set CONTEXT7_API_KEY)"

    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"query": library_name}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{CONTEXT7_BASE_URL}/resolve",
            params=params,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.text


async def query_framework_docs(query: str) -> str:
    """Query llm-pipeline framework documentation from Context7.

    Use this tool to look up how the llm-pipeline framework works:
    - How LLMResultMixin (Instructions) defines the output schema for a step
    - How PipelineContext passes data between steps
    - How step_definition decorator wires steps
    - How prompts (system/user) use {variable} template placeholders
    - How PipelineExtraction persists results to the database
    - Real examples of existing pipeline steps

    Args:
        query: Specific question about the llm-pipeline framework.
            Be detailed, e.g. 'How does LLMResultMixin define output fields
            and what is the difference between instructions and prompts?'

    Returns:
        Relevant documentation and code examples from the framework.
    """
    api_key = _get_api_key()
    if not api_key:
        return "Context7 API key not configured (set CONTEXT7_API_KEY)"

    headers = {"Authorization": f"Bearer {api_key}"}
    params = {
        "libraryId": CONTEXT7_LIBRARY_ID,
        "query": query,
        "type": "txt",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{CONTEXT7_BASE_URL}/context",
            params=params,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.text


__all__ = ["resolve_library_id", "query_framework_docs"]
