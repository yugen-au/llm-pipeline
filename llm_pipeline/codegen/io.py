"""Path-guarded IO for the codegen subsystem.

Every write goes through here. The path guard is structural: callers
pass a target ``Path`` and a (optional) root; the path must resolve to
a location *under* the root or :class:`CodegenPathError` raises
before disk is touched. The framework's own source code lives outside
``llm_pipelines/`` and is therefore unreachable to codegen — no
malicious or accidental modification of framework internals.

The default root is ``./llm_pipelines/`` resolved against the
process CWD. Override via the ``LLM_PIPELINES_ROOT`` env var or by
passing ``root=...`` explicitly.

Reads are not guarded (you can parse anything for inspection) — only
writes are.
"""
from __future__ import annotations

import os
import tempfile
from contextlib import suppress
from pathlib import Path

import libcst as cst


__all__ = [
    "CodegenPathError",
    "LLM_PIPELINES_ROOT_ENV",
    "assert_under_root",
    "read_module",
    "resolve_root",
    "write_module",
    "write_module_if_changed",
]


LLM_PIPELINES_ROOT_ENV = "LLM_PIPELINES_ROOT"
_DEFAULT_ROOT = "./llm_pipelines"


class CodegenPathError(ValueError):
    """A write target is outside the configured ``llm_pipelines/`` root.

    The codegen subsystem only mutates user-authored state directories.
    Framework code is off-limits structurally — this error fires
    before any IO so the framework cannot be corrupted by a buggy
    builder or a malicious YAML.
    """


def resolve_root(root: Path | None = None) -> Path:
    """Return the configured ``llm_pipelines/`` root, fully resolved.

    Resolution order: explicit ``root`` arg > ``LLM_PIPELINES_ROOT``
    env var > ``./llm_pipelines`` (against process CWD). The result
    is always an absolute, symlink-resolved path so subsequent path
    comparisons are unambiguous.
    """
    if root is not None:
        return Path(root).expanduser().resolve()
    raw = os.environ.get(LLM_PIPELINES_ROOT_ENV)
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(_DEFAULT_ROOT).expanduser().resolve()


def assert_under_root(path: Path, *, root: Path | None = None) -> Path:
    """Raise :class:`CodegenPathError` if ``path`` is not under ``root``.

    Resolves both sides (so symlinks / relative components don't
    sneak past the check) and verifies ``path`` is a descendant of
    ``root``. Returns the resolved ``path`` so callers can store it
    if desired.
    """
    resolved_root = resolve_root(root)
    resolved_path = Path(path).expanduser().resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise CodegenPathError(
            f"Codegen write blocked: {resolved_path} is not under "
            f"the configured llm_pipelines root {resolved_root}. "
            f"Set {LLM_PIPELINES_ROOT_ENV} or pass root=... if the "
            f"target is intentionally outside the default location."
        ) from exc
    return resolved_path


def read_module(path: Path) -> cst.Module:
    """Read + parse ``path`` into a libcst ``Module``.

    Not path-guarded — callers can read framework code for
    inspection. Raises ``OSError`` if unreadable or libcst parse
    errors if the file isn't valid Python.
    """
    source = Path(path).read_text(encoding="utf-8")
    return cst.parse_module(source)


def write_module(
    path: Path,
    module: cst.Module,
    *,
    root: Path | None = None,
) -> None:
    """Atomically write ``module.code`` to ``path`` under ``root``.

    Path-guarded: raises :class:`CodegenPathError` before opening
    any file if ``path`` falls outside ``root``. Write is atomic
    (tmp file + rename) so concurrent readers either see the old
    content or the new content, never a half-written file.

    Creates parent directories as needed.
    """
    resolved = assert_under_root(path, root=root)
    resolved.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp = tempfile.mkstemp(
        prefix=resolved.name + ".",
        suffix=".tmp",
        dir=str(resolved.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(module.code)
        os.replace(tmp, resolved)
    except Exception:
        with suppress(OSError):
            os.unlink(tmp)
        raise


def write_module_if_changed(
    path: Path,
    module: cst.Module,
    *,
    root: Path | None = None,
) -> bool:
    """Idempotent write — skips if existing content already matches.

    Returns ``True`` if the file was written (new content or didn't
    exist), ``False`` if the existing content already matched and
    no write was needed. Useful for build steps so unchanged files
    keep their mtime / don't churn editor reload.

    Path-guarded same as :func:`write_module`.
    """
    resolved = assert_under_root(path, root=root)
    new_code = module.code

    if resolved.exists():
        try:
            existing = resolved.read_text(encoding="utf-8")
        except OSError:
            existing = None
        if existing == new_code:
            return False

    write_module(resolved, module, root=root)
    return True
