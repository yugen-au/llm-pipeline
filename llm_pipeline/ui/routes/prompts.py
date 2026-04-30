"""Prompts route module — Phoenix passthrough.

Every ``/api/prompts/*`` endpoint proxies to Phoenix's ``/v1/prompts``
REST surface. One Phoenix prompt = one ``Prompt`` record on the wire,
carrying both ``system`` and ``user`` messages — same shape as
Phoenix's native CHAT template.
"""
from __future__ import annotations

import logging
import re
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel

from llm_pipeline.prompts.models import Prompt, PromptMessage, PromptMetadata
from llm_pipeline.prompts.phoenix_client import (
    PhoenixError,
    PhoenixNotConfiguredError,
    PhoenixPromptClient,
    PhoenixUnavailableError,
    PromptNotFoundError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prompts", tags=["prompts"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class PromptListResponse(BaseModel):
    items: List[Prompt]
    total: int
    offset: int
    limit: int


class PromptListParams(BaseModel):
    category: Optional[str] = None
    step_name: Optional[str] = None
    offset: int = Query(default=0, ge=0)
    limit: int = Query(default=50, ge=1, le=200)


# ---------------------------------------------------------------------------
# Phoenix <-> canonical model mapping
# ---------------------------------------------------------------------------


_NAME_INVALID_RE = re.compile(r"[^a-z0-9_-]+")
_SYSTEM_ROLES = frozenset({"system", "developer"})


def _sanitise_name(raw: str) -> str:
    s = raw.lower()
    s = _NAME_INVALID_RE.sub("_", s)
    s = re.sub(r"_+", "_", s).strip("_-")
    if not s:
        raise HTTPException(status_code=422, detail=f"Invalid prompt name {raw!r}")
    return s


def _get_client(request: Request) -> PhoenixPromptClient:
    """Resolve a per-app Phoenix client (cached on app.state)."""
    cached = getattr(request.app.state, "_phoenix_prompt_client", None)
    if cached is not None:
        return cached
    try:
        client = PhoenixPromptClient()
    except PhoenixNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    request.app.state._phoenix_prompt_client = client
    return client


def _extract_messages(version: Dict[str, Any]) -> List[PromptMessage]:
    """Pull messages out of a Phoenix version's CHAT/STR template."""
    template = version.get("template") or {}
    template_type = template.get("type")
    if template_type == "string":
        body = template.get("template")
        if isinstance(body, str):
            return [PromptMessage(role="system", content=body)]
        return []
    if template_type != "chat":
        return []
    out: List[PromptMessage] = []
    for msg in template.get("messages") or []:
        role = msg.get("role")
        content = msg.get("content")
        if isinstance(content, list):
            content = "".join(
                p.get("text", "")
                for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            )
        if not isinstance(content, str):
            continue
        ui_role = "system" if role in _SYSTEM_ROLES else "user" if role == "user" else None
        if ui_role is None:
            continue
        out.append(PromptMessage(role=ui_role, content=content))
    return out


def _record_metadata(record: Dict[str, Any]) -> Dict[str, Any]:
    md = record.get("metadata")
    return md if isinstance(md, dict) else {}


def _phoenix_to_prompt(
    record: Dict[str, Any], version: Dict[str, Any],
) -> Prompt:
    """Build a canonical ``Prompt`` from Phoenix record + version."""
    raw_meta = _record_metadata(record)
    metadata = PromptMetadata.model_validate(raw_meta)
    return Prompt(
        name=record.get("name") or "",
        description=version.get("description") or record.get("description"),
        metadata=metadata,
        messages=_extract_messages(version),
        version_id=version.get("id"),
    )


def _prompt_to_phoenix_payloads(
    payload: Prompt,
    *,
    base_version: Optional[Dict[str, Any]] = None,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Map a ``Prompt`` write payload onto Phoenix's ``prompt`` + ``version`` shapes.

    ``base_version`` carries forward model + invocation params + any
    response_format / tools settings on updates so we don't lose them
    when only messages change.
    """
    name = _sanitise_name(payload.name)
    metadata: Dict[str, Any] = payload.metadata.model_dump(exclude_none=True)
    metadata.setdefault("managed_by", "llm-pipeline")

    prompt_data: Dict[str, Any] = {"name": name, "metadata": metadata}
    if payload.description is not None:
        prompt_data["description"] = payload.description

    base = base_version or {}
    messages = [
        {"role": m.role, "content": m.content} for m in payload.messages
    ]
    messages.sort(key=lambda m: 0 if m["role"] == "system" else 1)
    version_data: Dict[str, Any] = {
        "model_provider": base.get("model_provider", "OPENAI"),
        "model_name": base.get("model_name", "gpt-4o-mini"),
        "template": {"type": "chat", "messages": messages},
        "template_type": "CHAT",
        "template_format": base.get("template_format", "F_STRING"),
        "invocation_parameters": base.get(
            "invocation_parameters", {"type": "openai", "openai": {}},
        ),
    }
    if payload.description is not None:
        version_data["description"] = payload.description
    if base.get("response_format") is not None:
        version_data["response_format"] = base["response_format"]
    if base.get("tools") is not None:
        version_data["tools"] = base["tools"]
    return prompt_data, version_data


def _tag_production(client: PhoenixPromptClient, version: Dict[str, Any]) -> None:
    version_id = version.get("id")
    if not version_id:
        return
    try:
        client.add_tag(version_id, "production", description="UI save")
    except PhoenixError as exc:
        logger.warning("Phoenix tag failed for version %s: %s", version_id, exc)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=PromptListResponse)
def list_prompts(
    request: Request,
    params: Annotated[PromptListParams, Depends()],
) -> PromptListResponse:
    """Paginated list — one row per Phoenix prompt."""
    client = _get_client(request)

    items: List[Prompt] = []
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
            try:
                version = client.get_latest(name)
            except (PromptNotFoundError, PhoenixUnavailableError):
                continue
            items.append(_phoenix_to_prompt(record, version))
        cursor = page.get("next_cursor")
        if not cursor:
            break

    if params.category is not None:
        items = [p for p in items if p.metadata.category == params.category]
    if params.step_name is not None:
        items = [p for p in items if p.metadata.step_name == params.step_name]

    items.sort(key=lambda p: p.name)
    total = len(items)
    sliced = items[params.offset : params.offset + params.limit]
    return PromptListResponse(
        items=sliced, total=total, offset=params.offset, limit=params.limit,
    )


@router.get("/{name}", response_model=Prompt)
def get_prompt(name: str, request: Request) -> Prompt:
    client = _get_client(request)
    sanitised = _sanitise_name(name)
    try:
        version = client.get_latest(sanitised)
    except PromptNotFoundError:
        raise HTTPException(status_code=404, detail="Prompt not found")
    except PhoenixUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    record = _find_record(client, sanitised)
    if record is None:
        record = {"name": sanitised}
    return _phoenix_to_prompt(record, version)


@router.post("", response_model=Prompt, status_code=201)
def create_prompt(body: Prompt, request: Request) -> Prompt:
    """Create a new prompt or push a new version under an existing name.

    Phoenix versions are append-only; if ``name`` already exists this
    creates a new version with the supplied ``messages`` array. Prompt-
    level metadata is set-once on first POST and ignored on subsequent
    versions (Phoenix behavior).
    """
    client = _get_client(request)

    try:
        existing_version = client.get_latest(_sanitise_name(body.name))
    except PromptNotFoundError:
        existing_version = None
    except PhoenixUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    prompt_data, version_data = _prompt_to_phoenix_payloads(
        body, base_version=existing_version,
    )

    try:
        new_version = client.create(prompt=prompt_data, version=version_data)
    except PhoenixUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    _tag_production(client, new_version)

    record = _find_record(client, prompt_data["name"]) or prompt_data
    return _phoenix_to_prompt(record, new_version)


@router.put("/{name}", response_model=Prompt)
def update_prompt(name: str, body: Prompt, request: Request) -> Prompt:
    """Replace the prompt's messages array atomically.

    Phoenix prompt-level metadata is set-once: subsequent updates can
    only change the version's content (messages, description, etc.).
    """
    client = _get_client(request)
    sanitised = _sanitise_name(name)
    try:
        existing_version = client.get_latest(sanitised)
    except PromptNotFoundError:
        raise HTTPException(status_code=404, detail="Prompt not found")
    except PhoenixUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    payload = body.model_copy(update={"name": sanitised})
    prompt_data, version_data = _prompt_to_phoenix_payloads(
        payload, base_version=existing_version,
    )

    try:
        new_version = client.create(prompt=prompt_data, version=version_data)
    except PhoenixUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    _tag_production(client, new_version)

    record = _find_record(client, sanitised) or prompt_data
    return _phoenix_to_prompt(record, new_version)


@router.delete("/{name}", status_code=204)
def delete_prompt(name: str, request: Request) -> Response:
    client = _get_client(request)
    sanitised = _sanitise_name(name)
    try:
        client.delete(sanitised)
    except PromptNotFoundError:
        raise HTTPException(status_code=404, detail="Prompt not found")
    except PhoenixUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Variable schema
# ---------------------------------------------------------------------------


@router.get("/{name}/variables")
def get_prompt_variable_schema(name: str, request: Request) -> dict:
    """Merged variable schema: Phoenix metadata + StepInputs introspection."""
    client = _get_client(request)
    sanitised = _sanitise_name(name)

    record = _find_record(client, sanitised) or {}
    metadata = _record_metadata(record)
    raw_defs = metadata.get("variable_definitions")
    db_defs: Dict[str, Dict[str, Any]] = (
        raw_defs if isinstance(raw_defs, dict) else {}
    )

    inputs_cls = _find_step_inputs_for(sanitised, request)
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


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _find_record(
    client: PhoenixPromptClient, name: str,
) -> Optional[Dict[str, Any]]:
    """Look up a prompt record by walking the list endpoint.

    Phoenix's prompt-detail endpoints return ``PromptVersion`` (no
    prompt-level metadata), so we list-and-filter. Cached briefly via
    ``client._prompt_record_cache``.
    """
    cache: Dict[str, Dict[str, Any]] = getattr(
        client, "_prompt_record_cache", {},
    )
    if name in cache:
        return cache[name]
    cursor = None
    while True:
        try:
            page = client.list_prompts(limit=200, cursor=cursor)
        except PhoenixUnavailableError:
            return None
        for record in page.get("data") or []:
            record_name = record.get("name")
            if isinstance(record_name, str):
                cache[record_name] = record
        cursor = page.get("next_cursor")
        if not cursor:
            break
    client._prompt_record_cache = cache  # type: ignore[attr-defined]
    return cache.get(name)


def _find_step_inputs_for(prompt_name: str, request: Request) -> Optional[type]:
    """Find a registered step's INPUTS class whose snake_case name matches."""
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
