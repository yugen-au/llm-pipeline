"""Generic versioning helpers for append-only version management.

Mediates all version writes for models with (version, is_active, is_latest, updated_at).
Helper flushes; caller commits.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypeVar

from sqlmodel import Session, select

from llm_pipeline.utils.versioning import compare_versions

T = TypeVar("T")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _bump_minor(version: str) -> str:
    """'1.0' -> '1.1', '1.9' -> '1.10', '1' -> '1.1', '1.2.3' -> '1.2.4'.
    ValueError on non-numeric parts."""
    parts = version.split(".")
    if not parts or not all(p.isdigit() for p in parts):
        raise ValueError(f"Non-numeric version: {version!r}")
    if len(parts) == 1:
        return f"{parts[0]}.1"
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)


def save_new_version(
    session: Session,
    model_cls: type[T],
    key_filters: dict[str, Any],
    new_fields: dict[str, Any],
    version: str | None = None,
) -> T:
    """Insert new version row, always flipping any prior active-latest.

    1. Find active-latest row matching key_filters.
    2. If found: flip is_latest=False (updated_at=now); session.flush();
       auto-bump minor unless `version` is supplied; INSERT new row.
    3. If not found: INSERT fresh row at version="1.0" (or `version` if supplied).

    Helper flushes; caller commits. Forbids managed cols in new_fields
    (version, is_active, is_latest, created_at, updated_at).
    """
    forbidden = {"version", "is_active", "is_latest", "created_at", "updated_at"}
    if forbidden & new_fields.keys():
        raise ValueError(
            f"new_fields must not include versioning-managed columns: "
            f"{sorted(forbidden & new_fields.keys())}"
        )

    stmt = select(model_cls).where(
        model_cls.is_active == True,  # noqa: E712
        model_cls.is_latest == True,  # noqa: E712
    )
    for col, val in key_filters.items():
        stmt = stmt.where(getattr(model_cls, col) == val)
    prior = session.exec(stmt).first()

    now = _utc_now()
    if prior is None:
        new_version = version or "1.0"
    else:
        new_version = version or _bump_minor(prior.version)
        if compare_versions(new_version, prior.version) <= 0:
            raise ValueError(
                f"new version {new_version!r} is not greater than prior "
                f"{prior.version!r} for {model_cls.__name__} {key_filters}"
            )
        prior.is_latest = False
        prior.updated_at = now
        session.add(prior)
        session.flush()  # release the partial-unique slot before INSERT

    row_kwargs = {
        **key_filters,
        **new_fields,
        "version": new_version,
        "is_active": True,
        "is_latest": True,
        "created_at": now,
        "updated_at": now,
    }
    new_row = model_cls(**row_kwargs)
    session.add(new_row)
    session.flush()
    return new_row


def get_latest(
    session: Session,
    model_cls: type[T],
    **filters: Any,
) -> T | None:
    """Return active-latest row matching filters, or None."""
    stmt = select(model_cls).where(
        model_cls.is_active == True,  # noqa: E712
        model_cls.is_latest == True,  # noqa: E712
    )
    for col, val in filters.items():
        stmt = stmt.where(getattr(model_cls, col) == val)
    return session.exec(stmt).first()


def soft_delete_latest(
    session: Session,
    model_cls: type[T],
    **key_filters: Any,
) -> T | None:
    """Set is_active=False on current active-latest row; keep is_latest=True
    (so historical 'most recent' queries still resolve). Writes updated_at.
    Flushes. Returns the soft-deleted row, or None if no match.
    """
    row = get_latest(session, model_cls, **key_filters)
    if row is None:
        return None
    row.is_active = False
    row.updated_at = _utc_now()
    session.add(row)
    session.flush()
    return row
