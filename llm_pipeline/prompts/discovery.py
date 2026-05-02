"""Auto-discovery of ``PromptVariables`` subclasses from convention dirs.

Walks loaded step modules and registers every ``PromptVariables``
subclass into the global registry by snake_case class name (with
the ``Prompt`` suffix stripped).

Each step file owns its paired ``XPrompt(PromptVariables)`` class
(1:1, same module). The walker filters by ``cls.__module__ ==
mod.__name__`` so unrelated PromptVariables imports don't leak into
the registry. Hooked into convention discovery via the ``steps``
subfolder in :data:`llm_pipeline.discovery.loading._LOAD_ORDER`.
"""
from __future__ import annotations

import inspect
import logging
from types import ModuleType

from llm_pipeline.naming import to_snake_case
from llm_pipeline.prompts.variables import (
    PromptVariables,
    register_prompt_variables,
)

logger = logging.getLogger(__name__)


def discover_prompt_variables(modules: list[ModuleType]) -> None:
    """Walk loaded modules and register their ``PromptVariables`` subclasses.

    Idempotent: re-registering the same class under the same name is a
    no-op (see ``register_prompt_variables``). Re-registering a *different*
    class under the same name raises ``ValueError``.
    """
    for mod in modules:
        for _, cls in inspect.getmembers(mod, inspect.isclass):
            if (
                issubclass(cls, PromptVariables)
                and cls is not PromptVariables
                and cls.__module__ == mod.__name__
            ):
                key = to_snake_case(cls.__name__, strip_suffix="Prompt")
                register_prompt_variables(key, cls)
                logger.debug(
                    "Registered PromptVariables: %s -> %s.%s",
                    key, cls.__module__, cls.__name__,
                )


__all__ = ["discover_prompt_variables"]
