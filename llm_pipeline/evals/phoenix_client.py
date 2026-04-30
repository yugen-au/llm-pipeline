"""Thin httpx wrapper over Phoenix's datasets + experiments REST API.

Mirrors the shape and conventions of
:mod:`llm_pipeline.prompts.phoenix_client` — low-level transport,
explicit error classes, identifier validation. Higher-level mapping
(variant deltas, evaluator score aggregation, per-case payload
assembly) lives in :mod:`llm_pipeline.evals.runner`.

Phoenix REST surface (subset we use):

- ``GET    /v1/datasets``                                     list datasets
- ``GET    /v1/datasets/{id}``                                get dataset
- ``DELETE /v1/datasets/{id}``                                delete dataset
- ``POST   /v1/datasets/upload``                              create / upsert dataset (JSON body)
- ``GET    /v1/datasets/{id}/examples``                       list examples
- ``POST   /v1/datasets/{id}/examples``                       add examples
- ``DELETE /v1/datasets/{id}/examples/{example_id}``          delete example
- ``POST   /v1/datasets/{id}/experiments``                    create experiment
- ``GET    /v1/datasets/{id}/experiments``                    list experiments
- ``GET    /v1/experiments/{id}``                             get experiment
- ``POST   /v1/experiments/{id}/runs``                        record per-case run
- ``GET    /v1/experiments/{id}/runs``                        list runs
- ``POST   /v1/experiments/{id}/runs/{run_id}/evaluations``   attach evaluation
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import httpx

from llm_pipeline.prompts import phoenix_config


_IDENTIFIER_RE = re.compile(r"^[a-z0-9]([_a-z0-9-]*[a-z0-9])?$")


class PhoenixDatasetError(Exception):
    """Base for all dataset/experiment client errors."""


class PhoenixDatasetNotConfiguredError(PhoenixDatasetError):
    """Phoenix base URL not set."""


class PhoenixDatasetUnavailableError(PhoenixDatasetError):
    """Phoenix returned a non-404 error or the connection failed."""


class DatasetNotFoundError(PhoenixDatasetError, LookupError):
    """The requested dataset / example doesn't exist (HTTP 404)."""


class ExperimentNotFoundError(PhoenixDatasetError, LookupError):
    """The requested experiment / run doesn't exist (HTTP 404)."""


def _validate_identifier(name: str) -> None:
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(
            f"Phoenix dataset name {name!r} is not a valid identifier "
            f"(must match {_IDENTIFIER_RE.pattern})"
        )


