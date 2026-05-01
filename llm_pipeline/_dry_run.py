"""Shared dry-run context for ``llm-pipeline`` subsystems.

The CLI commands (generate / pull / push) all need a "compute the
diff but don't mutate" mode for the UI startup pre-flight check
(B.3c step 7). Rather than thread a ``dry_run`` parameter through
every helper in :mod:`llm_pipeline.codegen.io` and
:mod:`llm_pipeline.yaml_sync` — those modules have 3-5 layers of
orchestration each, and most layers are pure decisions that don't
care — we set the flag once at the entry point and have only the
LEAF mutating functions check it.

Design rules:

- One process-wide flag, exposed via ``contextvars.ContextVar`` so
  it's async-safe and test-isolated.
- Set/reset only via :func:`dry_run_mode` (context manager) — no
  raw module-level setters. This keeps test cleanup automatic and
  the entry point obvious.
- LEAF mutating functions call :func:`is_dry_run` and short-circuit
  before performing the side effect. Their docstrings note the check.
- Intermediate orchestration code stays untouched. Reading
  ``yaml_sync._sync_one_step`` doesn't tell you whether the run will
  mutate — that's deliberate. The mutation primitives are where the
  contract lives.

Convention: the CLI wraps each command's ``run()`` body in
``with dry_run_mode(enabled=config.dry_run):``. The UI startup
pre-flight wraps the whole ``pull → generate → build → push`` chain
in one ``with dry_run_mode():`` block.
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Iterator


__all__ = [
    "dry_run_mode",
    "is_dry_run",
]


_DRY_RUN: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "llm_pipeline_dry_run", default=False,
)


def is_dry_run() -> bool:
    """Return ``True`` when the current call is inside a dry-run scope.

    Cheap to call (one ContextVar lookup). Leaf mutating functions
    in :mod:`llm_pipeline.codegen.io` and
    :mod:`llm_pipeline.yaml_sync` consult this before touching disk
    / Phoenix.
    """
    return _DRY_RUN.get()


@contextmanager
def dry_run_mode(*, enabled: bool = True) -> Iterator[None]:
    """Run a block of code with the dry-run flag set.

    ``enabled=False`` is a no-op (still pushes a token onto the
    ContextVar, but the value is False). This lets the CLI write
    ``with dry_run_mode(enabled=config.dry_run):`` unconditionally
    without an ``if`` branch, and lets the UI startup pre-flight
    nest scopes without surprises.

    The context manager always restores the previous value on exit
    (including on exception), so test cleanup is automatic.
    """
    token = _DRY_RUN.set(enabled)
    try:
        yield
    finally:
        _DRY_RUN.reset(token)
