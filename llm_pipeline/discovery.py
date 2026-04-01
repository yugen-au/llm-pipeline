"""Convention-based directory discovery for llm_pipelines/.

Scans for llm_pipelines/ directories (package-internal + CWD),
imports Python files in each subfolder in dependency order,
and registers discovered PipelineConfig subclasses.
"""
import importlib.util
import inspect
import logging
import os
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, Optional, Tuple, Type

logger = logging.getLogger(__name__)

# Subfolder load order (dependencies first)
_LOAD_ORDER = [
    "enums",
    "constants",
    "schemas",
    "extractions",
    "tools",
    "steps",
    "pipelines",
]


def _resolve_package_name(directory: Path) -> str:
    """Walk up from directory to find the full dotted package name.

    e.g. /project/logistics_intelligence/llm_pipelines/ -> "logistics_intelligence.llm_pipelines"
    Stops when a parent no longer has __init__.py.
    """
    parts = [directory.name]
    current = directory.parent
    while (current / "__init__.py").exists() and current != current.parent:
        parts.append(current.name)
        current = current.parent
    parts.reverse()
    return ".".join(parts)


_SKIP_PREFIXES = (".", "_", "node_modules")
_SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "site-packages", "dist", "build"}


def find_convention_dirs(include_package: bool = True) -> list[Path]:
    """Find all llm_pipelines/ directories to scan.

    Args:
        include_package: If False, skip the package-internal dir (demo).

    Returns directories in priority order (later overrides earlier):
    1. Package-internal: sibling to llm_pipeline/ package (if include_package)
    2. All llm_pipelines/ dirs found under CWD (any depth), excluding
       dot-prefixed, underscore-prefixed, and common non-source dirs.
    """
    dirs: list[Path] = []

    # 1. Package-internal (sibling to this package)
    pkg_dir = Path(__file__).resolve().parent.parent / "llm_pipelines"
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
    """Import a .py file via spec_from_file_location with a synthetic name."""
    spec = importlib.util.spec_from_file_location(synthetic_name, filepath)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create module spec for {filepath}")
    mod = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[synthetic_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_subfolder(
    base: Path, subfolder: str, namespace: str, pkg_name: str | None,
) -> list[ModuleType]:
    """Import all .py files in base/subfolder/, return loaded modules.

    If pkg_name is set (e.g. 'llm_pipelines'), use normal importlib to
    avoid duplicate module registration. Falls back to spec_from_file_location.
    """
    folder = base / subfolder
    if not folder.is_dir():
        return []

    modules = []
    for py_file in sorted(folder.glob("*.py")):
        if py_file.name == "__init__.py":
            continue
        stem = py_file.stem
        # Try normal import first if this is a proper package
        if pkg_name:
            dotted = f"{pkg_name}.{subfolder}.{stem}"
            try:
                import importlib
                mod = importlib.import_module(dotted)
                modules.append(mod)
                continue
            except ImportError:
                pass
        # Fallback: file-based import with synthetic name
        syn_name = f"{namespace}.{subfolder}.{stem}"
        try:
            mod = load_convention_module(py_file, syn_name)
            modules.append(mod)
        except Exception:
            logger.warning(
                "Failed to load %s, skipping", py_file, exc_info=True,
            )
    return modules


def _register_enums_constants(modules: list[ModuleType]) -> None:
    """Auto-register top-level classes/objects from enums/ and constants/."""
    from llm_pipeline.prompts.variables import register_auto_generate

    for mod in modules:
        for name, obj in inspect.getmembers(mod):
            if name.startswith("_"):
                continue
            if inspect.isclass(obj) and obj.__module__ == mod.__name__:
                register_auto_generate(name, obj)


def _discover_pipelines_from_modules(
    modules: list[ModuleType],
    default_model: Optional[str],
    engine: Any,
) -> Tuple[Dict[str, Callable], Dict[str, Type]]:
    """Scan loaded modules for PipelineConfig subclasses, build registries."""
    from llm_pipeline.pipeline import PipelineConfig
    from llm_pipeline.naming import to_snake_case
    from llm_pipeline.ui.app import _make_pipeline_factory

    pipeline_reg: Dict[str, Callable] = {}
    introspection_reg: Dict[str, Type] = {}

    for mod in modules:
        for _, cls in inspect.getmembers(mod, inspect.isclass):
            if (
                issubclass(cls, PipelineConfig)
                and cls is not PipelineConfig
                and not inspect.isabstract(cls)
                and cls.__module__ == mod.__name__
            ):
                key = to_snake_case(cls.__name__, strip_suffix="Pipeline")
                pipeline_reg[key] = _make_pipeline_factory(cls, default_model)
                introspection_reg[key] = cls

                # Seed prompts if method exists
                try:
                    if hasattr(cls, "_seed_prompts") and callable(cls._seed_prompts):
                        cls._seed_prompts(engine)
                except Exception:
                    logger.warning(
                        "_seed_prompts failed for '%s'", key, exc_info=True,
                    )

    return pipeline_reg, introspection_reg


def discover_from_convention(
    engine: Any,
    default_model: Optional[str],
    include_package: bool = True,
) -> Tuple[Dict[str, Callable], Dict[str, Type]]:
    """Find all convention dirs, load modules in order, return merged registries."""
    dirs = find_convention_dirs(include_package=include_package)
    if not dirs:
        return {}, {}

    all_pipeline_reg: Dict[str, Callable] = {}
    all_introspection_reg: Dict[str, Type] = {}

    for base in dirs:
        namespace = f"_llm_pipelines_{base.name}"
        # Detect if this is an importable package (has __init__.py)
        pkg_name = _resolve_package_name(base) if (base / "__init__.py").exists() else None
        logger.debug("Scanning convention dir: %s (pkg=%s)", base, pkg_name)

        # Load in dependency order
        for subfolder in _LOAD_ORDER:
            modules = _load_subfolder(base, subfolder, namespace, pkg_name)

            if subfolder in ("enums", "constants"):
                _register_enums_constants(modules)
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