class PhoenixDatasetClient:
    """httpx-backed client for Phoenix's datasets/experiments REST endpoints.

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
        timeout: float = 10.0,
    ) -> None:
        resolved = base_url if base_url is not None else phoenix_config.get_base_url()
        if not resolved:
            raise PhoenixDatasetNotConfiguredError(
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
        not_found_cls: type[PhoenixDatasetError] = DatasetNotFoundError,
    ) -> Optional[Dict[str, Any]]:
        url = f"{self._base_url}{path}"
        try:
            with httpx.Client(timeout=self._timeout, headers=self._headers) as client:
                resp = client.request(method, url, params=params, json=json)
        except httpx.HTTPError as exc:
            raise PhoenixDatasetUnavailableError(
                f"Phoenix request failed ({method} {path}): {exc}"
            ) from exc

        if resp.status_code == 404:
            raise not_found_cls(f"Phoenix returned 404 for {method} {path}")
        if resp.status_code >= 400:
            raise PhoenixDatasetUnavailableError(
                f"Phoenix {method} {path} returned {resp.status_code}: "
                f"{resp.text[:200]}"
            )
        if resp.status_code == 204 or not resp.content:
            return None
        try:
            return resp.json()
        except ValueError as exc:
            raise PhoenixDatasetUnavailableError(
                f"Phoenix {method} {path} returned non-JSON body"
            ) from exc

    def _graphql(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        """POST a GraphQL query/mutation. Phoenix exposes mutations the
        REST surface doesn't (notably ``patchDataset`` for dataset-level
        metadata updates — REST's ``/v1/datasets/upload`` body has no
        dataset-level metadata field, so the only way to set it is here)."""
        url = f"{self._base_url}/graphql"
        try:
            with httpx.Client(timeout=self._timeout, headers=self._headers) as client:
                resp = client.post(url, json={"query": query, "variables": variables})
        except httpx.HTTPError as exc:
            raise PhoenixDatasetUnavailableError(
                f"Phoenix GraphQL request failed: {exc}"
            ) from exc
        if resp.status_code >= 400:
            raise PhoenixDatasetUnavailableError(
                f"Phoenix GraphQL returned {resp.status_code}: {resp.text[:200]}"
            )
        try:
            payload = resp.json()
        except ValueError as exc:
            raise PhoenixDatasetUnavailableError(
                "Phoenix GraphQL returned non-JSON body"
            ) from exc
        errors = payload.get("errors")
        if errors:
            raise PhoenixDatasetUnavailableError(
                f"Phoenix GraphQL errors: {errors}"
            )
        return payload.get("data") or {}

    # ----- datasets -----------------------------------------------------------

    def list_datasets(
        self, *, limit: int = 100, cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """``GET /v1/datasets`` — paginated list of datasets."""
        params: Dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        return self._request("GET", "/v1/datasets", params=params) or {}

    def get_dataset(self, dataset_id: str) -> Dict[str, Any]:
        """``GET /v1/datasets/{id}`` — fetch one dataset record."""
        resp = self._request("GET", f"/v1/datasets/{dataset_id}")
        return (resp or {}).get("data") or {}

    def delete_dataset(self, dataset_id: str) -> None:
        """``DELETE /v1/datasets/{id}`` — delete a dataset and all examples."""
        self._request("DELETE", f"/v1/datasets/{dataset_id}")

    def upload_dataset(
        self,
        *,
        name: str,
        examples: List[Dict[str, Any]],
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        action: str = "create",
    ) -> Dict[str, Any]:
        """``POST /v1/datasets/upload`` — create or upsert a dataset.

        Each example is a dict with ``input`` (dict), ``output`` (dict,
        optional — the expected output for this case) and ``metadata``
        (dict, optional — the per-example bag we use for custom
        evaluator hooks via ``evaluators: list[name]``).

        Dataset-level ``metadata`` we conventionally include:

        - ``target_type``: ``"step"`` or ``"pipeline"``
        - ``target_name``: step class name or pipeline class name

        Phoenix's REST upload body has no dataset-metadata slot — REST
        only accepts per-example metadata. To make ``metadata`` actually
        land on the dataset record, we follow the REST upload with a
        GraphQL ``patchDataset`` call. Returns the REST response (with
        ``dataset_id`` etc.) unchanged so callers don't need to know
        about the second hop.
        """
        _validate_identifier(name)
        body: Dict[str, Any] = {
            "action": action,
            "name": name,
            "inputs": [ex.get("input", {}) for ex in examples],
            "outputs": [ex.get("output", {}) for ex in examples],
            "metadata": [ex.get("metadata", {}) for ex in examples],
        }
        if description is not None:
            body["description"] = description
        resp = self._request("POST", "/v1/datasets/upload", json=body)
        record = (resp or {}).get("data") or {}

        # REST silently drops dataset-level metadata; layer it in via
        # GraphQL when we have any to set.
        dataset_id = record.get("dataset_id") or record.get("id")
        if metadata and dataset_id:
            try:
                self.patch_dataset(dataset_id, metadata=metadata)
            except PhoenixDatasetError:
                # Don't fail the whole upload over a metadata patch —
                # surface it via the response/log path the caller controls.
                raise
        return record

    def patch_dataset(
        self,
        dataset_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """GraphQL ``patchDataset`` — update dataset-level fields.

        REST has no patch path; this is the only way to update
        ``metadata`` (carrying ``target_type`` / ``target_name``),
        ``description``, or ``name`` after creation.

        ``dataset_id`` is the GraphQL node id (base64) returned in
        ``id`` on REST list/get responses.
        """
        if name is None and description is None and metadata is None:
            return {}
        input_obj: Dict[str, Any] = {"datasetId": dataset_id}
        if name is not None:
            input_obj["name"] = name
        if description is not None:
            input_obj["description"] = description
        if metadata is not None:
            input_obj["metadata"] = metadata
        query = (
            "mutation P($input: PatchDatasetInput!) { "
            "patchDataset(input: $input) { "
            "  dataset { id name description metadata } "
            "} "
            "}"
        )
        data = self._graphql(query, {"input": input_obj})
        payload = data.get("patchDataset") or {}
        return payload.get("dataset") or {}

    # ----- examples -----------------------------------------------------------

    def list_examples(
        self,
        dataset_id: str,
        *,
        version_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """``GET /v1/datasets/{id}/examples`` — list examples for a dataset."""
        params: Dict[str, Any] = {}
        if version_id is not None:
            params["version_id"] = version_id
        return self._request(
            "GET", f"/v1/datasets/{dataset_id}/examples", params=params,
        ) or {}

    def add_examples(
        self,
        dataset_id: str,
        examples: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """``POST /v1/datasets/{id}/examples`` — append examples to an existing dataset."""
        body = {
            "inputs": [ex.get("input", {}) for ex in examples],
            "outputs": [ex.get("output", {}) for ex in examples],
            "metadata": [ex.get("metadata", {}) for ex in examples],
        }
        resp = self._request(
            "POST", f"/v1/datasets/{dataset_id}/examples", json=body,
        )
        return (resp or {}).get("data") or {}

    def delete_example(self, dataset_id: str, example_id: str) -> None:
        """``DELETE /v1/datasets/{id}/examples/{example_id}`` — drop a single example."""
        self._request(
            "DELETE", f"/v1/datasets/{dataset_id}/examples/{example_id}",
        )

    # ----- experiments --------------------------------------------------------

    def create_experiment(
        self,
        dataset_id: str,
        *,
        name: str,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        version_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """``POST /v1/datasets/{id}/experiments`` — start a new experiment.

        ``metadata`` is the variant payload we round-trip via
        ``Variant.model_dump()`` plus any pipeline-level context
        (``pipeline_name``, ``target_type``, ``target_name``).
        """
        body: Dict[str, Any] = {"name": name}
        if description is not None:
            body["description"] = description
        if metadata is not None:
            body["metadata"] = metadata
        if version_id is not None:
            body["version_id"] = version_id
        resp = self._request(
            "POST", f"/v1/datasets/{dataset_id}/experiments", json=body,
        )
        return (resp or {}).get("data") or {}

    def list_experiments(self, dataset_id: str) -> Dict[str, Any]:
        """``GET /v1/datasets/{id}/experiments`` — list experiments."""
        return self._request(
            "GET", f"/v1/datasets/{dataset_id}/experiments",
        ) or {}

    def get_experiment(self, experiment_id: str) -> Dict[str, Any]:
        """``GET /v1/experiments/{id}`` — fetch one experiment record."""
        resp = self._request(
            "GET", f"/v1/experiments/{experiment_id}",
            not_found_cls=ExperimentNotFoundError,
        )
        return (resp or {}).get("data") or {}

    # ----- experiment runs ----------------------------------------------------

    def record_run(
        self,
        experiment_id: str,
        *,
        dataset_example_id: str,
        output: Any,
        repetition_number: int = 1,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        error: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """``POST /v1/experiments/{id}/runs`` — record one case's result.

        ``start_time`` and ``end_time`` are ISO-8601 strings; the runner
        constructs them from the wall clock around the task call.
        """
        body: Dict[str, Any] = {
            "dataset_example_id": dataset_example_id,
            "output": output,
            "repetition_number": repetition_number,
        }
        if start_time is not None:
            body["start_time"] = start_time
        if end_time is not None:
            body["end_time"] = end_time
        if error is not None:
            body["error"] = error
        if trace_id is not None:
            body["trace_id"] = trace_id
        resp = self._request(
            "POST", f"/v1/experiments/{experiment_id}/runs", json=body,
            not_found_cls=ExperimentNotFoundError,
        )
        return (resp or {}).get("data") or {}

    def list_runs(self, experiment_id: str) -> Dict[str, Any]:
        """``GET /v1/experiments/{id}/runs`` — list per-case runs."""
        return self._request(
            "GET", f"/v1/experiments/{experiment_id}/runs",
            not_found_cls=ExperimentNotFoundError,
        ) or {}

    # ----- evaluations --------------------------------------------------------

    def attach_evaluation(
        self,
        experiment_id: str,
        run_id: str,
        *,
        name: str,
        label: Optional[str] = None,
        score: Optional[float] = None,
        explanation: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """``POST /v1/experiments/{id}/runs/{run_id}/evaluations`` — attach a score."""
        body: Dict[str, Any] = {"name": name}
        if label is not None:
            body["label"] = label
        if score is not None:
            body["score"] = score
        if explanation is not None:
            body["explanation"] = explanation
        if metadata is not None:
            body["metadata"] = metadata
        resp = self._request(
            "POST",
            f"/v1/experiments/{experiment_id}/runs/{run_id}/evaluations",
            json=body,
            not_found_cls=ExperimentNotFoundError,
        )
        return (resp or {}).get("data") or {}


__all__ = [
    "PhoenixDatasetClient",
    "PhoenixDatasetError",
    "PhoenixDatasetNotConfiguredError",
    "PhoenixDatasetUnavailableError",
    "DatasetNotFoundError",
    "ExperimentNotFoundError",
]
