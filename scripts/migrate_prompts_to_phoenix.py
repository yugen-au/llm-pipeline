"""One-shot bootstrap: copy prompts from local DB into Phoenix.

Reads every active-latest row in the framework's ``pipelines_prompts``
table, groups system + user content by step name, and pushes each step
to Phoenix as a ``CHAT`` prompt with both messages in one record. The
resulting version is tagged ``production`` so the runtime resolver
picks it up by default.

Idempotent: re-running compares the message bodies + variable
definitions against Phoenix's latest version and skips when equal, so
running it twice doesn't churn versions.

Usage::

    # Default: read DB at LLM_PIPELINE_DB (or auto-resolved sqlite),
    # push to Phoenix at PHOENIX_BASE_URL / OTEL_EXPORTER_OTLP_ENDPOINT.
    uv run python scripts/migrate_prompts_to_phoenix.py

    # Preview without writing.
    uv run python scripts/migrate_prompts_to_phoenix.py --dry-run

    # Override the DB or backend explicitly.
    uv run python scripts/migrate_prompts_to_phoenix.py \\
        --db-url sqlite:///./pipeline.db \\
        --phoenix-url http://localhost:6006

The local ``Prompt`` table is left untouched; cleanup happens in
Phase E once the runtime is fully Phoenix-backed.
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Default model defaults written into each migrated prompt. The
# runtime model is set on PipelineConfig at execute time, so what we
# put here only affects the Phoenix Playground view. Phase B (schema
# sync at registration) replaces these with the registered values.
_DEFAULT_MODEL_PROVIDER = "OPENAI"
_DEFAULT_MODEL_NAME = "gpt-4o-mini"
_DEFAULT_INVOCATION_PARAMS: Dict[str, Any] = {"type": "openai", "openai": {}}

# Suffix → role mapping, mirrors PromptService._SUFFIX_TO_ROLE.
_SUFFIX_TO_ROLE: Dict[str, str] = {
    "system_instruction": "system",
    "system": "system",
    "user_prompt": "user",
    "user": "user",
}

_NAME_INVALID_RE = re.compile(r"[^a-z0-9_-]+")


logger = logging.getLogger("migrate_prompts_to_phoenix")


def _sanitise_name(raw: str) -> str:
    s = raw.lower()
    s = _NAME_INVALID_RE.sub("_", s)
    s = re.sub(r"_+", "_", s).strip("_-")
    if not s:
        raise ValueError(f"Cannot derive Phoenix name from {raw!r}")
    return s


def _split_key(prompt_key: str) -> Tuple[str, Optional[str]]:
    """``widget_detection.system_instruction`` -> (``widget_detection``, ``system``).

    Returns ``(name, None)`` when the suffix isn't a recognised role —
    those rows fall through to a single-message migration (rare; mostly
    legacy guidance prompts).
    """
    if "." in prompt_key:
        head, _, tail = prompt_key.rpartition(".")
        if tail in _SUFFIX_TO_ROLE:
            return _sanitise_name(head), _SUFFIX_TO_ROLE[tail]
    return _sanitise_name(prompt_key), None


def _gather_local_prompts(db_url: Optional[str]) -> List[Dict[str, Any]]:
    """Open the framework DB and return all active-latest Prompt rows."""
    from sqlalchemy import create_engine
    from sqlmodel import Session, select

    from llm_pipeline.db import init_pipeline_db
    from llm_pipeline.db.prompt import Prompt

    engine = (
        create_engine(db_url) if db_url is not None else init_pipeline_db()
    )

    rows: List[Dict[str, Any]] = []
    with Session(engine) as session:
        stmt = select(Prompt).where(
            Prompt.is_active == True,  # noqa: E712
            Prompt.is_latest == True,  # noqa: E712
        )
        for row in session.exec(stmt):
            rows.append({
                "prompt_key": row.prompt_key,
                "prompt_type": row.prompt_type,
                "prompt_name": row.prompt_name,
                "step_name": row.step_name,
                "content": row.content,
                "description": row.description,
                "variable_definitions": row.variable_definitions or {},
            })
    return rows


def _group_by_phoenix_name(
    rows: Iterable[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Collapse rows onto one bucket per Phoenix prompt name."""
    buckets: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "messages": {},  # role -> content
            "description": None,
            "variable_definitions": {},
            "source_keys": [],
        }
    )

    for row in rows:
        name, role = _split_key(row["prompt_key"])
        if role is None:
            # Fall back to the row's own prompt_type for the role.
            role = row["prompt_type"] or "system"
        bucket = buckets[name]
        # Last writer wins — duplicate (name, role) pairs would only
        # occur if the local DB had drifted; the suffix uniqueness is
        # enforced by the partial-unique index on (key, type) when
        # active+latest.
        bucket["messages"][role] = row["content"]
        bucket["source_keys"].append(row["prompt_key"])
        if row["description"] and not bucket["description"]:
            bucket["description"] = row["description"]
        # Merge variable_definitions across system + user — duplicates
        # are fine; the dict-update preserves later writes.
        if isinstance(row["variable_definitions"], dict):
            bucket["variable_definitions"].update(row["variable_definitions"])

    return buckets


