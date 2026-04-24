"""Ambient pipeline runtime context.

``PipelineContext`` is the single typed container of framework-provided
fixtures (session, logger, run_id, event_emitter) passed to every
step method, every tool ``run()``, and every resource ``build()``.

Why a single type:

* steps, tools, and resources all need the same ambient values
  (session for DB access, logger for diagnostics, run_id for
  correlation); three parallel context types would be pure
  duplication
* code migrating across those surfaces can be moved without
  rewriting ambient access patterns
* sandbox pipelines construct the same context shape as production,
  so no behavioural drift between the two

The optional ``step_name`` / ``tool_name`` fields are populated by the
framework when the context is handed to the corresponding surface.
They are available for logging and event emission but are not load-
bearing for business logic — step/tool identity is already known
statically from the class that receives the context.

Name clash note:

``llm_pipeline.context.PipelineContext`` is the *old* "step output
context" concept which is being removed as part of the adapter
refactor (the ``context=`` kwarg on ``@step_definition`` was dropped
in an earlier commit). The old class is retained only while legacy
tests are migrated. Once those land on the new contract the old
symbol will be deleted and this module's ``PipelineContext`` can be
re-exported from ``context`` for a single canonical import path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from logging import Logger

    from sqlalchemy.orm import Session


__all__ = ["PipelineContext"]


@dataclass(frozen=True)
class PipelineContext:
    """Ambient fixtures available to steps, tools, and resources.

    Framework-owned. Not extended by user code — domain-specific values
    flow via ``StepInputs`` / ``Tool.Inputs`` / ``Resource.Inputs``.
    """

    session: "Session"
    logger: "Logger"
    run_id: str
    event_emitter: Any | None = None
    step_name: str | None = None
    tool_name: str | None = None
