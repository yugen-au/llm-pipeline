"""Explicit-module pipeline discovery.

Imports caller-supplied dotted module paths and registers their
``Pipeline`` subclasses. The CLI's ``--pipelines my_app.pipelines.x``
flag plumbs into here. Always strict — typos in the flag fail
loudly so users notice immediately.
"""
from __future__ import annotations

import importlib
import inspect
import logging
from typing import Dict, List, Tuple, Type


__all__ = ["discover_from_modules"]


logger = logging.getLogger(__name__)


def discover_from_modules(
    module_paths: List[str],
) -> Tuple[Dict[str, Type], Dict[str, Type]]:
    """Import ``module_paths`` and register their ``Pipeline`` subclasses.

    Each path is a dotted Python module path (e.g.
    ``my_app.pipelines.x``). The module is imported eagerly; any
    concrete ``Pipeline`` subclasses defined directly in the module
    are registered under their snake-cased name (with the ``Pipeline``
    suffix stripped).

    Raises:
        ``ValueError`` if a module can't be imported or has no
        ``Pipeline`` subclasses (caller error — strict by design so
        typos in the ``--pipelines`` flag fail loudly).

    Returns ``(pipeline_registry, introspection_registry)``; both
    dicts map snake-cased name to the ``Pipeline`` subclass.
    """
    from llm_pipeline.graph import Pipeline
    from llm_pipeline.naming import to_snake_case

    pipeline_reg: Dict[str, Type] = {}
    introspection_reg: Dict[str, Type] = {}

    for path in module_paths:
        try:
            mod = importlib.import_module(path)
        except ImportError as exc:
            raise ValueError(
                f"Failed to import pipeline module '{path}': {exc}"
            ) from exc

        members = inspect.getmembers(mod, inspect.isclass)
        found = [
            cls
            for _, cls in members
            if issubclass(cls, Pipeline)
            and cls is not Pipeline
            and not inspect.isabstract(cls)
            and cls.__module__ == mod.__name__
        ]

        if not found:
            raise ValueError(
                f"No Pipeline subclasses found in module '{path}'"
            )

        for cls in found:
            key = to_snake_case(cls.__name__, strip_suffix="Pipeline")
            pipeline_reg[key] = cls
            introspection_reg[key] = cls

    if pipeline_reg:
        logger.info(
            "Loaded %d pipeline(s) from modules: %s",
            len(pipeline_reg),
            ", ".join(sorted(pipeline_reg)),
        )

    return pipeline_reg, introspection_reg
