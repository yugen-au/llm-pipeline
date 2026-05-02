"""``ArtifactTemplate`` — per-kind Jinja template wrapper.

Each kind ships a ``TEMPLATE = ArtifactTemplate(template=...)``
constant declaring the file layout. The Writer's :meth:`write`
calls ``TEMPLATE.render(spec=self.spec, ...)`` to produce the full
file source.

The default Jinja environment registers each renderer in
:mod:`llm_pipeline.artifacts.base.renderers` as a filter — so
templates can do ``{{ block | render_import }}`` etc.

Jinja2 is an optional dependency (``[creator]`` extra). The import
is lazy so read-only callers don't pay the cost.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import jinja2


__all__ = ["ArtifactTemplate", "default_jinja_env"]


_DEFAULT_ENV: "jinja2.Environment | None" = None


def default_jinja_env() -> "jinja2.Environment":
    """Lazily build a Jinja environment with renderer filters registered.

    Cached on first call. The environment uses ``trim_blocks`` and
    ``lstrip_blocks`` so templates can use ``{% ... %}`` blocks
    without leaving extra whitespace in the output.
    """
    global _DEFAULT_ENV
    if _DEFAULT_ENV is not None:
        return _DEFAULT_ENV

    import jinja2

    from llm_pipeline.artifacts.base import renderers as _renderers

    env = jinja2.Environment(
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
    )
    env.filters["render_artifact_ref"] = _renderers.render_artifact_ref
    env.filters["render_code_body"] = _renderers.render_code_body
    env.filters["render_import"] = _renderers.render_import
    env.filters["render_pydantic_class"] = _renderers.render_pydantic_class
    env.filters["schema_to_annotation"] = _renderers.schema_to_annotation
    _DEFAULT_ENV = env
    return env


class ArtifactTemplate:
    """Per-kind Jinja template wrapper.

    Holds a compiled Jinja template plus a small helper for rendering
    against a spec. Pass ``env`` to override the default environment
    (for tests, or to register kind-specific filters).
    """

    __slots__ = ("_template",)

    def __init__(
        self,
        *,
        template: str,
        env: "jinja2.Environment | None" = None,
    ) -> None:
        environment = env or default_jinja_env()
        self._template = environment.from_string(template)

    def render(self, **context: Any) -> str:
        """Render the template against ``**context``.

        Per-kind writers typically pass ``spec=self.spec`` plus any
        kind-specific extras (derived class names, prefixes, etc.).
        Returns the full source text.
        """
        return self._template.render(**context)
