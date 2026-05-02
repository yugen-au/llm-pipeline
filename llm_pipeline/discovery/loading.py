"""File / module loading primitives for convention-based discovery.

The lower layer of :mod:`llm_pipeline.discovery`. Walks the
filesystem to find ``llm_pipelines/`` directories, then imports
the ``.py`` files inside each subfolder in dependency order.

Strict / lenient modes apply at the per-file level:

- **Lenient** (default): per-module failures (import errors,
  ``__init_subclass__`` validators that still raise, etc.) are
  logged as warnings and the bad module is dropped from the
  returned list. UI-boot-friendly — one broken file shouldn't
  take the whole UI down.
- **Strict**: per-module failures re-raise with file-path context.
  Used by ``llm-pipeline build`` so structural validation
  failures surface rather than silently drop a pipeline.

The subfolder load order is owned by
:data:`llm_pipeline.discovery.manifest.LOAD_ORDER` (derived from
the per-kind manifest). The ``_LOAD_ORDER`` re-export here is a
back-compat alias for callers that already import from this
module.
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import os
from pathlib import Path
from types import ModuleType

# Back-compat alias — the load order is owned by the manifest.
from llm_pipeline.discovery.manifest import LOAD_ORDER as _LOAD_ORDER


__all__ = [
    "_LOAD_ORDER",
    "_SKIP_DIRS",
    "_SKIP_PREFIXES",
    "_load_subfolder",
    "_resolve_package_name",
    "find_convention_dirs",
    "load_convention_module",
]


logger = logging.getLogger(__name__)


_SKIP_PREFIXES = (".", "_", "node_modules")
_SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "site-packages", "dist", "build"}


def _resolve_package_name(directory: Path) -> str:
    """Walk up from directory to find the full dotted package name.

    e.g. ``/project/logistics_intelligence/llm_pipelines/`` ->
    ``"logistics_intelligence.llm_pipelines"``. Stops when a parent
    no longer has ``__init__.py``.
    """
    parts = [directory.name]
    current = directory.parent
    while (current / "__init__.py").exists() and current != current.parent:
        parts.append(current.name)
        current = current.parent
    parts.reverse()
    return ".".join(parts)


def find_convention_dirs(include_package: bool = True) -> list[Path]:
    """Find all ``llm_pipelines/`` directories to scan.

    Args:
        include_package: If False, skip the package-internal dir (demo).

    Returns directories in priority order (later overrides earlier):

    1. Package-internal: sibling to ``llm_pipeline/`` package (if include_package)
    2. All ``llm_pipelines/`` dirs found under CWD (any depth), excluding
       dot-prefixed, underscore-prefixed, and common non-source dirs.
    """
    dirs: list[Path] = []

    # 1. Package-internal (sibling to this package)
    pkg_dir = Path(__file__).resolve().parent.parent.parent / "llm_pipelines"
    if include_package and pkg_dir.is_dir():
        dirs.append(pkg_dir)
    pkg_resolved = pkg_dir.resolve() if pkg_dir.is_dir() else None

    # 2. Recursive scan from CWD
    cwd = Path.cwd()
    for root, subdirs, _files in os.walk(cwd):
        # Prune dirs we shouldn't descend into
        subdirs[:] = [
            d for d in subdirs
            if not any(d.startswith(p) for p in _SKIP_PREFIXES)
            and d not in _SKIP_DIRS
        ]
        root_path = Path(root)
        if root_path.name == "llm_pipelines" and (root_path / "__init__.py").exists():
            resolved = root_path.resolve()
            if resolved != pkg_resolved:
                dirs.append(root_path)

    return dirs


def load_convention_module(filepath: Path, synthetic_name: str) -> ModuleType:
    """Import a ``.py`` file via ``spec_from_file_location`` with a synthetic name."""
    spec = importlib.util.spec_from_file_location(synthetic_name, filepath)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create module spec for {filepath}")
    mod = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[synthetic_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_subfolder(
    base: Path,
    subfolder: str,
    namespace: str,
    pkg_name: str | None,
    *,
    strict: bool = False,
) -> list[ModuleType]:
    """Import all ``.py`` files in ``base/subfolder/``; return loaded modules.

    If ``pkg_name`` is set (e.g. ``"llm_pipelines"``), use normal
    ``importlib`` to avoid duplicate module registration. Falls back
    to ``spec_from_file_location`` for loose convention dirs.

    Lenient mode (``strict=False``, default): per-module failures are
    logged as warnings and the bad module is dropped. Suitable for UI
    boot — one broken pipeline shouldn't take the whole UI down.

    Strict mode (``strict=True``): per-module failures re-raise with
    file-path context attached, so the caller surfaces them. Used by
    ``llm-pipeline build`` where any structural validation failure
    (e.g. an ``__init_subclass__`` validator rejecting a node) must
    fail the build, not silently drop the pipeline.
    """
    folder = base / subfolder
    if not folder.is_dir():
        return []

    modules = []
    for py_file in sorted(folder.glob("*.py")):
        if py_file.name == "__init__.py":
            continue
        stem = py_file.stem
        # Try normal import first if this is a proper package.
        # NB: we only catch ImportError here, since a successful import
        # may legitimately raise (e.g. __init_subclass__ validators).
        # Those bubble up to the strict/lenient branch below.
        if pkg_name:
            dotted = f"{pkg_name}.{subfolder}.{stem}"
            try:
                mod = importlib.import_module(dotted)
                modules.append(mod)
                continue
            except ImportError:
                # Fall through to the spec_from_file_location path.
                pass
            except Exception:
                if strict:
                    raise
                logger.warning(
                    "Failed to load %s, skipping",
                    py_file, exc_info=True,
                )
                continue
        # Fallback: file-based import with synthetic name.
        syn_name = f"{namespace}.{subfolder}.{stem}"
        try:
            mod = load_convention_module(py_file, syn_name)
            modules.append(mod)
        except Exception:
            if strict:
                raise
            logger.warning(
                "Failed to load %s, skipping", py_file, exc_info=True,
            )
    return modules
