"""Prompts route module — Phoenix passthrough (Phase D).

Every ``/api/prompts/*`` endpoint proxies to Phoenix's ``/v1/prompts``
REST surface. The local ``Prompt`` SQLModel is no longer touched by
these routes (Phase E removes it).

A single Phoenix CHAT prompt holds both a ``system`` and a ``user``
message in one record; the framework's UI historically modeled them
as two separate "variants" of the same ``prompt_key``. The handlers
collapse / expand on the way in and out so the existing frontend
hooks (``usePrompts``, ``usePromptDetail``, ``useUpdatePrompt`` …)
keep working unchanged.

Frontend prompt_keys may arrive in either shape:

* bare Phoenix name (``"sentiment_analysis"``) — the new canonical
* legacy split key (``"sentiment_analysis.system_instruction"``) — the
  pre-Phase-A shape, still appearing in past run snapshots.

``_split_key`` collapses both onto the bare name + role.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from llm_pipeline.prompts.phoenix_client import (
    PhoenixError,
    PhoenixNotConfiguredError,
    PhoenixPromptClient,
    PhoenixUnavailableError,
    PromptNotFoundError,
)
from llm_pipeline.prompts.utils import extract_variables_from_content

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prompts", tags=["prompts"])


# ---------------------------------------------------------------------------
# Response models (frontend-facing; shapes preserved from pre-Phase-D)
# ---------------------------------------------------------------------------


class PromptItem(BaseModel):
    """One (prompt_name, role) tuple as the frontend renders it.

    ``created_at`` / ``updated_at`` are Optional now: Phoenix doesn't
    expose timestamps on prompts or versions, so they are filled with
    a sentinel epoch when missing.
    """
    id: int
    prompt_key: str
    prompt_name: str
    prompt_type: str
    category: Optional[str] = None
    step_name: Optional[str] = None
    content: str
    required_variables: Optional[List[str]] = None
    variable_definitions: Optional[Dict[str, Any]] = None
    description: Optional[str] = None
    version: str
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None


class PromptListResponse(BaseModel):
    items: List[PromptItem]
    total: int
    offset: int
    limit: int


class PromptDetailResponse(BaseModel):
    prompt_key: str
    variants: List[PromptItem]


class HistoricalPromptItem(BaseModel):
    id: int
    prompt_key: str
    prompt_name: str
    prompt_type: str
    category: Optional[str] = None
    step_name: Optional[str] = None
    content: str
    required_variables: Optional[List[str]] = None
    variable_definitions: Optional[Dict[str, Any]] = None
    description: Optional[str] = None
    version: str
    is_active: bool
    is_latest: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class PromptCreateRequest(BaseModel):
    prompt_key: str
    prompt_name: Optional[str] = None
    prompt_type: str  # "system" or "user"
    content: str
    category: Optional[str] = None
    step_name: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None
    created_by: Optional[str] = None
    variable_definitions: Optional[Dict[str, Any]] = None


class PromptUpdateRequest(BaseModel):
    prompt_name: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    step_name: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None
    created_by: Optional[str] = None
    variable_definitions: Optional[Dict[str, Any]] = None


class PromptListParams(BaseModel):
    category: Optional[str] = None
    step_name: Optional[str] = None
    prompt_type: Optional[str] = None
    is_active: Optional[bool] = True
    offset: int = Query(default=0, ge=0)
    limit: int = Query(default=50, ge=1, le=200)


# ---------------------------------------------------------------------------
# Constants + helpers
# ---------------------------------------------------------------------------


_EPOCH = datetime.fromtimestamp(0, tz=timezone.utc)
_NAME_INVALID_RE = re.compile(r"[^a-z0-9_-]+")
_SUFFIX_TO_ROLE: Dict[str, str] = {
    "system_instruction": "system",
    "system": "system",
    "user_prompt": "user",
    "user": "user",
}
_SYSTEM_ROLES = frozenset({"system", "developer"})
_USER_ROLES = frozenset({"user"})


def _sanitise_name(raw: str) -> str:
    s = raw.lower()
    s = _NAME_INVALID_RE.sub("_", s)
    s = re.sub(r"_+", "_", s).strip("_-")
    if not s:
        raise HTTPException(status_code=422, detail=f"Invalid prompt name {raw!r}")
    return s


def _split_key(prompt_key: str, prompt_type: str) -> tuple[str, str]:
    """Frontend prompt_key + prompt_type -> (phoenix_name, role).

    Mirrors :func:`PromptService._split_key` so legacy split keys keep
    routing to the right Phoenix prompt.
    """
    if "." in prompt_key:
        head, _, tail = prompt_key.rpartition(".")
        if tail in _SUFFIX_TO_ROLE:
            return _sanitise_name(head), _SUFFIX_TO_ROLE[tail]
        return _sanitise_name(prompt_key), prompt_type
    return _sanitise_name(prompt_key), prompt_type


def _bare_name(prompt_key: str) -> str:
    """Strip a recognised role suffix; for endpoints that don't take a type."""
    if "." in prompt_key:
        head, _, tail = prompt_key.rpartition(".")
        if tail in _SUFFIX_TO_ROLE:
            return _sanitise_name(head)
    return _sanitise_name(prompt_key)