def _build_chat_template(messages_by_role: Dict[str, str]) -> Dict[str, Any]:
    """Phoenix CHAT template body ordered system -> user -> others."""
    ordered: List[Dict[str, Any]] = []
    for role in ("system", "user"):
        if role in messages_by_role:
            ordered.append({"role": role, "content": messages_by_role[role]})
    for role, content in messages_by_role.items():
        if role in ("system", "user"):
            continue
        ordered.append({"role": role, "content": content})
    return {"type": "chat", "messages": ordered}


def _versions_equivalent(
    existing: Dict[str, Any], proposed_version: Dict[str, Any],
) -> bool:
    """Cheap deep-equality on the bits we care about (template + format)."""
    if not existing:
        return False
    e_template = existing.get("template") or {}
    p_template = proposed_version.get("template") or {}
    if e_template.get("type") != p_template.get("type"):
        return False
    if e_template.get("type") == "chat":
        e_msgs = [
            (m.get("role"), m.get("content"))
            for m in e_template.get("messages") or []
        ]
        p_msgs = [
            (m.get("role"), m.get("content"))
            for m in p_template.get("messages") or []
        ]
        if e_msgs != p_msgs:
            return False
    if existing.get("template_format") != proposed_version.get("template_format"):
        return False
    return True


def _migrate_one(
    name: str,
    bucket: Dict[str, Any],
    *,
    client,
    dry_run: bool,
    tag: str,
) -> str:
    """Push one bucket; returns ``"created" | "updated" | "skipped"``."""
    from llm_pipeline.prompts.phoenix_client import PromptNotFoundError

    template = _build_chat_template(bucket["messages"])
    proposed_version = {
        "model_provider": _DEFAULT_MODEL_PROVIDER,
        "model_name": _DEFAULT_MODEL_NAME,
        "template": template,
        "template_type": "CHAT",
        "template_format": "F_STRING",
        "invocation_parameters": _DEFAULT_INVOCATION_PARAMS,
    }
    metadata: Dict[str, Any] = {"managed_by": "llm-pipeline"}
    if bucket["variable_definitions"]:
        metadata["variable_definitions"] = bucket["variable_definitions"]
    if bucket["source_keys"]:
        metadata["legacy_keys"] = sorted(set(bucket["source_keys"]))
    proposed_prompt: Dict[str, Any] = {"name": name, "metadata": metadata}
    if bucket["description"]:
        proposed_prompt["description"] = bucket["description"]

    if client is None:
        # Dry run: skip the existence check entirely so we don't need
        # a live Phoenix connection.
        logger.info(
            "[dry  ] would create %s (roles=%s)",
            name, sorted(bucket["messages"].keys()),
        )
        return "create"

    try:
        existing = client.get_latest(name)
    except PromptNotFoundError:
        existing = None

    if existing and _versions_equivalent(existing, proposed_version):
        logger.info("[skip ] %s — already up-to-date", name)
        return "skipped"

    action = "update" if existing else "create"

    new_version = client.create(prompt=proposed_prompt, version=proposed_version)
    version_id = new_version.get("id")
    if version_id:
        try:
            client.add_tag(version_id, tag, description=f"Migrated by {Path(__file__).name}")
        except Exception as exc:  # pragma: no cover - tag failure isn't fatal
            logger.warning("Tagging failed for %s: %s", name, exc)
    logger.info("[%-6s] %s -> version %s",
                action, name, version_id or "?")
    return action


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--db-url",
        default=None,
        help="SQLAlchemy URL for the framework DB. Defaults to env-resolved sqlite.",
    )
    parser.add_argument(
        "--phoenix-url",
        default=None,
        help="Phoenix base URL. Falls back to PHOENIX_BASE_URL / OTEL endpoint.",
    )
    parser.add_argument(
        "--tag", default="production",
        help="Tag to attach to the migrated version (default: production).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the plan without contacting Phoenix.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )

    rows = _gather_local_prompts(args.db_url)
    if not rows:
        logger.info("No active-latest prompts found in the local DB. Nothing to do.")
        return 0
    logger.info("Found %d local prompt rows.", len(rows))

    buckets = _group_by_phoenix_name(rows)
    logger.info("Mapped to %d Phoenix prompt(s).", len(buckets))

    if args.dry_run:
        client = None
    else:
        from llm_pipeline.prompts.phoenix_client import PhoenixPromptClient

        client = PhoenixPromptClient(base_url=args.phoenix_url)

    summary: Dict[str, int] = defaultdict(int)
    for name, bucket in sorted(buckets.items()):
        try:
            outcome = _migrate_one(
                name, bucket,
                client=client,
                dry_run=args.dry_run,
                tag=args.tag,
            )
        except Exception as exc:
            logger.error("[error] %s — %s", name, exc)
            summary["error"] += 1
            continue
        summary[outcome] += 1

    logger.info(
        "Done. created=%d updated=%d skipped=%d error=%d (dry_run=%s)",
        summary.get("create", 0) + summary.get("created", 0),
        summary.get("update", 0) + summary.get("updated", 0),
        summary.get("skipped", 0),
        summary.get("error", 0),
        args.dry_run,
    )
    return 0 if summary.get("error", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
