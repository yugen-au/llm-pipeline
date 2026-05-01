"""Pipeline discovery — convention dirs, entry points, and explicit modules.

Three sources, three functions (each in its own submodule):

- :func:`discover_from_convention` (:mod:`.conventions`) — scans
  ``llm_pipelines/`` directories (package-internal + CWD), imports
  Python files in dependency order, and registers discovered graph
  ``Pipeline`` subclasses.
- :func:`discover_from_entry_points` (:mod:`.entry_points`) — loads
  pipelines registered under the ``llm_pipeline.pipelines``
  entry-point group (used for demo pipelines bundled with the
  package).
- :func:`discover_from_modules` (:mod:`.modules`) — imports
  caller-supplied dotted module paths and registers their
  ``Pipeline`` subclasses (the ``--pipelines`` CLI flag plumbs
  into here).

All three return the same shape:
``(pipeline_registry, introspection_registry)`` where both dicts
map snake-cased pipeline name to the ``Pipeline`` subclass. The
two-dict shape is preserved for caller compat (legacy distinction
between executable factory closures and introspection classes);
in the graph world the dicts are identical.

Phase C.2.a structural restructure: this module was a single
``llm_pipeline/discovery.py`` until now. Splitting into a package
with one role per submodule makes room for per-kind walkers
(Phase C.2.b) without one file growing into a thousand lines.
The public re-exports here preserve every import path consumers
already use.

Phase C.2.a additions:
- :mod:`.registries` carries the future
  ``app.state.registries`` shape — initialised empty for now;
  walkers populate it in Phase C.2.b.

Loading internals (``find_convention_dirs``, ``_load_subfolder``,
``_LOAD_ORDER``, etc.) live in :mod:`.loading` and are re-exported
here for backward compatibility with existing tests / consumers.
"""
from llm_pipeline.discovery.conventions import discover_from_convention
from llm_pipeline.discovery.entry_points import discover_from_entry_points
from llm_pipeline.discovery.loading import (
    _LOAD_ORDER,
    _SKIP_DIRS,
    _SKIP_PREFIXES,
    _load_subfolder,
    _resolve_package_name,
    find_convention_dirs,
    load_convention_module,
)
from llm_pipeline.discovery.modules import discover_from_modules
from llm_pipeline.discovery.registries import init_empty_registries


__all__ = [
    # Public discovery API
    "discover_from_convention",
    "discover_from_entry_points",
    "discover_from_modules",
    # New per-kind registry plumbing (Phase C.2.a)
    "init_empty_registries",
    # Loading internals (kept exported for tests + power users)
    "find_convention_dirs",
    "load_convention_module",
    "_LOAD_ORDER",
    "_SKIP_DIRS",
    "_SKIP_PREFIXES",
    "_load_subfolder",
    "_resolve_package_name",
]
