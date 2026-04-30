"""Bidirectional YAML <-> Phoenix sync for prompts and eval datasets.

Dev-ergonomics tool: edit a checked-in YAML file, the change is pushed
to Phoenix on next boot. UI saves go the other way — after a successful
Phoenix write, the matching YAML file is rewritten so git stays
canonical across machines.

Design:

- The canonical models (``llm_pipeline.prompts.models.Prompt``,
  ``llm_pipeline.evals.models.Dataset``) are the join point. YAML
  deserialises into them; ``phoenix_to_*`` helpers parse Phoenix
  responses into them; the same hash function compares both sides.
- The hash excludes Phoenix-set fields (``version_id``, ``id``,
  ``created_at``, ``example_count``, per-Example ``id``). Two models
  hash equal iff their authored content is identical.
- Boot direction: YAML wins. A diff triggers a Phoenix write.
- UI direction: Phoenix wins. After a successful write the matching
  YAML file is rewritten with the canonical model.
- Idempotency: the YAML write skips if the existing file's hash already
  matches, breaking the boot -> write -> boot loop.

Deletion policy:

- Whole prompts / datasets: removing a YAML file does NOT delete from
  Phoenix. Phoenix experiments may reference a dataset; cascading the
  delete would silently destroy that history. The UI's DELETE endpoint
  is the only path that removes a whole record (and the matching YAML
  file).
- Within a dataset: the example diff is full bidirectional. Examples
  in YAML but not in Phoenix are added; examples in Phoenix but not
  in YAML are deleted. Examples are matched by ``sha256(input)``.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, TypeVar

import yaml

from llm_pipeline.evals.models import (
    Dataset,
    Example,
    dataset_to_phoenix_upload_kwargs,
    example_to_phoenix_payload,
    phoenix_to_dataset,
)
from llm_pipeline.evals.phoenix_client import (
    DatasetNotFoundError,
    PhoenixDatasetClient,
    PhoenixDatasetError,
)
from llm_pipeline.prompts.models import (
    Prompt,
    phoenix_to_prompt,
    prompt_to_phoenix_payloads,
)
from llm_pipeline.prompts.phoenix_client import (
    PhoenixError,
    PhoenixPromptClient,
    PromptNotFoundError,
)
from llm_pipeline.prompts.registration import (
    derive_step_extras,
    iter_step_classes,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hash + IO primitives
# ---------------------------------------------------------------------------


# Hash exclude — drop only the Phoenix-set bookkeeping that's never
# part of the authored OR derived content. ``response_format`` and
# ``tools`` ARE included in the hash so a code change to INSTRUCTIONS /
# DEFAULT_TOOLS triggers a sync push, not just a YAML edit.
_PROMPT_HASH_EXCLUDE = {"version_id"}

# YAML write exclude — also drop code-derived fields. The disk file is
# the human-authored slice; ``response_format`` / ``tools`` come from
# the step at push time, not from YAML.
_PROMPT_YAML_EXCLUDE = {"version_id", "response_format", "tools"}

_DATASET_EXCLUDE: dict[str, Any] = {
    "id": True,
    "created_at": True,
    "example_count": True,
    "examples": {"__all__": {"id": True}},
}


def _stable_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
    ).hexdigest()


def _hash_prompt(p: Prompt) -> str:
    """Sync-diff hash. Includes ``response_format`` / ``tools`` so a code
    change to INSTRUCTIONS triggers a Phoenix push even if YAML hasn't
    moved."""
    return _stable_hash(p.model_dump(exclude=_PROMPT_HASH_EXCLUDE, exclude_none=True))


def _hash_prompt_yaml(p: Prompt) -> str:
    """YAML-write idempotency hash. Excludes the same fields the YAML
    write does, so the on-disk file's hash matches a Prompt loaded from
    that file."""
    return _stable_hash(p.model_dump(exclude=_PROMPT_YAML_EXCLUDE, exclude_none=True))


def _hash_dataset(d: Dataset) -> str:
    return _stable_hash(d.model_dump(exclude=_DATASET_EXCLUDE, exclude_none=True))


def _hash_example_input(ex: Example) -> str:
    return _stable_hash(ex.input)


def _model_yaml_payload(model: Prompt | Dataset) -> dict[str, Any]:
    """Serialisation payload for YAML — drops Phoenix-set + code-derived fields."""
    if isinstance(model, Prompt):
        return model.model_dump(exclude=_PROMPT_YAML_EXCLUDE, exclude_none=True)
    return model.model_dump(exclude=_DATASET_EXCLUDE, exclude_none=True)


def _read_yaml(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    parsed = yaml.safe_load(text)
    return parsed if isinstance(parsed, dict) else None


def _write_yaml_atomic(path: Path, data: dict[str, Any]) -> None:
    """Write YAML to ``path`` atomically (temp file + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    serialised = yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    fd, tmp = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(serialised)
        os.replace(tmp, path)
    except Exception:
        with suppress(OSError):
            os.unlink(tmp)
        raise


def delete_yaml(name: str, dir_: Path) -> bool:
    """Remove ``{dir_}/{name}.yaml`` if it exists. Returns ``True`` on delete."""
    path = dir_ / f"{name}.yaml"
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


# ---------------------------------------------------------------------------
# Public report shape
# ---------------------------------------------------------------------------


@dataclass
class SyncReport:
    # Push direction (YAML -> Phoenix)
    prompts_pushed: list[str] = field(default_factory=list)
    prompts_skipped: list[str] = field(default_factory=list)
    prompts_failed: list[tuple[str, str]] = field(default_factory=list)
    datasets_created: list[str] = field(default_factory=list)
    datasets_diffed: list[str] = field(default_factory=list)
    datasets_skipped: list[str] = field(default_factory=list)
    datasets_failed: list[tuple[str, str]] = field(default_factory=list)
    # Pull direction (Phoenix -> YAML). Populated by pull_phoenix_to_yaml.
    prompts_pulled: list[str] = field(default_factory=list)
    prompts_pull_skipped: list[str] = field(default_factory=list)
    prompts_pull_failed: list[tuple[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Generic per-domain walk
# ---------------------------------------------------------------------------


M = TypeVar("M", Prompt, Dataset)


def _iter_yaml_diffs(
    dir_: Path,
    parser: Callable[[dict[str, Any]], M],
    fetcher: Callable[[str], M | None],
    hasher: Callable[[M], str],
    on_failed: Callable[[str, str], None],
    on_skipped: Callable[[str], None],
) -> Iterator[tuple[M, M | None]]:
    """Walk ``dir_``; yield ``(yaml_model, phoenix_model_or_None)`` only for
    entries that differ.

    Parse + Phoenix-fetch failures and hash-equal skips are bucketed via
    the callbacks so each per-domain caller controls its own report
    fields.
    """
    if not dir_.exists():
        return
    for path in sorted(dir_.glob("*.yaml")):
        payload = _read_yaml(path)
        if payload is None:
            on_failed(path.name, "could not parse YAML")
            continue
        try:
            yaml_model = parser(payload)
        except Exception as exc:
            on_failed(path.name, f"invalid: {exc}")
            continue
        try:
            phoenix_model = fetcher(yaml_model.name)
        except Exception as exc:  # noqa: BLE001 - report any client error
            on_failed(yaml_model.name, f"phoenix: {exc}")
            continue
        if (
            phoenix_model is not None
            and hasher(yaml_model) == hasher(phoenix_model)
        ):
            on_skipped(yaml_model.name)
            continue
        yield yaml_model, phoenix_model


# ---------------------------------------------------------------------------
# Prompt sync
# ---------------------------------------------------------------------------


def write_prompt_yaml(prompt: Prompt, prompts_dir: Path) -> bool:
    """Persist a prompt to ``{prompts_dir}/{name}.yaml`` (idempotent).

    Idempotency is based on the YAML-write hash, which excludes
    code-derived fields. Two prompts that only differ on
    ``response_format`` / ``tools`` produce the same on-disk file, so
    we don't churn YAML on every code change.
    """
    path = prompts_dir / f"{prompt.name}.yaml"
    new_payload = _model_yaml_payload(prompt)
    existing = _read_yaml(path)
    if existing is not None:
        try:
            existing_model = Prompt.model_validate(existing)
            if _hash_prompt_yaml(existing_model) == _hash_prompt_yaml(prompt):
                return False
        except Exception:
            # Malformed YAML; overwrite it.
            pass
    _write_yaml_atomic(path, new_payload)
    return True


def _fetch_phoenix_prompt(
    client: PhoenixPromptClient, name: str,
) -> tuple[dict[str, Any] | None, Prompt | None]:
    """Return ``(record, canonical_prompt)`` for ``name``, or ``(None, None)``.

    The raw ``record`` is needed when we need to call ``patch_prompt``
    (it carries the Phoenix prompt id); the canonical ``Prompt`` is what
    the diff logic compares against.
    """
    try:
        version = client.get_latest(name)
    except PromptNotFoundError:
        return None, None
    record: dict[str, Any] | None = None
    try:
        for r in (client.list_prompts(limit=200) or {}).get("data") or []:
            if r.get("name") == name:
                record = r
                break
    except PhoenixError:
        pass
    if record is None:
        record = {"name": name}
    return record, phoenix_to_prompt(record, version)


def _push_new_version(client: PhoenixPromptClient, prompt: Prompt) -> None:
    """POST a new ``PromptVersion`` (template + schemas + tools) + tag prod.

    Used when version-level fields (messages, response_format, tools)
    diverge. Phoenix's auto-version semantics on ``POST /v1/prompts``
    gives us the new version naturally; the prompt-level metadata in
    ``prompt_data`` is ignored on subsequent posts (set-once via REST)
    so we deliberately rely on ``patch_prompt`` for metadata updates.
    """
    try:
        existing_version = client.get_latest(prompt.name)
    except PromptNotFoundError:
        existing_version = None
    prompt_data, version_data = prompt_to_phoenix_payloads(
        prompt, base_version=existing_version,
    )
    new_version = client.create(prompt=prompt_data, version=version_data)
    version_id = new_version.get("id")
    if version_id:
        try:
            client.add_tag(version_id, "production", description="yaml-sync")
        except PhoenixError as exc:
            logger.warning(
                "Phoenix tag failed for prompt %s: %s", prompt.name, exc,
            )


def _prompt_level_differs(yaml_prompt: Prompt, phoenix_prompt: Prompt) -> bool:
    """True iff prompt-level (record) fields differ — metadata or description."""
    return (
        yaml_prompt.description != phoenix_prompt.description
        or yaml_prompt.metadata.model_dump(exclude_none=True)
        != phoenix_prompt.metadata.model_dump(exclude_none=True)
    )


def _version_level_differs(yaml_prompt: Prompt, phoenix_prompt: Prompt) -> bool:
    """True iff version-level (template/model/schemas) fields differ."""
    return (
        [m.model_dump() for m in yaml_prompt.messages]
        != [m.model_dump() for m in phoenix_prompt.messages]
        or yaml_prompt.model != phoenix_prompt.model
        or yaml_prompt.response_format != phoenix_prompt.response_format
        or yaml_prompt.tools != phoenix_prompt.tools
    )


def _sync_prompts(
    prompts_dir: Path,
    client: PhoenixPromptClient,
    report: SyncReport,
    introspection_registry: dict[str, Any] | None,
) -> None:
    """Step-driven sync: walk the registered LLMSteps, push the matching YAML.

    The LLMStep is the canonical entity — Phoenix's prompt record is
    just its persisted form. For each registered step we look for
    ``{prompts_dir}/{snake_case_name}.yaml`` to provide the human-
    authored slice (messages + metadata); ``response_format`` / ``tools``
    come from the step's ``INSTRUCTIONS`` / ``DEFAULT_TOOLS``.

    Steps without a matching YAML file are skipped (we only manage
    prompts authored as YAML). YAML files without a registered step
    are also skipped — they're orphans and shouldn't sync to Phoenix.
    """
    if not introspection_registry:
        return

    seen: set[type] = set()
    for pipeline_cls in introspection_registry.values():
        for step_cls in iter_step_classes(pipeline_cls):
            if step_cls in seen:
                continue
            seen.add(step_cls)
            _sync_one_step(
                step_cls, prompts_dir, client, report,
            )


def _sync_one_step(
    step_cls: type,
    prompts_dir: Path,
    client: PhoenixPromptClient,
    report: SyncReport,
) -> None:
    prompt_name = step_cls.step_name()
    yaml_path = prompts_dir / f"{prompt_name}.yaml"

    payload = _read_yaml(yaml_path)
    if payload is None:
        logger.info(
            "yaml_sync: step %s has no YAML file at %s; skipping",
            step_cls.__name__, yaml_path.name,
        )
        return

    try:
        loaded = Prompt.model_validate(payload)
    except Exception as exc:
        logger.warning(
            "yaml_sync: %s invalid prompt: %s", yaml_path.name, exc,
        )
        report.prompts_failed.append(
            (yaml_path.name, f"invalid prompt: {exc}"),
        )
        return

    response_format, tools = derive_step_extras(step_cls)
    prompt = loaded.model_copy(update={
        "name": prompt_name,
        "response_format": response_format,
        "tools": tools,
    })

    try:
        phoenix_record, phoenix_prompt = _fetch_phoenix_prompt(client, prompt_name)
    except PhoenixError as exc:
        logger.warning(
            "yaml_sync: %s phoenix lookup failed: %s", prompt_name, exc,
        )
        report.prompts_failed.append((prompt_name, f"phoenix: {exc}"))
        return

    # Case 1: Phoenix has nothing — full POST creates record + first version
    # in one call. Phoenix accepts metadata on the first POST so this also
    # seeds variable_definitions etc.
    if phoenix_prompt is None:
        logger.info(
            "yaml_sync: %s — Phoenix has no record, creating from YAML + step",
            prompt_name,
        )
        try:
            _push_new_version(client, prompt)
        except PhoenixError as exc:
            logger.warning("yaml_sync: %s create failed: %s", prompt_name, exc)
            report.prompts_failed.append((prompt_name, f"create: {exc}"))
            return
        report.prompts_pushed.append(prompt_name)
        return

    # Case 2: hashes match — nothing to do.
    if _hash_prompt(prompt) == _hash_prompt(phoenix_prompt):
        logger.info("yaml_sync: %s — hash matches, skipping", prompt_name)
        report.prompts_skipped.append(prompt_name)
        return

    # Case 3: something differs. Decide which path(s) to take.
    needs_version = _version_level_differs(prompt, phoenix_prompt)
    needs_patch = _prompt_level_differs(prompt, phoenix_prompt)
    diff_summary = _describe_prompt_diff(prompt, phoenix_prompt)
    logger.info(
        "yaml_sync: %s — diff: %s; new version=%s, patch metadata=%s",
        prompt_name, diff_summary, needs_version, needs_patch,
    )

    if needs_version:
        try:
            _push_new_version(client, prompt)
        except PhoenixError as exc:
            logger.warning("yaml_sync: %s push failed: %s", prompt_name, exc)
            report.prompts_failed.append((prompt_name, f"push: {exc}"))
            return

    if needs_patch:
        prompt_id = phoenix_record.get("id") if phoenix_record else None
        if not prompt_id:
            logger.warning(
                "yaml_sync: %s metadata diff detected but Phoenix didn't "
                "return a prompt id; cannot patch.",
                prompt_name,
            )
            report.prompts_failed.append(
                (prompt_name, "patch: missing prompt id"),
            )
            return
        try:
            client.patch_prompt(
                prompt_id,
                metadata=prompt.metadata.model_dump(exclude_none=True),
                description=prompt.description,
            )
        except PhoenixError as exc:
            logger.warning("yaml_sync: %s patch failed: %s", prompt_name, exc)
            report.prompts_failed.append((prompt_name, f"patch: {exc}"))
            return

    report.prompts_pushed.append(prompt_name)


def _describe_prompt_diff(yaml_prompt: Prompt, phoenix_prompt: Prompt) -> str:
    """Build a one-line summary of the fields that differ between two Prompts.

    Used for startup-sync diagnostics so we can see WHY a push happened.
    Returns the differing field names plus, where short, a glimpse of
    each side's value. Bypasses the canonical hash to compute against
    the same dump shape as the hash itself.
    """
    a = yaml_prompt.model_dump(exclude=_PROMPT_HASH_EXCLUDE, exclude_none=True)
    b = phoenix_prompt.model_dump(exclude=_PROMPT_HASH_EXCLUDE, exclude_none=True)
    parts: list[str] = []
    for key in sorted(set(a.keys()) | set(b.keys())):
        if a.get(key) == b.get(key):
            continue
        ya = json.dumps(a.get(key), sort_keys=True, default=str)
        yp = json.dumps(b.get(key), sort_keys=True, default=str)
        # Trim verbose payloads (response_format JSON-Schema) so the log
        # stays scannable.
        if len(ya) > 120:
            ya = ya[:117] + "..."
        if len(yp) > 120:
            yp = yp[:117] + "..."
        parts.append(f"{key}: yaml={ya} | phoenix={yp}")
    return "; ".join(parts) if parts else "(none)"


# ---------------------------------------------------------------------------
# Dataset sync
# ---------------------------------------------------------------------------


def write_dataset_yaml(dataset: Dataset, datasets_dir: Path) -> bool:
    """Persist a dataset to ``{datasets_dir}/{name}.yaml`` (idempotent)."""
    path = datasets_dir / f"{dataset.name}.yaml"
    new_payload = _model_yaml_payload(dataset)
    existing = _read_yaml(path)
    if existing is not None:
        try:
            existing_model = Dataset.model_validate(existing)
            if _hash_dataset(existing_model) == _hash_dataset(dataset):
                return False
        except Exception:
            pass
    _write_yaml_atomic(path, new_payload)
    return True


def _fetch_phoenix_dataset(
    client: PhoenixDatasetClient, name: str,
) -> Dataset | None:
    """Locate a Phoenix dataset by name (Phoenix lookup is by id natively)."""
    cursor: str | None = None
    record = None
    while True:
        page = client.list_datasets(limit=200, cursor=cursor)
        for rec in page.get("data") or []:
            if rec.get("name") == name:
                record = rec
                break
        if record is not None:
            break
        cursor = page.get("next_cursor")
        if not cursor:
            break
    if record is None or not record.get("id"):
        return None
    examples_payload = client.list_examples(record["id"])
    return phoenix_to_dataset(record, examples_payload)


def _diff_examples(
    yaml_examples: list[Example],
    phoenix_examples: list[Example],
) -> tuple[list[Example], list[str]]:
    """Match by ``sha256(input)``; return ``(to_add, to_delete_ids)``."""
    yaml_by_hash = {_hash_example_input(ex): ex for ex in yaml_examples}
    phoenix_by_hash = {_hash_example_input(ex): ex for ex in phoenix_examples}
    to_add = [
        ex for h, ex in yaml_by_hash.items() if h not in phoenix_by_hash
    ]
    to_delete_ids = [
        ex.id for h, ex in phoenix_by_hash.items()
        if h not in yaml_by_hash and ex.id is not None
    ]
    return to_add, to_delete_ids


def _push_dataset_diff(
    client: PhoenixDatasetClient,
    dataset_id: str,
    to_add: list[Example],
    to_delete_ids: list[str],
) -> None:
    if to_add:
        client.add_examples(
            dataset_id, [example_to_phoenix_payload(ex) for ex in to_add],
        )
    for ex_id in to_delete_ids:
        client.delete_example(dataset_id, ex_id)


def _dataset_level_differs(
    yaml_dataset: Dataset, phoenix_dataset: Dataset,
) -> bool:
    """True iff dataset-record fields (description, metadata) differ."""
    return (
        yaml_dataset.description != phoenix_dataset.description
        or yaml_dataset.metadata.model_dump(exclude_none=True)
        != phoenix_dataset.metadata.model_dump(exclude_none=True)
    )


def _sync_datasets(
    datasets_dir: Path,
    client: PhoenixDatasetClient,
    report: SyncReport,
) -> None:
    diffs = _iter_yaml_diffs(
        datasets_dir,
        Dataset.model_validate,
        lambda name: _fetch_phoenix_dataset(client, name),
        _hash_dataset,
        lambda n, msg: report.datasets_failed.append((n, msg)),
        report.datasets_skipped.append,
    )
    for yaml_dataset, phoenix_dataset in diffs:
        # Case 1: Phoenix has nothing — REST upload + GraphQL patch
        # (the upload helper does both internally now).
        if phoenix_dataset is None:
            try:
                client.upload_dataset(
                    **dataset_to_phoenix_upload_kwargs(yaml_dataset),
                )
            except PhoenixDatasetError as exc:
                logger.warning(
                    "yaml_sync dataset %s create failed: %s",
                    yaml_dataset.name, exc,
                )
                report.datasets_failed.append(
                    (yaml_dataset.name, f"create: {exc}"),
                )
                continue
            logger.info("yaml_sync dataset %s — created", yaml_dataset.name)
            report.datasets_created.append(yaml_dataset.name)
            continue

        # Case 2: hashes match — nothing to do.
        if _hash_dataset(yaml_dataset) == _hash_dataset(phoenix_dataset):
            report.datasets_skipped.append(yaml_dataset.name)
            continue

        # Case 3: something differs. Decide which path(s) to take.
        to_add, to_delete = _diff_examples(
            yaml_dataset.examples, phoenix_dataset.examples,
        )
        needs_examples = bool(to_add or to_delete)
        needs_patch = _dataset_level_differs(yaml_dataset, phoenix_dataset)
        logger.info(
            "yaml_sync dataset %s — diff: examples add=%d delete=%d, "
            "patch metadata=%s",
            yaml_dataset.name, len(to_add), len(to_delete), needs_patch,
        )

        if needs_examples:
            try:
                _push_dataset_diff(
                    client, phoenix_dataset.id or "", to_add, to_delete,
                )
            except PhoenixDatasetError as exc:
                logger.warning(
                    "yaml_sync dataset %s example diff failed: %s",
                    yaml_dataset.name, exc,
                )
                report.datasets_failed.append(
                    (yaml_dataset.name, f"examples: {exc}"),
                )
                continue

        if needs_patch and phoenix_dataset.id:
            try:
                client.patch_dataset(
                    phoenix_dataset.id,
                    metadata=yaml_dataset.metadata.model_dump(exclude_none=True),
                    description=yaml_dataset.description,
                )
            except PhoenixDatasetError as exc:
                logger.warning(
                    "yaml_sync dataset %s patch failed: %s",
                    yaml_dataset.name, exc,
                )
                report.datasets_failed.append(
                    (yaml_dataset.name, f"patch: {exc}"),
                )
                continue

        report.datasets_diffed.append(yaml_dataset.name)


# ---------------------------------------------------------------------------
# Pull direction: Phoenix -> YAML (step-driven)
# ---------------------------------------------------------------------------


def pull_phoenix_to_yaml(
    *,
    prompts_dir: Path,
    prompt_client: PhoenixPromptClient,
    introspection_registry: dict[str, Any],
) -> SyncReport:
    """Refresh ``prompts_dir`` from Phoenix for every registered step.

    Iterates the same step classes ``_sync_prompts`` walks (one entry
    per registered ``LLMStepNode`` subclass). For each step:

    - Fetch Phoenix's current canonical Prompt for ``step_name()``.
    - If Phoenix has nothing, leave YAML alone — this is a "new step
      bootstrapping" case and the push direction will create the
      Phoenix record from YAML in the next stage.
    - Otherwise compare the existing on-disk YAML (if any) to Phoenix
      via the YAML-write hash (excludes code-derived fields). If
      content differs (or YAML is missing), write the canonical
      Phoenix-shape to disk via :func:`write_prompt_yaml` (idempotent;
      no-op when the hash already matches).

    Step-driven by design: prompts that exist in Phoenix without a
    matching ``LLMStepNode`` subclass in the registry are ignored.
    Phoenix is shared infrastructure; we don't pull every prompt it
    has — only the ones the framework manages.

    Returns a :class:`SyncReport` populated on the pull-side fields
    (``prompts_pulled`` / ``prompts_pull_skipped`` /
    ``prompts_pull_failed``). Callers can merge with a push-direction
    report to get a single end-to-end view.
    """
    report = SyncReport()

    if not introspection_registry:
        return report

    seen: set[type] = set()
    for pipeline_cls in introspection_registry.values():
        for step_cls in iter_step_classes(pipeline_cls):
            if step_cls in seen:
                continue
            seen.add(step_cls)
            _pull_one_step(
                step_cls=step_cls,
                prompts_dir=prompts_dir,
                client=prompt_client,
                report=report,
            )

    return report


def _pull_one_step(
    *,
    step_cls: type,
    prompts_dir: Path,
    client: PhoenixPromptClient,
    report: SyncReport,
) -> None:
    """Pull a single step's prompt from Phoenix to YAML if Phoenix has changes."""
    prompt_name = step_cls.step_name()

    try:
        phoenix_record, phoenix_prompt = _fetch_phoenix_prompt(client, prompt_name)
    except PhoenixError as exc:
        logger.warning(
            "yaml_sync pull: %s phoenix lookup failed: %s",
            prompt_name, exc,
        )
        report.prompts_pull_failed.append((prompt_name, f"phoenix: {exc}"))
        return

    if phoenix_prompt is None:
        # Phoenix doesn't have this prompt yet — nothing to pull.
        # The push stage will create it from YAML if YAML exists,
        # or the validator will surface PromptYamlMissingError if not.
        logger.info(
            "yaml_sync pull: %s — Phoenix has no record, skipping pull",
            prompt_name,
        )
        report.prompts_pull_skipped.append(prompt_name)
        return

    # Always invoke write_prompt_yaml — it's hash-idempotent and
    # decides internally whether the on-disk file needs to change.
    try:
        wrote = write_prompt_yaml(phoenix_prompt, prompts_dir)
    except OSError as exc:
        logger.warning(
            "yaml_sync pull: %s could not write YAML: %s",
            prompt_name, exc,
        )
        report.prompts_pull_failed.append(
            (prompt_name, f"write: {exc}"),
        )
        return

    if wrote:
        logger.info(
            "yaml_sync pull: %s — refreshed YAML from Phoenix",
            prompt_name,
        )
        report.prompts_pulled.append(prompt_name)
    else:
        report.prompts_pull_skipped.append(prompt_name)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def startup_sync(
    *,
    prompts_dir: Path | None,
    datasets_dir: Path | None,
    prompt_client: PhoenixPromptClient | None,
    dataset_client: PhoenixDatasetClient | None,
    introspection_registry: dict[str, Any] | None = None,
) -> SyncReport:
    """Run YAML -> Phoenix sync for both prompts and datasets.

    Each ``*_dir`` / ``*_client`` pair is independent; pass ``None`` on
    either side to skip that domain. Failures in one domain don't
    affect the other.

    ``introspection_registry`` lets prompt sync look up the matching
    LLMStep by name and pull ``response_format`` / ``tools`` from its
    ``INSTRUCTIONS`` / ``DEFAULT_TOOLS``. Without it, those fields are
    left unset and Phoenix records the prompt without schemas (still
    useful for prompts not bound to a registered step).
    """
    report = SyncReport()
    if prompts_dir is not None and prompt_client is not None:
        try:
            _sync_prompts(
                prompts_dir, prompt_client, report, introspection_registry,
            )
        except Exception:
            logger.exception("Prompt YAML sync failed; continuing")
    if datasets_dir is not None and dataset_client is not None:
        try:
            _sync_datasets(datasets_dir, dataset_client, report)
        except Exception:
            logger.exception("Dataset YAML sync failed; continuing")
    return report


# Suppress unused-import warning for DatasetNotFoundError (re-exported for
# the test surface; keeping the import documented at module-top).
_ = DatasetNotFoundError


__all__ = [
    "SyncReport",
    "pull_phoenix_to_yaml",
    "startup_sync",
    "write_prompt_yaml",
    "write_dataset_yaml",
    "delete_yaml",
]
