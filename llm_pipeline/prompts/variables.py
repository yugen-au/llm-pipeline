"""``PromptVariables`` base class + registry, plus ``auto_generate`` evaluator.

``PromptVariables`` declares the typed contract for the variables rendered
into a Phoenix prompt template. Each subclass has two nested Pydantic
classes — ``system`` and ``user`` — corresponding to Phoenix's two
messages. Every field uses ``Field(description="...")`` (enforced at
class-definition time).

Subclasses live in ``llm_pipelines/variables/{prompt_name}.py`` and are
auto-discovered into ``PROMPT_VARIABLES_REGISTRY`` by snake_case class
name (sans the ``Prompt`` suffix). The registry keys map 1:1 to step
``step_name()`` and Phoenix prompt names.

The ``auto_generate`` evaluator (``enum_values(X)``, ``enum_names(X)``,
``enum_value(X, MEMBER)``, ``constant(value)``) lives on as a separate
concern — used by the prompts UI when computing default text snippets.
"""
from __future__ import annotations

import importlib
import logging
import re
from typing import Any, Callable

from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PromptVariables base class + registry
# ---------------------------------------------------------------------------


class PromptVariables:
    """Container for one prompt's variables: a ``system`` part and a ``user`` part.

    Each subclass declares two nested Pydantic classes — ``system`` and
    ``user`` — describing the variables for the corresponding Phoenix
    messages. Every field on those nested classes must use
    ``Field(description="...")``; this is enforced at class-definition
    time.

    The class name (with the ``Prompt`` suffix stripped, snake-cased)
    maps 1:1 to the Phoenix prompt name and the owning ``LLMStepNode``
    subclass's ``step_name()``.

    Instances hold validated ``system`` and ``user`` Pydantic instances;
    the framework reads ``instance.system.model_dump()`` and
    ``instance.user.model_dump()`` to render Phoenix's message templates.

    Example::

        class SentimentAnalysisPrompt(PromptVariables):
            class system(BaseModel):
                pass

            class user(BaseModel):
                text: str = Field(description="Input text to analyse")

        SentimentAnalysisPrompt(
            system=SentimentAnalysisPrompt.system(),
            user=SentimentAnalysisPrompt.user(text="hi"),
        )

    Not a Pydantic ``BaseModel`` — those treat nested classes as
    annotations rather than instance fields. A plain class with an
    explicit ``__init__`` is simpler and lets ``.system`` / ``.user``
    behave as ordinary attributes.
    """

    # Subclasses override these via the nested-class declaration.
    system: type[BaseModel]
    user: type[BaseModel]

    def __init__(
        self,
        *,
        system: BaseModel,
        user: BaseModel,
    ) -> None:
        cls = type(self)
        if not isinstance(system, cls.system):
            raise TypeError(
                f"{cls.__name__}.system expects a {cls.system.__name__} "
                f"instance, got {type(system).__name__}."
            )
        if not isinstance(user, cls.user):
            raise TypeError(
                f"{cls.__name__}.user expects a {cls.user.__name__} "
                f"instance, got {type(user).__name__}."
            )
        self.system = system
        self.user = user

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        for nested_name in ("system", "user"):
            nested = cls.__dict__.get(nested_name)
            if nested is None or not (
                isinstance(nested, type) and issubclass(nested, BaseModel)
            ):
                raise TypeError(
                    f"{cls.__name__}.{nested_name} must be a Pydantic "
                    f"BaseModel subclass declared inside the class body."
                )
            for field_name, field_info in nested.model_fields.items():
                if not field_info.description:
                    raise ValueError(
                        f"{cls.__name__}.{nested_name}.{field_name} must "
                        f"use Field(description='...')."
                    )


# Module-global registry. Keyed by snake_case class name with ``Prompt``
# suffix stripped — i.e. the same string returned by
# ``LLMStepNode.step_name()``.
_PROMPT_VARIABLES_REGISTRY: dict[str, type[PromptVariables]] = {}


def register_prompt_variables(name: str, cls: type[PromptVariables]) -> None:
    """Register a ``PromptVariables`` subclass under a snake_case key.

    Raises ``ValueError`` if ``name`` is already registered with a
    different class. Re-registering the *same* class is a no-op
    (allows convention discovery to run multiple times safely).
    """
    existing = _PROMPT_VARIABLES_REGISTRY.get(name)
    if existing is not None and existing is not cls:
        raise ValueError(
            f"Duplicate PromptVariables registration for {name!r}: "
            f"existing={existing!r}, new={cls!r}"
        )
    _PROMPT_VARIABLES_REGISTRY[name] = cls


