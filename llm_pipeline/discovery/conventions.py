"""Convention-based discovery — scans ``llm_pipelines/`` directories.

Walks every convention directory found by
:func:`.loading.find_convention_dirs`, loads each subfolder in
dependency order (``_LOAD_ORDER``), and registers discovered
``Pipeline`` subclasses into per-pipeline dicts. The
``_register_enums_constants`` helper handles the *legacy*
auto-generate registry — Phase C.2.b's per-kind walkers will
populate the new per-kind registries alongside, without disturbing
this path.
"""
from __future__ import annotations

import inspect
import logging
from typing import Any, Callable, Dict, Optional, Tuple, Type

from llm_pipeline.discovery import loading
from llm_pipeline.discovery.loading import (
    _LOAD_ORDER,
    _load_subfolder,
    _resolve_package_name,
)


__all__ = ["discover_from_convention"]


logger = logging.getLogger(__name__)


def _register_enums_constants(modules) -> None:
    """Auto-register Enum subclasses from ``enums/`` and simple constants from ``constants/``.

    Legacy path — registers into the global ``_AUTO_GENERATE_REGISTRY``
    used by prompt-rendering's auto_generate expressions. The
    per-kind walkers added in Phase C.2.b will populate
    ``app.state.registries[KIND_ENUM]`` and
    ``app.state.registries[KIND_CONSTANT]`` *alongside* this, not
    in place of it (until the legacy registry is migrated cleanly).
    """
    from enum import Enum

    from llm_pipeline.prompts.variables import register_auto_generate

    for mod in modules:
        for name, obj in inspect.getmembers(mod):
            if name.startswith("_"):
                continue
            # Only register Enum subclasses defined in this module
            if (
                inspect.isclass(obj)
                and obj.__module__ == mod.__name__
                and issubclass(obj, Enum)
            ):
                register_auto_generate(name, obj)
            # Register simple constants (str, int, float, dict, list)
            elif isinstance(obj, (str, int, float, dict, list)):
                register_auto_generate(name, obj)


def _discover_pipelines_from_modules(
    modules,
    default_model: Optional[str],
    engine: Any,
) -> Tuple[Dict[str, Type], Dict[str, Type]]:
    """Scan loaded modules for graph ``Pipeline`` subclasses, build registries."""
    del default_model, engine  # graph pipelines don't use either at registration time
    from llm_pipeline.graph import Pipeline
    from llm_pipeline.naming import to_snake_case

    pipeline_reg: Dict[str, Type] = {}
    introspection_reg: Dict[str, Type] = {}

    for mod in modules:
        for _, cls in inspect.getmembers(mod, inspect.isclass):
            if (
                issubclass(cls, Pipeline)
                and cls is not Pipeline
                and not inspect.isabstract(cls)
                and cls.__module__ == mod.__name__
            ):
                key = to_snake_case(cls.__name__, strip_suffix="Pipeline")
                pipeline_reg[key] = cls
                introspection_reg[key] = cls

    return pipeline_reg, introspection_reg


def discover_from_convention(
    engine: Any,
    default_model: Optional[str],
    include_package: bool = True,
    *,
    strict: bool = False,
) -> Tuple[Dict[str, Callable], Dict[str, Type]]:
    """Find all convention dirs, load modules in order, return merged registries.

    ``strict=False`` (default): per-module import failures are logged
    and the bad module is dropped — UI-boot-friendly.

    ``strict=True``: per-module import failures (including any error
    from ``__init_subclass__`` validators) re-raise with file context.
    Used by ``llm-pipeline build`` so structural validation failures
    are surfaced rather than swallowed.
    """
    # Module-attribute lookup (not local reference) so monkeypatches
    # against ``loading.find_convention_dirs`` are observed at call
    # time. Tests rely on this for stubbing the convention scan.
    dirs = loading.find_convention_dirs(include_package=include_package)
    if not dirs:
        return {}, {}

    all_pipeline_reg: Dict[str, Callable] = {}
    all_introspection_reg: Dict[str, Type] = {}

    for base in dirs:
        namespace = f"_llm_pipelines_{base.name}"
        # Detect if this is an importable package (has __init__.py)
        pkg_name = (
            _resolve_package_name(base)
            if (base / "__init__.py").exists() else None
        )
        logger.debug("Scanning convention dir: %s (pkg=%s)", base, pkg_name)

        # Load in dependency order
        for subfolder in _LOAD_ORDER:
            modules = _load_subfolder(
                base, subfolder, namespace, pkg_name, strict=strict,
            )

            if subfolder in ("enums", "constants"):
                _register_enums_constants(modules)
            elif subfolder == "_variables":
                from llm_pipeline.prompts.discovery import (
                    discover_prompt_variables,
                )
                discover_prompt_variables(modules)
            elif subfolder == "pipelines":
                p_reg, i_reg = _discover_pipelines_from_modules(
                    modules, default_model, engine,
                )
                all_pipeline_reg.update(p_reg)
                all_introspection_reg.update(i_reg)

    if all_pipeline_reg:
        logger.info(
            "Convention discovery found %d pipeline(s): %s",
            len(all_pipeline_reg),
            ", ".join(sorted(all_pipeline_reg)),
        )

    return all_pipeline_reg, all_introspection_reg
