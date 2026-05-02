"""``ToolSpec`` — pydantic-ai agent tools.

Tools are Level 3 artifacts. Each ``tools/foo.py`` declares a
tool function (or a tool class — TBD which the convention settles
on) that's bound to step agents via ``DEFAULT_TOOLS``. Today's
tools register manually via ``register_agent``; the per-artifact
discovery walker (Phase C.2) replaces that with structural
registration.

The shape carried here is a Phase C.1 *skeleton* — Inputs / Args /
body — and may grow as we learn how tools should expose their
internals to the UI. The minimum to make tool refs from a step's
``tools`` list (``list[ArtifactRef]``) resolvable is the ``name``
and ``cls`` fields inherited from :class:`ArtifactSpec`; the
optional fields below let the UI render input forms when present.
"""
from __future__ import annotations

from typing import Literal

from llm_pipeline.specs.base import ArtifactSpec
from llm_pipeline.specs.blocks import CodeBodySpec, JsonSchemaWithRefs
from llm_pipeline.specs.kinds import KIND_TOOL


__all__ = ["ToolSpec"]


class ToolSpec(ArtifactSpec):
    """A pydantic-ai agent tool declared in ``llm_pipelines/tools/``.

    Phase C.1 skeleton — fields below are likely to evolve as the
    actual tool-discovery walker is built in Phase C.2.
    """

    kind: Literal[KIND_TOOL] = KIND_TOOL  # type: ignore[assignment]

    # Pydantic Inputs class shape — what the agent passes the tool.
    inputs: JsonSchemaWithRefs | None = None

    # Pydantic Args class shape — arguments the tool function
    # itself receives (distinct from agent-supplied Inputs in
    # pydantic-ai's tool model).
    args: JsonSchemaWithRefs | None = None

    # Tool-callable body. ``None`` for tools whose body is
    # framework-internal (rare). Editable in the UI when set.
    body: CodeBodySpec | None = None
