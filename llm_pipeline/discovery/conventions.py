"""Convention-based discovery — scans ``llm_pipelines/`` directories.

Walks every convention directory found by
:func:`.loading.find_convention_dirs`, loads each subfolder in
dependency order (:data:`llm_pipeline.discovery.manifest.LOAD_ORDER`),
and registers discovered ``Pipeline`` subclasses into per-pipeline
dicts. The ``_register_enums_constants`` helper handles the *legacy*
auto-generate registry — per-kind walkers populate the new per-kind
registries alongside, without disturbing this path.
"""
from __future__ import annotations

import inspect
import logging
from typing import Any, Callable, Dict, Optional, Tuple, Type

from llm_pipeline.discovery import loading
from llm_pipeline.discovery.loading import (
    _load_subfolder,
    _resolve_package_name,
)
from llm_pipeline.discovery.manifest import LOAD_ORDER, WALKERS_BY_SUBFOLDER
from llm_pipeline.discovery.resolver import make_resolver

if False:  # type-only — no runtime import to avoid circular cost
    from llm_pipeline.specs import ArtifactRegistration  # noqa: F401


__all__ = ["discover_from_convention"]


# Subfolders whose walkers are cst_analysis-aware and benefit
# from the two-pass discovery pattern. Pass 1 populates the
# registries with bare specs (no cross-artifact refs because the
# resolver hook returns None for everything); pass 2 rebuilds
# specs with a resolver that sees every kind populated, filling
# in the refs.
_TWO_PASS_SUBFOLDERS = ("schemas", "tables", "extractions", "reviews", "steps")


def _null_resolver(module_path: str, imported_symbol: str) -> tuple[str, str] | None:
    """Pass-1 resolver — returns None for every lookup."""
    del module_path, imported_symbol
    return None


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
    registries: Optional[Dict[str, Dict[str, "ArtifactRegistration"]]] = None,
) -> Tuple[Dict[str, Callable], Dict[str, Type]]:
    """Find all convention dirs, load modules in order, return merged registries.

    ``strict=False`` (default): per-module import failures are logged
    and the bad module is dropped — UI-boot-friendly.

    ``strict=True``: per-module import failures (including any error
    from ``__init_subclass__`` validators) re-raise with file context.
    Used by ``llm-pipeline build`` so structural validation failures
    are surfaced rather than swallowed.

    ``registries=None`` (default): only the legacy
    ``pipeline_registry`` / ``introspection_registry`` plus the
    ``_AUTO_GENERATE_REGISTRY`` get populated — backward-compatible
    behaviour for existing CLI consumers.

    ``registries=<dict>``: in addition, the per-kind walkers from
    :mod:`.walkers` populate the supplied
    ``app.state.registries`` shape via the two-pass discovery
    pattern. Pass 1 registers each artifact with empty refs;
    pass 2 rebuilds cst_analysis-aware specs (schemas, tables,
    extractions, reviews, steps) with a fully-populated resolver
    so cross-artifact references get captured as ``SymbolRef``s
    on the right spec components.
    """
    # Module-attribute lookup (not local reference) so monkeypatches
    # against ``loading.find_convention_dirs`` are observed at call
    # time. Tests rely on this for stubbing the convention scan.
    dirs = loading.find_convention_dirs(include_package=include_package)
    if not dirs:
        return {}, {}

    all_pipeline_reg: Dict[str, Callable] = {}
    all_introspection_reg: Dict[str, Type] = {}

    # Modules-per-subfolder cache so pass 2 (when registries are
    # supplied) doesn't have to re-load any files. Keyed by
    # subfolder name; values accumulate across all convention
    # dirs.
    modules_by_subfolder: Dict[str, list] = {sf: [] for sf in LOAD_ORDER}

    for base in dirs:
        namespace = f"_llm_pipelines_{base.name}"
        # Detect if this is an importable package (has __init__.py)
        pkg_name = (
            _resolve_package_name(base)
            if (base / "__init__.py").exists() else None
        )
        logger.debug("Scanning convention dir: %s (pkg=%s)", base, pkg_name)

        # Pass 1: load each subfolder + run legacy registration +
        # invoke the per-kind walker (when registries supplied)
        # with the null resolver — bare specs only.
        for subfolder in LOAD_ORDER:
            modules = _load_subfolder(
                base, subfolder, namespace, pkg_name, strict=strict,
            )
            modules_by_subfolder[subfolder].extend(modules)

            # Legacy registration paths (always run):
            if subfolder in ("enums", "constants"):
                _register_enums_constants(modules)
            elif subfolder == "steps":
                # PromptVariables subclasses live alongside their
                # paired step (same file). Discovering them off step
                # modules keeps the 1:1 pairing visible — no separate
                # ``_variables/`` folder, no cross-file imports.
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

            # Per-kind walker pass 1 (null resolver — bare specs):
            if registries is not None:
                for walker in WALKERS_BY_SUBFOLDER.get(subfolder, []):
                    walker.walk(modules, registries, _null_resolver)

    # Pass 2: rebuild cst_analysis-aware specs with a resolver
    # that sees every kind populated. Constants / enums / tools /
    # pipelines walkers are unaffected by the resolver (they
    # don't consult cst_analysis), so we skip them here.
    if registries is not None:
        full_resolver = make_resolver(registries)
        for subfolder in _TWO_PASS_SUBFOLDERS:
            modules = modules_by_subfolder.get(subfolder, [])
            if not modules:
                continue
            for walker in WALKERS_BY_SUBFOLDER.get(subfolder, []):
                walker.walk(modules, registries, full_resolver)

    if all_pipeline_reg:
        logger.info(
            "Convention discovery found %d pipeline(s): %s",
            len(all_pipeline_reg),
            ", ".join(sorted(all_pipeline_reg)),
        )

    return all_pipeline_reg, all_introspection_reg
