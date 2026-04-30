"""Canonical eval-dataset wire model + Phoenix translation helpers.

Same role as ``llm_pipeline/prompts/models.py``: the single shape that
HTTP routes return, frontend types mirror, internal consumers read,
and (eventually) YAML sync deserialises into. Phoenix's REST surface
is the storage backend; the ``phoenix_to_*`` helpers are the ONE place
the codebase translates Phoenix dict responses into the canonical
model. Every layer above ``phoenix_client`` consumes ``Dataset`` /
``Example``, never raw dicts.

Out of scope here: ``Experiment`` / ``Run`` / ``Evaluation``. Those
are runtime artifacts (not authored, not hashed, not synced) and stay
as Phoenix-shape dicts in the route layer — typed only where the
codebase actually reads from them (e.g. ``experiment.metadata.variant``
in ``acceptance.py``).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Example(BaseModel):
    id: str | None = None
    input: dict[str, Any]
    output: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DatasetMetadata(BaseModel):
    target_type: str | None = None
    target_name: str | None = None

    model_config = {"extra": "allow"}


class Dataset(BaseModel):
    id: str | None = None
    name: str
    description: str | None = None
    metadata: DatasetMetadata = Field(default_factory=DatasetMetadata)
    examples: list[Example] = Field(default_factory=list)
    # Phoenix-set fields surfaced for UI display; ignored on writes.
    created_at: str | None = None
    example_count: int | None = None


# ---------------------------------------------------------------------------
# Phoenix <-> canonical translation
# ---------------------------------------------------------------------------


def phoenix_to_example(record: dict[str, Any]) -> Example:
    """Map a Phoenix example dict to ``Example``.

    Tolerates both the canonical ``input``/``output`` keys and the
    historical ``inputs``/``expected_output`` aliases that older
    Phoenix payloads have shipped.
    """
    return Example(
        id=record.get("id"),
        input=record.get("input") or record.get("inputs") or {},
        output=record.get("output") or record.get("expected_output") or {},
        metadata=record.get("metadata") or {},
    )


def phoenix_examples_payload_to_list(
    payload: dict[str, Any] | None,
) -> list[Example]:
    """Coerce ``PhoenixDatasetClient.list_examples`` output to ``[Example, ...]``.

    Phoenix's ``GET /v1/datasets/{id}/examples`` response wrapper has
    shipped a few variants: ``{"data": {"examples": [...]}}``,
    ``{"data": [...]}``, ``{"examples": [...]}``. This helper absorbs
    those so callers always see a flat list.
    """
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, dict):
        items = data.get("examples") or data.get("items") or []
    elif isinstance(data, list):
        items = data
    else:
        items = payload.get("examples") or []
    return [phoenix_to_example(ex) for ex in items]


def phoenix_to_dataset(
    record: dict[str, Any] | None,
    examples_payload: dict[str, Any] | None = None,
) -> Dataset:
    """Map a Phoenix dataset record to ``Dataset``.

    Pass ``examples_payload`` (the raw ``list_examples`` response) when
    you want examples populated; omit it for list rows where examples
    are intentionally absent.
    """
    record = record or {}
    raw_meta = record.get("metadata") or {}
    examples = (
        phoenix_examples_payload_to_list(examples_payload)
        if examples_payload is not None
        else []
    )
    return Dataset(
        id=record.get("id"),
        name=record.get("name") or "",
        description=record.get("description"),
        metadata=DatasetMetadata.model_validate(raw_meta),
        examples=examples,
        created_at=record.get("created_at"),
        example_count=record.get("example_count"),
    )


def dataset_to_phoenix_upload_kwargs(payload: Dataset) -> dict[str, Any]:
    """Map a ``Dataset`` write payload to ``upload_dataset`` kwargs."""
    return {
        "name": payload.name,
        "description": payload.description,
        "metadata": payload.metadata.model_dump(exclude_none=True),
        "examples": [
            {"input": ex.input, "output": ex.output, "metadata": ex.metadata}
            for ex in payload.examples
        ],
    }


def example_to_phoenix_payload(ex: Example) -> dict[str, Any]:
    """Map an ``Example`` write payload to the dict shape the client expects."""
    return {"input": ex.input, "output": ex.output, "metadata": ex.metadata}


__all__ = [
    "Example",
    "DatasetMetadata",
    "Dataset",
    "phoenix_to_example",
    "phoenix_examples_payload_to_list",
    "phoenix_to_dataset",
    "dataset_to_phoenix_upload_kwargs",
    "example_to_phoenix_payload",
]
