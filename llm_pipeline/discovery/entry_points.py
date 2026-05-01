"""Entry-point-based pipeline discovery.

Loads pipelines registered under the ``llm_pipeline.pipelines``
entry-point group. Used for demo pipelines bundled with the
package; production deployments typically rely on convention dirs
under :mod:`.conventions`.
"""
from __future__ import annotations

import importlib.metadata
import inspect
import logging
from typing import Dict, Tuple, Type


__all__ = ["discover_from_entry_points"]


logger = logging.getLogger(__name__)


def discover_from_entry_points(
    *, strict: bool = False,
) -> Tuple[Dict[str, Type], Dict[str, Type]]:
    """Load pipelines registered under ``llm_pipeline.pipelines`` entry points.

    Used for demo pipelines bundled with the package (e.g.
    ``text_analyzer``). Each entry point must reference a concrete
    ``Pipeline`` subclass.

    ``strict=False`` (default): per-entry-point failures are logged
    and skipped — one bad entry point doesn't poison the registry.
    Suitable for UI boot.

    ``strict=True``: per-entry-point failures re-raise. Entry points
    that don't reference a ``Pipeline`` subclass also raise. Used by
    ``llm-pipeline build``.

    Returns ``(pipeline_registry, introspection_registry)``; both
    dicts map ``ep.name`` to the ``Pipeline`` subclass.
    """
    from llm_pipeline.graph import Pipeline

    pipeline_reg: Dict[str, Type] = {}
    introspection_reg: Dict[str, Type] = {}

    eps = importlib.metadata.entry_points(group="llm_pipeline.pipelines")
    for ep in eps:
        try:
            cls = ep.load()
        except Exception as exc:
            if strict:
                raise RuntimeError(
                    f"Failed to load entry point {ep.name!r}: {exc}"
                ) from exc
            logger.warning(
                "Failed to load entry point '%s', skipping",
                ep.name,
                exc_info=True,
            )
            continue

        if not (inspect.isclass(cls) and issubclass(cls, Pipeline)):
            if strict:
                raise TypeError(
                    f"Entry point {ep.name!r} does not reference a "
                    f"Pipeline (graph) subclass; got {cls!r}."
                )
            logger.warning(
                "Entry point '%s' does not reference a Pipeline "
                "(graph) subclass, skipping",
                ep.name,
            )
            continue
        pipeline_reg[ep.name] = cls
        introspection_reg[ep.name] = cls

    if pipeline_reg:
        logger.info(
            "Discovered %d pipeline(s) via entry points: %s",
            len(pipeline_reg),
            ", ".join(sorted(pipeline_reg)),
        )

    return pipeline_reg, introspection_reg