def get_prompt_variables(name: str) -> type[PromptVariables] | None:
    """Look up a registered ``PromptVariables`` subclass by snake_case name."""
    return _PROMPT_VARIABLES_REGISTRY.get(name)


def get_all_prompt_variables() -> dict[str, type[PromptVariables]]:
    """Return a copy of the full registry. For introspection / tests."""
    return dict(_PROMPT_VARIABLES_REGISTRY)


def clear_prompt_variables_registry() -> None:
    """Clear the registry. For test teardown."""
    _PROMPT_VARIABLES_REGISTRY.clear()


# ---------------------------------------------------------------------------
# auto_generate registry
# ---------------------------------------------------------------------------


_AUTO_GENERATE_REGISTRY: dict[str, object] = {}
_AUTO_GENERATE_BASE_PATH: str | None = None

_EXPR_PATTERN = re.compile(
    r"^(enum_values|enum_names|enum_value|constant)\((.+)\)$"
)


def register_auto_generate(name: str, obj: object) -> None:
    """Register a Python object (enum, constant) for auto_generate expressions."""
    _AUTO_GENERATE_REGISTRY[name] = obj


def set_auto_generate_base_path(base_path: str | None) -> None:
    """Set the base module path for convention-based object resolution."""
    global _AUTO_GENERATE_BASE_PATH
    _AUTO_GENERATE_BASE_PATH = base_path


def clear_auto_generate_registry() -> None:
    """Clear auto_generate registry and base path. For test teardown."""
    global _AUTO_GENERATE_BASE_PATH
    _AUTO_GENERATE_REGISTRY.clear()
    _AUTO_GENERATE_BASE_PATH = None


def _parse_auto_generate(expr: str) -> tuple[str, list[str]]:
    """Parse ``func_name(arg1, arg2)`` -> ``(func_name, [arg1, arg2])``."""
    m = _EXPR_PATTERN.match(expr.strip())
    if not m:
        raise ValueError(f"Unrecognized auto_generate expression: {expr!r}")
    return m.group(1), [a.strip() for a in m.group(2).split(",")]


def _resolve_object(name: str, import_path: str | None, expr_type: str) -> object:
    """Resolve a named object via registry -> import_path -> convention."""
    if name in _AUTO_GENERATE_REGISTRY:
        return _AUTO_GENERATE_REGISTRY[name]

    if import_path:
        module_path, _, attr = import_path.rpartition(".")
        mod = importlib.import_module(module_path)
        return getattr(mod, attr)

    if _AUTO_GENERATE_BASE_PATH:
        submodule = "enums" if expr_type.startswith("enum") else "constants"
        full_path = f"{_AUTO_GENERATE_BASE_PATH}.{submodule}"
        try:
            mod = importlib.import_module(full_path)
            return getattr(mod, name)
        except (ImportError, AttributeError):
            pass

    raise ValueError(
        f"Cannot resolve {name!r} for auto_generate. Register via "
        f"register_auto_generate(), provide import_path, or set "
        f"base_path via set_auto_generate_base_path()."
    )


def build_auto_generate_factory(
    expr: str, import_path: str | None = None,
) -> Callable[[], str]:
    """Build a callable that resolves an ``auto_generate`` expression at call time."""
    func_name, args = _parse_auto_generate(expr)

    if func_name == "enum_values":
        name = args[0]

        def factory(_name=name, _import_path=import_path, _fn=func_name) -> str:
            obj = _resolve_object(_name, _import_path, _fn)
            return ", ".join(str(e.value) for e in obj)

        return factory

    if func_name == "enum_names":
        name = args[0]

        def factory(_name=name, _import_path=import_path, _fn=func_name) -> str:
            obj = _resolve_object(_name, _import_path, _fn)
            return ", ".join(e.name for e in obj)

        return factory

    if func_name == "enum_value":
        if len(args) != 2:
            raise ValueError(
                f"enum_value requires 2 args (EnumName, MEMBER), got {len(args)}"
            )
        name, member = args[0], args[1]

        def factory(
            _name=name, _member=member, _import_path=import_path, _fn=func_name,
        ) -> str:
            obj = _resolve_object(_name, _import_path, _fn)
            return str(obj[_member].value)

        return factory

    if func_name == "constant":
        value = args[0]

        def factory(_value=value) -> str:
            return _value

        return factory

    raise ValueError(f"Unknown auto_generate function: {func_name}")


__all__ = [
    # PromptVariables
    "PromptVariables",
    "register_prompt_variables",
    "get_prompt_variables",
    "get_all_prompt_variables",
    "clear_prompt_variables_registry",
    # auto_generate (existing)
    "register_auto_generate",
    "set_auto_generate_base_path",
    "clear_auto_generate_registry",
    "build_auto_generate_factory",
]