def _get_client(request: Request) -> PhoenixPromptClient:
    """Resolve a per-app Phoenix client.

    Cached on ``request.app.state`` so we share one instance across
    routes within a process. Raises 503 when Phoenix is unconfigured.
    """
    cached = getattr(request.app.state, "_phoenix_prompt_client", None)
    if cached is not None:
        return cached
    try:
        client = PhoenixPromptClient()
    except PhoenixNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    request.app.state._phoenix_prompt_client = client
    return client


def _humanise(name: str) -> str:
    """Best-effort display name for a snake_case Phoenix identifier."""
    return name.replace("_", " ").replace("-", " ").title()


def _stable_id(name: str, role: str) -> int:
    """Deterministic positive int id for a (name, role) pair.

    The frontend's ``id`` field is non-zero in some places; we hash to
    a stable integer that's unique across the page.
    """
    return abs(hash((name, role))) % (2**31 - 1)


def _normalise_metadata(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _variable_definitions_for(
    metadata: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    var_defs = metadata.get("variable_definitions")
    return var_defs if isinstance(var_defs, dict) and var_defs else None


def _extract_messages(version: Dict[str, Any]) -> List[tuple[str, str]]:
    """Pull (role, text) pairs out of the version's CHAT template.

    STR templates (single-message) collapse to ``[("system", body)]``
    so they still surface as one PromptItem.
    """
    template = version.get("template") or {}
    template_type = template.get("type")
    if template_type == "string":
        body = template.get("template")
        if isinstance(body, str):
            return [("system", body)]
        return []
    if template_type != "chat":
        return []
    out: List[tuple[str, str]] = []
    for msg in template.get("messages") or []:
        role = msg.get("role")
        content = msg.get("content")
        if isinstance(content, str):
            out.append((role, content))
        elif isinstance(content, list):
            text = "".join(
                p.get("text", "")
                for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            )
            out.append((role, text))
    return out


def _ui_role_for(message_role: str) -> str:
    """Map Phoenix message roles onto the frontend's ``system`` / ``user``."""
    if message_role in _SYSTEM_ROLES:
        return "system"
    if message_role in _USER_ROLES:
        return "user"
    return message_role


def _to_prompt_item(
    *,
    name: str,
    role: str,
    content: str,
    metadata: Dict[str, Any],
    version: Dict[str, Any],
    prompt_record: Optional[Dict[str, Any]] = None,
) -> PromptItem:
    """Build a frontend PromptItem from Phoenix data."""
    var_defs = _variable_definitions_for(metadata)
    description = (
        version.get("description")
        or (prompt_record or {}).get("description")
    )
    raw_version_id = version.get("id") or ""
    return PromptItem(
        id=_stable_id(name, role),
        prompt_key=name,
        prompt_name=metadata.get("display_name") or _humanise(name),
        prompt_type=role,
        category=metadata.get("category"),
        step_name=metadata.get("step_name") or name,
        content=content,
        required_variables=extract_variables_from_content(content),
        variable_definitions=var_defs,
        description=description,
        version=raw_version_id,
        is_active=True,
        created_at=_EPOCH,
        updated_at=_EPOCH,
        created_by=None,
    )


def _phoenix_prompt_metadata(
    client: PhoenixPromptClient, name: str,
) -> Dict[str, Any]:
    """Look up a prompt record's metadata via the list endpoint.

    Phoenix's prompt-detail endpoints return ``PromptVersion`` (no
    prompt-level metadata), so we list and filter. Cached briefly via
    ``client._prompt_record_cache``.
    """
    cache: Dict[str, Dict[str, Any]] = getattr(
        client, "_prompt_record_cache", {},
    )
    if name in cache:
        return cache[name]
    cursor = None
    while True:
        page = client.list_prompts(limit=200, cursor=cursor)
        for record in page.get("data") or []:
            cache[record.get("name")] = record
        cursor = page.get("next_cursor")
        if not cursor:
            break
    client._prompt_record_cache = cache  # type: ignore[attr-defined]
    return cache.get(name, {})


def _invalidate_record_cache(client: PhoenixPromptClient, name: str) -> None:
    cache = getattr(client, "_prompt_record_cache", None)
    if isinstance(cache, dict) and name in cache:
        cache.pop(name, None)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=PromptListResponse)
def list_prompts(
    request: Request,
    params: Annotated[PromptListParams, Depends()],
) -> PromptListResponse:
    """Paginated list. Each Phoenix prompt expands to one row per role."""
    client = _get_client(request)

    # Walk every Phoenix prompt; expand into per-role rows.
    items: List[PromptItem] = []
    cursor: Optional[str] = None
    while True:
        try:
            page = client.list_prompts(limit=200, cursor=cursor)
        except PhoenixUnavailableError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        for record in page.get("data") or []:
            name = record.get("name")
            if not isinstance(name, str):
                continue
            metadata = _normalise_metadata(record.get("metadata"))
            try:
                version = client.get_latest(name)
            except (PromptNotFoundError, PhoenixUnavailableError):
                continue
            for message_role, content in _extract_messages(version):
                ui_role = _ui_role_for(message_role)
                items.append(
                    _to_prompt_item(
                        name=name,
                        role=ui_role,
                        content=content,
                        metadata=metadata,
                        version=version,
                        prompt_record=record,
                    )
                )
        cursor = page.get("next_cursor")
        if not cursor:
            break

    # Filter — applied in Python since Phoenix doesn't expose these
    # facets server-side.
    if params.prompt_type is not None:
        items = [i for i in items if i.prompt_type == params.prompt_type]
    if params.category is not None:
        items = [i for i in items if i.category == params.category]
    if params.step_name is not None:
        items = [i for i in items if i.step_name == params.step_name]
    # ``is_active`` is always True for live Phoenix prompts; the
    # ``False`` filter returns nothing.
    if params.is_active is False:
        items = []

    items.sort(key=lambda i: (i.prompt_key, i.prompt_type))
    total = len(items)
    sliced = items[params.offset : params.offset + params.limit]
    return PromptListResponse(
        items=sliced,
        total=total,
        offset=params.offset,
        limit=params.limit,
    )


@router.get("/{prompt_key}", response_model=PromptDetailResponse)
def get_prompt(prompt_key: str, request: Request) -> PromptDetailResponse:
    """Grouped detail: both system + user variants for a prompt name."""
    client = _get_client(request)
    name = _bare_name(prompt_key)

    record = _phoenix_prompt_metadata(client, name)
    metadata = _normalise_metadata(record.get("metadata"))
    try:
        version = client.get_latest(name)
    except PromptNotFoundError:
        raise HTTPException(status_code=404, detail="Prompt not found")
    except PhoenixUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    variants: List[PromptItem] = []
    for message_role, content in _extract_messages(version):
        variants.append(
            _to_prompt_item(
                name=name,
                role=_ui_role_for(message_role),
                content=content,
                metadata=metadata,
                version=version,
                prompt_record=record,
            )
        )
    if not variants:
        raise HTTPException(status_code=404, detail="Prompt has no messages")

    return PromptDetailResponse(prompt_key=name, variants=variants)


@router.post("", response_model=PromptItem, status_code=201)
def create_prompt(
    body: PromptCreateRequest,
    request: Request,
) -> PromptItem:
    """Create or extend a Phoenix prompt with a new (role, content) message.

    Phoenix versions are append-only, so this either:

    * creates a fresh prompt with one CHAT message (role = ``prompt_type``)
      when no record exists for ``prompt_key``, or
    * pushes a new version that adds / replaces the matching role on
      an existing prompt.
    """
    client = _get_client(request)
    name, role = _split_key(body.prompt_key, body.prompt_type)
    if role not in ("system", "user"):
        raise HTTPException(
            status_code=422, detail=f"prompt_type must be system or user, got {role!r}",
        )

    # Existing version (None on fresh create).
    try:
        existing_version = client.get_latest(name)
    except PromptNotFoundError:
        existing_version = None
    except PhoenixUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # Build the new messages list: keep every other role, replace ours.
    messages: List[Dict[str, Any]] = []
    if existing_version is not None:
        for r, c in _extract_messages(existing_version):
            ui_r = _ui_role_for(r)
            if ui_r == role:
                continue
            messages.append({"role": ui_r, "content": c})
    messages.append({"role": role, "content": body.content})
    # Stable ordering: system first, then user, then anything else.
    messages.sort(key=lambda m: (
        0 if m["role"] == "system" else 1 if m["role"] == "user" else 2
    ))

    # Metadata: only set on first create (Phoenix ignores it on
    # subsequent versions). Merge supplied variable_definitions and
    # back-compat fields.
    record = {} if existing_version is None else _phoenix_prompt_metadata(
        client, name,
    )
    record_metadata = _normalise_metadata(record.get("metadata"))
    new_metadata: Dict[str, Any] = {**record_metadata, "managed_by": "llm-pipeline"}
    if body.variable_definitions is not None:
        new_metadata["variable_definitions"] = body.variable_definitions
    if body.category is not None:
        new_metadata["category"] = body.category
    if body.step_name is not None:
        new_metadata["step_name"] = body.step_name
    if body.prompt_name is not None:
        new_metadata["display_name"] = body.prompt_name

    prompt_payload: Dict[str, Any] = {"name": name, "metadata": new_metadata}
    if body.description is not None:
        prompt_payload["description"] = body.description

    # Use existing model + invocation params when extending; defaults
    # when creating fresh.
    base = existing_version or {}
    version_payload: Dict[str, Any] = {
        "model_provider": base.get("model_provider", "OPENAI"),
        "model_name": base.get("model_name", "gpt-4o-mini"),
        "template": {"type": "chat", "messages": messages},
        "template_type": "CHAT",
        "template_format": base.get("template_format", "F_STRING"),
        "invocation_parameters": base.get(
            "invocation_parameters", {"type": "openai", "openai": {}},
        ),
    }
    if body.description is not None:
        version_payload["description"] = body.description
    if base.get("response_format") is not None:
        version_payload["response_format"] = base["response_format"]
    if base.get("tools") is not None:
        version_payload["tools"] = base["tools"]

    try:
        new_version = client.create(prompt=prompt_payload, version=version_payload)
    except PhoenixUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    _invalidate_record_cache(client, name)

    # Tag latest version "production" (best-effort).
    version_id = new_version.get("id")
    if version_id:
        try:
            client.add_tag(version_id, "production", description="UI save")
        except PhoenixError as exc:
            logger.warning("Phoenix tag failed for %s: %s", name, exc)

    return _to_prompt_item(
        name=name,
        role=role,
        content=body.content,
        metadata=new_metadata,
        version=new_version,
        prompt_record={"description": body.description},
    )


@router.put("/{prompt_key}/{prompt_type}", response_model=PromptItem)
def update_prompt(
    prompt_key: str,
    prompt_type: str,
    body: PromptUpdateRequest,
    request: Request,
) -> PromptItem:
    """Update a single role's content on an existing Phoenix prompt."""
    client = _get_client(request)
    name, role = _split_key(prompt_key, prompt_type)
    if role not in ("system", "user"):
        raise HTTPException(
            status_code=422, detail=f"prompt_type must be system or user, got {role!r}",
        )

    try:
        existing_version = client.get_latest(name)
    except PromptNotFoundError:
        raise HTTPException(status_code=404, detail="Prompt not found")
    except PhoenixUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    updates = body.model_dump(exclude_unset=True)

    # Resolve final content for this role: explicit body wins,
    # otherwise keep the existing message.
    current_messages = _extract_messages(existing_version)
    current_content = next(
        (c for r, c in current_messages if _ui_role_for(r) == role),
        "",
    )
    new_content = updates.get("content", current_content)

    # Rebuild messages list.
    messages: List[Dict[str, Any]] = []
    for r, c in current_messages:
        ui_r = _ui_role_for(r)
        if ui_r == role:
            continue
        messages.append({"role": ui_r, "content": c})
    messages.append({"role": role, "content": new_content})
    messages.sort(key=lambda m: (
        0 if m["role"] == "system" else 1 if m["role"] == "user" else 2
    ))

    # Metadata: only the first create persists, but we still pass it
    # for first-time fields (no harm — Phoenix ignores the rest).
    record = _phoenix_prompt_metadata(client, name)
    record_metadata = _normalise_metadata(record.get("metadata"))
    new_metadata: Dict[str, Any] = {**record_metadata, "managed_by": "llm-pipeline"}
    if "variable_definitions" in updates:
        if updates["variable_definitions"] is None:
            new_metadata.pop("variable_definitions", None)
        else:
            new_metadata["variable_definitions"] = updates["variable_definitions"]
    for meta_field in ("category", "step_name"):
        if meta_field in updates and updates[meta_field] is not None:
            new_metadata[meta_field] = updates[meta_field]
    if updates.get("prompt_name") is not None:
        new_metadata["display_name"] = updates["prompt_name"]

    prompt_payload: Dict[str, Any] = {"name": name, "metadata": new_metadata}
    description = updates.get("description", existing_version.get("description"))
    if description is not None:
        prompt_payload["description"] = description

    version_payload: Dict[str, Any] = {
        "model_provider": existing_version.get("model_provider"),
        "model_name": existing_version.get("model_name"),
        "template": {"type": "chat", "messages": messages},
        "template_type": existing_version.get("template_type", "CHAT"),
        "template_format": existing_version.get("template_format", "F_STRING"),
        "invocation_parameters": existing_version.get("invocation_parameters"),
    }
    if description is not None:
        version_payload["description"] = description
    if existing_version.get("response_format") is not None:
        version_payload["response_format"] = existing_version["response_format"]
    if existing_version.get("tools") is not None:
        version_payload["tools"] = existing_version["tools"]

    try:
        new_version = client.create(prompt=prompt_payload, version=version_payload)
    except PhoenixUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    _invalidate_record_cache(client, name)

    version_id = new_version.get("id")
    if version_id:
        try:
            client.add_tag(version_id, "production", description="UI save")
        except PhoenixError as exc:
            logger.warning("Phoenix tag failed for %s: %s", name, exc)

    return _to_prompt_item(
        name=name,
        role=role,
        content=new_content,
        metadata=new_metadata,
        version=new_version,
        prompt_record=record,
    )


@router.delete("/{prompt_key}/{prompt_type}")
def delete_prompt(
    prompt_key: str,
    prompt_type: str,
    request: Request,
) -> dict:
    """Delete the Phoenix prompt entirely.

    Phoenix has no per-role delete; ``prompt_type`` is accepted for
    URL compatibility but ignored. The whole prompt + every version
    are removed. Re-creating uses ``POST /prompts``.
    """
    del prompt_type  # accepted for URL compat
    client = _get_client(request)
    name = _bare_name(prompt_key)

    try:
        client.delete(name)
    except PromptNotFoundError:
        raise HTTPException(status_code=404, detail="Prompt not found")
    except PhoenixUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    _invalidate_record_cache(client, name)
    return {"detail": "Prompt deleted"}


@router.get(
    "/{prompt_key}/{prompt_type}/versions/{version}",
    response_model=HistoricalPromptItem,
)
def get_historical_prompt(
    prompt_key: str,
    prompt_type: str,
    version: str,
    request: Request,
) -> HistoricalPromptItem:
    """Resolve a specific version's role content.

    ``version`` is whatever the caller previously stored — Phoenix's
    base64 ``version_id`` for new snapshots, or a legacy semver string
    (``"1.2"``) for pre-Phoenix run snapshots. Legacy strings can't
    be resolved against Phoenix; we fall back to the latest version
    for those so the compare page still renders something rather than
    breaking.
    """
    client = _get_client(request)
    name, role = _split_key(prompt_key, prompt_type)

    record = _phoenix_prompt_metadata(client, name)
    metadata = _normalise_metadata(record.get("metadata"))

    fetched: Optional[Dict[str, Any]] = None
    # Phoenix version IDs are base64-ish (``UHJvbXB0…``); they don't
    # look like semver. If the supplied ``version`` doesn't match the
    # Phoenix shape, fall back to latest.
    looks_like_phoenix = bool(version) and not version[0].isdigit()
    if looks_like_phoenix:
        try:
            fetched = client.get_version(version)
        except (PromptNotFoundError, PhoenixUnavailableError):
            fetched = None
    if fetched is None:
        try:
            fetched = client.get_latest(name)
        except PromptNotFoundError:
            raise HTTPException(status_code=404, detail="Prompt version not found")
        except PhoenixUnavailableError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    # ``is_latest`` is true when the fetched version's id matches the
    # current latest. The compare page uses this to decide whether
    # to badge a row as "current" or "historical".
    try:
        latest_version = client.get_latest(name)
        is_latest = bool(latest_version.get("id")) and (
            latest_version.get("id") == fetched.get("id")
        )
    except PhoenixError:
        is_latest = False

    content = next(
        (c for r, c in _extract_messages(fetched) if _ui_role_for(r) == role),
        None,
    )
    if content is None:
        raise HTTPException(
            status_code=404,
            detail=f"No {role!r} message in version",
        )

    return HistoricalPromptItem(
        id=_stable_id(name, role),
        prompt_key=name,
        prompt_name=metadata.get("display_name") or _humanise(name),
        prompt_type=role,
        category=metadata.get("category"),
        step_name=metadata.get("step_name") or name,
        content=content,
        required_variables=extract_variables_from_content(content),
        variable_definitions=_variable_definitions_for(metadata),
        description=fetched.get("description") or record.get("description"),
        version=fetched.get("id") or version,
        is_active=True,
        is_latest=is_latest,
        created_at=None,
        updated_at=None,
    )


@router.get("/{prompt_key}/{prompt_type}/variables")
def get_prompt_variable_schema(
    prompt_key: str,
    prompt_type: str,
    request: Request,
) -> dict:
    """Merged variable schema: Phoenix metadata + StepInputs introspection."""
    client = _get_client(request)
    name, role = _split_key(prompt_key, prompt_type)
    del role  # roles share inputs (one StepInputs per step)

    record = _phoenix_prompt_metadata(client, name)
    metadata = _normalise_metadata(record.get("metadata"))
    raw_defs = metadata.get("variable_definitions")
    db_defs: Dict[str, Dict[str, Any]] = (
        raw_defs if isinstance(raw_defs, dict) else {}
    )

    # Phase E: code-side variable shape comes from the step's
    # ``StepInputs`` class (one per step, shared across system/user
    # messages). Walk the introspection registry to find a step whose
    # snake_case name matches the bare prompt name.
    inputs_cls = _find_step_inputs_for(name, request)
    code_fields: Dict[str, Dict[str, Any]] = {}
    code_cls_name: Optional[str] = None
    if inputs_cls is not None:
        code_cls_name = inputs_cls.__name__
        for field_name, field_info in inputs_cls.model_fields.items():
            annotation = field_info.annotation
            type_name = getattr(annotation, "__name__", str(annotation))
            code_fields[field_name] = {
                "type": type_name,
                "description": field_info.description or "",
                "required": field_info.is_required(),
                "has_default": (
                    field_info.default is not None
                    or field_info.default_factory is not None
                ),
            }

    all_names = set(db_defs.keys()) | set(code_fields.keys())
    fields: List[Dict[str, Any]] = []
    for field_name in sorted(all_names):
        in_db = field_name in db_defs
        in_code = field_name in code_fields
        if in_db and in_code:
            source = "both"
        elif in_db:
            source = "db"
        else:
            source = "code"
        if in_db:
            f_type = db_defs[field_name].get("type", "str")
            f_desc = db_defs[field_name].get("description", "")
            f_auto = db_defs[field_name].get("auto_generate", "")
        else:
            f_type = code_fields[field_name]["type"]
            f_desc = code_fields[field_name]["description"]
            f_auto = ""
        f_required = code_fields[field_name]["required"] if in_code else True
        f_has_default = code_fields[field_name]["has_default"] if in_code else False
        fields.append({
            "name": field_name,
            "type": f_type,
            "description": f_desc,
            "required": f_required,
            "has_default": f_has_default,
            "source": source,
            "auto_generate": f_auto,
        })

    return {
        "fields": fields,
        "has_code_class": inputs_cls is not None,
        "code_class_name": code_cls_name,
    }


def _find_step_inputs_for(prompt_name: str, request: Request) -> Optional[type]:
    """Find a registered step's INPUTS class whose snake_case step name
    matches ``prompt_name``. Returns the StepInputs subclass or None.
    """
    from llm_pipeline.naming import to_snake_case

    registry: Dict[str, Any] = getattr(
        request.app.state, "introspection_registry", {},
    ) or {}
    for pipeline_cls in registry.values():
        strategies_cls = getattr(pipeline_cls, "STRATEGIES", None)
        strategy_classes = (
            getattr(strategies_cls, "STRATEGIES", []) if strategies_cls else []
        ) or []
        for strategy_cls in strategy_classes:
            try:
                strategy = strategy_cls()
                bindings = strategy.get_bindings()
            except Exception:
                continue
            for bind in bindings:
                step_cls = getattr(bind, "step", None)
                if step_cls is None:
                    continue
                step_snake = to_snake_case(
                    step_cls.__name__, strip_suffix="Step",
                )
                bound_name = getattr(bind, "prompt_name", None) or step_snake
                if bound_name != prompt_name and step_snake != prompt_name:
                    continue
                inputs_cls = getattr(step_cls, "INPUTS", None)
                if inputs_cls is not None:
                    return inputs_cls
    return None
