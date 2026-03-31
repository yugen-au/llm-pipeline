"""Convention-based directory discovery for llm_pipelines/.

Scans for llm_pipelines/ directories (package-internal + CWD),
imports Python files in each subfolder in dependency order,
and registers discovered PipelineConfig subclasses.
"""
import importlib.util
import inspect
import logging
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


def find_convention_dirs() -> list[Path]:
    """Find all llm_pipelines/ directories to scan.

    Returns directories in priority order (later overrides earlier):
    1. Package-internal: sibling to llm_pipeline/ package
    2. CWD: ./llm_pipelines/
    """
    dirs: list[Path] = []

    # 1. Package-internal (sibling to this package)
    pkg_dir = Path(__file__).resolve().parent.parent / "llm_pipelines"
    if pkg_dir.is_dir():
        dirs.append(pkg_dir)

    # 2. CWD
    cwd_dir = Path.cwd() / "llm_pipelines"
    if cwd_dir.is_dir() and cwd_dir.resolve() != pkg_dir.resolve():
        dirs.append(cwd_dir)

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
) -> Tuple[Dict[str, Callable], Dict[str, Type]]:
    """Find all convention dirs, load modules in order, return merged registries."""
    dirs = find_convention_dirs()
    if not dirs:
        return {}, {}

    all_pipeline_reg: Dict[str, Callable] = {}
    all_introspection_reg: Dict[str, Type] = {}

    for base in dirs:
        namespace = f"_llm_pipelines_{base.name}"
        # Detect if this is an importable package (has __init__.py)
        pkg_name = base.name if (base / "__init__.py").exists() else None
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
